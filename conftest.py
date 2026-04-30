"""Root conftest: stub homeassistant modules so tests can import the integration."""

import sys
from unittest.mock import MagicMock

# Stub all homeassistant sub-modules referenced by the integration.
# This must run before pytest collects any test that imports from
# custom_components.eeg_energy_optimizer.
_HA_MODULES = [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.websocket_api",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.util",
    "homeassistant.util.dt",
    "voluptuous",
]

for mod in _HA_MODULES:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


# Phase 8 (08-03): Make `@websocket_api.websocket_command(...)` and
# `@websocket_api.async_response` no-op pass-through decorators so the
# decorated coroutines remain awaitable in tests. Without this the MagicMock
# stub turns each decorator call into another MagicMock, which is not
# awaitable. We only patch the public-facing decorator names that the
# integration uses; everything else stays a MagicMock.
_ws_module = sys.modules["homeassistant.components.websocket_api"]


def _websocket_command_decorator(_schema):
    def _wrap(func):
        return func
    return _wrap


def _async_response_decorator(func):
    return func


_ws_module.websocket_command = _websocket_command_decorator
_ws_module.async_response = _async_response_decorator
_ws_module.async_register_command = MagicMock()
_ws_module.ActiveConnection = MagicMock

# Wichtig: `from homeassistant.components import websocket_api` greift NICHT auf
# sys.modules zu, sondern auf das Attribut `websocket_api` des `homeassistant.components`
# MagicMock — das standardmäßig ein eigener MagicMock ist (nicht unser gepatchter).
# Daher: gepatchtes Modul auch als Attribut auf homeassistant.components legen.
sys.modules["homeassistant.components"].websocket_api = _ws_module
