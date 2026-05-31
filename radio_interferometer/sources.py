"""Sample sources for simulated and hardware-backed interferometry streams."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import asin, atan2, cos, degrees, pi, radians, sin, sqrt
from threading import Event, Lock, Thread
from time import sleep

import numpy as np

SPEED_OF_LIGHT_M_S = 299_792_458.0
MOON_SEMIMAJOR_EARTH_RADII = 60.2666


@dataclass(frozen=True)
class ObservationConfig:
    observing_frequency_mhz: float
    intermediate_frequency_mhz: float
    ra_deg: float
    dec_deg: float
    observer_lat_deg: float
    observer_lon_deg: float
    bandwidth_mhz: float
    bins: int
    averaging_blocks: int = 32
    spectrum_smoothing_bins: int = 1
    baseline_east_m: float = 10.0
    baseline_north_m: float = 0.0
    baseline_up_m: float = 0.0
    b210_gain_db: float = 35.0
    b210_read_timeout_ms: int = 1000
    b210_stream_chunk_samples: int = 262144
    b210_queue_blocks: int = 32
    b210_process_blocks_per_update: int = 8
    b210_device_args: str = ""

    @property
    def sample_rate_hz(self) -> float:
        return self.bandwidth_mhz * 1_000_000.0

    @property
    def observing_frequency_hz(self) -> float:
        return self.observing_frequency_mhz * 1_000_000.0

    @property
    def intermediate_frequency_hz(self) -> float:
        return self.intermediate_frequency_mhz * 1_000_000.0


@dataclass(frozen=True)
class FringeModel:
    """Predicted geometric fringe terms for the configured source and baseline."""

    when_utc: datetime
    delay_s: float
    phase_rad: float
    phase_rate_rad_s: float


@dataclass(frozen=True)
class TargetCoordinates:
    """Right ascension and declination for a named sky target."""

    name: str
    ra_deg: float
    dec_deg: float


class SampleSource:
    """Common interface for two-channel complex sample sources."""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def read(self, sample_count: int) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def update_config(self, config: ObservationConfig) -> None:
        self.config = config

    def status_snapshot(self) -> dict[str, int]:
        return {}


class B210ReadOverflow(RuntimeError):
    """Raised when the B210 reports an RX overflow."""


class SimulatedInterferometerSource(SampleSource):
    """Deterministic two-antenna source with geometric delay and noise."""

    def __init__(self, config: ObservationConfig, seed: int = 20260516) -> None:
        self.config = config
        self._rng = np.random.default_rng(seed)
        self._sample_index = 0
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def update_config(self, config: ObservationConfig) -> None:
        self.config = config

    def read(self, sample_count: int) -> tuple[np.ndarray, np.ndarray]:
        if not self._running:
            raise RuntimeError("Sample source is not running.")

        rate = self.config.sample_rate_hz
        indices = np.arange(sample_count, dtype=np.float64) + self._sample_index
        self._sample_index += sample_count

        # Place a synthetic source at 11 percent of the visible passband.
        tone_hz = 0.11 * rate
        source = np.exp(2j * np.pi * tone_hz * indices / rate)

        delay_s = geometric_delay_seconds(self.config)
        phase = 2.0 * np.pi * self.config.observing_frequency_hz * delay_s
        antenna_a = source * np.exp(-1j * phase)
        antenna_b = source

        noise_scale = 0.45
        noise_a = noise_scale * (
            self._rng.normal(size=sample_count) + 1j * self._rng.normal(size=sample_count)
        )
        noise_b = noise_scale * (
            self._rng.normal(size=sample_count) + 1j * self._rng.normal(size=sample_count)
        )
        return (antenna_a + noise_a).astype(np.complex64), (antenna_b + noise_b).astype(np.complex64)


class B210SoapySource(SampleSource):
    """Two-channel Ettus B210 source using SoapySDR when available."""

    def __init__(self, config: ObservationConfig) -> None:
        self.config = config
        self._sdr = None
        self._rx_stream = None
        self._read_thread: Thread | None = None
        self._stop_event = Event()
        self._queue_ready = Event()
        self._queue_lock = Lock()
        self._queued_blocks: deque[tuple[np.ndarray, np.ndarray]] = deque()
        self._stream_error: Exception | None = None
        self._overflow_count = 0
        self._timeout_count = 0
        self._dropped_count = 0
        self._read_count = 0
        self._chunk_count = 0
        self._pending_a = np.empty(0, dtype=np.complex64)
        self._pending_b = np.empty(0, dtype=np.complex64)

    def start(self) -> None:
        try:
            import SoapySDR  # type: ignore
            from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_HAS_TIME, SOAPY_SDR_RX  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "SoapySDR is not installed. Install UHD/SoapySDR or use the simulator."
            ) from exc

        sdr = None
        rx_stream = None
        try:
            device_args = {"driver": "uhd", **parse_device_args(self.config.b210_device_args)}
            sdr = run_b210_step("open B210 device", lambda: SoapySDR.Device(device_args))
            sleep(0.25)

            for channel in (0, 1):
                run_b210_step(
                    f"set channel {channel} sample rate",
                    lambda channel=channel: sdr.setSampleRate(
                        SOAPY_SDR_RX, channel, self.config.sample_rate_hz
                    ),
                )
                run_b210_step(
                    f"set channel {channel} RF bandwidth",
                    lambda channel=channel: sdr.setBandwidth(
                        SOAPY_SDR_RX, channel, self.config.sample_rate_hz
                    ),
                )
                run_b210_step(
                    f"tune channel {channel}",
                    lambda channel=channel: sdr.setFrequency(
                        SOAPY_SDR_RX, channel, self.config.intermediate_frequency_hz
                    ),
                )
                run_b210_step(
                    f"disable channel {channel} AGC",
                    lambda channel=channel: sdr.setGainMode(SOAPY_SDR_RX, channel, False),
                )
                run_b210_step(
                    f"set channel {channel} gain",
                    lambda channel=channel: sdr.setGain(
                        SOAPY_SDR_RX, channel, self.config.b210_gain_db
                    ),
                )

            rx_stream = run_b210_step(
                "create two-channel RX stream",
                lambda: sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0, 1]),
            )
            activate_b210_stream_with_timed_start(sdr, rx_stream, SOAPY_SDR_HAS_TIME)
        except Exception:
            if sdr is not None and rx_stream is not None:
                try:
                    sdr.closeStream(rx_stream)
                except Exception:
                    pass
            raise

        self._sdr = sdr
        self._rx_stream = rx_stream
        self._stop_event.clear()
        self._queue_ready.clear()
        with self._queue_lock:
            self._queued_blocks.clear()
        self._stream_error = None
        self._overflow_count = 0
        self._timeout_count = 0
        self._dropped_count = 0
        self._read_count = 0
        self._chunk_count = 0
        self._pending_a = np.empty(0, dtype=np.complex64)
        self._pending_b = np.empty(0, dtype=np.complex64)
        self._read_thread = Thread(target=self._stream_worker, name="B210StreamReader", daemon=True)
        self._read_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._sdr is not None and self._rx_stream is not None:
            try:
                self._sdr.deactivateStream(self._rx_stream)
            except Exception:
                pass
        if self._read_thread is not None:
            self._read_thread.join(timeout=2.0)
        if self._sdr is not None and self._rx_stream is not None:
            try:
                self._sdr.closeStream(self._rx_stream)
            except Exception:
                pass
        self._sdr = None
        self._rx_stream = None
        self._read_thread = None
        self._queue_ready.clear()
        with self._queue_lock:
            self._queued_blocks.clear()
        self._pending_a = np.empty(0, dtype=np.complex64)
        self._pending_b = np.empty(0, dtype=np.complex64)

    def update_config(self, config: ObservationConfig) -> None:
        if self._sdr is None:
            self.config = config
            return

        try:
            from SoapySDR import SOAPY_SDR_RX  # type: ignore
        except ImportError:
            self.config = config
            return

        if config.bandwidth_mhz != self.config.bandwidth_mhz:
            for channel in (0, 1):
                run_b210_step(
                    f"set channel {channel} sample rate",
                    lambda channel=channel: self._sdr.setSampleRate(
                        SOAPY_SDR_RX, channel, config.sample_rate_hz
                    ),
                )
                run_b210_step(
                    f"set channel {channel} RF bandwidth",
                    lambda channel=channel: self._sdr.setBandwidth(
                        SOAPY_SDR_RX, channel, config.sample_rate_hz
                    ),
                )

        if config.intermediate_frequency_mhz != self.config.intermediate_frequency_mhz:
            for channel in (0, 1):
                run_b210_step(
                    f"tune channel {channel}",
                    lambda channel=channel: self._sdr.setFrequency(
                        SOAPY_SDR_RX, channel, config.intermediate_frequency_hz
                    ),
                )

        if config.b210_gain_db != self.config.b210_gain_db:
            for channel in (0, 1):
                run_b210_step(
                    f"set channel {channel} gain",
                    lambda channel=channel: self._sdr.setGain(
                        SOAPY_SDR_RX, channel, config.b210_gain_db
                    ),
                )

        self.config = config

    def read(self, sample_count: int) -> tuple[np.ndarray, np.ndarray]:
        if self._sdr is None or self._rx_stream is None or self._read_thread is None:
            raise RuntimeError("B210 source is not running.")

        timeout_s = max(self.config.b210_read_timeout_ms, 100) / 1000.0
        if not self._queue_ready.wait(timeout=timeout_s):
            if self._stream_error is not None:
                raise RuntimeError(f"B210 stream reader failed: {self._stream_error}")
            raise RuntimeError("B210 stream queue is empty.")

        with self._queue_lock:
            if self._queued_blocks:
                block = self._queued_blocks.popleft()
                if not self._queued_blocks:
                    self._queue_ready.clear()
                return block

        if self._stream_error is not None:
            raise RuntimeError(f"B210 stream reader failed: {self._stream_error}")
        raise RuntimeError("B210 stream queue is empty.")

    def status_snapshot(self) -> dict[str, int]:
        with self._queue_lock:
            queued = len(self._queued_blocks)
        return {
            "queued": queued,
            "overflows": self._overflow_count,
            "timeouts": self._timeout_count,
            "dropped": self._dropped_count,
            "reads": self._read_count,
            "chunks": self._chunk_count,
        }

    def _max_queued_blocks(self) -> int:
        return max(1, self.config.b210_queue_blocks)

    def _stream_worker(self) -> None:
        try:
            block_size = self.config.bins
            chunk_samples = max(block_size, self.config.b210_stream_chunk_samples)
            buffs = [
                np.empty(chunk_samples, dtype=np.complex64),
                np.empty(chunk_samples, dtype=np.complex64),
            ]

            while not self._stop_event.is_set():
                if self._sdr is None or self._rx_stream is None:
                    return

                timeout_us = max(self.config.b210_read_timeout_ms, 100) * 1000
                result = self._sdr.readStream(
                    self._rx_stream,
                    buffs,
                    chunk_samples,
                    timeoutUs=timeout_us,
                )

                if result.ret == -4:
                    self._overflow_count += 1
                    continue
                if result.ret == -1:
                    self._timeout_count += 1
                    continue
                if result.ret <= 0:
                    raise RuntimeError(f"B210 read failed with code {result.ret}.")

                self._chunk_count += 1
                self._queue_stream_chunk(buffs[0][: result.ret], buffs[1][: result.ret], block_size)
        except Exception as exc:
            self._stream_error = exc
            self._queue_ready.set()

    def _queue_stream_chunk(
        self,
        antenna_a: np.ndarray,
        antenna_b: np.ndarray,
        block_size: int,
    ) -> None:
        if self._pending_a.size:
            antenna_a = np.concatenate((self._pending_a, antenna_a))
            antenna_b = np.concatenate((self._pending_b, antenna_b))

        complete_blocks = antenna_a.size // block_size
        if complete_blocks == 0:
            self._pending_a = antenna_a.copy()
            self._pending_b = antenna_b.copy()
            return

        used_samples = complete_blocks * block_size
        max_queued_blocks = self._max_queued_blocks()
        with self._queue_lock:
            free_blocks = max_queued_blocks - len(self._queued_blocks)
            if free_blocks <= 0:
                self._dropped_count += complete_blocks
                self._pending_a = antenna_a[used_samples:].copy()
                self._pending_b = antenna_b[used_samples:].copy()
                return

            blocks_to_queue = min(complete_blocks, free_blocks)
            first_block = complete_blocks - blocks_to_queue
            self._dropped_count += complete_blocks - blocks_to_queue

            for block_index in range(first_block, complete_blocks):
                start = block_index * block_size
                stop = start + block_size
                self._queued_blocks.append(
                    (
                        antenna_a[start:stop].copy(),
                        antenna_b[start:stop].copy(),
                    )
                )
                self._read_count += 1
            self._queue_ready.set()

        self._pending_a = antenna_a[used_samples:].copy()
        self._pending_b = antenna_b[used_samples:].copy()


def parse_device_args(raw_args: str) -> dict[str, str]:
    """Parse comma-separated SoapySDR device args such as serial=123,type=b200."""

    parsed: dict[str, str] = {}
    for item in raw_args.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"B210 device arg must be key=value: {item}")
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def run_b210_step(step_name: str, action):
    """Run a Soapy/UHD call and preserve the failing setup step in the GUI error."""

    try:
        return action()
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise RuntimeError(f"B210 failed while trying to {step_name}: {detail}") from exc


def activate_b210_stream_with_timed_start(sdr, rx_stream, has_time_flag: int) -> None:
    """Start a two-channel B210 stream with a future timestamp for time alignment."""

    run_b210_step("reset B210 hardware time", lambda: sdr.setHardwareTime(0))
    start_time_ns = run_b210_step("read B210 hardware time", lambda: sdr.getHardwareTime())
    start_time_ns += 100_000_000
    run_b210_step(
        "activate time-aligned RX stream",
        lambda: sdr.activateStream(rx_stream, flags=has_time_flag, timeNs=start_time_ns),
    )


def target_coordinates(
    target_name: str,
    when: datetime | None = None,
    observer_lat_deg: float | None = None,
    observer_lon_deg: float | None = None,
) -> TargetCoordinates:
    """Return approximate RA/DEC for supported bright calibrators."""

    if when is None:
        when = datetime.now(timezone.utc)
    target_name = target_name.strip().lower()
    if target_name == "sun":
        return sun_coordinates(when)
    if target_name == "moon":
        if observer_lat_deg is not None and observer_lon_deg is not None:
            return topocentric_moon_coordinates(when, observer_lat_deg, observer_lon_deg)
        return moon_coordinates(when)
    raise ValueError(f"Unsupported target source: {target_name}")


def sun_coordinates(when: datetime) -> TargetCoordinates:
    """Return low-precision apparent Sun RA/DEC in decimal degrees."""

    jd = julian_date(when)
    n = jd - 2451545.0
    mean_longitude = normalize_degrees(280.460 + 0.9856474 * n)
    mean_anomaly = radians(normalize_degrees(357.528 + 0.9856003 * n))
    ecliptic_lon = normalize_degrees(
        mean_longitude + 1.915 * sin(mean_anomaly) + 0.020 * sin(2.0 * mean_anomaly)
    )
    ra_deg, dec_deg = ecliptic_to_equatorial_degrees(ecliptic_lon, 0.0, mean_obliquity_degrees(jd))
    return TargetCoordinates("Sun", ra_deg, dec_deg)


def moon_coordinates(when: datetime) -> TargetCoordinates:
    """Return low-precision geocentric Moon RA/DEC in decimal degrees."""

    x_eq, y_eq, z_eq = moon_equatorial_vector_earth_radii(when)
    ra_deg, dec_deg = equatorial_vector_to_ra_dec_degrees(x_eq, y_eq, z_eq)
    return TargetCoordinates("Moon", ra_deg, dec_deg)


def topocentric_moon_coordinates(
    when: datetime,
    observer_lat_deg: float,
    observer_lon_deg: float,
) -> TargetCoordinates:
    """Return low-precision topocentric Moon RA/DEC for an observer site."""

    moon_x, moon_y, moon_z = moon_equatorial_vector_earth_radii(when)
    sidereal = radians(local_sidereal_time_degrees(when, observer_lon_deg))
    lat = radians(observer_lat_deg)
    observer_x = cos(lat) * cos(sidereal)
    observer_y = cos(lat) * sin(sidereal)
    observer_z = sin(lat)
    ra_deg, dec_deg = equatorial_vector_to_ra_dec_degrees(
        moon_x - observer_x,
        moon_y - observer_y,
        moon_z - observer_z,
    )
    return TargetCoordinates("Moon", ra_deg, dec_deg)


def moon_equatorial_vector_earth_radii(when: datetime) -> tuple[float, float, float]:
    """Return approximate geocentric Moon vector in equatorial Earth radii."""

    jd = julian_date(when)
    d = jd - 2451543.5
    ascending_node_deg = normalize_degrees(125.1228 - 0.0529538083 * d)
    inclination_deg = 5.1454
    arg_perigee_deg = normalize_degrees(318.0634 + 0.1643573223 * d)
    eccentricity = 0.054900
    mean_anomaly_deg = normalize_degrees(115.3654 + 13.0649929509 * d)
    mean_anomaly = radians(mean_anomaly_deg)

    eccentric_anomaly_deg = mean_anomaly_deg + degrees(
        eccentricity * sin(mean_anomaly) * (1.0 + eccentricity * cos(mean_anomaly))
    )
    eccentric_anomaly = radians(eccentric_anomaly_deg)
    xv = MOON_SEMIMAJOR_EARTH_RADII * (cos(eccentric_anomaly) - eccentricity)
    yv = (
        MOON_SEMIMAJOR_EARTH_RADII
        * sqrt(1.0 - eccentricity * eccentricity)
        * sin(eccentric_anomaly)
    )
    true_anomaly = atan2(yv, xv)
    radius = sqrt(xv * xv + yv * yv)

    ascending_node = radians(ascending_node_deg)
    inclination = radians(inclination_deg)
    longitude_arg = true_anomaly + radians(arg_perigee_deg)
    xh = radius * (
        cos(ascending_node) * cos(longitude_arg)
        - sin(ascending_node) * sin(longitude_arg) * cos(inclination)
    )
    yh = radius * (
        sin(ascending_node) * cos(longitude_arg)
        + cos(ascending_node) * sin(longitude_arg) * cos(inclination)
    )
    zh = radius * sin(longitude_arg) * sin(inclination)

    ecliptic_lon_deg = normalize_degrees(degrees(atan2(yh, xh)))
    ecliptic_lat_deg = degrees(atan2(zh, sqrt(xh * xh + yh * yh)))
    ecliptic_lon_deg, ecliptic_lat_deg, radius = apply_lunar_perturbations(
        ecliptic_lon_deg,
        ecliptic_lat_deg,
        radius,
        ascending_node_deg,
        arg_perigee_deg,
        mean_anomaly_deg,
        d,
    )
    lon = radians(ecliptic_lon_deg)
    lat = radians(ecliptic_lat_deg)
    x_ecl = radius * cos(lon) * cos(lat)
    y_ecl = radius * sin(lon) * cos(lat)
    z_ecl = radius * sin(lat)

    obliquity = radians(mean_obliquity_degrees(jd))
    x_eq = x_ecl
    y_eq = y_ecl * cos(obliquity) - z_ecl * sin(obliquity)
    z_eq = y_ecl * sin(obliquity) + z_ecl * cos(obliquity)
    return x_eq, y_eq, z_eq


def apply_lunar_perturbations(
    longitude_deg: float,
    latitude_deg: float,
    distance_earth_radii: float,
    ascending_node_deg: float,
    arg_perigee_deg: float,
    moon_mean_anomaly_deg: float,
    days_since_epoch: float,
) -> tuple[float, float, float]:
    """Apply the largest lunar perturbation terms to lon/lat/range."""

    sun_mean_anomaly_deg = normalize_degrees(356.0470 + 0.9856002585 * days_since_epoch)
    sun_perigee_deg = normalize_degrees(282.9404 + 0.0000470935 * days_since_epoch)
    sun_mean_longitude_deg = normalize_degrees(sun_mean_anomaly_deg + sun_perigee_deg)
    moon_mean_longitude_deg = normalize_degrees(
        ascending_node_deg + arg_perigee_deg + moon_mean_anomaly_deg
    )
    elongation_deg = moon_mean_longitude_deg - sun_mean_longitude_deg
    argument_latitude_deg = moon_mean_longitude_deg - ascending_node_deg

    mm = moon_mean_anomaly_deg
    ms = sun_mean_anomaly_deg
    d = elongation_deg
    f = argument_latitude_deg
    longitude_deg += (
        -1.274 * sin(radians(mm - 2.0 * d))
        + 0.658 * sin(radians(2.0 * d))
        - 0.186 * sin(radians(ms))
        - 0.059 * sin(radians(2.0 * mm - 2.0 * d))
        - 0.057 * sin(radians(mm - 2.0 * d + ms))
        + 0.053 * sin(radians(mm + 2.0 * d))
        + 0.046 * sin(radians(2.0 * d - ms))
        + 0.041 * sin(radians(mm - ms))
        - 0.035 * sin(radians(d))
        - 0.031 * sin(radians(mm + ms))
        - 0.015 * sin(radians(2.0 * f - 2.0 * d))
        + 0.011 * sin(radians(mm - 4.0 * d))
    )
    latitude_deg += (
        -0.173 * sin(radians(f - 2.0 * d))
        - 0.055 * sin(radians(mm - f - 2.0 * d))
        - 0.046 * sin(radians(mm + f - 2.0 * d))
        + 0.033 * sin(radians(f + 2.0 * d))
        + 0.017 * sin(radians(2.0 * mm + f))
    )
    distance_earth_radii += (
        -0.58 * cos(radians(mm - 2.0 * d))
        - 0.46 * cos(radians(2.0 * d))
    )
    return normalize_degrees(longitude_deg), latitude_deg, distance_earth_radii


def geometric_delay_seconds(config: ObservationConfig, when: datetime | None = None) -> float:
    """Return geometric delay for an east/north/up baseline."""

    if when is None:
        when = datetime.now(timezone.utc)

    alt_deg, az_deg = horizontal_coordinates(
        config.ra_deg,
        config.dec_deg,
        config.observer_lat_deg,
        config.observer_lon_deg,
        when,
    )
    alt = radians(alt_deg)
    az = radians(az_deg)

    east = cos(alt) * sin(az)
    north = cos(alt) * cos(az)
    up = sin(alt)
    projected_m = (
        config.baseline_east_m * east
        + config.baseline_north_m * north
        + config.baseline_up_m * up
    )
    return projected_m / SPEED_OF_LIGHT_M_S


def fringe_model(
    config: ObservationConfig,
    when: datetime | None = None,
    rate_step_s: float = 1.0,
) -> FringeModel:
    """Return the current model delay, phase, and fringe rate for display."""

    if when is None:
        when = datetime.now(timezone.utc)
    if rate_step_s <= 0:
        raise ValueError("Fringe model rate step must be positive.")

    delay_s = geometric_delay_seconds(config, when)
    future_delay_s = geometric_delay_seconds(
        config,
        when + timedelta(seconds=rate_step_s),
    )
    phase_rad = 2.0 * pi * config.observing_frequency_hz * delay_s
    phase_rate_rad_s = (
        2.0
        * pi
        * config.observing_frequency_hz
        * (future_delay_s - delay_s)
        / rate_step_s
    )
    return FringeModel(
        when_utc=when,
        delay_s=delay_s,
        phase_rad=phase_rad,
        phase_rate_rad_s=phase_rate_rad_s,
    )


def horizontal_coordinates(
    ra_deg: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
    when: datetime,
) -> tuple[float, float]:
    """Convert RA/DEC to approximate altitude and azimuth in decimal degrees."""

    lst_deg = local_sidereal_time_degrees(when, lon_deg)
    hour_angle = radians((lst_deg - ra_deg + 540.0) % 360.0 - 180.0)
    dec = radians(dec_deg)
    lat = radians(lat_deg)

    sin_alt = sin(dec) * sin(lat) + cos(dec) * cos(lat) * cos(hour_angle)
    alt = asin(np.clip(sin_alt, -1.0, 1.0))
    az = atan2(
        -sin(hour_angle) * cos(dec),
        sin(dec) * cos(lat) - cos(dec) * sin(lat) * cos(hour_angle),
    )
    return degrees(alt), (degrees(az) + 360.0) % 360.0


def local_sidereal_time_degrees(when: datetime, lon_deg: float) -> float:
    """Approximate local apparent sidereal time for GUI/simulation use."""

    jd = julian_date(when)
    d = jd - 2451545.0
    gmst = 280.46061837 + 360.98564736629 * d
    return (gmst + lon_deg) % 360.0


def julian_date(when: datetime) -> float:
    """Return Julian Date for a timezone-aware or naive UTC datetime."""

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    year = when.year
    month = when.month
    day = when.day
    if month <= 2:
        year -= 1
        month += 12

    a = year // 100
    b = 2 - a + a // 4
    day_fraction = (
        when.hour + when.minute / 60.0 + (when.second + when.microsecond / 1_000_000.0) / 3600.0
    ) / 24.0
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + day_fraction
        + b
        - 1524.5
    )


def mean_obliquity_degrees(jd: float) -> float:
    return 23.439291 - 0.0000004 * (jd - 2451545.0)


def ecliptic_to_equatorial_degrees(
    ecliptic_lon_deg: float,
    ecliptic_lat_deg: float,
    obliquity_deg: float,
) -> tuple[float, float]:
    lon = radians(ecliptic_lon_deg)
    lat = radians(ecliptic_lat_deg)
    obliquity = radians(obliquity_deg)
    x = cos(lon) * cos(lat)
    y = sin(lon) * cos(lat) * cos(obliquity) - sin(lat) * sin(obliquity)
    z = sin(lon) * cos(lat) * sin(obliquity) + sin(lat) * cos(obliquity)
    return normalize_degrees(degrees(atan2(y, x))), degrees(asin(np.clip(z, -1.0, 1.0)))


def equatorial_vector_to_ra_dec_degrees(x: float, y: float, z: float) -> tuple[float, float]:
    return normalize_degrees(degrees(atan2(y, x))), degrees(atan2(z, sqrt(x * x + y * y)))


def normalize_degrees(value: float) -> float:
    return value % 360.0
