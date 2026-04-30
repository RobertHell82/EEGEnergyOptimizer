"""Persistente Speicherung für Telemetrie-Identität + Ringbuffer (D-04, D-05, D-06).

Zwei Store-Dateien werden genutzt, damit ein korrupter Buffer die Identität nicht
zerstören kann:
  - STORAGE_TELEMETRY        : installation_id, api_key, registered_at
  - STORAGE_TELEMETRY_BUFFER : FIFO-Ringbuffer ausstehender Events (max 100)

Siehe .planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md.
"""
from __future__ import annotations

import collections
import logging
from datetime import datetime, timezone
from typing import Any

from .const import (
    STORAGE_TELEMETRY,
    STORAGE_TELEMETRY_BUFFER,
    TELEMETRY_BUFFER_MAX,
)

_LOGGER = logging.getLogger(__name__)

# HA-Imports für Test-Umgebung abgesichert
try:
    from homeassistant.helpers.storage import Store
except ImportError:  # pragma: no cover
    Store = None  # type: ignore[assignment,misc]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class TelemetryBuffer:
    """Owns persistent identity + FIFO event buffer for telemetry.

    Construction is sync. ``load()`` must be awaited once before use to
    populate internal state from disk. All mutating methods persist immediately.
    """

    def __init__(self, hass: Any) -> None:
        self._hass = hass
        if Store is not None:
            self._identity_store: Any = Store(hass, 1, STORAGE_TELEMETRY)
            self._buffer_store: Any = Store(hass, 1, STORAGE_TELEMETRY_BUFFER)
        else:  # pragma: no cover — only triggered when HA helpers missing
            self._identity_store = None
            self._buffer_store = None
        self._identity: dict | None = None
        self._buffer: collections.deque = collections.deque(maxlen=TELEMETRY_BUFFER_MAX)

    async def load(self) -> None:
        """Read identity and buffer from disk into memory. Idempotent."""
        # Identity
        if self._identity_store is not None:
            try:
                raw = await self._identity_store.async_load()
                if isinstance(raw, dict) and raw.get("installation_id"):
                    self._identity = {
                        "installation_id": raw.get("installation_id"),
                        "api_key": raw.get("api_key"),
                        "registered_at": raw.get("registered_at"),
                    }
            except Exception:  # pragma: no cover
                _LOGGER.exception("Telemetry identity load failed")

        # Event buffer
        if self._buffer_store is not None:
            try:
                raw = await self._buffer_store.async_load()
                if isinstance(raw, list):
                    # Truncate to MAX in case the file was edited externally
                    for entry in raw[-TELEMETRY_BUFFER_MAX:]:
                        if isinstance(entry, dict):
                            self._buffer.append(entry)
            except Exception:  # pragma: no cover
                _LOGGER.exception("Telemetry buffer load failed")

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def identity_known(self) -> bool:
        return self._identity is not None and bool(self._identity.get("installation_id"))

    def get_identity(self) -> dict | None:
        return dict(self._identity) if self._identity else None

    async def set_identity(self, installation_id: str, api_key: str,
                           registered_at: str) -> None:
        self._identity = {
            "installation_id": installation_id,
            "api_key": api_key,
            "registered_at": registered_at,
        }
        if self._identity_store is not None:
            await self._identity_store.async_save(dict(self._identity))

    async def clear_identity(self) -> None:
        self._identity = None
        if self._identity_store is None:
            return
        # Bevorzuge async_remove (HA 2024.x); Fallback auf leeres Dict
        remove = getattr(self._identity_store, "async_remove", None)
        if remove is not None:
            try:
                await remove()
                return
            except Exception:  # pragma: no cover
                _LOGGER.debug("async_remove identity failed; falling back to async_save({})")
        try:
            await self._identity_store.async_save({})
        except Exception:  # pragma: no cover
            _LOGGER.exception("Telemetry identity clear failed")

    # ------------------------------------------------------------------
    # Event buffer
    # ------------------------------------------------------------------
    async def append(self, endpoint: str, body: dict) -> None:
        """Append an entry. If buffer at MAX, drops the oldest (deque maxlen)."""
        self._buffer.append({
            "endpoint": endpoint,
            "body": body,
            "queued_at": _now_iso(),
        })
        await self._save_buffer()

    def peek_batch(self, limit: int) -> list[dict]:
        """Return up to ``limit`` oldest entries without removing them."""
        if limit <= 0:
            return []
        return list(self._buffer)[:limit]

    async def drop(self, n: int) -> None:
        """Remove the first ``n`` entries (after a successful flush)."""
        for _ in range(min(max(n, 0), len(self._buffer))):
            self._buffer.popleft()
        await self._save_buffer()

    async def clear_buffer(self) -> None:
        self._buffer.clear()
        await self._save_buffer()

    def size(self) -> int:
        return len(self._buffer)

    async def _save_buffer(self) -> None:
        if self._buffer_store is None:
            return
        try:
            await self._buffer_store.async_save(list(self._buffer))
        except Exception:  # pragma: no cover
            _LOGGER.exception("Telemetry buffer save failed")
