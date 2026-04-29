"""Tests for TelemetryReporter — HTTP, register, send_*, retry, backoff, whitelist.

Mocks ``aiohttp.ClientSession`` via the patched ``async_get_clientsession``
inside the reporter module. The HTTP-contract pin
``test_payload_field_names_match_types_ts`` (W-7) compares POSTed payloads
against the field sets in EEGEnergyOptimzierBackend/src/types.ts.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    TELEMETRY_BUFFER_MAX,
    TELEMETRY_FLUSH_BATCH,
)
from custom_components.eeg_energy_optimizer.telemetry_buffer import TelemetryBuffer


# ---------------------------------------------------------------------------
# Reusable fakes
# ---------------------------------------------------------------------------
class _FakeStore:
    """In-memory drop-in for homeassistant.helpers.storage.Store."""

    def __init__(self, backing: dict, key: str) -> None:
        self._backing = backing
        self._key = key

    async def async_load(self):
        return self._backing.get(self._key)

    async def async_save(self, data) -> None:
        if isinstance(data, list):
            self._backing[self._key] = list(data)
        elif isinstance(data, dict):
            self._backing[self._key] = dict(data)
        else:
            self._backing[self._key] = data

    async def async_remove(self) -> None:
        self._backing.pop(self._key, None)


def _store_factory(backing: dict):
    def _f(hass, version, key):
        return _FakeStore(backing, key)
    return _f


class _FakeResponse:
    """Async-context-manager-shaped aiohttp response stub."""

    def __init__(self, status: int, body: dict | None = None, headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}
        self.content_length = len((str(body) if body is not None else "")) or 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._body or {}

    async def text(self):
        return str(self._body or "")


def _make_session(post_responses=None, delete_responses=None, post_default=None, delete_default=None):
    """Build a session whose .post and .delete return scripted FakeResponses.

    Capture-Always: jeder Aufruf wird in ``session._captured_posts`` /
    ``session._captured_deletes`` aufgezeichnet, unabhängig davon, ob der Test
    später ``session.post.side_effect`` umsetzt — wir wrappen die Konsumenten-
    Schicht in ``_capturing_post`` / ``_capturing_delete`` und lassen sie an
    eine austauschbare Strategie delegieren.

    post_responses / delete_responses: list (FIFO scripted)
    post_default / delete_default: callable used after responses exhausted
    """
    session = MagicMock()
    captured_posts: list[dict] = []
    captured_deletes: list[dict] = []

    post_iter = iter(post_responses or [])
    delete_iter = iter(delete_responses or [])

    def _post_strategy(url, **kwargs):
        try:
            nxt = next(post_iter)
        except StopIteration:
            if post_default is not None:
                return post_default(url, **kwargs)
            return _FakeResponse(204, None)
        return nxt(url, **kwargs) if callable(nxt) else nxt

    def _delete_strategy(url, **kwargs):
        try:
            nxt = next(delete_iter)
        except StopIteration:
            if delete_default is not None:
                return delete_default(url, **kwargs)
            return _FakeResponse(204, None)
        return nxt(url, **kwargs) if callable(nxt) else nxt

    def _capturing_post(url, **kwargs):
        captured_posts.append({"url": url, **kwargs})
        # Tests may swap session.post.side_effect to supply a different
        # response strategy after _make_session() returns — we honor that
        # while still capturing.
        strategy = session.post._strategy
        return strategy(url, **kwargs)

    def _capturing_delete(url, **kwargs):
        captured_deletes.append({"url": url, **kwargs})
        strategy = session.delete._strategy
        return strategy(url, **kwargs)

    session.post = MagicMock(side_effect=_capturing_post)
    session.post._strategy = _post_strategy

    session.delete = MagicMock(side_effect=_capturing_delete)
    session.delete._strategy = _delete_strategy

    session._captured_posts = captured_posts
    session._captured_deletes = captured_deletes
    return session


def _set_post_strategy(session, strategy):
    """Replace the response strategy without losing the capture wrapper."""
    session.post._strategy = strategy


def _set_delete_strategy(session, strategy):
    session.delete._strategy = strategy


@pytest.fixture
def hass():
    return MagicMock()


@pytest.fixture
def shared_backing():
    return {}


async def _make_buffer(hass, shared_backing):
    with patch(
        "custom_components.eeg_energy_optimizer.telemetry_buffer.Store",
        side_effect=_store_factory(shared_backing),
    ):
        buf = TelemetryBuffer(hass)
        await buf.load()
    return buf


def _import_reporter():
    """Lazy import so that any monkeypatching of constants happens before."""
    from custom_components.eeg_energy_optimizer import telemetry as tm
    return tm


# ---------------------------------------------------------------------------
# a) No-op when URL empty
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_op_when_url_empty(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "tok")

    buf = await _make_buffer(hass, shared_backing)
    session = _make_session()
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    assert reporter.is_configured is False

    await reporter.send_state_change({"ts": "x", "transition": "a->b"})
    await reporter.send_snapshot({"ts": "x"})
    await reporter.send_outcome({"event_type": "x", "started_at": "a", "ended_at": "b"})

    assert session.post.call_count == 0
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# b) No-op when bootstrap token empty
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_op_when_token_empty(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "")

    buf = await _make_buffer(hass, shared_backing)
    session = _make_session()
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    assert reporter.is_configured is False
    await reporter.send_state_change({"ts": "x", "transition": "a->b"})
    assert session.post.call_count == 0
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# c) register happy path — bootstrap header, identity stored, settings filtered
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_happy_path(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    session = _make_session(post_responses=[
        _FakeResponse(201, {"installation_id": "uuid-x", "api_key": "key-y"}),
    ])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    ok = await reporter.register({
        "app_version": "1.1.0",
        "battery_capacity_kwh": 10,
        "settings": {"min_soc": 10, "battery_soc_sensor": "sensor.foo"},
    })

    assert ok is True
    assert session.post.call_count == 1
    call = session._captured_posts[0]
    assert call["url"].endswith("/v1/register")
    assert call["headers"].get("X-Bootstrap-Token") == "boot-tok"
    assert "Authorization" not in call["headers"]
    body = call["json"]
    assert body["app_version"] == "1.1.0"
    assert body["battery_capacity_kwh"] == 10
    # entity_id-Sensor wurde durch Whitelist gefiltert
    assert body["settings"] == {"min_soc": 10}

    # Identity persisted
    assert buf.identity_known()
    ident = buf.get_identity()
    assert ident["installation_id"] == "uuid-x"
    assert ident["api_key"] == "key-y"


# ---------------------------------------------------------------------------
# d) register 4xx — no identity, no buffering
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_4xx_does_not_buffer_or_set_identity(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    session = _make_session(post_responses=[_FakeResponse(400, {"error": "bad"})])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    ok = await reporter.register({"app_version": "1.1.0"})
    assert ok is False
    assert buf.identity_known() is False
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# e) send_state_change uses Bearer auth
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_state_change_uses_bearer_auth(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    session = _make_session(post_responses=[_FakeResponse(204)])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    await reporter.send_state_change({
        "ts": "2026-04-29T20:00:00+00:00",
        "transition": "normal->morgen_einspeisung",
        "mode": "ein",
        "reasons": ["pv_forecast_exceeds_demand"],
        "blocked_by": [],
        "snapshot": {"soc_pct": 50},
    })

    assert session.post.call_count == 1
    call = session._captured_posts[0]
    assert call["url"].endswith("/v1/state-change")
    assert call["headers"].get("Authorization") == "Bearer k"
    assert "X-Bootstrap-Token" not in call["headers"]


# ---------------------------------------------------------------------------
# f) No identity ⇒ no send and no buffering
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_identity_means_no_send(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    session = _make_session(post_responses=[_FakeResponse(204)])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    await reporter.send_state_change({"ts": "x", "transition": "a->b"})
    assert session.post.call_count == 0
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# g) 5xx → 1× retry, then buffer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5xx_retry_then_buffer(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    session = _make_session(post_responses=[
        _FakeResponse(500, None),
        _FakeResponse(500, None),
    ])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    body = {"ts": "x", "transition": "a->b"}
    await reporter.send_state_change(body)

    assert session.post.call_count == 2  # one retry
    assert buf.size() == 1
    queued = buf.peek_batch(1)[0]
    assert queued["endpoint"] == "/v1/state-change"
    assert queued["body"] == body


# ---------------------------------------------------------------------------
# h) 4xx → no retry, no buffer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4xx_no_retry_no_buffer(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    session = _make_session(post_responses=[_FakeResponse(400, {"error": "bad"})])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    await reporter.send_state_change({"ts": "x", "transition": "a->b"})
    assert session.post.call_count == 1
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# i) 429 with Retry-After respected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_429_respects_retry_after(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    session = _make_session(post_responses=[_FakeResponse(429, headers={"Retry-After": "120"})])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    body = {"ts": "x", "transition": "a->b"}
    await reporter.send_state_change(body)

    # 429 → 1 POST attempt (no retry on 429), event buffered
    assert session.post.call_count == 1
    assert buf.size() == 1

    # Backoff window honoured: subsequent send goes straight to buffer
    body2 = {"ts": "y", "transition": "a->b"}
    await reporter.send_state_change(body2)
    assert session.post.call_count == 1  # no new POST
    assert buf.size() == 2

    # Backoff time ≈ 120 s (Retry-After). Manually rewind clock by setting
    # _next_attempt_at into the past to simulate that the cooloff has expired.
    reporter._next_attempt_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    # Provide a successful POST for the live send + drains
    _set_post_strategy(session, lambda *a, **kw: _FakeResponse(204))
    await reporter.send_state_change({"ts": "z", "transition": "a->b"})
    # Now POST happens again — at least 1 new call (live send)
    assert session.post.call_count >= 2


# ---------------------------------------------------------------------------
# j) Backoff grows then resets on success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backoff_grows_then_resets(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")

    # Helper that returns a 500 (with retry → 2 attempts per send)
    def make_500(*_a, **_kw):
        return _FakeResponse(500)

    session = _make_session(post_default=make_500)
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)

    # Send 1 — 1 failure increment, but backoff window not yet skipped.
    # Reset _next_attempt_at to past between sends so that we actually attempt POST.
    for i in range(3):
        reporter._next_attempt_at = None  # bypass backoff gate per attempt
        await reporter.send_state_change({"ts": f"t{i}", "transition": "a->b"})

    assert reporter._consecutive_failures == 3
    # Expected delay: 60 * 2^(3-1) = 240 s, capped at 1800
    expected_delay = min(60 * (2 ** 2), 1800)
    assert reporter._next_attempt_at is not None
    delta = reporter._next_attempt_at - datetime.now(tz=timezone.utc)
    assert 0 <= delta.total_seconds() <= expected_delay + 5

    # Now a 204 response resets
    _set_post_strategy(session, lambda *a, **kw: _FakeResponse(204))
    reporter._next_attempt_at = None
    await reporter.send_state_change({"ts": "ok", "transition": "a->b"})
    assert reporter._consecutive_failures == 0
    assert reporter._next_attempt_at is None


# ---------------------------------------------------------------------------
# k) Successful send drains buffer FIFO up to TELEMETRY_FLUSH_BATCH
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_successful_send_drains_buffer_fifo(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    # Pre-populate 12 events
    for i in range(12):
        await buf.append("/v1/snapshot", {"ts": f"t{i}"})
    assert buf.size() == 12

    session = _make_session(post_default=lambda *a, **kw: _FakeResponse(204))
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    await reporter.send_outcome({
        "event_type": "morgen_einspeisung",
        "started_at": "2026-04-29T07:00:00+00:00",
        "ended_at":   "2026-04-29T11:00:00+00:00",
    })

    # 1 POST for the live outcome + TELEMETRY_FLUSH_BATCH (=10) for drain
    assert session.post.call_count == 1 + TELEMETRY_FLUSH_BATCH
    assert buf.size() == 12 - TELEMETRY_FLUSH_BATCH


# ---------------------------------------------------------------------------
# l) forget clears locally even on backend failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_forget_clears_locally_even_on_failure(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")
    await buf.append("/v1/snapshot", {"ts": "x"})

    session = _make_session(delete_responses=[_FakeResponse(500)])
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    ok = await reporter.forget()
    assert ok is False
    assert buf.identity_known() is False
    assert buf.size() == 0


# ---------------------------------------------------------------------------
# m) send_snapshot_batch chunks at 100
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_snapshot_batch_chunks_at_100(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")

    buf = await _make_buffer(hass, shared_backing)
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")

    session = _make_session(post_default=lambda *a, **kw: _FakeResponse(204))
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)
    payloads = [{"ts": f"t{i}"} for i in range(250)]
    await reporter.send_snapshot_batch(payloads)

    # 250 / 100 → 3 POSTs of size 100, 100, 50
    bodies = [c["json"] for c in session._captured_posts]
    # Filter to the snapshot endpoint posts (no register/etc.)
    snapshot_bodies = [b for c, b in zip(session._captured_posts, bodies) if c["url"].endswith("/v1/snapshot")]
    assert len(snapshot_bodies) == 3
    assert [len(b) for b in snapshot_bodies] == [100, 100, 50]


# ---------------------------------------------------------------------------
# n) Settings whitelist filters unknown keys
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_settings_whitelist_filters_unknown_keys(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")
    buf = await _make_buffer(hass, shared_backing)
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: MagicMock())

    reporter = tm.TelemetryReporter(hass, buf)
    shaped = reporter._shape_profile({
        "app_version": "1.1.0",
        "battery_capacity_kwh": 10,
        "entry_id": "should-be-dropped",  # unknown top-level
        "settings": {
            "min_soc": 10,
            "battery_soc_sensor": "sensor.foo",
            "fronius_modbus_host": "1.2.3.4",
            "enable_peakshare": True,
        },
    })

    assert shaped["app_version"] == "1.1.0"
    assert shaped["battery_capacity_kwh"] == 10
    assert "entry_id" not in shaped
    assert set(shaped["settings"].keys()) == {"min_soc", "enable_peakshare"}
    assert "battery_soc_sensor" not in shaped["settings"]
    assert "fronius_modbus_host" not in shaped["settings"]


# ---------------------------------------------------------------------------
# o) HTTP-Contract Pin (W-7) — payload field names match types.ts
# ---------------------------------------------------------------------------
# NOTE: If EEGEnergyOptimzierBackend/src/types.ts changes, update BOTH this
#       dict AND the reporter's payload builders. This test is the single
#       backstop against drift between the HA reporter and the backend.
EXPECTED_KEYS_BY_ENDPOINT = {
    "/v1/register": {  # RegisterPayload extends ProfilePayload
        "integration_started_at", "app_version", "ha_version", "inverter_type",
        "battery_capacity_kwh", "pv_peak_kwp", "forecast_provider", "country_iso",
        "settings",
    },
    "/v1/profile": {
        "integration_started_at", "app_version", "ha_version", "inverter_type",
        "battery_capacity_kwh", "pv_peak_kwp", "forecast_provider", "country_iso",
        "settings",
    },
    "/v1/snapshot": {
        "ts", "state", "mode", "soc_pct", "pv_now_kw", "consumption_now_kw",
        "grid_now_kw", "battery_now_kw", "min_soc_dyn", "hysteresis",
    },
    "/v1/state-change": {
        "ts", "transition", "mode", "reasons", "blocked_by", "snapshot",
    },
    "/v1/outcome": {
        "event_type", "started_at", "ended_at", "duration_minutes",
        "grid_export_kwh", "peak_power_kw", "soc_start_pct", "soc_end_pct",
        "predicted_pv_kwh", "actual_pv_kwh", "predicted_consumption_kwh",
        "actual_consumption_kwh", "terminated_by",
    },
    "/v1/failure": {
        "ts", "category", "severity", "message_hash", "context",
    },
}


@pytest.mark.asyncio
async def test_payload_field_names_match_types_ts(hass, shared_backing, monkeypatch):
    """W-7: every reporter endpoint POSTs only fields defined in types.ts."""
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")
    buf = await _make_buffer(hass, shared_backing)

    # Need identity for Bearer-protected endpoints
    await buf.set_identity("u", "k", "2026-01-01T00:00:00+00:00")

    # Maximally populated payloads — every field listed in types.ts
    profile_full = {
        "integration_started_at": "2026-04-29T00:00:00+00:00",
        "app_version": "1.1.0",
        "ha_version": "2026.4.0",
        "inverter_type": "fronius_gen24",
        "battery_capacity_kwh": 10,
        "pv_peak_kwp": None,
        "forecast_provider": "solcast_solar",
        "country_iso": "AT",
        "settings": {"min_soc": 10, "enable_peakshare": True},
    }
    state_change_full = {
        "ts": "2026-04-29T20:00:00+00:00",
        "transition": "normal->morgen_einspeisung",
        "mode": "ein",
        "reasons": ["pv_forecast_exceeds_demand"],
        "blocked_by": [],
        "snapshot": {"soc_pct": 50},
    }
    snapshot_full = {
        "ts": "2026-04-29T20:00:00+00:00",
        "state": "Normal",
        "mode": "ein",
        "soc_pct": 50,
        "pv_now_kw": 1.2,
        "consumption_now_kw": 0.8,
        "grid_now_kw": -0.4,
        "battery_now_kw": 0.0,
        "min_soc_dyn": 15,
        "hysteresis": False,
    }
    outcome_full = {
        "event_type": "morgen_einspeisung",
        "started_at": "2026-04-29T07:00:00+00:00",
        "ended_at": "2026-04-29T11:00:00+00:00",
        "duration_minutes": 240,
        "grid_export_kwh": 4.0,
        "peak_power_kw": 3.0,
        "soc_start_pct": 90,
        "soc_end_pct": 60,
        "predicted_pv_kwh": 25.0,
        "actual_pv_kwh": 24.0,
        "predicted_consumption_kwh": 8.0,
        "actual_consumption_kwh": 7.5,
        "terminated_by": "schedule",
    }
    failure_full = {
        "ts": "2026-04-29T20:00:00+00:00",
        "category": "inverter_write",
        "severity": "warning",
        "message_hash": "deadbeef",
        "context": {"endpoint": "set_charge_limit"},
    }

    # Allow snapshot drain to also POST, but with empty buffer it's a single POST per send.
    def _strategy(url, **kwargs):
        if str(url).endswith("/v1/register"):
            return _FakeResponse(201, {"installation_id": "uuid-x", "api_key": "key-y"})
        return _FakeResponse(204, None)

    session = _make_session(post_default=_strategy)
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: session)

    reporter = tm.TelemetryReporter(hass, buf)

    await reporter.register(profile_full)
    await reporter.update_profile(profile_full)
    await reporter.send_state_change(state_change_full)
    await reporter.send_snapshot(snapshot_full)
    await reporter.send_snapshot_batch([snapshot_full, snapshot_full])
    await reporter.send_outcome(outcome_full)
    await reporter.send_failure(failure_full)

    # Every captured post: subset rule
    for call in session._captured_posts:
        url = call["url"]
        endpoint = "/" + url.split("/", 3)[3]  # take everything after host
        # Strip query / trailing
        endpoint = endpoint.split("?")[0]
        assert endpoint in EXPECTED_KEYS_BY_ENDPOINT, f"Unexpected endpoint posted: {endpoint}"
        body = call["json"]
        allowed = EXPECTED_KEYS_BY_ENDPOINT[endpoint]

        if endpoint == "/v1/snapshot" and isinstance(body, list):
            for item in body:
                extra = set(item.keys()) - allowed
                assert not extra, f"Endpoint {endpoint} batch item has unknown fields: {extra}"
        else:
            assert isinstance(body, dict), f"Body for {endpoint} should be dict, got {type(body)}"
            extra = set(body.keys()) - allowed
            assert not extra, f"Endpoint {endpoint} body has unknown fields: {extra}"


# ---------------------------------------------------------------------------
# p) flush_buffer is idempotent and respects identity precondition
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flush_buffer_no_identity_returns_zero(hass, shared_backing, monkeypatch):
    tm = _import_reporter()
    monkeypatch.setattr(tm, "TELEMETRY_BACKEND_URL", "https://eeg.example")
    monkeypatch.setattr(tm, "TELEMETRY_BOOTSTRAP_TOKEN", "boot-tok")
    buf = await _make_buffer(hass, shared_backing)
    monkeypatch.setattr(tm, "async_get_clientsession", lambda h: MagicMock())

    reporter = tm.TelemetryReporter(hass, buf)
    # No identity set → flush_buffer is a no-op
    n = await reporter.flush_buffer()
    assert n == 0
