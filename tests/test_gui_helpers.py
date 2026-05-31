import pytest

from radio_interferometer.gui import (
    format_ra_hours,
    fringe_model_config_changed,
    parse_ra_hours_text,
)
from radio_interferometer.sources import ObservationConfig


def test_parse_ra_hours_accepts_hms_and_decimal_hours() -> None:
    assert parse_ra_hours_text("04:31:39.6") == pytest.approx(4.527667, abs=1e-6)
    assert parse_ra_hours_text("4.527667") == pytest.approx(4.527667, abs=1e-6)


def test_format_ra_hours_returns_hms_display() -> None:
    assert format_ra_hours(67.9186 / 15.0) == "04:31:40.5"


def test_parse_ra_hours_rejects_degree_like_value() -> None:
    with pytest.raises(ValueError):
        parse_ra_hours_text("67.9186")


def test_fringe_model_config_changed_detects_target_change() -> None:
    base = make_config()

    assert fringe_model_config_changed(base, make_config(ra_deg=242.38))
    assert fringe_model_config_changed(base, make_config(dec_deg=-25.40))
    assert not fringe_model_config_changed(base, make_config(bins=1024))


def make_config(**overrides) -> ObservationConfig:
    values = {
        "observing_frequency_mhz": 4800.0,
        "intermediate_frequency_mhz": 1150.0,
        "ra_deg": 83.6331,
        "dec_deg": 22.0145,
        "observer_lat_deg": -33.8688,
        "observer_lon_deg": 151.2093,
        "bandwidth_mhz": 30.72,
        "bins": 2048,
        "averaging_blocks": 8196,
    }
    values.update(overrides)
    return ObservationConfig(**values)
