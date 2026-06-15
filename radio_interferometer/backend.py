"""Process-isolated streaming and correlation backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from multiprocessing import Event, Process, Queue, get_context
from queue import Empty, Full
from time import monotonic
import traceback
from typing import Any

from .correlator import CorrelatorConfig, CorrelatorResult, FXCorrelator
from .sources import (
    B210ReadOverflow,
    B210SoapySource,
    ObservationConfig,
    SampleBlock,
    SampleSource,
    SimulatedInterferometerSource,
    fringe_stop_correction,
)

BACKEND_RESULT_INTERVAL_S = 0.08


@dataclass
class BackendUpdate:
    """Reduced backend update sent from the worker process to the GUI."""

    result: CorrelatorResult | None
    status: dict[str, Any]


class CorrelatorBackendProcess:
    """Own a separate process for SDR streaming and FX correlation."""

    def __init__(self, config: ObservationConfig, source_mode: str) -> None:
        self.config = config
        self.source_mode = source_mode
        context = get_context("spawn")
        self._result_queue: Queue = context.Queue(maxsize=2)
        self._command_queue: Queue = context.Queue(maxsize=8)
        self._stop_event: Event = context.Event()
        self._process = context.Process(
            target=backend_worker,
            args=(
                config,
                source_mode,
                self._result_queue,
                self._command_queue,
                self._stop_event,
            ),
            name="RadioInterferometerBackend",
            daemon=True,
        )
        self._last_status: dict[str, Any] = {}

    def start(self) -> None:
        self._process.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._send_command({"type": "stop"})
        self._process.join(timeout=3.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2.0)

    def reset_average(self) -> None:
        self._send_command({"type": "reset_average"})

    def update_config(self, config: ObservationConfig, source_mode: str) -> None:
        self.config = config
        self.source_mode = source_mode
        self._clear_results()
        self._send_command(
            {
                "type": "update_config",
                "config": config,
                "source_mode": source_mode,
            }
        )

    def poll_latest(self) -> BackendUpdate | None:
        latest: BackendUpdate | None = None
        while True:
            try:
                latest = self._result_queue.get_nowait()
            except Empty:
                break
        if latest is not None:
            self._last_status = latest.status
        return latest

    def status_snapshot(self) -> dict[str, Any]:
        return self._last_status

    def is_alive(self) -> bool:
        return self._process.is_alive()

    def exitcode(self) -> int | None:
        return self._process.exitcode

    def _send_command(self, command: dict[str, Any]) -> None:
        try:
            self._command_queue.put_nowait(command)
        except Full:
            try:
                self._command_queue.get_nowait()
            except Empty:
                pass
            self._command_queue.put_nowait(command)

    def _clear_results(self) -> None:
        while True:
            try:
                self._result_queue.get_nowait()
            except Empty:
                break


def backend_worker(
    config: ObservationConfig,
    source_mode: str,
    result_queue: Queue,
    command_queue: Queue,
    stop_event: Event,
) -> None:
    source: SampleSource | None = None
    correlator: FXCorrelator | None = None
    overflow_count = 0
    processed_count = 0
    dropped_results = 0
    last_emit = 0.0

    try:
        source = make_source(config, source_mode)
        correlator = make_correlator(config)
        source.start()
        stream_start_utc = datetime.now(timezone.utc)

        while not stop_event.is_set():
            config, source_mode, source, correlator, source_restarted = apply_pending_commands(
                command_queue,
                config,
                source_mode,
                source,
                correlator,
            )
            if source_restarted:
                stream_start_utc = datetime.now(timezone.utc)

            result: CorrelatorResult | None = None
            blocks_this_cycle = calculate_blocks_per_cycle(config, source_mode)
            for _ in range(blocks_this_cycle):
                if stop_event.is_set():
                    break
                try:
                    block = source.read(correlator.config.bins)
                except B210ReadOverflow:
                    overflow_count += 1
                    continue
                block_time = block_midpoint_time_utc(
                    stream_start_utc,
                    block,
                    correlator.config.bins,
                    config.sample_rate_hz,
                )
                correction = None
                if config.fringe_stop_mode == "Backend":
                    correction = fringe_stop_correction(
                        config,
                        correlator.frequency_offsets_unshifted_hz,
                        block_time,
                    )
                result = correlator.process(block.antenna_a, block.antenna_b, correction)
                processed_count += 1

            now = monotonic()
            if result is not None and now - last_emit >= BACKEND_RESULT_INTERVAL_S:
                status = build_status(
                    source,
                    correlator,
                    processed_count,
                    overflow_count,
                    dropped_results,
                )
                dropped_results += put_latest_result(result_queue, BackendUpdate(result, status))
                last_emit = now
    except StopBackend:
        pass
    except Exception as exc:
        put_latest_result(
            result_queue,
            BackendUpdate(
                None,
                {
                    "error": format_backend_exception(exc),
                    "error_type": exc.__class__.__name__,
                    "traceback": traceback.format_exc(),
                    "processed": processed_count,
                    "overflows": overflow_count,
                },
            ),
        )
    finally:
        if source is not None:
            try:
                source.stop()
            except Exception:
                pass


def apply_pending_commands(
    command_queue: Queue,
    config: ObservationConfig,
    source_mode: str,
    source: SampleSource,
    correlator: FXCorrelator,
) -> tuple[ObservationConfig, str, SampleSource, FXCorrelator, bool]:
    source_restarted = False
    while True:
        try:
            command = command_queue.get_nowait()
        except Empty:
            break

        command_type = command.get("type")
        if command_type == "stop":
            raise StopBackend
        if command_type == "reset_average":
            correlator.reset()
            continue
        if command_type != "update_config":
            continue

        new_config = command["config"]
        new_source_mode = command["source_mode"]
        if source_mode != new_source_mode or requires_source_restart(
            config, new_config, new_source_mode
        ):
            source.stop()
            source = make_source(new_config, new_source_mode)
            source.start()
            source_restarted = True
        else:
            source.update_config(new_config)

        if requires_correlator_rebuild(config, new_config):
            correlator = make_correlator(new_config)
        config = new_config
        source_mode = new_source_mode

    return config, source_mode, source, correlator, source_restarted


class StopBackend(Exception):
    """Internal signal used to exit the backend worker."""


def format_backend_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{exc.__class__.__name__}: {detail}"
    return exc.__class__.__name__


def make_source(config: ObservationConfig, source_mode: str) -> SampleSource:
    if source_mode == "B210 / SoapySDR":
        return B210SoapySource(config)
    return SimulatedInterferometerSource(config)


def make_correlator(config: ObservationConfig) -> FXCorrelator:
    return FXCorrelator(
        CorrelatorConfig(
            sample_rate_hz=config.sample_rate_hz,
            bins=config.bins,
            averaging_blocks=config.averaging_blocks,
        )
    )


def block_midpoint_time_utc(
    stream_start_utc: datetime,
    block: SampleBlock,
    bins: int,
    sample_rate_hz: float,
) -> datetime:
    midpoint_sample = block.sample_index + bins / 2.0
    return stream_start_utc + timedelta(seconds=midpoint_sample / sample_rate_hz)


def calculate_blocks_per_cycle(config: ObservationConfig, source_mode: str) -> int:
    if source_mode != "B210 / SoapySDR":
        return 1
    samples_per_update = config.sample_rate_hz * BACKEND_RESULT_INTERVAL_S
    blocks = ceil(samples_per_update / config.bins)
    return max(1, min(config.b210_process_blocks_per_update, blocks))


def build_status(
    source: SampleSource,
    correlator: FXCorrelator,
    processed_count: int,
    overflow_count: int,
    dropped_results: int,
) -> dict[str, Any]:
    status = source.status_snapshot()
    source_config = getattr(source, "config", None)
    status.update(
        {
            "processed": processed_count,
            "overflows": status.get("overflows", 0) + overflow_count,
            "averaging_fill": correlator.averaging_fill_fraction,
            "dropped_results": dropped_results,
            "active_bins": correlator.config.bins,
            "active_averaging_blocks": correlator.config.averaging_blocks,
            "active_bandwidth_mhz": correlator.config.sample_rate_hz / 1_000_000.0,
            "active_fringe_stop_mode": getattr(source_config, "fringe_stop_mode", "--"),
            "active_frequency_sideband": getattr(source_config, "frequency_sideband", "--"),
            "active_instrumental_delay_ns": getattr(source_config, "instrumental_delay_ns", "--"),
            "active_instrumental_phase_deg": getattr(source_config, "instrumental_phase_deg", "--"),
        }
    )
    return status


def put_latest_result(result_queue: Queue, update: BackendUpdate) -> int:
    dropped = 0
    while True:
        try:
            result_queue.put_nowait(update)
            return dropped
        except Full:
            try:
                result_queue.get_nowait()
                dropped += 1
            except Empty:
                return dropped


def requires_correlator_rebuild(old: ObservationConfig, new: ObservationConfig) -> bool:
    return (
        old.bandwidth_mhz != new.bandwidth_mhz
        or old.bins != new.bins
        or old.averaging_blocks != new.averaging_blocks
        or old.fringe_stop_mode != new.fringe_stop_mode
        or old.frequency_sideband != new.frequency_sideband
        or old.instrumental_delay_ns != new.instrumental_delay_ns
        or old.instrumental_phase_deg != new.instrumental_phase_deg
    )


def requires_source_restart(
    old: ObservationConfig,
    new: ObservationConfig,
    source_mode: str,
) -> bool:
    if source_mode != "B210 / SoapySDR":
        return False
    return (
        old.b210_device_args != new.b210_device_args
        or old.bandwidth_mhz != new.bandwidth_mhz
        or old.bins != new.bins
        or old.b210_stream_chunk_samples != new.b210_stream_chunk_samples
        or old.b210_queue_blocks != new.b210_queue_blocks
    )
