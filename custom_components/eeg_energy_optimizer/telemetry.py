"""TelemetryReporter — HTTP-Client + Retry/Backoff + Whitelist-Filter.

Implementiert die Decisions D-01..D-06, D-18/D-19 und D-30..D-36 aus
.planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md.

Alle public Coroutinen sind mehrfach aufrufbar; ist der Reporter nicht
konfiguriert (URL oder Bootstrap-Token leer), ist jede Methode ein stilles
No-Op (D-01, D-02). Backend-Schema-Quelle: EEGEnergyOptimzierBackend/src/types.ts.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .const import (
    TELEMETRY_BACKEND_URL,
    TELEMETRY_BACKOFF_MAX_S,
    TELEMETRY_BACKOFF_MIN_S,
    TELEMETRY_BOOTSTRAP_TOKEN,
    TELEMETRY_FLUSH_BATCH,
    TELEMETRY_HTTP_TIMEOUT,
    TELEMETRY_SETTINGS_KEYS,
)
from .telemetry_buffer import TelemetryBuffer

_LOGGER = logging.getLogger(__name__)

# HA-/aiohttp-Imports für Test-Umgebung abgesichert.
# Wenn aiohttp fehlt (z.B. in nackter pytest-Umgebung), stellen wir minimale
# Stubs bereit — die Tests mocken ohnehin die Session.
try:
    import aiohttp  # type: ignore
except ImportError:  # pragma: no cover - exercised only outside CI
    class _AiohttpStub:
        class ClientError(Exception):
            pass

        @staticmethod
        def ClientTimeout(*_args, **_kwargs):  # noqa: N802 — match aiohttp API
            return None

    aiohttp = _AiohttpStub()  # type: ignore[assignment]

try:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
except ImportError:  # pragma: no cover
    async_get_clientsession = None  # type: ignore[assignment]


# Erlaubte Top-Level-Keys für Profile/Register-Payloads (siehe types.ts).
# Reihenfolge irrelevant — wird nur als Filter-Whitelist genutzt.
_PROFILE_TOP_LEVEL = (
    "integration_started_at",
    "app_version",
    "ha_version",
    "inverter_type",
    "battery_capacity_kwh",
    "pv_peak_kwp",
    "forecast_provider",
    "country_iso",
    "settings",
)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class TelemetryReporter:
    """HTTP-Reporter für das Telemetrie-Backend.

    Konstruktor liest die Backend-Konfiguration aus dem Modul-State (siehe
    ``const.py``). Für Tests können ``TELEMETRY_BACKEND_URL`` /
    ``TELEMETRY_BOOTSTRAP_TOKEN`` per ``monkeypatch`` auf dem Modul gesetzt
    werden, BEVOR der Reporter instantiiert wird.
    """

    def __init__(self, hass: Any, buffer: TelemetryBuffer) -> None:
        self._hass = hass
        self._buffer = buffer
        # Werte zur Konstruktionszeit ablesen — Tests setzen sie via monkeypatch
        # auf dem Modul, bevor TelemetryReporter() aufgerufen wird.
        self._url = (TELEMETRY_BACKEND_URL or "").rstrip("/")
        self._bootstrap = TELEMETRY_BOOTSTRAP_TOKEN or ""
        self._consecutive_failures = 0
        self._next_attempt_at: datetime | None = None
        self._send_lock = asyncio.Lock()
        self._session: Any = None  # lazy

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return bool(self._url and self._bootstrap)

    # ------------------------------------------------------------------
    # Profile shaping (used by register + update_profile)
    # ------------------------------------------------------------------
    @staticmethod
    def _shape_profile(profile: dict) -> dict:
        """Filter profile dict against types.ts ProfilePayload schema.

        - Top-Level: nur Keys aus ``_PROFILE_TOP_LEVEL`` bleiben erhalten.
        - ``settings``: nur Keys aus ``TELEMETRY_SETTINGS_KEYS`` bleiben erhalten.
          Leeres settings-Dict ⇒ ``None`` (matches Optional|null in types.ts).
        - Unbekannte Top-Level-Keys werden stillschweigend verworfen.
        """
        out: dict = {}
        for key in _PROFILE_TOP_LEVEL:
            if key in profile and key != "settings":
                out[key] = profile[key]

        settings = profile.get("settings")
        if isinstance(settings, dict):
            filtered = {k: v for k, v in settings.items() if k in TELEMETRY_SETTINGS_KEYS}
            out["settings"] = filtered if filtered else None
        elif "settings" in profile:
            # Explicit None / wrong type → keep as None
            out["settings"] = None
        return out

    # ------------------------------------------------------------------
    # Public API — register / forget
    # ------------------------------------------------------------------
    async def register(self, profile: dict) -> bool:
        """POST /v1/register with X-Bootstrap-Token. Returns True on 201."""
        if not self.is_configured:
            return False
        shaped = self._shape_profile(profile)
        res = await self._post(
            "/v1/register",
            shaped,
            headers={"X-Bootstrap-Token": self._bootstrap},
            expect_status={201},
            buffer_on_failure=False,
            retry_on_5xx=True,
        )
        if not res or not res.get("ok"):
            return False
        data = res.get("body") or {}
        installation_id = data.get("installation_id")
        api_key = data.get("api_key")
        if not installation_id or not api_key:
            return False
        await self._buffer.set_identity(installation_id, api_key, _now_utc().isoformat())
        return True

    async def forget(self) -> bool:
        """DELETE /v1/installation. Always clears identity + buffer locally (D-31)."""
        if not self.is_configured or not self._buffer.identity_known():
            # Idempotent: lokal aufräumen, auch wenn Backend nicht erreichbar.
            await self._buffer.clear_identity()
            await self._buffer.clear_buffer()
            return False

        ok = await self._delete_authed("/v1/installation")
        # Lokale Cleanup IMMER, auch bei Backend-Fehler (D-31).
        await self._buffer.clear_identity()
        await self._buffer.clear_buffer()
        return ok

    # ------------------------------------------------------------------
    # Public API — events
    # ------------------------------------------------------------------
    async def send_state_change(self, payload: dict) -> None:
        await self._send_authed("/v1/state-change", payload)

    async def send_snapshot(self, payload: dict) -> None:
        await self._send_authed("/v1/snapshot", payload)

    async def send_snapshot_batch(self, payloads: list[dict]) -> None:
        if not payloads:
            return
        # Backend cap: max 100 Items pro Request (endpoints.ts Zeile 121).
        for i in range(0, len(payloads), 100):
            chunk = payloads[i:i + 100]
            await self._send_authed("/v1/snapshot", chunk)

    async def send_outcome(self, payload: dict) -> None:
        await self._send_authed("/v1/outcome", payload)

    async def send_failure(self, payload: dict) -> None:
        await self._send_authed("/v1/failure", payload)

    async def update_profile(self, profile: dict) -> None:
        await self._send_authed("/v1/profile", self._shape_profile(profile))

    async def flush_buffer(self) -> int:
        """Drain up to TELEMETRY_FLUSH_BATCH events FIFO. Returns count drained."""
        if not self.is_configured or not self._buffer.identity_known():
            return 0
        batch = self._buffer.peek_batch(TELEMETRY_FLUSH_BATCH)
        drained = 0
        for entry in batch:
            ok = await self._post_authed(
                entry["endpoint"], entry["body"], already_buffered=True
            )
            if not ok:
                break
            drained += 1
        if drained > 0:
            await self._buffer.drop(drained)
        return drained

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _send_authed(self, endpoint: str, body) -> None:
        """Live-Send mit Backoff-Gate + nach Erfolg Buffer-Drain."""
        if not self.is_configured:
            return
        if not self._buffer.identity_known():
            _LOGGER.debug("Telemetry: skip %s — no identity", endpoint)
            return
        # Backoff-Gate: während der Sperre direkt in den Buffer.
        if self._next_attempt_at is not None and _now_utc() < self._next_attempt_at:
            if isinstance(body, dict):
                await self._buffer.append(endpoint, body)
            return

        ok = await self._post_authed(endpoint, body, already_buffered=False)
        if ok:
            await self.flush_buffer()

    async def _post_authed(self, endpoint: str, body, *, already_buffered: bool) -> bool:
        ident = self._buffer.get_identity()
        if not ident:
            return False
        headers = {"Authorization": f"Bearer {ident['api_key']}"}
        res = await self._post(
            endpoint,
            body,
            headers=headers,
            expect_status={200, 204},
            buffer_on_failure=not already_buffered,
            retry_on_5xx=True,
        )
        return bool(res and res.get("ok"))

    async def _delete_authed(self, endpoint: str) -> bool:
        ident = self._buffer.get_identity()
        if not ident:
            return False
        headers = {"Authorization": f"Bearer {ident['api_key']}"}
        session = self._get_session()
        if session is None or aiohttp is None:
            return False
        url = f"{self._url}{endpoint}"
        try:
            async with session.delete(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=TELEMETRY_HTTP_TIMEOUT),
            ) as resp:
                return 200 <= resp.status < 300
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            _LOGGER.warning("Telemetry forget: network error (%s)", exc)
            return False
        except Exception:  # pragma: no cover
            _LOGGER.exception("Telemetry forget: unexpected error")
            return False

    async def _post(
        self,
        endpoint: str,
        body,
        *,
        headers: dict,
        expect_status,
        buffer_on_failure: bool,
        retry_on_5xx: bool,
    ) -> dict | None:
        """Single POST with optional 1× retry on 5xx/network plus backoff bookkeeping.

        Returns:
          {"ok": True, "body": <dict|None>} on success
          {"ok": False, "status": <int|None>} on failure
          None if the reporter is unconfigured.
        """
        if not self.is_configured or aiohttp is None:
            return None

        session = self._get_session()
        if session is None:
            return None
        url = f"{self._url}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=TELEMETRY_HTTP_TIMEOUT)
        attempts = 2 if retry_on_5xx else 1
        last_status: int | None = None

        for attempt in range(attempts):
            try:
                async with session.post(
                    url, json=body, headers=headers, timeout=timeout,
                ) as resp:
                    last_status = resp.status
                    status = resp.status

                    # 4xx (außer 429) → kein Retry, kein Buffer
                    if 400 <= status < 500 and status != 429:
                        self._on_4xx(endpoint, status)
                        return {"ok": False, "status": status}

                    # Erfolg
                    success = (
                        (isinstance(expect_status, set) and status in expect_status)
                        or (isinstance(expect_status, int) and status == expect_status)
                    )
                    if success:
                        self._on_success()
                        body_obj: Any = None
                        try:
                            content_length = getattr(resp, "content_length", 0) or 0
                            if content_length and content_length > 0:
                                body_obj = await resp.json()
                            else:
                                # Manche Mocks setzen content_length nicht — versuche json() defensiv.
                                try:
                                    body_obj = await resp.json()
                                except Exception:
                                    body_obj = None
                        except Exception:
                            body_obj = None
                        return {"ok": True, "body": body_obj}

                    # 429 → Retry-After respektieren, dann Buffer
                    if status == 429:
                        ra_raw = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
                        ra = int(ra_raw) if ra_raw and str(ra_raw).isdigit() else None
                        self._on_5xx_or_rate_limited(retry_after_s=ra)
                        break

                    # 5xx → einmaliger Retry
                    if status >= 500 and attempt + 1 < attempts:
                        continue
                    self._on_5xx_or_rate_limited()
                    break

            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_status = None
                if attempt + 1 < attempts:
                    continue
                _LOGGER.debug("Telemetry %s network error: %s", endpoint, exc)
                self._on_5xx_or_rate_limited()
                break
            except Exception:  # pragma: no cover
                _LOGGER.exception("Telemetry %s unexpected error", endpoint)
                self._on_5xx_or_rate_limited()
                break

        # Failure-Pfad: Body in den Buffer schieben, falls erlaubt.
        if buffer_on_failure and isinstance(body, dict):
            await self._buffer.append(endpoint, body)
        return {"ok": False, "status": last_status}

    # ------------------------------------------------------------------
    # Backoff bookkeeping
    # ------------------------------------------------------------------
    def _on_success(self) -> None:
        self._consecutive_failures = 0
        self._next_attempt_at = None

    def _on_4xx(self, endpoint: str, status: int) -> None:
        _LOGGER.warning(
            "Telemetry %s rejected with %d (no retry, no buffer)", endpoint, status
        )
        # 4xx zählt NICHT in den Backoff — permanenter Fehler.

    def _on_5xx_or_rate_limited(self, *, retry_after_s: int | None = None) -> None:
        self._consecutive_failures += 1
        if retry_after_s is not None:
            delay = max(1, min(retry_after_s, TELEMETRY_BACKOFF_MAX_S))
        else:
            exp = TELEMETRY_BACKOFF_MIN_S * (2 ** (self._consecutive_failures - 1))
            delay = min(exp, TELEMETRY_BACKOFF_MAX_S)
        self._next_attempt_at = _now_utc() + timedelta(seconds=delay)

    # ------------------------------------------------------------------
    # Session lifecycle (HA owns the session — never close)
    # ------------------------------------------------------------------
    def _get_session(self):
        if self._session is None and async_get_clientsession is not None:
            try:
                self._session = async_get_clientsession(self._hass)
            except Exception:  # pragma: no cover
                _LOGGER.exception("Telemetry: failed to obtain aiohttp session")
                self._session = None
        return self._session
