from radio_interferometer.backend import (
    build_status,
    make_correlator,
    requires_correlator_rebuild,
    requires_source_restart,
)
from radio_interferometer.sources import ObservationConfig


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


class EmptyStatusSource:
    def status_snapshot(self):
        return {}


def test_fx_bins_and_smoothing_rebuild_correlator() -> None:
    config = make_config()

    assert requires_correlator_rebuild(config, make_config(bins=1024))
    assert requires_correlator_rebuild(config, make_config(averaging_blocks=128))
    assert requires_correlator_rebuild(config, make_config(fringe_stop_mode="Backend"))
    assert requires_correlator_rebuild(config, make_config(frequency_sideband="LO + IF"))


def test_b210_fx_bins_restart_source() -> None:
    config = make_config()

    assert requires_source_restart(config, make_config(bins=1024), "B210 / SoapySDR")
    assert not requires_source_restart(config, make_config(bins=1024), "Simulator")


def test_backend_status_reports_active_correlator_config() -> None:
    config = make_config(bins=1024, averaging_blocks=128)
    correlator = make_correlator(config)

    status = build_status(EmptyStatusSource(), correlator, 1, 0, 0)

    assert status["active_bins"] == 1024
    assert status["active_averaging_blocks"] == 128
