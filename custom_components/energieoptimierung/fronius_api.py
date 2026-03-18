"""
Fronius inverter API client for battery discharge control.

Implements HTTP Digest Auth against the Fronius local API to set
HYB_EM_MODE (0=auto, 1=manual) and HYB_EM_POWER (W, negative=discharge).
Extracted from the existing Node-RED "Batterieeinspeisung" flow.
"""

from __future__ import annotations

import hashlib
import logging
import random
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


def _hash(text: str, algorithm: str = "MD5") -> str:
    algo = algorithm.upper().replace("-", "")
    if algo in ("SHA256", "SHA256SESS"):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _random_hex(n: int = 8) -> str:
    return "".join(f"{random.randint(0, 255):02x}" for _ in range(n))


class FroniusAPI:
    """Async client for Fronius inverter battery control via Digest Auth."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._base_url = f"http://{self._host}"

    async def async_set_discharge(self, power_kw: float) -> bool:
        """Enable forced battery discharge at the given power (kW)."""
        power_w = int(power_kw * -1000)  # negative = discharge
        payload = {"HYB_EM_POWER": power_w, "HYB_EM_MODE": 1}
        return await self._async_set_battery_config(payload)

    async def async_set_auto_mode(self) -> bool:
        """Return inverter to automatic battery management."""
        return await self._async_set_battery_config({"HYB_EM_MODE": 0})

    async def _async_set_battery_config(self, payload: dict[str, Any]) -> bool:
        """Login via Digest Auth, then POST to /config/batteries."""
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: GET login → 401 with digest challenge
                login_url = f"{self._base_url}/api/commands/Login?user={self._username}"
                async with session.get(login_url) as resp:
                    if resp.status != 401:
                        _LOGGER.warning("Fronius: Expected 401, got %s", resp.status)
                        return False

                    www_auth = resp.headers.get("X-WWW-Authenticate", "")
                    if not www_auth:
                        www_auth = resp.headers.get("WWW-Authenticate", "")
                    if not www_auth:
                        _LOGGER.error("Fronius: No auth challenge header")
                        return False

                digest = self._parse_digest_challenge(www_auth)
                if not digest:
                    return False

                cnonce = _random_hex(8)

                # Step 2: GET login with digest auth → 200
                auth_header = self._build_auth_header(
                    method="GET",
                    uri=f"/api/commands/Login?user={self._username}",
                    digest=digest,
                    nc="00000001",
                    cnonce=cnonce,
                )
                headers = {"Authorization": auth_header}
                async with session.get(login_url, headers=headers) as resp:
                    if resp.status != 200:
                        _LOGGER.error("Fronius: Login failed with %s", resp.status)
                        return False

                # Step 3: POST battery config with digest auth (nc incremented)
                post_uri = "/api/config/batteries"
                post_url = f"{self._base_url}{post_uri}"
                auth_header = self._build_auth_header(
                    method="POST",
                    uri=post_uri,
                    digest=digest,
                    nc="00000002",
                    cnonce=cnonce,
                )
                headers = {"Authorization": auth_header}

                import json
                async with session.post(
                    post_url,
                    headers=headers,
                    data=json.dumps(payload),
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Fronius: Battery config set: %s", payload)
                        return True
                    _LOGGER.error(
                        "Fronius: POST failed with %s: %s",
                        resp.status, await resp.text(),
                    )
                    return False

        except aiohttp.ClientError as exc:
            _LOGGER.error("Fronius: Connection error: %s", exc)
            return False
        except Exception:
            _LOGGER.exception("Fronius: Unexpected error")
            return False

    def _parse_digest_challenge(self, header: str) -> dict[str, str] | None:
        """Extract realm, nonce, qop from digest challenge header."""
        import re

        realm = re.search(r'realm="([^"]+)"', header)
        nonce = re.search(r'nonce="([^"]+)"', header)
        qop = re.search(r'qop="([^"]+)"', header)
        algorithm = re.search(r'algorithm="?([^",\s]+)"?', header)

        if not realm or not nonce:
            _LOGGER.error("Fronius: Could not parse digest challenge")
            return None

        return {
            "realm": realm.group(1),
            "nonce": nonce.group(1),
            "qop": qop.group(1) if qop else "auth",
            "algorithm": algorithm.group(1) if algorithm else "MD5",
        }

    def _build_auth_header(
        self,
        method: str,
        uri: str,
        digest: dict[str, str],
        nc: str,
        cnonce: str,
    ) -> str:
        """Build a Digest Auth header string.

        Fronius Gen24 uses a hybrid digest auth:
        - HA1 = MD5(user:realm:password)  (always MD5)
        - HA2 = SHA256(method:digest_uri) (SHA256 when algorithm=SHA256)
        - response = SHA256(HA1:nonce:nc:cnonce:qop:HA2)
        - digest_uri = path WITHOUT query string
        """
        realm = digest["realm"]
        nonce = digest["nonce"]
        qop = digest["qop"]
        algorithm = digest.get("algorithm", "MD5")

        # Strip query string from URI for digest computation
        digest_uri = uri.split("?")[0]

        # Fronius hybrid: HA1 always MD5, HA2+response use challenge algorithm
        ha1 = _hash(f"{self._username}:{realm}:{self._password}", "MD5")
        ha2 = _hash(f"{method}:{digest_uri}", algorithm)
        response = _hash(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}", algorithm)

        return (
            f'Digest username="{self._username}", '
            f'realm="{realm}", '
            f'nonce="{nonce}", '
            f'uri="{digest_uri}", '
            f"qop={qop}, "
            f"nc={nc}, "
            f'cnonce="{cnonce}", '
            f'response="{response}", '
            f"algorithm={algorithm}"
        )
