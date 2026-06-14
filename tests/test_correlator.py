import numpy as np
import pytest

from radio_interferometer.correlator import (
    CorrelatorConfig,
    FXCorrelator,
    continuum_channel_mask,
    estimate_broadband_continuum_snr,
    estimate_peak_snr,
)
from radio_interferometer.sources import (
    ObservationConfig,
    fringe_stop_phasor,
    instrumental_calibration_phasor,
    sky_frequencies_hz,
)


def test_fx_correlator_returns_requested_bin_count() -> None:
    bins = 128
    correlator = FXCorrelator(CorrelatorConfig(sample_rate_hz=1_000_000.0, bins=bins))
    indices = np.arange(bins)
    signal = np.exp(2j * np.pi * 0.125 * indices).astype(np.complex64)

    result = correlator.process(signal, signal)

    assert result.cross_spectrum.shape == (bins,)
    assert result.raw_cross_spectrum.shape == (bins,)
    assert result.interferogram.shape == (bins,)
    assert result.east_auto_spectrum.shape == (bins,)
    assert result.west_auto_spectrum.shape == (bins,)
    assert result.east_autocorrelation.shape == (bins,)
    assert result.west_autocorrelation.shape == (bins,)
    assert result.frequency_offsets_hz.shape == (bins,)
    assert result.lag_bins[0] == -bins // 2
    assert result.lag_bins[-1] == bins // 2 - 1


def test_fx_correlator_pads_short_blocks() -> None:
    correlator = FXCorrelator(CorrelatorConfig(sample_rate_hz=2_000_000.0, bins=64))
    short_block = np.ones(16, dtype=np.complex64)

    result = correlator.process(short_block, short_block)

    assert result.cross_spectrum.shape == (64,)
    assert np.all(np.isfinite(result.cross_spectrum))


def test_fx_correlator_rejects_invalid_config() -> None:
    try:
        FXCorrelator(CorrelatorConfig(sample_rate_hz=0.0, bins=64))
    except ValueError as exc:
        assert "Sample rate" in str(exc)
    else:
        raise AssertionError("Expected invalid sample rate to raise ValueError")


def test_fx_correlator_uses_averaging_blocks_for_alpha() -> None:
    config = CorrelatorConfig(sample_rate_hz=1_000_000.0, bins=64, averaging_blocks=16)

    assert config.integration_alpha == 1.0 / 16.0


def test_estimate_peak_snr_excludes_peak_neighborhood() -> None:
    spectrum = np.ones(16)
    spectrum[8] = 10.0
    spectrum[7] = 4.0
    spectrum[9] = 5.0

    result = estimate_peak_snr(spectrum, exclusion_bins=1)

    assert result.index == 8
    assert result.peak_value == 10.0
    assert result.noise_floor == 1.0
    assert result.snr == 10.0


def test_continuum_channel_mask_excludes_edges_and_rfi() -> None:
    spectrum = np.ones(16, dtype=np.complex128)
    spectrum[8] = 100.0

    mask = continuum_channel_mask(spectrum, edge_percent=12.5, rfi_sigma=3.0)

    assert not np.any(mask[:2])
    assert not np.any(mask[-2:])
    assert not mask[8]
    assert np.count_nonzero(mask) == 11


def test_estimate_broadband_continuum_snr_uses_selected_bins() -> None:
    bins = 64
    offsets = np.fft.fftshift(np.fft.fftfreq(bins, d=1.0 / 1_000_000.0))
    cross = np.ones(bins, dtype=np.complex128)
    cross += 0.01 * np.exp(2j * np.pi * np.arange(bins) / bins)

    result = estimate_broadband_continuum_snr(
        cross,
        offsets,
        lag_bin=0.0,
        sample_rate_hz=1_000_000.0,
        edge_percent=10.0,
    )

    assert result.bins_used == 52
    assert result.amplitude > 0.9
    assert result.snr > 10.0


def test_broadband_visibility_keeps_east_conj_west_phase_sign() -> None:
    bins = 128
    sample_rate_hz = 1_000_000.0
    observing_frequency_hz = 4_801_234_567.0
    delay_s = 3.25 / sample_rate_hz
    offsets = np.fft.fftshift(np.fft.fftfreq(bins, d=1.0 / sample_rate_hz))
    model_phase = 2.0 * np.pi * observing_frequency_hz * delay_s
    cross = np.exp(-1j * (model_phase + 2.0 * np.pi * offsets * delay_s))

    result = estimate_broadband_continuum_snr(
        cross,
        offsets,
        lag_bin=delay_s * sample_rate_hz,
        sample_rate_hz=sample_rate_hz,
        edge_percent=0.0,
    )

    assert abs(np.angle(result.visibility * np.exp(1j * model_phase))) < 1e-12


def test_sky_frequencies_respect_lnb_sideband() -> None:
    offsets = np.array([-1_000.0, 0.0, 1_000.0])
    low_side = make_config(frequency_sideband="LO - IF")
    high_side = make_config(frequency_sideband="LO + IF")

    assert np.allclose(
        sky_frequencies_hz(low_side, offsets),
        low_side.observing_frequency_hz - offsets,
    )
    assert np.allclose(
        sky_frequencies_hz(high_side, offsets),
        high_side.observing_frequency_hz + offsets,
    )


def test_fringe_stop_phasor_removes_east_conj_west_band_phase() -> None:
    bins = 128
    sample_rate_hz = 1_000_000.0
    delay_s = 3.25 / sample_rate_hz
    config = make_config(
        bandwidth_mhz=sample_rate_hz / 1_000_000.0,
        frequency_sideband="LO - IF",
    )
    offsets = np.fft.fftfreq(bins, d=1.0 / sample_rate_hz)
    sky_freqs = sky_frequencies_hz(config, offsets)
    raw_cross = np.exp(-2j * np.pi * sky_freqs * delay_s)

    corrected = raw_cross * fringe_stop_phasor(config, offsets, delay_s)

    assert np.max(np.abs(corrected - 1.0)) < 1e-12


def test_instrumental_calibration_applies_delay_slope_and_phase_offset() -> None:
    offsets = np.array([-1_000_000.0, 0.0, 1_000_000.0])
    config = make_config(
        frequency_sideband="LO + IF",
        instrumental_delay_ns=1.0,
        instrumental_phase_deg=30.0,
    )

    phasor = instrumental_calibration_phasor(config, offsets)
    phase = np.unwrap(np.angle(phasor))

    assert phase[1] == pytest.approx(np.radians(30.0), abs=1e-12)
    assert phase[2] - phase[0] == pytest.approx(2.0 * np.pi * 2_000_000.0e-9)


def test_instrumental_delay_respects_low_sideband_inversion() -> None:
    offsets = np.array([-1_000_000.0, 1_000_000.0])
    high_side = make_config(frequency_sideband="LO + IF", instrumental_delay_ns=1.0)
    low_side = make_config(frequency_sideband="LO - IF", instrumental_delay_ns=1.0)

    high_phase = np.unwrap(np.angle(instrumental_calibration_phasor(high_side, offsets)))
    low_phase = np.unwrap(np.angle(instrumental_calibration_phasor(low_side, offsets)))

    assert high_phase[1] - high_phase[0] == pytest.approx(
        -(low_phase[1] - low_phase[0])
    )


def test_fx_correlator_applies_cross_correction_before_averaging() -> None:
    bins = 64
    correlator = FXCorrelator(CorrelatorConfig(sample_rate_hz=1_000_000.0, bins=bins))
    signal = np.ones(bins, dtype=np.complex64)
    correction = np.full(bins, 1j, dtype=np.complex128)

    result = correlator.process(signal, signal, cross_correction=correction)

    peak = int(np.argmax(np.abs(result.raw_cross_spectrum)))
    assert np.angle(result.cross_spectrum[peak] / result.raw_cross_spectrum[peak]) == (
        pytest.approx(np.pi / 2.0)
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
