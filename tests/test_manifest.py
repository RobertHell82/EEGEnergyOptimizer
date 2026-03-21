"""Tests for HACS packaging and manifest validation (INF-03)."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "eeg_energy_optimizer"


class TestManifest:
    """Verify manifest.json contains all required fields."""

    def test_manifest_required_fields(self):
        """manifest.json has domain, name, version, config_flow, integration_type."""
        manifest = json.loads((INTEGRATION_DIR / "manifest.json").read_text())
        assert manifest["domain"] == "eeg_energy_optimizer"
        assert manifest["name"] == "EEG Energy Optimizer"
        assert manifest["version"] == "0.1.0"
        assert manifest["config_flow"] is True
        assert manifest["integration_type"] == "hub"

    def test_manifest_after_dependencies(self):
        """manifest.json lists huawei_solar as after_dependency."""
        manifest = json.loads((INTEGRATION_DIR / "manifest.json").read_text())
        assert "huawei_solar" in manifest["after_dependencies"]


class TestHacsJson:
    """Verify hacs.json is valid."""

    def test_hacs_json_valid(self):
        """hacs.json contains name and homeassistant fields."""
        hacs = json.loads((REPO_ROOT / "hacs.json").read_text())
        assert "name" in hacs
        assert "homeassistant" in hacs

    def test_hacs_json_homeassistant_version(self):
        """hacs.json requires HA 2025.1.0."""
        hacs = json.loads((REPO_ROOT / "hacs.json").read_text())
        assert hacs["homeassistant"] == "2025.1.0"


class TestReadme:
    """Verify README exists for HACS."""

    def test_readme_exists(self):
        """README.md exists at repository root and is non-empty."""
        readme = REPO_ROOT / "README.md"
        assert readme.exists(), "README.md must exist at repository root"
        content = readme.read_text()
        assert len(content.strip()) > 0, "README.md must not be empty"
