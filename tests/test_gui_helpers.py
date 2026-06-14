from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from radio_interferometer.gui import (
    apply_display_fringe_stop,
    apply_target_display_rounding,
    estimate_phase_rate_deg_s,
    format_ra_hours,
    format_fringe_model_status,
    format_runtime_status_text,
    format_status_text,
    format_stopped_phase_label,
    format_visibility_status,
    fringe_reset_signature,
    parse_ra_hours_text,
    resolve_automatic_target_coordinates,
    runtime_configs_match,
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


def test_readout_formatters_keep_stable_line_counts() -> None:
    assert len(format_status_text("Ready").splitlines()) == 4
    assert len(format_runtime_status_text("Averaging stable.", {}).splitlines()) == 4
    assert len(format_visibility_status(None).splitlines()) == 4
    assert len(format_fringe_model_status(None, None, None).splitlines()) == 6

    b210_status = {
        "queued": 2,
        "chunks": 123,
        "dropped": 0,
        "reads": 4567,
        "processed": 4560,
        "active_bins": 2048,
        "active_averaging_blocks": 8196,
        "dropped_results": 0,
        "overflows": 0,
        "timeouts": 0,
    }
    runtime_lines = format_runtime_status_text("Averaging stable.", b210_status).splitlines()
    assert len(runtime_lines) == 4
    assert runtime_lines[1].startswith("B210 q 2")

    continuum = SimpleNamespace(
        visibility=1.0 + 2.0j,
        amplitude=2.236,
        phase_rad=1.107,
        snr=12.3,
    )
    model = SimpleNamespace(
        when_utc=datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc),
        delay_s=1e-9,
        phase_rad=0.5,
        phase_rate_rad_s=0.01,
    )
    assert len(format_visibility_status(continuum).splitlines()) == 4
    fringe_lines = format_fringe_model_status(
        model,
        continuum.visibility,
        1.0j,
        0.15,
    ).splitlines()
    assert len(fringe_lines) == 6
    assert fringe_lines[-1] == "Stopped phase +90.0 deg, rate +0.150 deg/s"


def test_display_fringe_stop_uses_east_conj_west_sign() -> None:
    model = SimpleNamespace(phase_rad=0.75)
    raw_visibility = np.exp(-1j * model.phase_rad)

    stopped = apply_display_fringe_stop(raw_visibility, model)

    assert np.angle(stopped) == pytest.approx(0.0, abs=1e-12)


def test_stopped_phase_rate_estimator_handles_unwrapped_ramp() -> None:
    times = np.linspace(0.0, 120.0, 25)
    phase_deg = -170.0 + 0.15 * times
    wrapped_phase_rad = np.radians(((phase_deg + 180.0) % 360.0) - 180.0)

    rate = estimate_phase_rate_deg_s(times, wrapped_phase_rad)

    assert rate == pytest.approx(0.15, abs=1e-12)
    assert format_stopped_phase_label(rate) == "Stopped phase (+0.150 deg/s)"
    assert format_stopped_phase_label(None) == "Stopped phase (-- deg/s)"


def test_automatic_target_coordinates_keep_full_precision_for_config() -> None:
    raw_inputs = {
        "observer_lat_deg": "-32.9283",
        "observer_lon_deg": "151.7817",
        "ra_hours": "00:00:00.0",
        "dec_deg": "0.0",
    }
    coords = resolve_automatic_target_coordinates(
        "Sun",
        raw_inputs,
        datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )

    display_inputs = apply_target_display_rounding(raw_inputs, coords)
    display_ra_deg = parse_ra_hours_text(display_inputs["ra_hours"]) * 15.0
    display_dec_deg = float(display_inputs["dec_deg"])

    assert coords is not None
    assert display_inputs["ra_hours"] == format_ra_hours(coords.ra_deg / 15.0)
    assert display_dec_deg == pytest.approx(coords.dec_deg, abs=0.00005)
    assert display_ra_deg != pytest.approx(coords.ra_deg, abs=1e-10)


def test_runtime_config_match_ignores_automatic_target_ephemeris_drift() -> None:
    base = make_config(ra_deg=70.0, dec_deg=22.0)
    drifted = make_config(ra_deg=70.01, dec_deg=22.01)

    assert runtime_configs_match(drifted, base, "Sun")
    assert not runtime_configs_match(drifted, base, "Manual RA/DEC")
    assert not runtime_configs_match(make_config(bandwidth_mhz=31.0), base, "Sun")


def test_fringe_reset_signature_detects_manual_target_change() -> None:
    base = make_config()

    assert fringe_reset_signature(base, "Manual RA/DEC", "B210 / SoapySDR") != (
        fringe_reset_signature(make_config(ra_deg=242.38), "Manual RA/DEC", "B210 / SoapySDR")
    )
    assert fringe_reset_signature(base, "Manual RA/DEC", "B210 / SoapySDR") != (
        fringe_reset_signature(make_config(dec_deg=-25.40), "Manual RA/DEC", "B210 / SoapySDR")
    )
    assert fringe_reset_signature(base, "Manual RA/DEC", "B210 / SoapySDR") == (
        fringe_reset_signature(make_config(bins=1024), "Manual RA/DEC", "B210 / SoapySDR")
    )


def test_fringe_reset_signature_ignores_automatic_moon_ephemeris_drift() -> None:
    base = make_config(ra_deg=242.38, dec_deg=-25.40)
    drifted = make_config(ra_deg=242.39, dec_deg=-25.41)

    assert fringe_reset_signature(base, "Moon", "B210 / SoapySDR") == (
        fringe_reset_signature(drifted, "Moon", "B210 / SoapySDR")
    )
    assert fringe_reset_signature(base, "Moon", "B210 / SoapySDR") != (
        fringe_reset_signature(drifted, "Manual RA/DEC", "B210 / SoapySDR")
    )
    assert fringe_reset_signature(base, "Moon", "B210 / SoapySDR") != (
        fringe_reset_signature(
            make_config(observer_lat_deg=-32.0),
            "Moon",
            "B210 / SoapySDR",
        )
    )


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
