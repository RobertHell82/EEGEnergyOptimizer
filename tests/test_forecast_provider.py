"""Tests for PV forecast providers."""

from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer.forecast_provider import (
    ForecastProvider,
    ForecastSolarProvider,
    PVForecast,
    SolcastProvider,
    _read_float,
)


def _make_state(value):
    """Create a mock HA state object."""
    state = MagicMock()
    state.state = value
    return state


def _mock_hass_states(mapping: dict):
    """Create a mock hass with states.get returning from mapping."""
    hass = MagicMock()
    hass.states.get = MagicMock(side_effect=lambda eid: mapping.get(eid))
    return hass


# -- _read_float tests --


class TestReadFloat:
    def test_valid_numeric_string(self):
        hass = _mock_hass_states({"sensor.x": _make_state("12.5")})
        assert _read_float(hass, "sensor.x") == 12.5

    def test_integer_string(self):
        hass = _mock_hass_states({"sensor.x": _make_state("25")})
        assert _read_float(hass, "sensor.x") == 25.0

    def test_unavailable(self):
        hass = _mock_hass_states({"sensor.x": _make_state("unavailable")})
        assert _read_float(hass, "sensor.x") is None

    def test_unknown(self):
        hass = _mock_hass_states({"sensor.x": _make_state("unknown")})
        assert _read_float(hass, "sensor.x") is None

    def test_non_numeric(self):
        hass = _mock_hass_states({"sensor.x": _make_state("abc")})
        assert _read_float(hass, "sensor.x") is None

    def test_none_state(self):
        hass = _mock_hass_states({})
        assert _read_float(hass, "sensor.missing") is None

    def test_empty_string(self):
        hass = _mock_hass_states({"sensor.x": _make_state("")})
        assert _read_float(hass, "sensor.x") is None


# -- SolcastProvider tests --


class TestSolcastProvider:
    def test_solcast_provider_valid_states(self):
        hass = _mock_hass_states({
            "sensor.solcast_remaining": _make_state("12.5"),
            "sensor.solcast_tomorrow": _make_state("25.0"),
        })
        provider = SolcastProvider(
            hass, "sensor.solcast_remaining", "sensor.solcast_tomorrow"
        )
        forecast = provider.get_forecast()
        assert isinstance(forecast, PVForecast)
        assert forecast.remaining_today_kwh == 12.5
        assert forecast.tomorrow_kwh == 25.0

    def test_solcast_provider_unavailable(self):
        hass = _mock_hass_states({
            "sensor.solcast_remaining": _make_state("unavailable"),
            "sensor.solcast_tomorrow": _make_state("unavailable"),
        })
        provider = SolcastProvider(
            hass, "sensor.solcast_remaining", "sensor.solcast_tomorrow"
        )
        forecast = provider.get_forecast()
        assert forecast.remaining_today_kwh is None
        assert forecast.tomorrow_kwh is None

    def test_solcast_provider_partial(self):
        hass = _mock_hass_states({
            "sensor.solcast_remaining": _make_state("12.5"),
            "sensor.solcast_tomorrow": _make_state("unknown"),
        })
        provider = SolcastProvider(
            hass, "sensor.solcast_remaining", "sensor.solcast_tomorrow"
        )
        forecast = provider.get_forecast()
        assert forecast.remaining_today_kwh == 12.5
        assert forecast.tomorrow_kwh is None


# -- ForecastSolarProvider tests --


class TestForecastSolarProvider:
    def test_forecast_solar_provider_valid_states(self):
        hass = _mock_hass_states({
            "sensor.fc_remaining": _make_state("10.0"),
            "sensor.fc_tomorrow": _make_state("20.0"),
        })
        provider = ForecastSolarProvider(
            hass, "sensor.fc_remaining", "sensor.fc_tomorrow"
        )
        forecast = provider.get_forecast()
        assert isinstance(forecast, PVForecast)
        assert forecast.remaining_today_kwh == 10.0
        assert forecast.tomorrow_kwh == 20.0

    def test_forecast_solar_provider_unknown(self):
        hass = _mock_hass_states({
            "sensor.fc_remaining": _make_state("unknown"),
            "sensor.fc_tomorrow": _make_state("unknown"),
        })
        provider = ForecastSolarProvider(
            hass, "sensor.fc_remaining", "sensor.fc_tomorrow"
        )
        forecast = provider.get_forecast()
        assert forecast.remaining_today_kwh is None
        assert forecast.tomorrow_kwh is None

    def test_forecast_solar_provider_missing_entities(self):
        hass = _mock_hass_states({})
        provider = ForecastSolarProvider(
            hass, "sensor.fc_remaining", "sensor.fc_tomorrow"
        )
        forecast = provider.get_forecast()
        assert forecast.remaining_today_kwh is None
        assert forecast.tomorrow_kwh is None


# -- Base class test --


class TestForecastProviderBase:
    def test_base_class_raises(self):
        hass = MagicMock()
        provider = ForecastProvider(hass)
        with pytest.raises(NotImplementedError):
            provider.get_forecast()
