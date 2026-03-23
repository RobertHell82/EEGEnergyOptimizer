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
