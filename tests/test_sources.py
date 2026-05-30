from datetime import datetime, timezone

import numpy as np
import pytest

from radio_interferometer.sources import (
    ObservationConfig,
    SimulatedInterferometerSource,
    fringe_model,
    geometric_delay_seconds,
    horizontal_coordinates,
    parse_device_args,
    target_coordinates,
)


def make_config() -> ObservationConfig:
    return ObservationConfig(
        observing_frequency_mhz=1420.405751,
        intermediate_frequency_mhz=150.0,
        ra_deg=83.6331,
        dec_deg=22.0145,
        observer_lat_deg=-33.8688,
        observer_lon_deg=151.2093,
        bandwidth_mhz=2.0,
        bins=256,
        baseline_east_m=10.0,
    )


def test_simulated_source_reads_two_complex_channels() -> None:
    source = SimulatedInterferometerSource(make_config())
    source.start()

    antenna_a, antenna_b = source.read(256)

    assert antenna_a.dtype == np.complex64
    assert antenna_b.dtype == np.complex64
    assert antenna_a.shape == (256,)
    assert antenna_b.shape == (256,)


def test_geometric_delay_is_finite() -> None:
    delay = geometric_delay_seconds(
        make_config(),
        datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert np.isfinite(delay)
    assert abs(delay) < 1e-6


def test_fringe_model_matches_geometric_delay_phase() -> None:
    config = make_config()
    when = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)

    model = fringe_model(config, when)

    expected_delay = geometric_delay_seconds(config, when)
    assert model.when_utc == when
    assert model.delay_s == pytest.approx(expected_delay)
    assert model.phase_rad == pytest.approx(
        2.0 * np.pi * config.observing_frequency_hz * expected_delay
    )
    assert np.isfinite(model.phase_rate_rad_s)


def test_fringe_model_rejects_non_positive_rate_step() -> None:
    with pytest.raises(ValueError):
        fringe_model(make_config(), rate_step_s=0.0)


def test_sun_target_coordinates_are_plausible() -> None:
    coords = target_coordinates("Sun", datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc))

    assert coords.name == "Sun"
    assert 60.0 <= coords.ra_deg <= 80.0
    assert 20.0 <= coords.dec_deg <= 25.0


def test_moon_target_coordinates_are_in_expected_ranges() -> None:
    coords = target_coordinates("Moon", datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc))

    assert coords.name == "Moon"
    assert 0.0 <= coords.ra_deg < 360.0
    assert -90.0 <= coords.dec_deg <= 90.0


def test_unknown_target_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError):
        target_coordinates("Mars", datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc))


def test_horizontal_coordinates_are_in_expected_ranges() -> None:
    alt_deg, az_deg = horizontal_coordinates(
        ra_deg=83.6331,
        dec_deg=22.0145,
        lat_deg=-33.8688,
        lon_deg=151.2093,
        when=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert -90.0 <= alt_deg <= 90.0
    assert 0.0 <= az_deg < 360.0


def test_parse_device_args() -> None:
    assert parse_device_args("serial=1234, type=b200") == {
        "serial": "1234",
        "type": "b200",
    }
