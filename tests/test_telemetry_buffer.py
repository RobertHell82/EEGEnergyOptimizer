"""Tests for TelemetryBuffer (persistent identity + FIFO ring buffer).

These tests verify D-04, D-05, D-06 from
.planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md:
  - identity persisted via Store (key STORAGE_TELEMETRY)
  - event ring buffer persisted via Store (key STORAGE_TELEMETRY_BUFFER), max 100 entries
  - identity and buffer survive HA restart (load() round-trips)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    STORAGE_TELEMETRY,
    STORAGE_TELEMETRY_BUFFER,
    TELEMETRY_BUFFER_MAX,
)
from custom_components.eeg_energy_optimizer.telemetry_buffer import TelemetryBuffer


# ---------------------------------------------------------------------------
# Helpers — fake Store that round-trips through a shared dict (HA-restart sim)
# ---------------------------------------------------------------------------
class _FakeStore:
    """Drop-in replacement for homeassistant.helpers.storage.Store backed by a dict."""

    def __init__(self, backing: dict, key: str) -> None:
        self._backing = backing
        self._key = key

    async def async_load(self):
        return self._backing.get(self._key)

    async def async_save(self, data) -> None:
        # Deep-copyish: we json-serialize-trip via list/dict to mimic real Store behaviour
        if isinstance(data, list):
            self._backing[self._key] = list(data)
        elif isinstance(data, dict):
            self._backing[self._key] = dict(data)
        else:
            self._backing[self._key] = data

    async def async_remove(self) -> None:
        self._backing.pop(self._key, None)


def _patched_store_factory(backing: dict):
    """Return a function compatible with `Store(hass, version, key)` signature."""

    def _factory(hass, version, key):
        return _FakeStore(backing, key)

    return _factory


@pytest.fixture
def hass():
    return MagicMock()


@pytest.fixture
def shared_backing():
    """Shared dict that simulates the on-disk Store contents across buffer instances."""
    return {}


# ---------------------------------------------------------------------------
# a) Empty load
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_empty_returns_no_identity(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        assert buf.identity_known() is False
        assert buf.get_identity() is None
        assert buf.size() == 0


# ---------------------------------------------------------------------------
# b) set_identity persists
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_identity_persists(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        await buf.set_identity("uuid-1", "key-abc", "2026-04-29T12:00:00+00:00")

        # Verify persisted to backing dict under STORAGE_TELEMETRY key
        assert STORAGE_TELEMETRY in shared_backing
        assert shared_backing[STORAGE_TELEMETRY] == {
            "installation_id": "uuid-1",
            "api_key": "key-abc",
            "registered_at": "2026-04-29T12:00:00+00:00",
        }

        # Round-trip via a fresh buffer
        buf2 = TelemetryBuffer(hass)
        await buf2.load()
        assert buf2.identity_known() is True
        ident = buf2.get_identity()
        assert ident == {
            "installation_id": "uuid-1",
            "api_key": "key-abc",
            "registered_at": "2026-04-29T12:00:00+00:00",
        }


# ---------------------------------------------------------------------------
# c) clear_identity empties storage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clear_identity_empties_storage(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        await buf.set_identity("u", "k", "2026-04-29T12:00:00+00:00")
        await buf.clear_identity()

        # Reload — identity gone
        buf2 = TelemetryBuffer(hass)
        await buf2.load()
        assert buf2.identity_known() is False
        assert buf2.get_identity() is None


# ---------------------------------------------------------------------------
# d) append adds to buffer + persists
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_append_adds_to_buffer_and_persists(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        await buf.append("/v1/snapshot", {"ts": "2026-04-29T12:00:00+00:00"})

        assert buf.size() == 1
        # Persisted as a list of one entry
        assert STORAGE_TELEMETRY_BUFFER in shared_backing
        persisted = shared_backing[STORAGE_TELEMETRY_BUFFER]
        assert isinstance(persisted, list)
        assert len(persisted) == 1
        assert persisted[0]["endpoint"] == "/v1/snapshot"
        assert persisted[0]["body"] == {"ts": "2026-04-29T12:00:00+00:00"}
        assert "queued_at" in persisted[0]


# ---------------------------------------------------------------------------
# e) buffer caps at max — drop oldest
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_buffer_caps_at_max_drops_oldest(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()

        # Append MAX + 5 → size capped at MAX, the first 5 dropped
        for i in range(TELEMETRY_BUFFER_MAX + 5):
            await buf.append("/v1/snapshot", {"i": i})

        assert buf.size() == TELEMETRY_BUFFER_MAX
        # The first 5 (i=0..4) are gone, head is i=5
        peeked = buf.peek_batch(1)
        assert peeked[0]["body"] == {"i": 5}
        # Tail is i=MAX+4
        all_entries = buf.peek_batch(TELEMETRY_BUFFER_MAX)
        assert all_entries[-1]["body"] == {"i": TELEMETRY_BUFFER_MAX + 4}


# ---------------------------------------------------------------------------
# f) peek_batch does not remove
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_peek_batch_does_not_remove(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        for i in range(10):
            await buf.append("/v1/snapshot", {"i": i})

        assert len(buf.peek_batch(3)) == 3
        assert buf.size() == 10


# ---------------------------------------------------------------------------
# g) drop removes n oldest
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_drop_removes_n_oldest(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        for i in range(10):
            await buf.append("/v1/snapshot", {"i": i})

        await buf.drop(3)
        assert buf.size() == 7
        remaining = buf.peek_batch(10)
        assert remaining[0]["body"] == {"i": 3}
        assert remaining[-1]["body"] == {"i": 9}


# ---------------------------------------------------------------------------
# h) clear_buffer empties + persists
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clear_buffer_empties_and_persists(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        for i in range(5):
            await buf.append("/v1/snapshot", {"i": i})

        await buf.clear_buffer()
        assert buf.size() == 0
        assert shared_backing.get(STORAGE_TELEMETRY_BUFFER) == []


# ---------------------------------------------------------------------------
# i) restart survival — identity + queued events round-trip via fresh buffer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_restart_survival(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        # Buffer A: set identity + 3 events
        buf_a = TelemetryBuffer(hass)
        await buf_a.load()
        await buf_a.set_identity("uuid-9", "key-9", "2026-04-29T12:00:00+00:00")
        for i in range(3):
            await buf_a.append("/v1/state-change", {"i": i, "ts": "2026-04-29"})

        # Buffer B reads the same backing dict — simulates HA restart
        buf_b = TelemetryBuffer(hass)
        await buf_b.load()
        assert buf_b.identity_known() is True
        assert buf_b.get_identity() == {
            "installation_id": "uuid-9",
            "api_key": "key-9",
            "registered_at": "2026-04-29T12:00:00+00:00",
        }
        assert buf_b.size() == 3
        rebuilt = buf_b.peek_batch(3)
        assert [e["body"]["i"] for e in rebuilt] == [0, 1, 2]
        assert all(e["endpoint"] == "/v1/state-change" for e in rebuilt)


# ---------------------------------------------------------------------------
# j) drop with n > size is safe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_drop_more_than_size_is_safe(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_patched_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
        await buf.append("/v1/snapshot", {"i": 0})
        await buf.drop(99)
        assert buf.size() == 0
