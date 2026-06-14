# Version History

## 0.5.1-iota - Instrumental Phase Calibration

- Added live GUI fields for instrumental delay in ns and instrumental phase in
  degrees.
- Applied the instrumental delay as a band-centred phase-slope correction, with
  RF sideband inversion respected.
- Applied the instrumental phase as a constant complex visibility rotation.
- Reset the correlator average when either instrumental calibration term is
  changed so old and new phase corrections are not mixed.
- Recorded the instrumental calibration values in visibility CSV output.

## 0.5.0-iota - Backend Fringe Stopping

- Added a new Iota app line with backend fringe stopping enabled by default.
- Added GUI controls for fringe stopping mode: Off, Display, or Backend.
- Added an RF sideband control so the per-bin sky-frequency mapping can use
  either LO - IF or LO + IF.
- Applied the geometric fringe-stopping phasor across every FFT bin before
  cross-spectrum averaging when Backend mode is selected.
- Preserved the integrated raw cross spectrum as a diagnostic so the phase
  panel can still compare raw and stopped phase behaviour.
- Added stream-relative sample indexing to source blocks so correction timing
  uses the block midpoint rather than GUI draw time.

## 0.4.12-theta - Stopped Phase Panel Rate

- Added the stopped-fringe phase-rate value to the left GUI fringe-model
  readout on the same line as the stopped phase value.
- Kept the stopped-phase plot legend rate readout in place.
- The panel rate follows the currently displayed stopped-phase time span.

## 0.4.11-theta - Stopped Phase Rate Readout

- Added a live stopped-fringe phase-rate readout in degrees/second to the
  stopped-phase plot legend.
- The rate is calculated from the unwrapped stopped phase across the currently
  displayed time span.
- Added tests for the stopped-phase rate estimator and plot-label formatting.

## 0.4.10-theta - Full Precision Solar-System Targets

- Kept full-precision Sun/Moon coordinates for the runtime configuration and
  fringe model while continuing to show rounded RA/DEC values in the GUI.
- Avoided unnecessary backend updates from normal automatic ephemeris drift so
  B210 streaming and averaging remain stable while the display model advances.
- Added tests covering rounded target display values and full-precision
  automatic target handling.

## 0.4.9-theta - Fringe Stop Sign Correction

- Corrected the display fringe-stopping sign for the `East * conj(West)`
  visibility convention used by the FX correlator.
- Updated the simulator phase convention to match the East/West channel labels
  and positive baseline direction.
- Added regression tests for broadband visibility phase sign and the display
  fringe-stop correction.

## 0.4.8-theta - Wrapped Stable Readouts

- Restored natural sizing for the always-visible readout panel so it no
  longer reserves a large blank block below the status text.
- Reworked runtime backend status into short fixed lines so B210 queue and
  FFT status remain readable in the left pane.
- Kept stable line counts for status, visibility, and fringe-model readouts
  so the controls do not jump as fields update.

## 0.4.7-theta - Stable Readout Panel

- Fixed the bottom-left status/readout panel height so the scrollable GUI
  controls no longer jump when readout text length changes.
- Gave visibility and fringe-model readouts fixed line counts so missing
  continuum updates no longer collapse the panel content.

## 0.4.6-theta - Moon Tracking Averaging Fix

- Stopped automatic Moon ephemeris drift from repeatedly resetting backend
  averaging and the fringe display history.
- Target changes still reset averaging once, but continuous Sun/Moon coordinate
  tracking now updates the model without restarting the smoothing cycle.

## 0.4.5-theta - Fringe Model Readout Layout

- Moved the raw/stopped phase legend to the left side of the stopped-fringe
  pane so it does not cover new data at the right edge.
- Moved status, visibility, and fringe-model readouts into a fixed left-side
  panel that remains visible while the parameter controls scroll.
- Reset fringe display history when target/model parameters change so Moon and
  manual RA/DEC switches visibly update the stopped-phase plot.

## 0.4.4-theta - RA Hours Display

- Changed the GUI target RA field from decimal degrees to hours format.
- Manual RA now accepts `HH:MM:SS`, `04h31m40s`, or decimal hours input and
  converts internally to degrees for the fringe model.
- Migrates old saved decimal-degree RA settings to hours on load.

## 0.4.3-theta - Topocentric Moon Coordinates

- Verified Sun/Moon RA/DEC against NASA/JPL Horizons reference values.
- Changed Moon target coordinates from geocentric to observer-topocentric
  RA/DEC when observer latitude/longitude are available.
- Improved the built-in lunar approximation with the largest perturbation
  terms so the GUI readout is close to Horizons for calibration use.

## 0.4.2-theta - Spectrum Panel Scaling

- Moved Cross-Correlation Spectrum manual Y-axis scaling out of the left GUI
  and into the spectrum plot pane.
- Reused the same compact Auto/Manual and min/max controls used by the other
  plot panes.

## 0.4.1-theta - Solar System Targets

- Added a Target dropdown with Manual RA/DEC, Sun, and Moon options.
- Sun/Moon modes calculate and display live RA/DEC values for the fringe model
  and backend configuration.
- Kept manual RA/DEC editing available for non-solar-system targets.

## 0.4.0-theta - Display Fringe Model

- Branched from stable Eta for the start of Theta development.
- Added a geometric fringe model readout showing predicted delay, phase, and
  phase rate for the configured source, baseline, location, and sky frequency.
- Added a display-only stopped phase trace as a live sanity check without
  changing the backend correlation or averaging path.
- Stored Theta settings separately from Eta settings.

## 0.3.16-eta - Fringe Control Alignment

- Moved the Fringe I/Q control stack left so its boxes align with the plot
  Y-axis.

## 0.3.15-eta - Fringe Control Simplification

- Removed the I/Q legend from the Fringe I/Q plot.
- Restored the Fringe I/Q Auto/Manual and Y-axis scale controls to the same
  size and font as the other plot controls.
- Placed the standard Fringe I/Q control stack at the top-left of the panel.

## 0.3.14-eta - Fringe Control Alignment

- Reduced the Fringe I/Q manual scale box width and font size.
- Moved the Fringe I/Q control stack left to align with the I/Q legend.

## 0.3.13-eta - Fringe Control Stack

- Stacked the Fringe I/Q Auto/Manual and manual Y-axis scale controls vertically
  under the I/Q legend without overlap.
- Used wider Fringe I/Q control boxes and a smaller control font for cleaner
  value display.

## 0.3.12-eta - Fringe Control Fit

- Repositioned the Fringe I/Q Auto/Manual and Y-axis scale controls into a
  compact horizontal row under the I/Q legend.
- Reduced control text size and widened the scale boxes so the values fit
  cleanly without overlapping.

## 0.3.11-eta - Stable Fringe Layout

- Moved the Fringe I/Q Auto/Manual and Y-axis scale controls to the left side
  of the Fringe I/Q panel below the I/Q legend.
- Treat this as the stable Eta version before moving future work to Theta.

## 0.3.10-eta - Fringe Time Controls

- Added a Time span slider under the Fringe I/Q plot with a selectable range
  from 10 to 180 minutes.
- Added compact Auto/Manual Y-axis scaling controls to the Fringe I/Q plot.
- Increased retained Fringe I/Q history to support the full 180-minute display
  window.

## 0.3.9-eta - Fringe I/Q Time Plot

- Added a rolling Fringe I/Q vs Time panel below the existing plot panes.
- The panel plots the real (I) and imaginary (Q) broadband visibility
  components, giving a live fringe trace for later fringe-stopping validation.
- Fringe history resets on app start and averaging reset, while the final trace
  remains visible after stop.

## 0.3.8-eta - Plot Graticules

- Added consistent major and minor graticules to every plot pane.
- Graticules are applied during GUI plot setup, so they are visible before
  start, while running, and after stop.

## 0.3.7-eta - Runtime Field Feedback

- Cleared stale backend plot results when runtime GUI parameters are changed.
- Added backend active FX bins and X-corr smoothing values to the status line
  so committed runtime changes can be confirmed while the app is running.
- Added keypad Enter support for committing GUI text fields.

## 0.3.6-eta - Antenna Spectra Panels

- Added East Antenna Spectrum and West Antenna Spectrum panels using the
  integrated autocorrelation-derived antenna power spectra.
- Moved interferogram manual Y-axis scaling into the realtime interferogram
  panel and removed those scale fields from the left GUI.
- Reduced the in-plot Auto and manual scale controls to a more compact size.

## 0.3.5-eta - Autocorrelation Panels

- Removed the global Apply Scales and Use Current Scales buttons.
- Moved Start and Stop near the top of the control panel above Observing freq.
- Added East Antenna and West Antenna autocorrelation lag panels.
- Added per-panel Auto On/Off buttons and manual Y-axis scale controls for the
  autocorrelation panels.

## 0.3.4-eta - Decoupled Interferogram Manual Scale

- Stopped copying the last autoscaled interferogram Y-axis limits into the
  manual scale fields when Auto is turned off.
- Turning Auto off now leaves the plot at its current displayed Y-axis range,
  while manual fields retain their existing values until the user edits them.

## 0.3.3-eta - Interferogram Autoscale Button

- Moved the interferogram autoscale control from the left GUI panel to a plot
  button at the top right of the realtime interferogram.
- Made the autoscale button visually indicate Auto On versus Auto Off.
- When autoscale is turned off, the current autoscaled Y-axis limits are kept
  and copied into the manual scale fields for further adjustment.

## 0.3.2-eta - Calculated Observing Frequency

- Branched Eta development from the corrected Epsilon baseline.
- Kept the Observing freq field visible, but made it read-only and calculated
  from LNB LO freq minus B210 tune IF.
- Added the LNB LO freq field between Observing freq and B210 tune IF.
- Changed Observing freq, LNB LO freq, and B210 tune IF defaults/display to
  whole-MHz values with no decimal point.

## 0.3.1-eta - Eta Identity Baseline

- Branched Eta from the frozen Epsilon visibility-recording baseline.
- Changed the app version suffix from Delta to Eta.
- Changed persisted GUI settings to use an Eta-specific settings file so Eta
  starts cleanly and does not inherit Delta/Zeta GUI settings.
- No functional GUI, correlator, backend, SDR, or documentation behaviour was
  changed in this baseline commit.

## 0.3.1-delta - Broadband Visibility Display and Recording

- Added realtime broadband visibility readout with real, imaginary, amplitude,
  phase, and SNR values.
- Added visibility recording controls for on/off, CSV output path, and recording
  interval.
- CSV visibility recording writes integrated broadband continuum visibility rows
  for post-processing.

## 0.3.0-delta - Process-Isolated Correlator Backend

- Moved SDR streaming, sample reading, FFT correlation, and averaging into a
  separate backend process.
- Changed the Tkinter GUI to receive reduced correlator products instead of
  reading raw B210 sample blocks directly.
- Added a bounded result queue so stale plot updates are dropped before they can
  slow down the streaming/correlation backend.
- Kept committed text-entry behavior: text fields apply only after Enter.
- Changed persisted settings to a Delta-specific settings file.

## 0.2.4-beta - Committed Inputs and Averaging Draw Throttle

- Text-entry GUI parameters now commit only when the user presses Enter in an
  entry field; partially typed values are no longer applied while running.
- Runtime config, continuum settings, scale settings, and saved settings now use
  the last committed text-entry values.
- Reduced B210 plot redraw rate while the cross-correlation average is refilling
  so GUI drawing is less likely to interrupt continuous hardware streaming.
- Added averaging fill percentage to the runtime status line.

## 0.2.3-beta - B210 Stream-First Backpressure

- Prioritized continuous B210 draining by dropping excess FFT blocks before
  they create Python copy and FFT backlog.
- Added bounded B210 queue controls so realtime display work cannot grow until
  it starves the hardware read thread.
- Increased default B210 hardware read chunk size to `262144` samples.
- Added `B210 queued FFT blocks` and `B210 FFT blocks/update` GUI fields.

## 0.2.2-beta - Large-Chunk B210 Streaming

- Changed the B210 reader thread to request larger continuous `readStream()`
  transfers instead of one hardware read per FFT block.
- Split each returned B210 chunk into FX-sized blocks inside the app so the
  correlator pipeline still receives normal block sizes.
- Added a `B210 stream chunk samples` GUI field, defaulting to `65536`, for
  tuning hardware read cadence independently of FX bin count.
- Restart B210 streaming cleanly when the live stream chunk size changes.

## 0.2.1-beta - Continuous B210 Streaming

- Added a dedicated B210 stream reader thread that continuously drains
  `readStream()` into a bounded block queue.
- Changed GUI/correlator processing to consume queued B210 blocks instead of
  directly pacing hardware reads from the GUI update loop.
- Added B210 queue, dropped-block, overflow, and timeout counters to runtime
  status output.
- Restart B210 streaming cleanly when live bandwidth, bin count, or device args
  change.

## 0.2.0-beta - Broadband Continuum SNR

- Branched from the alpha interferometer app for beta development.
- Added broadband continuum SNR mode that phase-aligns and coherently averages
  selected cross-spectrum bins at the detected lag.
- Added edge-channel exclusion and optional RFI outlier rejection for continuum
  bin selection.
- Added continuum visibility amplitude, phase, SNR, and clean-bin count readout.

## 0.1.8-dev - Interferogram Peak Marker and SNR

- Branched from the frozen `v0.1.7` baseline.
- Added a realtime peak marker on the interferogram.
- Added a realtime SNR estimate using the strongest lag bin and the median
  non-peak interferogram level.
- Added spectrum and phase plot radio-button visibility controls, with spectrum
  on and phase off by default.
- Added spectrum smoothing bins for the displayed spectrum envelope line.
- Added live GUI parameter updates while the app is running.
- Added persisted GUI settings loaded at startup.
- Added auto/manual Y-axis scale controls for the interferogram and spectrum
  plots.
- Updated default bandwidth to 30.72 MHz, FX bins to 2048, smoothing to 8196
  blocks, B210 gain to 70 dB, and B210 device args to `num_recv_frames=256`.

## 0.1.7 - Clear Cross-Correlation Smoothing Control

- Renamed the averaging GUI field to `X-corr smoothing blocks`.
- Show the active smoothing block count in the run status.

## 0.1.6 - GUI Averaging Control

- Added an averaging blocks GUI parameter for reducing correlation plot noise.
- Use the averaging value to set the FX correlator integration length.

## 0.1.5 - Updated 4800 MHz Default

- Set the default observing frequency to 4800 MHz.
- Kept the default B210 IF tune frequency at 1150 MHz.
- Kept the default east baseline at 6 m.

## 0.1.4 - Updated Observing Defaults

- Set the default observing frequency to 8500 MHz.
- Set the default B210 IF tune frequency to 1150 MHz.
- Set the default east baseline to 6 m.

## 0.1.3 - B210 Overflow Recovery

- Drain and integrate multiple B210 FFT blocks per GUI refresh so the SDR
  receive buffer is less likely to overflow.
- Treat individual B210 RX overflow reports as recoverable runtime events.

## 0.1.2 - B210 Timed Stream Start

- Start the two-channel B210 RX stream with a future hardware timestamp so UHD
  can align both channels.

## 0.1.1 - B210 Startup Diagnostics

- Switched B210 startup to manual gain instead of automatic gain mode.
- Added B210 gain, read timeout, and device argument GUI inputs.
- Added clearer B210 startup error messages that identify the failing setup step.
- Added B210 hardware troubleshooting notes.

## 0.1.0 - Initial FX Correlator Baseline

- Added Tkinter GUI for interferometry input parameters.
- Added two-input FX correlator with realtime integrated cross spectrum.
- Added lag-domain interferogram display.
- Added simulated two-antenna source with coordinate-based geometric delay.
- Added initial Ettus B210/SoapySDR source adapter.
- Added Ubuntu setup notes and dependency file.
