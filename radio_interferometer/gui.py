"""Tkinter GUI for the radio interferometry FX correlator."""

from __future__ import annotations

from collections import deque
import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from time import monotonic

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator
from matplotlib.widgets import Button, Slider, TextBox

from . import __version__
from .backend import CorrelatorBackendProcess
from .correlator import (
    estimate_broadband_continuum_snr,
    estimate_peak_snr,
)
from .sources import ObservationConfig, fringe_model, sky_frequencies_hz, target_coordinates

GUI_REFRESH_MS = 80
AVERAGING_DRAW_REFRESH_MS = 500
SETTINGS_PATH = Path.home() / ".radio_interferometer_iota_settings.json"
TARGET_SOURCE_OPTIONS = ("Manual RA/DEC", "Sun", "Moon")
MANUAL_TARGET_SOURCE = TARGET_SOURCE_OPTIONS[0]
FRINGE_STOP_OPTIONS = ("Off", "Display", "Backend")
FREQUENCY_SIDEBAND_OPTIONS = ("LO - IF", "LO + IF")
PLOT_CONTROL_WIDTH = 0.055
PLOT_CONTROL_HEIGHT = 0.026
PLOT_CONTROL_GAP = 0.006
PLOT_CONTROL_FONT_SIZE = 8
GRID_MAJOR_COLOR = "#d0d0d0"
GRID_MINOR_COLOR = "#e8e8e8"
STATUS_LINE_COUNT = 4
STATUS_WRAP_LENGTH = 300
FRINGE_WINDOW_MINUTES_MIN = 10.0
FRINGE_WINDOW_MINUTES_MAX = 180.0
FRINGE_WINDOW_MINUTES_DEFAULT = 10.0
FRINGE_HISTORY_MAX_SECONDS = FRINGE_WINDOW_MINUTES_MAX * 60.0
FRINGE_DISPLAY_MAX_POINTS = 5000

FIELD_DEFAULTS = [
    ("observing_frequency_mhz", "Observing freq (MHz)", "4800"),
    ("lnb_lo_frequency_mhz", "LNB LO freq (MHz)", "5950"),
    ("intermediate_frequency_mhz", "B210 tune IF (MHz)", "1150"),
    ("ra_hours", "Target RA (HH:MM:SS)", "05:34:31.9"),
    ("dec_deg", "Target DEC (deg)", "22.0145"),
    ("observer_lat_deg", "Observer lat (deg)", "-33.8688"),
    ("observer_lon_deg", "Observer lon (deg)", "151.2093"),
    ("bandwidth_mhz", "Bandwidth (MHz)", "30.72"),
    ("bins", "FX bins", "2048"),
    ("averaging_blocks", "X-corr smoothing blocks", "8196"),
    ("spectrum_smoothing_bins", "Spectrum smoothing bins", "1"),
    ("baseline_east_m", "Baseline east (m)", "6.0"),
    ("baseline_north_m", "Baseline north (m)", "0.0"),
    ("baseline_up_m", "Baseline up (m)", "0.0"),
    ("instrumental_delay_ns", "Instrument delay (ns)", "0.0"),
    ("instrumental_phase_deg", "Instrument phase (deg)", "0.0"),
    ("b210_gain_db", "B210 gain (dB)", "70.0"),
    ("b210_read_timeout_ms", "B210 read timeout (ms)", "1000"),
    ("b210_stream_chunk_samples", "B210 stream chunk samples", "262144"),
    ("b210_queue_blocks", "B210 queued FFT blocks", "32"),
    ("b210_process_blocks_per_update", "B210 FFT blocks/update", "8"),
    ("b210_device_args", "B210 device args", "num_recv_frames=256"),
]

PLOT_SCALE_DEFAULTS = [
    ("interferogram_y_min", "Interferogram Y min", "0.0"),
    ("interferogram_y_max", "Interferogram Y max", "1.0"),
    ("spectrum_y_min", "Spectrum Y min", "0.0"),
    ("spectrum_y_max", "Spectrum Y max", "1.0"),
    ("east_autocorr_y_min", "East autocorr Y min", "0.0"),
    ("east_autocorr_y_max", "East autocorr Y max", "1.0"),
    ("west_autocorr_y_min", "West autocorr Y min", "0.0"),
    ("west_autocorr_y_max", "West autocorr Y max", "1.0"),
    ("east_auto_spectrum_y_min", "East spectrum Y min", "0.0"),
    ("east_auto_spectrum_y_max", "East spectrum Y max", "1.0"),
    ("west_auto_spectrum_y_min", "West spectrum Y min", "0.0"),
    ("west_auto_spectrum_y_max", "West spectrum Y max", "1.0"),
    ("fringe_iq_y_min", "Fringe I/Q Y min", "-1.0"),
    ("fringe_iq_y_max", "Fringe I/Q Y max", "1.0"),
]

CONTINUUM_FIELD_DEFAULTS = [
    ("continuum_edge_percent", "Continuum edge exclude (%)", "10.0"),
    ("continuum_rfi_sigma", "Continuum RFI sigma (0 off)", "0.0"),
]

VISIBILITY_FIELD_DEFAULTS = [
    ("visibility_output_path", "Visibility CSV path", "visibilities.csv"),
    ("visibility_record_interval_s", "Visibility record interval (s)", "1.0"),
]

VISIBILITY_CSV_FIELDS = [
    "timestamp_utc",
    "observing_frequency_mhz",
    "intermediate_frequency_mhz",
    "bandwidth_mhz",
    "bins",
    "averaging_blocks",
    "baseline_east_m",
    "baseline_north_m",
    "baseline_up_m",
    "source_ra_deg",
    "source_dec_deg",
    "observer_lat_deg",
    "observer_lon_deg",
    "fringe_stop_mode",
    "frequency_sideband",
    "instrumental_delay_ns",
    "instrumental_phase_deg",
    "lag_bin",
    "visibility_real",
    "visibility_imag",
    "visibility_amp",
    "visibility_phase_rad",
    "visibility_snr",
    "visibility_noise_floor",
    "clean_bins",
    "edge_bins_excluded",
]

DEFAULT_SETTINGS = {
    "source_mode": "Simulator",
    "target_mode": MANUAL_TARGET_SOURCE,
    "fringe_stop_mode": "Backend",
    "frequency_sideband": "LO - IF",
    "spectrum_plot_mode": "on",
    "phase_plot_mode": "off",
    "interferogram_autoscale": "on",
    "spectrum_autoscale": "on",
    "east_autocorr_autoscale": "on",
    "west_autocorr_autoscale": "on",
    "east_auto_spectrum_autoscale": "on",
    "west_auto_spectrum_autoscale": "on",
    "fringe_iq_autoscale": "on",
    "fringe_time_window_minutes": f"{FRINGE_WINDOW_MINUTES_DEFAULT:.0f}",
    "continuum_snr_mode": "on",
    "record_visibility_mode": "off",
    **{key: default for key, _, default in FIELD_DEFAULTS},
    **{key: default for key, _, default in PLOT_SCALE_DEFAULTS},
    **{key: default for key, _, default in CONTINUUM_FIELD_DEFAULTS},
    **{key: default for key, _, default in VISIBILITY_FIELD_DEFAULTS},
}


class InterferometryApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"Radio Interferometry FX Correlator v{__version__}")
        self.geometry("1320x1040")
        self.minsize(1080, 840)

        self._backend: CorrelatorBackendProcess | None = None
        self._running = False
        self._latest_config: ObservationConfig | None = None
        self._latest_source_mode = "Simulator"
        self._latest_fringe_reset_signature: tuple[object, ...] | None = None
        self._latest_backend_status: dict[str, object] = {}
        self._loading_settings = True
        self._settings = load_settings()
        self._committed_inputs = {
            key: self._settings.get(key, default) for key, _, default in FIELD_DEFAULTS
        }
        self._committed_continuum_inputs = {
            key: self._settings.get(key, default) for key, _, default in CONTINUUM_FIELD_DEFAULTS
        }
        self._committed_visibility_inputs = {
            key: self._settings.get(key, default) for key, _, default in VISIBILITY_FIELD_DEFAULTS
        }
        self._plot_scale_inputs = {
            key: self._settings.get(key, default) for key, _, default in PLOT_SCALE_DEFAULTS
        }
        self._update_calculated_observing_frequency(self._committed_inputs)
        self._last_draw_time = 0.0
        self._last_visibility_record_time = 0.0
        self._last_interferogram_mag: np.ndarray | None = None
        self._last_spectrum_envelope: np.ndarray | None = None
        self._last_east_autocorr_mag: np.ndarray | None = None
        self._last_west_autocorr_mag: np.ndarray | None = None
        self._last_east_auto_spectrum_mag: np.ndarray | None = None
        self._last_west_auto_spectrum_mag: np.ndarray | None = None
        self._fringe_history_start: float | None = None
        self._fringe_time_history: deque[float] = deque()
        self._fringe_i_history: deque[float] = deque()
        self._fringe_q_history: deque[float] = deque()
        self._fringe_raw_phase_history: deque[float] = deque()
        self._fringe_stopped_phase_history: deque[float] = deque()
        self._latest_fringe_model = None
        self._latest_raw_visibility: complex | None = None
        self._latest_stopped_visibility: complex | None = None
        self._latest_stopped_phase_rate_deg_s: float | None = None
        self._fringe_time_window_minutes = parse_fringe_window_minutes(
            self._settings["fringe_time_window_minutes"]
        )

        self._build_controls()
        self._build_plots()
        self._loading_settings = False
        self._save_settings()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(side=tk.LEFT, fill=tk.Y)
        controls.rowconfigure(0, weight=1)
        controls.columnconfigure(0, weight=1)

        scroll_area = ttk.Frame(controls)
        scroll_area.grid(row=0, column=0, sticky="nsew")
        ttk.Separator(controls).grid(row=1, column=0, sticky="ew")
        fixed_status = ttk.Frame(controls, padding=(10, 8))
        fixed_status.grid(row=2, column=0, sticky="ew")

        controls_canvas = tk.Canvas(scroll_area, width=320, highlightthickness=0)
        controls_scroll = ttk.Scrollbar(
            scroll_area, orient=tk.VERTICAL, command=controls_canvas.yview
        )
        controls_canvas.configure(yscrollcommand=controls_scroll.set)
        controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        controls_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        panel = ttk.Frame(controls_canvas, padding=10)
        controls_window = controls_canvas.create_window((0, 0), window=panel, anchor="nw")

        def update_scroll_region(_event=None) -> None:
            controls_canvas.configure(scrollregion=controls_canvas.bbox("all"))
            controls_canvas.itemconfigure(controls_window, width=controls_canvas.winfo_width())

        panel.bind("<Configure>", update_scroll_region)
        controls_canvas.bind("<Configure>", update_scroll_region)

        self.source_mode = tk.StringVar(value=self._settings["source_mode"])
        ttk.Label(panel, text="Input").grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Combobox(
            panel,
            textvariable=self.source_mode,
            values=("Simulator", "B210 / SoapySDR"),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        self.target_mode = tk.StringVar(value=self._settings["target_mode"])
        ttk.Label(panel, text="Target").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(
            panel,
            textvariable=self.target_mode,
            values=TARGET_SOURCE_OPTIONS,
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="ew", pady=3)

        self.fringe_stop_mode = tk.StringVar(value=self._settings["fringe_stop_mode"])
        ttk.Label(panel, text="Fringe stop").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Combobox(
            panel,
            textvariable=self.fringe_stop_mode,
            values=FRINGE_STOP_OPTIONS,
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="ew", pady=3)

        self.frequency_sideband = tk.StringVar(value=self._settings["frequency_sideband"])
        ttk.Label(panel, text="RF sideband").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(
            panel,
            textvariable=self.frequency_sideband,
            values=FREQUENCY_SIDEBAND_OPTIONS,
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="ew", pady=3)

        self.spectrum_plot_mode = tk.StringVar(value=self._settings["spectrum_plot_mode"])
        self.phase_plot_mode = tk.StringVar(value=self._settings["phase_plot_mode"])
        ttk.Label(panel, text="Spectrum plot").grid(row=4, column=0, sticky="w", pady=3)
        spectrum_options = ttk.Frame(panel)
        spectrum_options.grid(row=4, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            spectrum_options,
            text="On",
            variable=self.spectrum_plot_mode,
            value="on",
            command=self._apply_plot_visibility,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            spectrum_options,
            text="Off",
            variable=self.spectrum_plot_mode,
            value="off",
            command=self._apply_plot_visibility,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(panel, text="Phase plot").grid(row=5, column=0, sticky="w", pady=3)
        phase_options = ttk.Frame(panel)
        phase_options.grid(row=5, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            phase_options,
            text="On",
            variable=self.phase_plot_mode,
            value="on",
            command=self._apply_plot_visibility,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            phase_options,
            text="Off",
            variable=self.phase_plot_mode,
            value="off",
            command=self._apply_plot_visibility,
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.interferogram_autoscale = tk.StringVar(value=self._settings["interferogram_autoscale"])
        self.spectrum_autoscale = tk.StringVar(value=self._settings["spectrum_autoscale"])
        self.east_autocorr_autoscale = tk.StringVar(
            value=self._settings["east_autocorr_autoscale"]
        )
        self.west_autocorr_autoscale = tk.StringVar(
            value=self._settings["west_autocorr_autoscale"]
        )
        self.east_auto_spectrum_autoscale = tk.StringVar(
            value=self._settings["east_auto_spectrum_autoscale"]
        )
        self.west_auto_spectrum_autoscale = tk.StringVar(
            value=self._settings["west_auto_spectrum_autoscale"]
        )
        self.fringe_iq_autoscale = tk.StringVar(value=self._settings["fringe_iq_autoscale"])

        self.continuum_snr_mode = tk.StringVar(value=self._settings["continuum_snr_mode"])
        ttk.Label(panel, text="Continuum SNR").grid(row=6, column=0, sticky="w", pady=3)
        continuum_options = ttk.Frame(panel)
        continuum_options.grid(row=6, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            continuum_options,
            text="On",
            variable=self.continuum_snr_mode,
            value="on",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            continuum_options,
            text="Off",
            variable=self.continuum_snr_mode,
            value="off",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.record_visibility_mode = tk.StringVar(value=self._settings["record_visibility_mode"])
        ttk.Label(panel, text="Record visibilities").grid(row=7, column=0, sticky="w", pady=3)
        record_options = ttk.Frame(panel)
        record_options.grid(row=7, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            record_options,
            text="On",
            variable=self.record_visibility_mode,
            value="on",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            record_options,
            text="Off",
            variable=self.record_visibility_mode,
            value="off",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.start_button = ttk.Button(panel, text="Start", command=self.start)
        self.start_button.grid(row=8, column=0, sticky="ew", pady=(10, 3))
        self.stop_button = ttk.Button(panel, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.grid(row=8, column=1, sticky="ew", pady=(10, 3))

        self.inputs: dict[str, tk.StringVar] = {}
        self.input_entries: dict[str, ttk.Entry] = {}
        for row, (key, label, default) in enumerate(FIELD_DEFAULTS, start=9):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=3)
            value = tk.StringVar(value=self._settings.get(key, default))
            self.inputs[key] = value
            entry = ttk.Entry(panel, textvariable=value, width=18)
            self.input_entries[key] = entry
            if key == "observing_frequency_mhz":
                entry.configure(state="readonly")
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            if key != "observing_frequency_mhz":
                self._bind_commit_entry(entry)

        continuum_row = len(FIELD_DEFAULTS) + 9
        self.continuum_inputs: dict[str, tk.StringVar] = {}
        for row, (key, label, default) in enumerate(CONTINUUM_FIELD_DEFAULTS, start=continuum_row):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=3)
            value = tk.StringVar(value=self._settings.get(key, default))
            self.continuum_inputs[key] = value
            entry = ttk.Entry(panel, textvariable=value, width=18)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self._bind_commit_entry(entry)

        visibility_row = continuum_row + len(CONTINUUM_FIELD_DEFAULTS)
        self.visibility_inputs: dict[str, tk.StringVar] = {}
        for row, (key, label, default) in enumerate(VISIBILITY_FIELD_DEFAULTS, start=visibility_row):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=3)
            value = tk.StringVar(value=self._settings.get(key, default))
            self.visibility_inputs[key] = value
            entry = ttk.Entry(panel, textvariable=value, width=18)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self._bind_commit_entry(entry)

        button_row = visibility_row + len(VISIBILITY_FIELD_DEFAULTS)
        self.reset_button = ttk.Button(panel, text="Reset Avg", command=self.reset_average)
        self.reset_button.grid(row=button_row, column=0, columnspan=2, sticky="ew", pady=3)

        self.status = tk.StringVar(value=format_status_text("Ready"))
        ttk.Label(
            fixed_status,
            textvariable=self.status,
            anchor="nw",
            justify=tk.LEFT,
            wraplength=STATUS_WRAP_LENGTH,
        ).pack(anchor="w", fill=tk.X)
        self.visibility_status = tk.StringVar(value=format_visibility_status(None))
        ttk.Label(
            fixed_status,
            textvariable=self.visibility_status,
            anchor="nw",
            justify=tk.LEFT,
            wraplength=STATUS_WRAP_LENGTH,
        ).pack(anchor="w", fill=tk.X, pady=(4, 0))
        self.fringe_model_status = tk.StringVar(
            value=format_fringe_model_status(None, None, None)
        )
        ttk.Label(
            fixed_status,
            textvariable=self.fringe_model_status,
            anchor="nw",
            justify=tk.LEFT,
            wraplength=STATUS_WRAP_LENGTH,
        ).pack(anchor="w", fill=tk.X, pady=(4, 0))
        panel.columnconfigure(1, weight=1)

        self._watch_control(self.source_mode)
        self._watch_control(self.target_mode)
        self._watch_control(self.fringe_stop_mode)
        self._watch_control(self.frequency_sideband)
        self._watch_control(self.spectrum_plot_mode)
        self._watch_control(self.phase_plot_mode)
        self._watch_control(self.interferogram_autoscale)
        self._watch_control(self.spectrum_autoscale)
        self._watch_control(self.east_autocorr_autoscale)
        self._watch_control(self.west_autocorr_autoscale)
        self._watch_control(self.east_auto_spectrum_autoscale)
        self._watch_control(self.west_auto_spectrum_autoscale)
        self._watch_control(self.fringe_iq_autoscale)
        self._watch_control(self.continuum_snr_mode)
        self._watch_control(self.record_visibility_mode)
        self._refresh_target_coordinate_fields(force=True)

    def _bind_commit_entry(self, entry: ttk.Entry) -> None:
        entry.bind("<Return>", self._commit_text_fields)
        entry.bind("<KP_Enter>", self._commit_text_fields)

    def _set_status(self, *lines: str) -> None:
        self.status.set(format_status_text(*lines))

    def _set_runtime_status(self) -> None:
        self.status.set(
            format_runtime_status_text(
                self._format_averaging_status(),
                self._latest_backend_status,
            )
        )

    def _build_plots(self) -> None:
        plot_frame = ttk.Frame(self, padding=(0, 10, 10, 10))
        plot_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.figure = Figure(figsize=(11, 12), dpi=100)
        grid = self.figure.add_gridspec(
            6,
            2,
            height_ratios=[1.0, 1.0, 1.0, 0.75, 0.75, 0.12],
        )
        self.ax_interferogram = self.figure.add_subplot(grid[0, 0])
        self.ax_spectrum = self.figure.add_subplot(grid[0, 1])
        self.ax_east_autocorr = self.figure.add_subplot(grid[1, 0])
        self.ax_west_autocorr = self.figure.add_subplot(grid[1, 1])
        self.ax_east_auto_spectrum = self.figure.add_subplot(grid[2, 0])
        self.ax_west_auto_spectrum = self.figure.add_subplot(grid[2, 1])
        self.ax_fringe_time = self.figure.add_subplot(grid[3, :])
        self.ax_fringe_phase = self.figure.add_subplot(grid[4, :])
        self.ax_fringe_time_slider = self.figure.add_subplot(grid[5, :])
        self.ax_phase = self.ax_spectrum.twinx()

        self.ax_interferogram.set_title("Realtime Interferogram")
        self.ax_interferogram.set_xlabel("Lag bin")
        self.ax_interferogram.set_ylabel("|Correlation|")
        self.ax_spectrum.set_title("Cross-Correlation Spectrum")
        self.ax_spectrum.set_xlabel("Sky frequency (MHz)")
        self.ax_spectrum.set_ylabel("|Cross power|")
        self.ax_phase.set_ylabel("Phase (rad)")
        self.ax_east_autocorr.set_title("East Antenna Autocorrelation")
        self.ax_east_autocorr.set_xlabel("Lag bin")
        self.ax_east_autocorr.set_ylabel("|Autocorrelation|")
        self.ax_west_autocorr.set_title("West Antenna Autocorrelation")
        self.ax_west_autocorr.set_xlabel("Lag bin")
        self.ax_west_autocorr.set_ylabel("|Autocorrelation|")
        self.ax_east_auto_spectrum.set_title("East Antenna Spectrum")
        self.ax_east_auto_spectrum.set_xlabel("Sky frequency (MHz)")
        self.ax_east_auto_spectrum.set_ylabel("Power")
        self.ax_west_auto_spectrum.set_title("West Antenna Spectrum")
        self.ax_west_auto_spectrum.set_xlabel("Sky frequency (MHz)")
        self.ax_west_auto_spectrum.set_ylabel("Power")
        self.ax_fringe_time.set_title("Fringe I/Q vs Time")
        self.ax_fringe_time.set_xlabel("Time since start (s)")
        self.ax_fringe_time.set_ylabel("Broadband visibility")
        self.ax_fringe_time.set_xlim(0.0, self._fringe_window_seconds())
        self.ax_fringe_time.set_ylim(-1.0, 1.0)
        self.ax_fringe_phase.set_title("Raw and Display-Stopped Fringe Phase")
        self.ax_fringe_phase.set_xlabel("Time since start (s)")
        self.ax_fringe_phase.set_ylabel("Phase (deg)")
        self.ax_fringe_phase.set_xlim(0.0, self._fringe_window_seconds())
        self.ax_fringe_phase.set_ylim(-180.0, 180.0)
        self._apply_graticules()

        (self.interferogram_line,) = self.ax_interferogram.plot([], [], color="#1f77b4", lw=1.4)
        (self.spectrum_line,) = self.ax_spectrum.plot(
            [], [], color="#2ca02c", lw=1.3, drawstyle="default"
        )
        (self.phase_line,) = self.ax_phase.plot([], [], color="#d62728", lw=1.0, alpha=0.78)
        (self.east_autocorr_line,) = self.ax_east_autocorr.plot(
            [], [], color="#9467bd", lw=1.2
        )
        (self.west_autocorr_line,) = self.ax_west_autocorr.plot(
            [], [], color="#17becf", lw=1.2
        )
        (self.east_auto_spectrum_line,) = self.ax_east_auto_spectrum.plot(
            [], [], color="#9467bd", lw=1.1
        )
        (self.west_auto_spectrum_line,) = self.ax_west_auto_spectrum.plot(
            [], [], color="#17becf", lw=1.1
        )
        (self.fringe_i_line,) = self.ax_fringe_time.plot([], [], color="#1f77b4", lw=1.1)
        (self.fringe_q_line,) = self.ax_fringe_time.plot([], [], color="#d62728", lw=1.1)
        (self.fringe_raw_phase_line,) = self.ax_fringe_phase.plot(
            [], [], color="#9467bd", lw=1.1, label="Raw phase"
        )
        (self.fringe_stopped_phase_line,) = self.ax_fringe_phase.plot(
            [],
            [],
            color="#2ca02c",
            lw=1.1,
            label=format_stopped_phase_label(None),
        )
        self.fringe_phase_legend = self.ax_fringe_phase.legend(loc="upper left", framealpha=0.8)
        self.fringe_time_slider = Slider(
            self.ax_fringe_time_slider,
            "Time span (min)",
            FRINGE_WINDOW_MINUTES_MIN,
            FRINGE_WINDOW_MINUTES_MAX,
            valinit=self._fringe_time_window_minutes,
            valstep=1.0,
        )
        self.fringe_time_slider.on_changed(self._on_fringe_window_changed)
        self.peak_vline = self.ax_interferogram.axvline(
            0.0, color="#111111", lw=1.0, ls="--", alpha=0.7
        )
        (self.peak_marker,) = self.ax_interferogram.plot(
            [], [], marker="o", ms=6, color="#111111", linestyle="None"
        )
        self.snr_text = self.ax_interferogram.text(
            0.02,
            0.94,
            "Lag peak: --\nLag SNR: --\nContinuum SNR: --",
            transform=self.ax_interferogram.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.75},
        )

        self.figure.tight_layout()
        self._build_plot_panel_controls()
        self._apply_plot_visibility(draw=False)

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas, plot_frame)

    def _apply_graticules(self) -> None:
        axes = (
            self.ax_interferogram,
            self.ax_spectrum,
            self.ax_east_autocorr,
            self.ax_west_autocorr,
            self.ax_east_auto_spectrum,
            self.ax_west_auto_spectrum,
            self.ax_fringe_time,
            self.ax_fringe_phase,
        )
        for axis in axes:
            axis.set_axisbelow(True)
            axis.xaxis.set_minor_locator(AutoMinorLocator(2))
            axis.yaxis.set_minor_locator(AutoMinorLocator(2))
            axis.grid(True, which="major", color=GRID_MAJOR_COLOR, linewidth=0.75, alpha=0.9)
            axis.grid(True, which="minor", color=GRID_MINOR_COLOR, linewidth=0.5, alpha=0.8)

        self.ax_phase.grid(False)

    def _plot_panel_specs(self) -> dict[str, tuple[object, tk.StringVar, str, str]]:
        return {
            "interferogram": (
                self.ax_interferogram,
                self.interferogram_autoscale,
                "interferogram_y_min",
                "interferogram_y_max",
            ),
            "spectrum": (
                self.ax_spectrum,
                self.spectrum_autoscale,
                "spectrum_y_min",
                "spectrum_y_max",
            ),
            "east_autocorr": (
                self.ax_east_autocorr,
                self.east_autocorr_autoscale,
                "east_autocorr_y_min",
                "east_autocorr_y_max",
            ),
            "west_autocorr": (
                self.ax_west_autocorr,
                self.west_autocorr_autoscale,
                "west_autocorr_y_min",
                "west_autocorr_y_max",
            ),
            "east_auto_spectrum": (
                self.ax_east_auto_spectrum,
                self.east_auto_spectrum_autoscale,
                "east_auto_spectrum_y_min",
                "east_auto_spectrum_y_max",
            ),
            "west_auto_spectrum": (
                self.ax_west_auto_spectrum,
                self.west_auto_spectrum_autoscale,
                "west_auto_spectrum_y_min",
                "west_auto_spectrum_y_max",
            ),
            "fringe_time": (
                self.ax_fringe_time,
                self.fringe_iq_autoscale,
                "fringe_iq_y_min",
                "fringe_iq_y_max",
            ),
        }

    def _build_plot_panel_controls(self) -> None:
        self._plot_buttons: dict[str, Button] = {}
        self._plot_textboxes: dict[str, TextBox] = {}
        for name, (axis, autoscale_var, min_key, max_key) in self._plot_panel_specs().items():
            position = axis.get_position()
            control_x = position.x1 - PLOT_CONTROL_WIDTH
            control_width = PLOT_CONTROL_WIDTH
            control_font_size = PLOT_CONTROL_FONT_SIZE
            button_y = position.y1 - PLOT_CONTROL_HEIGHT
            if name == "fringe_time":
                control_x = position.x0
            button_axis = self.figure.add_axes(
                [control_x, button_y, control_width, PLOT_CONTROL_HEIGHT]
            )
            button = Button(
                button_axis,
                autoscale_button_label(autoscale_var, compact=True),
                color=autoscale_button_color(autoscale_var),
                hovercolor="#d9ead3",
            )
            button.label.set_fontsize(control_font_size)
            button.on_clicked(
                lambda _event, name=name: self._toggle_plot_autoscale(name)
            )
            self._plot_buttons[name] = button

            min_y = button_y - PLOT_CONTROL_HEIGHT - PLOT_CONTROL_GAP
            max_y = button_y - (PLOT_CONTROL_HEIGHT * 2.0) - (PLOT_CONTROL_GAP * 2.0)
            min_axis = self.figure.add_axes(
                [control_x, min_y, control_width, PLOT_CONTROL_HEIGHT]
            )
            max_axis = self.figure.add_axes(
                [control_x, max_y, control_width, PLOT_CONTROL_HEIGHT]
            )
            min_box = TextBox(
                min_axis,
                "",
                initial=self._plot_scale_inputs[min_key],
            )
            max_box = TextBox(
                max_axis,
                "",
                initial=self._plot_scale_inputs[max_key],
            )
            min_box.text_disp.set_fontsize(control_font_size)
            max_box.text_disp.set_fontsize(control_font_size)
            min_box.on_submit(lambda _text, name=name: self._commit_plot_scale(name))
            max_box.on_submit(lambda _text, name=name: self._commit_plot_scale(name))
            self._plot_textboxes[f"{name}_min"] = min_box
            self._plot_textboxes[f"{name}_max"] = max_box

    def _toggle_plot_autoscale(self, name: str) -> None:
        axis, autoscale_var, _min_key, _max_key = self._plot_panel_specs()[name]
        autoscale_var.set("off" if autoscale_var.get() == "on" else "on")
        if autoscale_var.get() == "on" and (values := self._latest_plot_values(name)) is not None:
            autoscale_plot_axis(axis, values, symmetric=(name == "fringe_time"))
        self._refresh_plot_button(name)
        self._apply_panel_plot_scales(draw=True)

    def _refresh_plot_button(self, name: str) -> None:
        button = self._plot_buttons[name]
        variable = self._plot_panel_specs()[name][1]
        button.label.set_text(autoscale_button_label(variable, compact=True))
        button.color = autoscale_button_color(variable)
        button.ax.set_facecolor(autoscale_button_color(variable))

    def _refresh_plot_buttons(self) -> None:
        for name in self._plot_buttons:
            self._refresh_plot_button(name)

    def _commit_plot_scale(self, name: str) -> None:
        min_box = self._plot_textboxes[f"{name}_min"]
        max_box = self._plot_textboxes[f"{name}_max"]
        _axis, _autoscale_var, min_key, max_key = self._plot_panel_specs()[name]
        try:
            y_min = parse_scale_value(min_box.text)
            y_max = parse_scale_value(max_box.text)
            validate_scale_limits(y_min, y_max)
        except ValueError as exc:
            self._set_status(f"{plot_control_label(name)} scale not applied:", str(exc))
            return
        self._plot_scale_inputs[min_key] = min_box.text.strip()
        self._plot_scale_inputs[max_key] = max_box.text.strip()
        self._save_settings()
        self._apply_panel_plot_scales(draw=True)
        self._set_status(f"{plot_control_label(name)} scale committed")

    def _latest_plot_values(self, name: str) -> np.ndarray | None:
        return {
            "interferogram": self._last_interferogram_mag,
            "spectrum": self._last_spectrum_envelope,
            "east_autocorr": self._last_east_autocorr_mag,
            "west_autocorr": self._last_west_autocorr_mag,
            "east_auto_spectrum": self._last_east_auto_spectrum_mag,
            "west_auto_spectrum": self._last_west_auto_spectrum_mag,
            "fringe_time": self._latest_fringe_values(),
        }[name]

    def _latest_fringe_values(self) -> np.ndarray | None:
        if not self._fringe_i_history:
            return None
        return np.asarray(
            (*self._fringe_i_history, *self._fringe_q_history),
            dtype=np.float64,
        )

    def start(self) -> None:
        try:
            self._refresh_target_coordinate_fields(force=True)
            config = self._read_config()
            backend = CorrelatorBackendProcess(config, self.source_mode.get())
            backend.start()
        except Exception as exc:
            messagebox.showerror("Unable to start", str(exc))
            self._set_status("Start failed:", str(exc))
            return

        self._latest_config = config
        self._latest_source_mode = self.source_mode.get()
        self._latest_fringe_reset_signature = fringe_reset_signature(
            config,
            self._target_mode_value(),
            self._latest_source_mode,
        )
        self._backend = backend
        self._latest_backend_status = {}
        self._last_draw_time = 0.0
        self._reset_fringe_history()
        self._running = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._set_status("Running.", f"X-corr smoothing {config.averaging_blocks} blocks")
        self.after(20, self._update_loop)

    def stop(self) -> None:
        self._running = False
        if self._backend is not None:
            try:
                self._backend.stop()
            except Exception as exc:
                self._set_status("Stopped with backend warning:", str(exc))
            else:
                self._set_status("Stopped")
        self._backend = None
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self._set_fringe_model_status(None, None, None)

    def reset_average(self) -> None:
        if self._backend is not None:
            self._backend.reset_average()
            self._reset_fringe_history()
            self._set_status("Averaging reset")

    def _update_loop(self) -> None:
        if not self._running or self._backend is None:
            return

        try:
            if not self._apply_runtime_config_if_needed():
                self.after(GUI_REFRESH_MS, self._update_loop)
                return

            if not self._backend.is_alive():
                raise RuntimeError("Backend process stopped unexpectedly.")

            update = self._backend.poll_latest()
            if update is not None:
                self._latest_backend_status = update.status
                if "error" in update.status:
                    raise RuntimeError(str(update.status["error"]))
                if update.result is not None and self._should_draw_result():
                    self._draw_result(update.result)

            self._set_runtime_status()
        except Exception as exc:
            self.stop()
            messagebox.showerror("Runtime error", str(exc))
            return

        self.after(GUI_REFRESH_MS, self._update_loop)

    def _draw_result(self, result) -> None:
        config = self._latest_config
        if config is None:
            return

        sky_freq_mhz = sky_frequencies_hz(config, result.frequency_offsets_hz) / 1_000_000.0
        interferogram_mag = np.abs(result.interferogram)
        self._last_interferogram_mag = interferogram_mag
        spectrum_mag = np.abs(result.cross_spectrum)
        spectrum_envelope = smooth_line(spectrum_mag, config.spectrum_smoothing_bins)
        self._last_spectrum_envelope = spectrum_envelope
        phase = np.angle(result.cross_spectrum)
        peak_snr = estimate_peak_snr(interferogram_mag)
        peak_lag_bin = float(result.lag_bins[peak_snr.index])
        model = fringe_model(config)
        continuum, continuum_error = self._estimate_broadband_visibility(
            result,
            config,
            result.cross_spectrum,
            peak_lag_bin,
        )
        raw_continuum = None
        if config.fringe_stop_mode == "Backend":
            raw_continuum, _raw_continuum_error = self._estimate_broadband_visibility(
                result,
                config,
                result.raw_cross_spectrum,
                peak_lag_bin,
            )
        continuum_text = "Continuum SNR: off"
        if self.continuum_snr_mode.get() == "on":
            if continuum is not None:
                continuum_text = (
                    f"Continuum SNR: {continuum.snr:.2f}\n"
                    f"Cont amp: {continuum.amplitude:.3g}\n"
                    f"Cont phase: {continuum.phase_rad:.3f} rad\n"
                    f"Clean bins: {continuum.bins_used}"
                )
            elif continuum_error is not None:
                continuum_text = f"Continuum SNR: {continuum_error}"

        if continuum is not None:
            raw_visibility = (
                raw_continuum.visibility
                if raw_continuum is not None
                else continuum.visibility
            )
            if config.fringe_stop_mode == "Backend":
                stopped_visibility = continuum.visibility
                iq_visibility = stopped_visibility
            elif config.fringe_stop_mode == "Display":
                stopped_visibility = apply_display_fringe_stop(continuum.visibility, model)
                iq_visibility = continuum.visibility
            else:
                stopped_visibility = continuum.visibility
                iq_visibility = continuum.visibility
            self.visibility_status.set(format_visibility_status(continuum))
            self._set_fringe_model_status(model, raw_visibility, stopped_visibility)
            self._append_fringe_sample(iq_visibility, raw_visibility, stopped_visibility)
            self._record_visibility_if_needed(config, continuum, peak_lag_bin)
        else:
            self.visibility_status.set(format_visibility_status(None))
            self._set_fringe_model_status(model, None, None)
        self._draw_fringe_history()

        self.interferogram_line.set_data(result.lag_bins, interferogram_mag)
        self.peak_marker.set_data([peak_lag_bin], [peak_snr.peak_value])
        self.peak_vline.set_xdata([peak_lag_bin, peak_lag_bin])
        self.snr_text.set_text(
            f"Peak lag: {peak_lag_bin:.0f}\n"
            f"Lag SNR: {peak_snr.snr:.2f}\n"
            f"Lag noise: {peak_snr.noise_floor:.3g}\n"
            f"{continuum_text}"
        )
        self.ax_interferogram.set_xlim(float(result.lag_bins.min()), float(result.lag_bins.max()))
        if self.interferogram_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_interferogram, interferogram_mag)

        self.spectrum_line.set_data(sky_freq_mhz, spectrum_envelope)
        self.phase_line.set_data(sky_freq_mhz, phase)
        self.ax_spectrum.set_xlim(float(sky_freq_mhz.min()), float(sky_freq_mhz.max()))
        if self.spectrum_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_spectrum, spectrum_envelope)
        self.ax_phase.set_ylim(-np.pi, np.pi)

        east_autocorr_mag = np.abs(result.east_autocorrelation)
        west_autocorr_mag = np.abs(result.west_autocorrelation)
        east_auto_spectrum_mag = np.abs(result.east_auto_spectrum)
        west_auto_spectrum_mag = np.abs(result.west_auto_spectrum)
        self._last_east_autocorr_mag = east_autocorr_mag
        self._last_west_autocorr_mag = west_autocorr_mag
        self._last_east_auto_spectrum_mag = east_auto_spectrum_mag
        self._last_west_auto_spectrum_mag = west_auto_spectrum_mag
        self.east_autocorr_line.set_data(result.lag_bins, east_autocorr_mag)
        self.west_autocorr_line.set_data(result.lag_bins, west_autocorr_mag)
        self.east_auto_spectrum_line.set_data(sky_freq_mhz, east_auto_spectrum_mag)
        self.west_auto_spectrum_line.set_data(sky_freq_mhz, west_auto_spectrum_mag)
        lag_min = float(result.lag_bins.min())
        lag_max = float(result.lag_bins.max())
        self.ax_east_autocorr.set_xlim(lag_min, lag_max)
        self.ax_west_autocorr.set_xlim(lag_min, lag_max)
        self.ax_east_auto_spectrum.set_xlim(float(sky_freq_mhz.min()), float(sky_freq_mhz.max()))
        self.ax_west_auto_spectrum.set_xlim(float(sky_freq_mhz.min()), float(sky_freq_mhz.max()))
        if self.east_autocorr_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_east_autocorr, east_autocorr_mag)
        if self.west_autocorr_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_west_autocorr, west_autocorr_mag)
        if self.east_auto_spectrum_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_east_auto_spectrum, east_auto_spectrum_mag)
        if self.west_auto_spectrum_autoscale.get() == "on":
            autoscale_positive_axis(self.ax_west_auto_spectrum, west_auto_spectrum_mag)

        self._apply_plot_visibility(draw=False)
        self._apply_panel_plot_scales(draw=False)
        self._refresh_plot_buttons()

        self.canvas.draw_idle()

    def _estimate_broadband_visibility(self, result, config, cross_spectrum, peak_lag_bin: float):
        try:
            continuum = estimate_broadband_continuum_snr(
                cross_spectrum,
                result.frequency_offsets_hz,
                peak_lag_bin,
                config.sample_rate_hz,
                edge_percent=parse_float_text(
                    self._committed_continuum_inputs["continuum_edge_percent"],
                    "Continuum edge exclude",
                ),
                rfi_sigma=parse_float_text(
                    self._committed_continuum_inputs["continuum_rfi_sigma"],
                    "Continuum RFI sigma",
                ),
            )
        except ValueError as exc:
            return None, exc
        return continuum, None

    def _reset_fringe_history(self) -> None:
        self._fringe_history_start = None
        self._fringe_time_history.clear()
        self._fringe_i_history.clear()
        self._fringe_q_history.clear()
        self._fringe_raw_phase_history.clear()
        self._fringe_stopped_phase_history.clear()
        if hasattr(self, "fringe_i_line"):
            self._draw_fringe_history(draw=True)

    def _append_fringe_sample(
        self,
        iq_visibility: complex,
        raw_visibility: complex,
        stopped_visibility: complex,
    ) -> None:
        now = monotonic()
        if self._fringe_history_start is None:
            self._fringe_history_start = now
        elapsed = now - self._fringe_history_start
        self._fringe_time_history.append(elapsed)
        self._fringe_i_history.append(float(np.real(iq_visibility)))
        self._fringe_q_history.append(float(np.imag(iq_visibility)))
        self._fringe_raw_phase_history.append(float(np.angle(raw_visibility)))
        self._fringe_stopped_phase_history.append(float(np.angle(stopped_visibility)))

        oldest_time = elapsed - FRINGE_HISTORY_MAX_SECONDS
        while self._fringe_time_history and self._fringe_time_history[0] < oldest_time:
            self._fringe_time_history.popleft()
            self._fringe_i_history.popleft()
            self._fringe_q_history.popleft()
            self._fringe_raw_phase_history.popleft()
            self._fringe_stopped_phase_history.popleft()

    def _on_fringe_window_changed(self, value: float) -> None:
        self._fringe_time_window_minutes = clamp_fringe_window_minutes(float(value))
        self._save_settings()
        self._draw_fringe_history(draw=True)

    def _fringe_window_seconds(self) -> float:
        return self._fringe_time_window_minutes * 60.0

    def _draw_fringe_history(self, draw: bool = False) -> None:
        window_seconds = self._fringe_window_seconds()
        if not self._fringe_time_history:
            self.fringe_i_line.set_data([], [])
            self.fringe_q_line.set_data([], [])
            self.fringe_raw_phase_line.set_data([], [])
            self.fringe_stopped_phase_line.set_data([], [])
            self._update_stopped_phase_label(None)
            self._latest_stopped_phase_rate_deg_s = None
            self._refresh_fringe_model_status()
            self.ax_fringe_time.set_xlim(0.0, window_seconds)
            self.ax_fringe_phase.set_xlim(0.0, window_seconds)
            self.ax_fringe_phase.set_ylim(-180.0, 180.0)
            if self.fringe_iq_autoscale.get() == "on":
                self.ax_fringe_time.set_ylim(-1.0, 1.0)
            else:
                self._apply_panel_plot_scales(draw=False)
            if draw:
                self.canvas.draw_idle()
            return

        times = np.asarray(self._fringe_time_history, dtype=np.float64)
        i_values = np.asarray(self._fringe_i_history, dtype=np.float64)
        q_values = np.asarray(self._fringe_q_history, dtype=np.float64)
        raw_phase_values = np.asarray(self._fringe_raw_phase_history, dtype=np.float64)
        stopped_phase_values = np.asarray(
            self._fringe_stopped_phase_history,
            dtype=np.float64,
        )

        x_max = max(window_seconds, float(times[-1]))
        x_min = max(0.0, x_max - window_seconds)
        visible = times >= x_min
        display_times = times[visible]
        display_i = i_values[visible]
        display_q = q_values[visible]
        display_raw_phase = np.degrees(np.unwrap(raw_phase_values[visible]))
        display_stopped_phase = np.degrees(np.unwrap(stopped_phase_values[visible]))
        stopped_phase_rate = estimate_phase_rate_deg_s(
            display_times,
            stopped_phase_values[visible],
        )
        self._update_stopped_phase_label(stopped_phase_rate)
        self._latest_stopped_phase_rate_deg_s = stopped_phase_rate
        self._refresh_fringe_model_status()
        if display_times.size > FRINGE_DISPLAY_MAX_POINTS:
            step = int(np.ceil(display_times.size / FRINGE_DISPLAY_MAX_POINTS))
            display_times = display_times[::step]
            display_i = display_i[::step]
            display_q = display_q[::step]
            display_raw_phase = display_raw_phase[::step]
            display_stopped_phase = display_stopped_phase[::step]
        self.fringe_i_line.set_data(display_times, display_i)
        self.fringe_q_line.set_data(display_times, display_q)
        self.fringe_raw_phase_line.set_data(display_times, display_raw_phase)
        self.fringe_stopped_phase_line.set_data(display_times, display_stopped_phase)
        self.ax_fringe_time.set_xlim(x_min, x_max)
        self.ax_fringe_phase.set_xlim(x_min, x_max)

        if self.fringe_iq_autoscale.get() == "on":
            autoscale_symmetric_axis(self.ax_fringe_time, np.concatenate((display_i, display_q)))
        else:
            self._apply_panel_plot_scales(draw=False)
        phase_values = np.concatenate((display_raw_phase, display_stopped_phase))
        autoscale_phase_axis(self.ax_fringe_phase, phase_values)
        if draw:
            self.canvas.draw_idle()

    def _update_stopped_phase_label(self, rate_deg_s: float | None) -> None:
        self.fringe_stopped_phase_line.set_label(format_stopped_phase_label(rate_deg_s))
        self.fringe_phase_legend = self.ax_fringe_phase.legend(loc="upper left", framealpha=0.8)

    def _set_fringe_model_status(
        self,
        model,
        raw_visibility: complex | None,
        stopped_visibility: complex | None,
        stopped_phase_rate_deg_s: float | None = None,
    ) -> None:
        self._latest_fringe_model = model
        self._latest_raw_visibility = raw_visibility
        self._latest_stopped_visibility = stopped_visibility
        self._latest_stopped_phase_rate_deg_s = stopped_phase_rate_deg_s
        self._refresh_fringe_model_status()

    def _refresh_fringe_model_status(self) -> None:
        self.fringe_model_status.set(
            format_fringe_model_status(
                self._latest_fringe_model,
                self._latest_raw_visibility,
                self._latest_stopped_visibility,
                self._latest_stopped_phase_rate_deg_s,
            )
        )

    def _target_mode_value(self) -> str:
        if not hasattr(self, "target_mode"):
            return MANUAL_TARGET_SOURCE
        target_mode = self.target_mode.get()
        if target_mode not in TARGET_SOURCE_OPTIONS:
            return MANUAL_TARGET_SOURCE
        return target_mode

    def _target_adjusted_inputs(
        self,
        raw_inputs: dict[str, str],
        when: datetime | None = None,
    ) -> dict[str, str]:
        coords = resolve_automatic_target_coordinates(
            self._target_mode_value(),
            raw_inputs,
            when,
        )
        return apply_target_display_rounding(raw_inputs, coords)

    def _refresh_target_coordinate_fields(self, force: bool = False) -> None:
        if not hasattr(self, "inputs") or not hasattr(self, "input_entries"):
            return

        target_mode = self._target_mode_value()
        manual = target_mode == MANUAL_TARGET_SOURCE
        for key in ("ra_hours", "dec_deg"):
            entry = self.input_entries.get(key)
            if entry is not None:
                entry.configure(state=tk.NORMAL if manual else "readonly")

        if manual:
            return

        try:
            adjusted = self._target_adjusted_inputs(self._committed_inputs)
        except ValueError as exc:
            self._set_status(str(exc))
            return

        changed = any(
            adjusted[key] != self._committed_inputs.get(key)
            for key in ("ra_hours", "dec_deg")
        )
        if not force and not changed:
            return

        for key in ("ra_hours", "dec_deg"):
            self._committed_inputs[key] = adjusted[key]
            self.inputs[key].set(adjusted[key])
        if not self._loading_settings:
            self._save_settings()

    def _read_config(self, raw_inputs: dict[str, str] | None = None) -> ObservationConfig:
        raw_inputs = self._committed_inputs if raw_inputs is None else raw_inputs
        target_coords = resolve_automatic_target_coordinates(
            self._target_mode_value(),
            raw_inputs,
        )
        values: dict[str, float | int | str] = {}
        for key, _, _default in FIELD_DEFAULTS:
            raw = raw_inputs[key].strip()
            if key == "b210_device_args":
                values[key] = raw
            elif key == "ra_hours":
                values["ra_deg"] = (
                    target_coords.ra_deg
                    if target_coords is not None
                    else parse_ra_hours_text(raw) * 15.0
                )
            elif key == "dec_deg":
                values[key] = (
                    target_coords.dec_deg if target_coords is not None else float(raw)
                )
            elif key in {
                "bins",
                "averaging_blocks",
                "spectrum_smoothing_bins",
                "b210_read_timeout_ms",
                "b210_stream_chunk_samples",
                "b210_queue_blocks",
                "b210_process_blocks_per_update",
            }:
                values[key] = int(raw)
            else:
                values[key] = float(raw)

        if values["bandwidth_mhz"] <= 0:
            raise ValueError("Bandwidth must be positive.")
        if values["lnb_lo_frequency_mhz"] <= 0:
            raise ValueError("LNB LO frequency must be positive.")
        if values["intermediate_frequency_mhz"] <= 0:
            raise ValueError("B210 tune IF must be positive.")
        observing_frequency_mhz = (
            values["lnb_lo_frequency_mhz"] - values["intermediate_frequency_mhz"]
        )
        if observing_frequency_mhz <= 0:
            raise ValueError("Calculated observing frequency must be positive.")
        if values["bins"] < 8:
            raise ValueError("FX bins must be at least 8.")
        if values["bins"] & (values["bins"] - 1):
            raise ValueError("FX bins should be a power of two for realtime FFT performance.")
        if values["averaging_blocks"] < 1:
            raise ValueError("Averaging blocks must be at least 1.")
        if values["spectrum_smoothing_bins"] < 1:
            raise ValueError("Spectrum smoothing bins must be at least 1.")
        if not -90 <= values["observer_lat_deg"] <= 90:
            raise ValueError("Observer latitude must be between -90 and 90 degrees.")
        if not 0 <= values["ra_deg"] < 360:
            raise ValueError("Target RA must be between 00:00:00 and <24:00:00.")
        if not -90 <= values["dec_deg"] <= 90:
            raise ValueError("Target DEC must be between -90 and 90 degrees.")
        if values["b210_read_timeout_ms"] < 100:
            raise ValueError("B210 read timeout must be at least 100 ms.")
        if values["b210_stream_chunk_samples"] < 1024:
            raise ValueError("B210 stream chunk samples must be at least 1024.")
        if values["b210_queue_blocks"] < 1:
            raise ValueError("B210 queued FFT blocks must be at least 1.")
        if values["b210_process_blocks_per_update"] < 1:
            raise ValueError("B210 FFT blocks/update must be at least 1.")
        if values["b210_gain_db"] < 0:
            raise ValueError("B210 gain must not be negative.")
        if not np.isfinite(values["instrumental_delay_ns"]):
            raise ValueError("Instrument delay must be finite.")
        if not np.isfinite(values["instrumental_phase_deg"]):
            raise ValueError("Instrument phase must be finite.")

        values["observing_frequency_mhz"] = observing_frequency_mhz
        values.pop("lnb_lo_frequency_mhz")
        values["fringe_stop_mode"] = self.fringe_stop_mode.get()
        values["frequency_sideband"] = self.frequency_sideband.get()
        if values["fringe_stop_mode"] not in FRINGE_STOP_OPTIONS:
            raise ValueError("Fringe stop mode is invalid.")
        if values["frequency_sideband"] not in FREQUENCY_SIDEBAND_OPTIONS:
            raise ValueError("RF sideband mode is invalid.")
        return ObservationConfig(**values)

    def _should_draw_result(self) -> bool:
        now = monotonic()
        draw_interval = GUI_REFRESH_MS / 1000.0
        if (
            self.source_mode.get() == "B210 / SoapySDR"
            and float(self._latest_backend_status.get("averaging_fill", 1.0)) < 1.0
        ):
            draw_interval = AVERAGING_DRAW_REFRESH_MS / 1000.0
        if self._last_draw_time and now - self._last_draw_time < draw_interval:
            return False
        self._last_draw_time = now
        return True

    def _format_averaging_status(self) -> str:
        fill_fraction = float(self._latest_backend_status.get("averaging_fill", 1.0))
        if fill_fraction >= 1.0:
            return "Averaging stable."
        return f"Averaging {fill_fraction * 100.0:.1f}%."

    def _watch_control(self, value: tk.StringVar) -> None:
        value.trace_add("write", lambda *_args: self._on_control_changed())

    def _on_control_changed(self) -> None:
        if self._loading_settings:
            return
        self._refresh_target_coordinate_fields(force=True)
        self._save_settings()
        self._apply_plot_visibility(draw=False)
        self._apply_panel_plot_scales(draw=False)
        if hasattr(self, "_plot_buttons"):
            self._refresh_plot_buttons()
        if self._running:
            self._apply_runtime_config_if_needed()

    def _commit_text_fields(self, _event=None) -> str:
        new_inputs = {key: value.get() for key, value in self.inputs.items()}
        new_inputs = self._target_adjusted_inputs(new_inputs)
        new_continuum_inputs = {key: value.get() for key, value in self.continuum_inputs.items()}
        new_visibility_inputs = {key: value.get() for key, value in self.visibility_inputs.items()}

        try:
            self._read_config(new_inputs)
            validate_continuum_inputs(new_continuum_inputs)
            validate_visibility_inputs(new_visibility_inputs)
        except Exception as exc:
            self._set_status("Text fields not committed:", str(exc))
            return "break"

        self._update_calculated_observing_frequency(new_inputs)
        for key in (
            "observing_frequency_mhz",
            "lnb_lo_frequency_mhz",
            "intermediate_frequency_mhz",
        ):
            new_inputs[key] = format_no_decimal(float(new_inputs[key]))
            self.inputs[key].set(new_inputs[key])
        new_inputs["ra_hours"] = format_ra_hours(parse_ra_hours_text(new_inputs["ra_hours"]))
        self.inputs["ra_hours"].set(new_inputs["ra_hours"])
        if self._target_mode_value() != MANUAL_TARGET_SOURCE:
            for key in ("ra_hours", "dec_deg"):
                self.inputs[key].set(new_inputs[key])

        self._committed_inputs = new_inputs
        self._committed_continuum_inputs = new_continuum_inputs
        self._committed_visibility_inputs = new_visibility_inputs
        self._save_settings()
        self._apply_panel_plot_scales(draw=True)

        if self._running:
            self._apply_runtime_config_if_needed()
        else:
            self._set_status("Text fields committed")
        return "break"

    def _update_calculated_observing_frequency(self, inputs: dict[str, str]) -> None:
        lnb_lo_mhz = parse_float_text(inputs["lnb_lo_frequency_mhz"], "LNB LO frequency")
        tune_if_mhz = parse_float_text(inputs["intermediate_frequency_mhz"], "B210 tune IF")
        inputs["observing_frequency_mhz"] = format_no_decimal(lnb_lo_mhz - tune_if_mhz)

    def _apply_runtime_config_if_needed(self) -> bool:
        if self._backend is None or self._latest_config is None:
            return True

        try:
            self._refresh_target_coordinate_fields()
            config = self._read_config()
        except Exception as exc:
            self._set_status("Live settings not applied yet:", str(exc))
            return False

        source_mode = self.source_mode.get()
        reset_signature = fringe_reset_signature(
            config,
            self._target_mode_value(),
            source_mode,
        )
        model_changed = reset_signature != self._latest_fringe_reset_signature
        if (
            source_mode == self._latest_source_mode
            and runtime_configs_match(config, self._latest_config, self._target_mode_value())
            and not model_changed
        ):
            self._latest_config = config
            return True

        self._backend.update_config(config, source_mode)
        if model_changed:
            self._backend.reset_average()
            self._reset_fringe_history()
        self._latest_config = config
        self._latest_source_mode = source_mode
        self._latest_fringe_reset_signature = reset_signature
        self._latest_backend_status = {}
        self._last_draw_time = 0.0
        self._set_status(
            "Live settings sent to backend",
            "Fringe history reset" if model_changed else "Runtime settings updated",
            f"FX bins {config.bins}",
            f"X-corr smoothing {config.averaging_blocks} blocks",
        )
        return True

    def _apply_plot_visibility(self, draw: bool = True) -> None:
        spectrum_enabled = self.spectrum_plot_mode.get() == "on"
        phase_enabled = self.phase_plot_mode.get() == "on"
        self.spectrum_line.set_visible(spectrum_enabled)
        self.phase_line.set_visible(phase_enabled)
        self.ax_phase.set_visible(phase_enabled)
        if draw:
            self.canvas.draw_idle()

    def _apply_panel_plot_scales(self, draw: bool = True) -> None:
        try:
            for _name, (axis, autoscale_var, min_key, max_key) in self._plot_panel_specs().items():
                if autoscale_var.get() == "on":
                    continue
                y_min = parse_scale_value(self._plot_scale_inputs[min_key])
                y_max = parse_scale_value(self._plot_scale_inputs[max_key])
                validate_scale_limits(y_min, y_max)
                axis.set_ylim(y_min, y_max)
        except ValueError as exc:
            self._set_status("Panel scale not applied:", str(exc))
            return
        if draw:
            self.canvas.draw_idle()

    def _record_visibility_if_needed(self, config, continuum, peak_lag_bin: float) -> None:
        if self.record_visibility_mode.get() != "on":
            return

        try:
            interval_s = parse_float_text(
                self._committed_visibility_inputs["visibility_record_interval_s"],
                "Visibility record interval",
            )
            now = monotonic()
            if interval_s > 0 and now - self._last_visibility_record_time < interval_s:
                return

            output_path = Path(
                self._committed_visibility_inputs["visibility_output_path"]
            ).expanduser()
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not output_path.exists() or output_path.stat().st_size == 0

            timestamp = datetime.now(timezone.utc).isoformat()
            with output_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=VISIBILITY_CSV_FIELDS)
                if write_header:
                    writer.writeheader()
                writer.writerow(
                    {
                        "timestamp_utc": timestamp,
                        "observing_frequency_mhz": config.observing_frequency_mhz,
                        "intermediate_frequency_mhz": config.intermediate_frequency_mhz,
                        "bandwidth_mhz": config.bandwidth_mhz,
                        "bins": config.bins,
                        "averaging_blocks": config.averaging_blocks,
                        "baseline_east_m": config.baseline_east_m,
                        "baseline_north_m": config.baseline_north_m,
                        "baseline_up_m": config.baseline_up_m,
                        "source_ra_deg": config.ra_deg,
                        "source_dec_deg": config.dec_deg,
                        "observer_lat_deg": config.observer_lat_deg,
                        "observer_lon_deg": config.observer_lon_deg,
                        "fringe_stop_mode": config.fringe_stop_mode,
                        "frequency_sideband": config.frequency_sideband,
                        "instrumental_delay_ns": config.instrumental_delay_ns,
                        "instrumental_phase_deg": config.instrumental_phase_deg,
                        "lag_bin": peak_lag_bin,
                        "visibility_real": continuum.visibility.real,
                        "visibility_imag": continuum.visibility.imag,
                        "visibility_amp": continuum.amplitude,
                        "visibility_phase_rad": continuum.phase_rad,
                        "visibility_snr": continuum.snr,
                        "visibility_noise_floor": continuum.noise_floor,
                        "clean_bins": continuum.bins_used,
                        "edge_bins_excluded": continuum.edge_bins_excluded,
                    }
                )
            self._last_visibility_record_time = now
        except OSError as exc:
            self.record_visibility_mode.set("off")
            self._set_status("Visibility recording stopped:", str(exc))

    def _save_settings(self) -> None:
        settings = {
            "source_mode": self.source_mode.get(),
            "target_mode": self.target_mode.get(),
            "fringe_stop_mode": self.fringe_stop_mode.get(),
            "frequency_sideband": self.frequency_sideband.get(),
            "spectrum_plot_mode": self.spectrum_plot_mode.get(),
            "phase_plot_mode": self.phase_plot_mode.get(),
            "interferogram_autoscale": self.interferogram_autoscale.get(),
            "spectrum_autoscale": self.spectrum_autoscale.get(),
            "east_autocorr_autoscale": self.east_autocorr_autoscale.get(),
            "west_autocorr_autoscale": self.west_autocorr_autoscale.get(),
            "east_auto_spectrum_autoscale": self.east_auto_spectrum_autoscale.get(),
            "west_auto_spectrum_autoscale": self.west_auto_spectrum_autoscale.get(),
            "fringe_iq_autoscale": self.fringe_iq_autoscale.get(),
            "fringe_time_window_minutes": f"{self._fringe_time_window_minutes:.0f}",
            "continuum_snr_mode": self.continuum_snr_mode.get(),
            "record_visibility_mode": self.record_visibility_mode.get(),
        }
        settings.update(self._committed_inputs)
        settings.update(self._committed_continuum_inputs)
        settings.update(self._committed_visibility_inputs)
        settings.update(self._plot_scale_inputs)
        try:
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError as exc:
            self._set_status("Settings not saved:", str(exc))

    def _close(self) -> None:
        self._save_settings()
        self.stop()
        self.destroy()


def smooth_line(values: np.ndarray, bins: int) -> np.ndarray:
    """Return a moving-average envelope for a plotted spectrum line."""

    if bins <= 1 or values.size < 2:
        return values
    width = min(int(bins), values.size)
    kernel = np.ones(width, dtype=np.float64) / width
    return np.convolve(values, kernel, mode="same")


def format_fixed_lines(lines: tuple[str, ...], line_count: int) -> str:
    expanded: list[str] = []
    for line in lines:
        parts = str(line).splitlines()
        expanded.extend(parts if parts else [""])
    expanded = expanded[:line_count]
    expanded.extend([" "] * (line_count - len(expanded)))
    return "\n".join(expanded)


def format_status_text(*lines: str) -> str:
    return format_fixed_lines(lines, STATUS_LINE_COUNT)


def apply_display_fringe_stop(visibility: complex, model) -> complex:
    """Remove geometric phase from an East * conj(West) visibility."""

    return visibility * np.exp(1j * model.phase_rad)


def estimate_phase_rate_deg_s(times_s: np.ndarray, phase_rad: np.ndarray) -> float | None:
    times = np.asarray(times_s, dtype=np.float64)
    phases = np.asarray(phase_rad, dtype=np.float64)
    if times.size < 2 or phases.size < 2 or times.shape != phases.shape:
        return None

    duration_s = float(times[-1] - times[0])
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return None

    phase_deg = np.degrees(np.unwrap(phases))
    valid = np.isfinite(times) & np.isfinite(phase_deg)
    if np.count_nonzero(valid) < 2:
        return None

    valid_times = times[valid]
    valid_phase_deg = phase_deg[valid]
    centered_times = valid_times - float(np.mean(valid_times))
    denominator = float(np.dot(centered_times, centered_times))
    if denominator <= 0.0:
        return None
    centered_phase = valid_phase_deg - float(np.mean(valid_phase_deg))
    return float(np.dot(centered_times, centered_phase) / denominator)


def format_stopped_phase_label(rate_deg_s: float | None) -> str:
    rate_text = format_phase_rate_value(rate_deg_s)
    if rate_text == "--":
        return "Stopped phase (-- deg/s)"
    return f"Stopped phase ({rate_text} deg/s)"


def format_phase_rate_value(rate_deg_s: float | None) -> str:
    if rate_deg_s is None or not np.isfinite(rate_deg_s):
        return "--"
    return f"{rate_deg_s:+.3f}"


def resolve_automatic_target_coordinates(
    target_mode: str,
    raw_inputs: dict[str, str],
    when: datetime | None = None,
):
    if target_mode == MANUAL_TARGET_SOURCE:
        return None

    observer_lat_deg = parse_float_text(raw_inputs["observer_lat_deg"], "Observer latitude")
    observer_lon_deg = parse_float_text(raw_inputs["observer_lon_deg"], "Observer longitude")
    return target_coordinates(
        target_mode,
        when,
        observer_lat_deg=observer_lat_deg,
        observer_lon_deg=observer_lon_deg,
    )


def apply_target_display_rounding(raw_inputs: dict[str, str], coords) -> dict[str, str]:
    adjusted = dict(raw_inputs)
    if coords is not None:
        adjusted["ra_hours"] = format_ra_hours(coords.ra_deg / 15.0)
        adjusted["dec_deg"] = f"{coords.dec_deg:.4f}"
    return adjusted


def runtime_configs_match(
    config: ObservationConfig,
    latest_config: ObservationConfig | None,
    target_mode: str,
) -> bool:
    if latest_config is None:
        return False
    if target_mode == MANUAL_TARGET_SOURCE:
        return config == latest_config
    return replace(config, ra_deg=0.0, dec_deg=0.0) == replace(
        latest_config,
        ra_deg=0.0,
        dec_deg=0.0,
    )


def format_runtime_status_text(averaging_status: str, status: dict[str, object]) -> str:
    if not status:
        return format_status_text(
            "Running backend.",
            averaging_status,
            "Backend status pending.",
        )

    if "queued" not in status and "chunks" not in status:
        return format_status_text(
            f"Running backend. {averaging_status}",
            f"Processed {status.get('processed', 0)}, bins {status.get('active_bins', '--')}",
            (
                f"Smooth {status.get('active_averaging_blocks', '--')}, "
                f"stale {status.get('dropped_results', 0)}"
            ),
        )

    return format_status_text(
        f"Running backend. {averaging_status}",
        (
            f"B210 q {status.get('queued', 0)}, "
            f"chunks {status.get('chunks', 0)}, drop {status.get('dropped', 0)}"
        ),
        (
            f"FFT {status.get('reads', 0)}, bins {status.get('active_bins', '--')}, "
            f"smooth {status.get('active_averaging_blocks', '--')}"
        ),
        (
            f"Stale {status.get('dropped_results', 0)}, "
            f"ovf {status.get('overflows', 0)}, to {status.get('timeouts', 0)}"
        ),
    )


def format_visibility_status(continuum) -> str:
    if continuum is None:
        return "\n".join(
            (
                "Visibility: --",
                "Re --, Im --",
                "Amp --, Phase -- rad",
                "SNR --",
            )
        )
    return "\n".join(
        (
            "Visibility:",
            f"Re {continuum.visibility.real:.4g}, Im {continuum.visibility.imag:.4g}",
            f"Amp {continuum.amplitude:.4g}, Phase {continuum.phase_rad:.4f} rad",
            f"SNR {continuum.snr:.2f}",
        )
    )


def format_fringe_model_status(
    model,
    raw_visibility: complex | None,
    stopped_visibility: complex | None,
    stopped_phase_rate_deg_s: float | None = None,
) -> str:
    if model is None:
        return "\n".join(
            (
                "Fringe model: --",
                "Delay -- ns",
                "Phase -- deg",
                "Rate -- Hz (-- deg/s)",
                "Raw vis phase -- deg",
                "Stopped phase -- deg, rate -- deg/s",
            )
        )

    delay_ns = model.delay_s * 1_000_000_000.0
    model_phase_deg = wrap_degrees(np.degrees(model.phase_rad))
    rate_hz = model.phase_rate_rad_s / (2.0 * np.pi)
    rate_deg_s = np.degrees(model.phase_rate_rad_s)
    if raw_visibility is None or stopped_visibility is None:
        raw_phase_text = "--"
        stopped_phase_text = "--"
    else:
        raw_phase_text = f"{wrap_degrees(np.degrees(np.angle(raw_visibility))):+.1f}"
        stopped_phase_text = f"{wrap_degrees(np.degrees(np.angle(stopped_visibility))):+.1f}"
    stopped_rate_text = format_phase_rate_value(stopped_phase_rate_deg_s)
    return "\n".join(
        (
            f"Fringe model {model.when_utc.strftime('%H:%M:%S')} UTC",
            f"Delay {delay_ns:+.2f} ns",
            f"Phase {model_phase_deg:+.1f} deg",
            f"Rate {rate_hz:+.4f} Hz ({rate_deg_s:+.1f} deg/s)",
            f"Raw vis phase {raw_phase_text} deg",
            f"Stopped phase {stopped_phase_text} deg, rate {stopped_rate_text} deg/s",
        )
    )


def fringe_reset_signature(
    config: ObservationConfig,
    target_mode: str,
    source_mode: str,
) -> tuple[object, ...]:
    signature = (
        source_mode,
        target_mode,
        config.observing_frequency_mhz,
        config.observer_lat_deg,
        config.observer_lon_deg,
        config.baseline_east_m,
        config.baseline_north_m,
        config.baseline_up_m,
        config.fringe_stop_mode,
        config.frequency_sideband,
        config.instrumental_delay_ns,
        config.instrumental_phase_deg,
    )
    if target_mode == MANUAL_TARGET_SOURCE:
        signature += (config.ra_deg, config.dec_deg)
    return signature


def autoscale_positive_axis(axis, values: np.ndarray) -> None:
    if values.size == 0:
        axis.set_ylim(0, 1.0)
        return
    maximum = float(np.nanmax(values))
    if not np.isfinite(maximum) or maximum <= 0.0:
        maximum = 1e-6
    axis.set_ylim(0, maximum * 1.15)


def autoscale_symmetric_axis(axis, values: np.ndarray) -> None:
    if values.size == 0:
        axis.set_ylim(-1.0, 1.0)
        return
    maximum = float(np.nanmax(np.abs(values)))
    if not np.isfinite(maximum) or maximum <= 0.0:
        maximum = 1e-6
    axis.set_ylim(-maximum * 1.15, maximum * 1.15)


def autoscale_phase_axis(axis, values: np.ndarray) -> None:
    if values.size == 0:
        axis.set_ylim(-180.0, 180.0)
        return
    maximum = float(np.nanmax(np.abs(values)))
    if not np.isfinite(maximum) or maximum <= 0.0:
        maximum = 180.0
    maximum = max(180.0, maximum)
    axis.set_ylim(-maximum * 1.10, maximum * 1.10)


def autoscale_plot_axis(axis, values: np.ndarray, symmetric: bool = False) -> None:
    if symmetric:
        autoscale_symmetric_axis(axis, values)
    else:
        autoscale_positive_axis(axis, values)


def autoscale_button_label(variable: tk.StringVar, compact: bool = False) -> str:
    if compact:
        return "Auto" if variable.get() == "on" else "Man"
    return "Auto On" if variable.get() == "on" else "Auto Off"


def autoscale_button_color(variable: tk.StringVar) -> str:
    return "#b6d7a8" if variable.get() == "on" else "#f4cccc"


def plot_control_label(name: str) -> str:
    labels = {
        "interferogram": "Interferogram",
        "spectrum": "Cross-corr spectrum",
        "east_autocorr": "East autocorr",
        "west_autocorr": "West autocorr",
        "east_auto_spectrum": "East spectrum",
        "west_auto_spectrum": "West spectrum",
        "fringe_time": "Fringe I/Q",
    }
    return labels[name]


def parse_scale_value(value: str) -> float:
    parsed = float(value.strip())
    if not np.isfinite(parsed):
        raise ValueError("Scale limits must be finite numbers.")
    return parsed


def parse_float_text(value: str, label: str) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not np.isfinite(parsed):
        raise ValueError(f"{label} must be finite.")
    return parsed


def format_no_decimal(value: float) -> str:
    return f"{value:.0f}"


def parse_ra_hours_text(value: str) -> float:
    text = value.strip().lower()
    if not text:
        raise ValueError("Target RA must not be empty.")
    if any(marker in text for marker in ("h", "m", "s")):
        text = text.replace("h", ":").replace("m", ":").replace("s", "")
    if ":" in text:
        parts = [part.strip() for part in text.split(":")]
        if not 1 <= len(parts) <= 3 or any(part == "" for part in parts):
            raise ValueError("Target RA must be decimal hours or HH:MM:SS.")
        hours = float(parts[0])
        minutes = float(parts[1]) if len(parts) >= 2 else 0.0
        seconds = float(parts[2]) if len(parts) >= 3 else 0.0
        if hours < 0 or minutes < 0 or seconds < 0 or minutes >= 60 or seconds >= 60:
            raise ValueError("Target RA must be in the range 00:00:00 to <24:00:00.")
        value_hours = hours + minutes / 60.0 + seconds / 3600.0
    else:
        try:
            value_hours = float(text)
        except ValueError as exc:
            raise ValueError("Target RA must be decimal hours or HH:MM:SS.") from exc
    if not np.isfinite(value_hours) or not 0.0 <= value_hours < 24.0:
        raise ValueError("Target RA must be in the range 00:00:00 to <24:00:00.")
    return value_hours


def format_ra_hours(value_hours: float) -> str:
    value_hours = value_hours % 24.0
    hours = int(value_hours)
    minutes_float = (value_hours - hours) * 60.0
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60.0
    if seconds >= 59.995:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        hours = (hours + 1) % 24
    return f"{hours:02d}:{minutes:02d}:{seconds:04.1f}"


def wrap_degrees(value: float) -> float:
    return ((value + 180.0) % 360.0) - 180.0


def clamp_fringe_window_minutes(value: float) -> float:
    return min(FRINGE_WINDOW_MINUTES_MAX, max(FRINGE_WINDOW_MINUTES_MIN, value))


def parse_fringe_window_minutes(value: str) -> float:
    try:
        parsed = parse_float_text(value, "Fringe time span")
    except ValueError:
        parsed = FRINGE_WINDOW_MINUTES_DEFAULT
    return clamp_fringe_window_minutes(parsed)


def validate_continuum_inputs(values: dict[str, str]) -> None:
    edge_percent = parse_float_text(values["continuum_edge_percent"], "Continuum edge exclude")
    rfi_sigma = parse_float_text(values["continuum_rfi_sigma"], "Continuum RFI sigma")
    if edge_percent < 0 or edge_percent >= 50:
        raise ValueError("Continuum edge exclude must be in the range 0 to <50 percent.")
    if rfi_sigma < 0:
        raise ValueError("Continuum RFI sigma must not be negative.")


def validate_visibility_inputs(values: dict[str, str]) -> None:
    output_path = values["visibility_output_path"].strip()
    if not output_path:
        raise ValueError("Visibility CSV path must not be empty.")
    interval_s = parse_float_text(values["visibility_record_interval_s"], "Visibility record interval")
    if interval_s < 0:
        raise ValueError("Visibility record interval must be 0 or greater.")


def validate_scale_limits(y_min: float, y_max: float) -> None:
    if y_min >= y_max:
        raise ValueError("Manual scale minimum must be less than maximum.")


def load_settings() -> dict[str, str]:
    settings = DEFAULT_SETTINGS.copy()
    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if isinstance(loaded, dict):
        if "ra_hours" not in loaded and "ra_deg" in loaded:
            try:
                settings["ra_hours"] = format_ra_hours(
                    parse_float_text(str(loaded["ra_deg"]), "Saved RA") / 15.0
                )
            except ValueError:
                settings["ra_hours"] = DEFAULT_SETTINGS["ra_hours"]
        for key, value in loaded.items():
            if key in settings:
                settings[key] = str(value)
    if settings["source_mode"] not in {"Simulator", "B210 / SoapySDR"}:
        settings["source_mode"] = DEFAULT_SETTINGS["source_mode"]
    if settings["target_mode"] not in TARGET_SOURCE_OPTIONS:
        settings["target_mode"] = DEFAULT_SETTINGS["target_mode"]
    if settings["fringe_stop_mode"] not in FRINGE_STOP_OPTIONS:
        settings["fringe_stop_mode"] = DEFAULT_SETTINGS["fringe_stop_mode"]
    if settings["frequency_sideband"] not in FREQUENCY_SIDEBAND_OPTIONS:
        settings["frequency_sideband"] = DEFAULT_SETTINGS["frequency_sideband"]
    for key in (
        "spectrum_plot_mode",
        "phase_plot_mode",
        "interferogram_autoscale",
        "spectrum_autoscale",
        "east_autocorr_autoscale",
        "west_autocorr_autoscale",
        "east_auto_spectrum_autoscale",
        "west_auto_spectrum_autoscale",
        "fringe_iq_autoscale",
        "continuum_snr_mode",
        "record_visibility_mode",
    ):
        if settings[key] not in {"on", "off"}:
            settings[key] = DEFAULT_SETTINGS[key]
    settings["fringe_time_window_minutes"] = (
        f"{parse_fringe_window_minutes(settings['fringe_time_window_minutes']):.0f}"
    )
    try:
        settings["ra_hours"] = format_ra_hours(parse_ra_hours_text(settings["ra_hours"]))
    except ValueError:
        settings["ra_hours"] = DEFAULT_SETTINGS["ra_hours"]
    for key in (
        "observing_frequency_mhz",
        "lnb_lo_frequency_mhz",
        "intermediate_frequency_mhz",
    ):
        try:
            settings[key] = format_no_decimal(parse_float_text(settings[key], key))
        except ValueError:
            settings[key] = DEFAULT_SETTINGS[key]
    try:
        lnb_lo_mhz = parse_float_text(settings["lnb_lo_frequency_mhz"], "LNB LO frequency")
        tune_if_mhz = parse_float_text(settings["intermediate_frequency_mhz"], "B210 tune IF")
        settings["observing_frequency_mhz"] = format_no_decimal(lnb_lo_mhz - tune_if_mhz)
    except ValueError:
        settings["observing_frequency_mhz"] = DEFAULT_SETTINGS["observing_frequency_mhz"]
    return settings


def main() -> None:
    app = InterferometryApp()
    app.mainloop()
