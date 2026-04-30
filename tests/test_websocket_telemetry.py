"""Tests for Phase 8 Plan 03 — Telemetry WebSocket commands.

Tests die 4 neuen Befehle:
  - eeg_optimizer/telemetry_get_status
  - eeg_optimizer/telemetry_enable
  - eeg_optimizer/telemetry_disable
  - eeg_optimizer/telemetry_forget

Test-Idiom: WebSocket-Befehle sind durch @websocket_api.async_response dekoriert.
Wir rufen die innere Coroutine direkt mit (hass, connection, msg) auf — das ist
das gleiche Pattern, das HA intern nutzt, und vermeidet die Notwendigkeit eines
echten WebSocket-Servers.

Zugriff auf die innere Funktion: Decorator hängt sie an `_handler` oder das
äußere Objekt ist callable wie eine Funktion. Wir nutzen den dokumentierten
Schedule-Pattern — die Funktion ist nach dem Dekorator immer noch callable.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_TELEMETRY_ENABLED,
    DOMAIN,
    TELEMETRY_SETTINGS_KEYS,
)


# ---------------------------------------------------------------------------
# Test-Helfer: hass / connection / data dict
# ---------------------------------------------------------------------------
def _make_hass(entry, data):
    """Build a hass mock that _get_entry_data can resolve to (entry, data)."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.config_entries.async_update_entry = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: data}}
    return hass


def _make_entry(telemetry_enabled=False, extra_data=None):
    extra_data = extra_data or {}
    return SimpleNamespace(
        entry_id="entry-1",
        data={CONF_TELEMETRY_ENABLED: telemetry_enabled, **extra_data},
        options={},
        version=13,
        created_at=None,
    )


def _make_buffer(identity=None, size=0):
    buf = MagicMock()
    buf.identity_known = MagicMock(return_value=identity is not None)
    buf.get_identity = MagicMock(return_value=identity)
    buf.size = MagicMock(return_value=size)
    return buf


def _make_reporter(configured=True):
    rep = MagicMock()
    rep.is_configured = configured
    rep.register = AsyncMock(return_value=True)
    rep.forget = AsyncMock(return_value=True)
    rep.update_profile = AsyncMock()
    return rep


def _make_connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


def _msg(cmd_type: str, **kwargs) -> dict:
    return {"id": 42, "type": f"eeg_optimizer/{cmd_type}", **kwargs}


# Resolve the inner coroutine from a websocket_api-decorated function.
# HA's @websocket_api.websocket_command sets the schema and exposes the
# original function on attribute `_func` (or simply remains callable). The
# safest path: import the module attribute, which after decoration is
# typically a callable wrapper. We strip the wrapper if needed.
def _call(handler, hass, connection, msg):
    """Call a (decorated) websocket handler, awaiting if it returns a coroutine."""
    inner = getattr(handler, "_func", handler)
    return inner(hass, connection, msg)


# ---------------------------------------------------------------------------
# e) telemetry_get_status — registered + identity prefix
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_status_returns_8_char_prefix_when_registered():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_get_status,
    )

    entry = _make_entry(telemetry_enabled=True)
    identity = {
        "installation_id": "abcdef01-2345-6789-abcd-ef0123456789",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    }
    buffer = _make_buffer(identity=identity, size=3)
    reporter = _make_reporter(configured=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [{}, {}],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_get_status, hass, conn, _msg("telemetry_get_status"))

    assert conn.send_result.called
    payload = conn.send_result.call_args.args[1]
    assert payload["registered"] is True
    assert payload["installation_id_prefix"] == "abcdef01"
    assert payload["registered_at"] == "2026-01-01T00:00:00+00:00"
    assert payload["configured"] is True
    assert payload["enabled"] is True
    assert payload["buffer_size"] == 3
    # queue_size = snapshot_queue + buffer
    assert payload["queue_size"] == 2 + 3


# ---------------------------------------------------------------------------
# f) telemetry_get_status — unregistered
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_status_when_unregistered():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_get_status,
    )

    entry = _make_entry(telemetry_enabled=False)
    buffer = _make_buffer(identity=None, size=0)
    reporter = _make_reporter(configured=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_get_status, hass, conn, _msg("telemetry_get_status"))

    payload = conn.send_result.call_args.args[1]
    assert payload["registered"] is False
    assert payload["installation_id_prefix"] is None
    assert payload["registered_at"] is None
    assert payload["enabled"] is False


# ---------------------------------------------------------------------------
# g) telemetry_enable — register + update config
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enable_calls_register_and_updates_config():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_enable,
    )

    entry = _make_entry(telemetry_enabled=False, extra_data={"min_soc": 15})
    # Buffer starts empty; after register the mock will populate identity
    buffer = _make_buffer(identity=None)
    reporter = _make_reporter(configured=True)

    async def _register_side_effect(profile):
        # After register: simulate identity stored
        ident = {
            "installation_id": "uuid-x-prefix-1234",
            "api_key": "k",
            "registered_at": "2026-04-15T00:00:00+00:00",
        }
        buffer.get_identity.return_value = ident
        buffer.identity_known.return_value = True
        return True

    reporter.register.side_effect = _register_side_effect

    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_enable, hass, conn, _msg("telemetry_enable"))

    # register was awaited
    assert reporter.register.await_count == 1
    profile = reporter.register.await_args.args[0]
    # whitelist constraint — only TELEMETRY_SETTINGS_KEYS may show up under settings
    extra_keys = set(profile.get("settings", {}).keys()) - set(TELEMETRY_SETTINGS_KEYS)
    assert not extra_keys, f"non-whitelisted settings leaked: {extra_keys}"
    # config update fired
    assert hass.config_entries.async_update_entry.called
    update_args, update_kwargs = hass.config_entries.async_update_entry.call_args
    new_data = update_kwargs.get("data") or (update_args[1] if len(update_args) > 1 else None)
    assert new_data and new_data[CONF_TELEMETRY_ENABLED] is True
    # send_result success+prefix
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is True
    assert payload["installation_id_prefix"] == "uuid-x-p"  # first 8 chars


# ---------------------------------------------------------------------------
# g2) telemetry_enable bei vorhandener Identity = Pause→Resume (D-33):
#     KEIN erneutes Register, stattdessen update_profile mit dem
#     gemeinsamen Profile-Builder (I-4). Verhindert verwaiste Datensätze
#     am Backend bei jedem Disable→Enable-Toggle.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enable_after_disable_resumes_without_register():
    from custom_components.eeg_energy_optimizer import websocket_api as ws_mod
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_enable,
    )

    # Pause-State: Flag aus, Identity bleibt erhalten (so verhält sich
    # ws_telemetry_disable seit Phase 4).
    entry = _make_entry(telemetry_enabled=False)
    buffer = _make_buffer(identity={
        "installation_id": "abcdef01-1111-2222-3333-444455556666",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    })
    reporter = _make_reporter(configured=True)
    reporter.register = AsyncMock(return_value=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    fake_profile = {"app_version": "1.0.11", "ha_version": "2026.4", "settings": None}
    with patch.object(ws_mod, "_build_telemetry_profile", return_value=fake_profile) as patched:
        await _call(ws_telemetry_enable, hass, conn, _msg("telemetry_enable"))

    # Kein zweiter Backend-Datensatz: register darf NICHT aufgerufen werden.
    assert reporter.register.await_count == 0
    # Stattdessen update_profile mit dem korrekt gebauten Profil.
    assert reporter.update_profile.await_count == 1
    assert reporter.update_profile.await_args.args[0] == fake_profile

    # Profile-Builder wurde mit identity_registered_at der vorhandenen
    # Identity aufgerufen — I-4-Vertrag bleibt gewahrt.
    assert patched.call_count == 1
    call_args = patched.call_args
    assert call_args.args[0] is hass
    assert call_args.args[1] is entry
    rid = call_args.kwargs.get("identity_registered_at")
    if rid is None and len(call_args.args) >= 3:
        rid = call_args.args[2]
    assert rid == "2026-01-01T00:00:00+00:00"

    # Flag wurde wieder aktiviert.
    assert hass.config_entries.async_update_entry.called
    update_args, update_kwargs = hass.config_entries.async_update_entry.call_args
    new_data = update_kwargs.get("data") or (update_args[1] if len(update_args) > 1 else None)
    assert new_data and new_data[CONF_TELEMETRY_ENABLED] is True

    # send_result success + already_active=False (Resume aus Pause)
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is True
    assert payload["already_active"] is False
    assert payload["installation_id_prefix"] == "abcdef01"


# ---------------------------------------------------------------------------
# g3) telemetry_enable bei bereits aktiver Telemetrie = Idempotenz:
#     identity_known + Flag=True → kein register, already_active=True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enable_when_already_active_is_idempotent():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_enable,
    )

    entry = _make_entry(telemetry_enabled=True)
    buffer = _make_buffer(identity={
        "installation_id": "abcdef01-aaaa-bbbb-cccc-dddddddddddd",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    })
    reporter = _make_reporter(configured=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_enable, hass, conn, _msg("telemetry_enable"))

    assert reporter.register.await_count == 0
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is True
    assert payload["already_active"] is True


# ---------------------------------------------------------------------------
# h) telemetry_enable failure → config NOT updated
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enable_failure_does_not_update_config():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_enable,
    )

    entry = _make_entry(telemetry_enabled=False)
    buffer = _make_buffer(identity=None)
    reporter = _make_reporter(configured=True)
    reporter.register = AsyncMock(return_value=False)  # auth fail
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_enable, hass, conn, _msg("telemetry_enable"))

    assert reporter.register.await_count == 1
    assert not hass.config_entries.async_update_entry.called
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# i) telemetry_disable preserves identity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_preserves_identity():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_disable,
    )

    entry = _make_entry(telemetry_enabled=True)
    buffer = _make_buffer(identity={
        "installation_id": "x-id",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    })
    buffer.clear_identity = AsyncMock()
    buffer.clear_buffer = AsyncMock()
    reporter = _make_reporter(configured=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_disable, hass, conn, _msg("telemetry_disable"))

    # forget NOT called, identity preserved
    assert reporter.forget.await_count == 0
    assert buffer.clear_identity.await_count == 0
    # config flipped to False
    assert hass.config_entries.async_update_entry.called
    update_args, update_kwargs = hass.config_entries.async_update_entry.call_args
    new_data = update_kwargs.get("data") or (update_args[1] if len(update_args) > 1 else None)
    assert new_data and new_data[CONF_TELEMETRY_ENABLED] is False
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is True


# ---------------------------------------------------------------------------
# j) telemetry_forget — calls reporter.forget + clears config
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_forget_calls_reporter_forget_and_updates_config():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_forget,
    )

    entry = _make_entry(telemetry_enabled=True)
    buffer = _make_buffer(identity={
        "installation_id": "x-id",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    })
    reporter = _make_reporter(configured=True)
    reporter.forget = AsyncMock(return_value=True)
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_forget, hass, conn, _msg("telemetry_forget"))

    assert reporter.forget.await_count == 1
    assert hass.config_entries.async_update_entry.called
    update_args, update_kwargs = hass.config_entries.async_update_entry.call_args
    new_data = update_kwargs.get("data") or (update_args[1] if len(update_args) > 1 else None)
    assert new_data and new_data[CONF_TELEMETRY_ENABLED] is False
    payload = conn.send_result.call_args.args[1]
    assert payload["success"] is True
    assert payload["backend_deleted"] is True


# ---------------------------------------------------------------------------
# k) telemetry_forget — success=True even when backend fails
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_forget_returns_success_even_when_backend_call_fails():
    from custom_components.eeg_energy_optimizer.websocket_api import (
        ws_telemetry_forget,
    )

    entry = _make_entry(telemetry_enabled=True)
    buffer = _make_buffer(identity={
        "installation_id": "x-id",
        "api_key": "k",
        "registered_at": "2026-01-01T00:00:00+00:00",
    })
    reporter = _make_reporter(configured=True)
    reporter.forget = AsyncMock(return_value=False)  # backend down
    data = {
        "telemetry_buffer": buffer,
        "telemetry_reporter": reporter,
        "snapshot_queue": [],
    }
    hass = _make_hass(entry, data)
    conn = _make_connection()

    await _call(ws_telemetry_forget, hass, conn, _msg("telemetry_forget"))

    assert reporter.forget.await_count == 1
    payload = conn.send_result.call_args.args[1]
    # local cleanup is the success criterion (D-31)
    assert payload["success"] is True
    assert payload["backend_deleted"] is False
