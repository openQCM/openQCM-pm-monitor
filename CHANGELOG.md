# Changelog

## [4.3.1] - 2026-04-17

### Serial I/O Consolidation (Robustness Overhaul)
Complete refactor of serial port coordination. Every read/write now passes through the shared `threading.Lock` — no more uncoordinated access from the main thread.

#### Phase 1 — Main thread serial I/O locked
- `_check_hardware()` (Gh command) wrapped in `with self._serial_lock:`
- `_read_flow_between_sweeps()` uses blocking acquire with 500ms timeout
- `_set_pump_speed()` uses blocking acquire with 3s timeout — pump commands no longer corrupt data during active sweeps
- `_send_command()` (console) uses blocking acquire with 3s timeout
- `reset_input_buffer()` calls at `_start_monitoring` / `_start_cycle` now locked
- GUI updates (cards, status) happen **outside** the critical section to minimize lock hold time

#### Phase 2 — SweepWorker non-blocking with timeout
- `do_sweep()` now uses `acquire(timeout=2.0)` instead of blocking acquire — if the serial is busy (e.g. TEC enable with 1s sleep), the sweep cycle is skipped cleanly with `sweep_error("Serial busy — sweep skipped")` and the next one is scheduled normally
- `do_find_peak()` uses 5s timeout — explicit user action deserves longer wait
- Fixed existing bug: `finally` now only releases the lock if `acquire` succeeded (flag `lock_acquired`)
- Eliminates potential deadlock when TEC enable is invoked during active monitoring

#### Phase 3 — Unified hardware polling in TECWorker
- TECWorker `_poll_cycle` now reads `Te? + E? + A? + G?` in a single locked session
- New signal `flow_updated(float)` emitted every 2s with current flow velocity
- Main window `flow_timer` (QTimer on GUI thread) removed entirely
- `_read_flow()` method removed; new slot `_on_flow_updated()` receives polling data
- TECWorker polling starts at connect (not only on TEC enable) — flow is monitored regardless of TEC state
- `[TEC]` terminal print suppressed when TEC is off (avoids spam during passive polling)

#### Phase 4 — Cleanup
- Deleted `openqcm/core/serial_manager.py` (dead code — the `QMutex` wasn't used by any worker)
- Removed all `SerialManager` imports and `set_connection` calls from `main_window.py`

### Bug Fixes
- Fixed `QObject::killTimer: Timers cannot be stopped from another thread` warning at disconnect: removed redundant `self.stop_polling()` call from `TECWorker.set_serial()` (it was already invoked via `_tec_invoke` queued call)
- Cleaned orphaned `apply_speed_btn` references and `_apply_pump_speed()` method
- Pump slider now sends `B{speed}` on `sliderReleased` only if pump is active (prevents accidental starts)

### Files Modified
- `openqcm/gui/main_window.py` — 8 serial-access points locked, `flow_timer` removed, `_on_flow_updated` slot added
- `openqcm/gui/sweep_worker.py` — timeout-based lock acquisition, improved finally block
- `openqcm/core/tec_worker.py` — unified polling (`G?` added), `flow_updated` signal, `set_serial` no longer self-calls `stop_polling`
- `openqcm/core/serial_manager.py` — **deleted** (dead code)

## [4.3.0] - 2026-04-15

### Particulate Concentration Measurement
- New concentration calculation: `C = Δm_total / V_sampled` (µg/m³)
- Two flow calibration modes in Pump & Flow panel:
  - **Analytical** (`Q = v × πD²/4`): configurable outlet diameter (mm)
  - **Calibrated** (`Q = K_cal × v`): configurable calibration factor
- Flow rate display (L/min) updates in real-time from FS3000 sensor velocity
- Average flow velocity accumulated during PUMP_ON phase for accurate volume calculation

### Robust Cycle Measurements (Median Filtering)
- REFERENCE and WAITING phases are now timed (wait_spin duration, default 120s)
- Sweep data accumulated during each phase; median of last 1/3 samples used as value
- First cycle: full REFERENCE phase (120s) to establish baseline
- Subsequent cycles: measurement from WAITING becomes new reference → skip REFERENCE wait
- `_median_last_third()` helper: takes last N/3 samples, computes median

### New Metric Cards
- Added **Flow Rate** card (L/min) and **Concentration** card (µg/m³)
- Renamed Flow card to **Velocity** (m/s)
- Mass and Concentration cards update only at end of each cycle (not real-time)
- Card order: Frequency, Dissipation, Mass, Concentration, Velocity, Flow Rate, Temperature

### Plot Layout Reorganization
- Row 1: Frequency + Dissipation vs Time (real-time)
- Row 2: Δm per Cycle | Concentration per Cycle (bar charts)
- Row 3: Δf/ΔD vs Cycle | Measured Freq/Diss vs Cycle (trend, median values)
- Row 4: Air Flow | Temperature

### GUI Tweaks
- Dissipation axis and card rounded to 1 decimal (ppm)
- Pump speed progress bar shows percentage (0–100%) instead of raw 0–255
- Default window size reduced to minimum (1024×600)
- Default timing: Pump On = 30s, Waiting = 120s

### Cycle CSV Logging
- Added `volume` (cm³) and `concentration` (µg/m³) columns to CYCLE_COLUMNS
- Flow logged as average velocity during PUMP_ON (not instantaneous)

### Bug Fixes
- Fixed `start_time is None` TypeError when sweep arrives before monitoring starts
- Fixed `flow_display` AttributeError (widget removed, references cleaned up)
- Fixed `shift_card` AttributeError (card removed, color-code block cleaned up)

## [4.2.0] - 2026-04-13

### Async Data Logging
- New `openqcm/core/data_logger.py`: dedicated daemon thread with `queue.Queue` for non-blocking CSV writes
- Every sweep row flushed to disk immediately without blocking GUI or acquisition
- Monitoring: single CSV file (frequency, dissipation, flow, temperature)
- Cycles: dual CSV logging — raw monitor (`_raw.csv`) + cycle measurements (Δf, ΔD, Δm per cycle)

### Measurement Cycle Improvements
- Shift and mass calculated only during active cycles (zero during monitoring)
- Each cycle re-acquires its own reference frequency/dissipation
- Mass displayed as per-cycle vertical bar chart (BarGraphItem) instead of time-series curve
- Cycle logger records: cycle number, frequency, dissipation, flow, temperature, Δf, ΔD, Δm

### GUI Left Panel Reorganization
- Split monolithic "Measurement" group into 4 logical sections:
  - **Plot Control** — Clear + Autoscale buttons
  - **Peak Detection** — Crystal, Search Range/Step, Find Peak
  - **Continuous Measurement** — Fine Range/Step, Start Monitor
  - **Pump Cycle Procedure** — Pump On/Waiting Time, cycle status, Start Cycle
- Removed 'Custom' crystal option (only 5 MHz and 10 MHz)
- Sampling time indicator moved standalone below cycle group, left-aligned

### Bug Fixes
- Fixed serial timeout after file dialog: `reset_input_buffer()` before first sweep (monitoring and cycles)
- Fixed `clear_btn` AttributeError after removing Reset button
- Fixed `freq_label` reference after removing Custom crystal option

## [4.1.1] - 2026-04-09

### Bug Fixes
- **Fixed SIGBUS crash (stack overflow):** `calculate_comprehensive_qcm_parameters` was defined twice in `sweep.py` — the "backward compatibility" wrapper at line 908 called itself infinitely, shadowing the real implementation at line 439. Removed the duplicate.
- **Fixed `-3dB dissipation NameError:** `baseline` and `noise_std` variables referenced in return dict but removed with sliding window cleanup. Removed stale references.
- **Fixed spurious "TEC Error" during monitoring:** firmware metadata always sends `error=1` when TEC is off. GUI now ignores `tec_error` from sweep metadata (real errors come from TEC polling `E?`).
- **Fixed transient "TEC Error" on enable:** added 1s stabilisation delay after X1 command + 2-cycle grace period ignoring error register.

### Threading Robustness
- Added `@pyqtSlot()` decorators to `SweepWorker.do_sweep()` and `do_find_peak()`
- Replaced `QTimer.singleShot(0, callable)` with `QMetaObject.invokeMethod(Qt.QueuedConnection)` for cross-thread sweep dispatch
- Added explicit `Qt.QueuedConnection` to all cross-thread signal connections (sweep worker, TEC worker)
- Serial coordination upgraded from acquire/release pattern to `threading.Lock` mutex shared between SweepWorker and TECWorker

### TEC Enable Sequence Simplified
- Removed PID parameter commands (C/P/I/D) from enable sequence — only sends X1 + T{setpoint}
- Polling starts automatically after enable with stabilisation delay (all on worker thread)

### Cleanup
- Removed sliding window remnants (`baseline`, `noise_std` from dissipation return dict)
- Fixed incorrect dissipation formula in `main_window.py` docstring (was `f0/(f_max-f_min) 3-sigma`, now `Δf₋₃dB/f₀`)
- Removed sweep debug prints from terminal output

## [4.1.0] - 2026-04-08

### TEC Worker Thread (Major Refactor)
- New `openqcm/core/tec_worker.py`: dedicated QThread for all TEC serial communication
- `temperature_widget.py` rewritten as pure GUI — zero serial I/O, zero `time.sleep()`
- Serial coordination via acquire/release pattern:
  - `acquire_serial()` called before every sweep — stops TEC polling, blocks commands
  - `release_serial()` called after sweep — executes queued commands, restarts polling
  - TEC commands (enable, disable, set temp, reset) queued automatically during sweeps
- All TEC calls from main thread use `QMetaObject.invokeMethod` (QueuedConnection) to avoid cross-thread QObject creation
- TEC polling (Te? + E? + A?) runs only when system is IDLE and TEC is enabled
- During monitoring: temperature comes from sweep metadata, no polling needed
- Eliminates all GUI freezes caused by `time.sleep()` on main thread (was up to 1.5s during TEC reset)

### Sweep Scheduling Rewrite
- Removed periodic `QTimer` for monitoring sweeps
- Sweeps now chained: `_on_sweep_finished` triggers next sweep via `QTimer.singleShot(100ms)`
- Removed `Time Interval` spinbox control (no longer needed)
- Constant sweep rate = sweep duration + 100ms inter-sweep delay
- Added "Actual interval" label in GUI showing real time between acquisitions

### Bug Fixes
- Fixed `numpy.float64` TypeError: `range()` received float from spline interpolation — added `int()` casts
- Fixed peak index out of bounds on interpolated signal
- Fixed alternating 25°C/0°C temperature readings: `reset_input_buffer()` was flushing valid responses between queries
- Fixed TEC polling starting automatically on connect (now starts only on Temperature On)
- Fixed serial port contention: TEC commands during sweep caused "multiple access on port" errors

### Cleanup
- Reduced terminal output: removed verbose debug prints from TEC worker, sweep worker, serial I/O
- Only essential output remains: sweep results `[SWEEP]`, TEC state changes `[TEC]`, errors `[ERROR]`

## [4.0.0] - 2026-03-26

### Project Restructure
- Reorganized from 4 flat Python files into a proper `openqcm/` package
- Extracted constants, styles, widgets, and workers into separate modules
- Created entry point `run.py` for clean application launch
- Added `requirements.txt` and `.gitignore`
- Moved firmware into `firmware/Firmware-QCM_aerosol/` (Arduino IDE requires folder name = .ino name)
- Moved `openqcm_resonance_config.json` to `openqcm/data/`

### New Package Structure
```
openqcm/
├── __init__.py              # Package info, version
├── constants.py             # COLORS, CRYSTAL_OPTIONS, Sauerbrey constants
├── config.py                # Crystal configuration presets
├── core/
│   ├── sweep.py             # OpenQCMSweepEnhanced controller
│   ├── serial_manager.py    # Thread-safe serial communication
│   └── tec_worker.py        # TECWorker (dedicated QThread)
├── gui/
│   ├── main_window.py       # OpenQCMAerosolGUI main window
│   ├── styles.py            # Global stylesheet
│   ├── metric_card.py       # MetricCard widget
│   ├── sweep_worker.py      # SweepWorker + CycleState enum
│   └── temperature_widget.py # TEC control widget (pure GUI)
└── data/
    └── resonance_config.json
```

### Measurement Cycle State Machine
- Implemented particulate deposition cycle: IDLE → REFERENCE → PUMP_ON → WAITING → MEASURE
- Continuous sweeps run throughout the entire cycle
- State machine controls pump on/off timing and records Δf/ΔD per cycle
- Elapsed time indicator with countdown for timed states
- Prominent colored state label in Measurement panel
- Δf/ΔD vs Cycle dual-axis plot

### GUI Improvements
- Uniform neutral gray button style across all widgets (#757575/#212121)
- Uniform QGroupBox title style (removed per-widget colored overrides)
- Dissipation displayed in PPM (parts per million) instead of raw values
- Dissipation card added to metric cards row (Frequency → Dissipation → Mass → Flow → Temp)
- Sweep tab: plots stacked vertically (Amplitude above, Phase below)
- Monitoring tab: 3 plot rows — Freq+Diss, Temp+Flow, Δf/ΔD Cycle + Mass
- Hidden unused UI elements: SNR plot, QCM-D analysis, shift/Q-factor cards
- Removed legacy "Read" buttons from temperature and flow displays
- Temperature buttons renamed to "Temperature On" / "Temperature Off"
- Quit confirmation dialog on window close
- PID controls hidden in temperature widget

### Bug Fixes
- Fixed cycle stuck in "acquiring reference": moved cycle hook before early-return in `_on_sweep_finished`
- Fixed flow not reading during measurement cycles: added `_read_flow_between_sweeps()` fallback when sweep metadata is unavailable
- Fixed temperature setpoint not updating during monitoring/cycle: queued `_set_temperature` via `process_pending_commands()` to avoid serial conflicts
- Fixed dissipation showing "0.00": converted to PPM (×1e6) for meaningful display

## [3.2.0] - 2025-01-20

### Initial Version
- Real-time frequency and dissipation monitoring
- QCM-D analysis with Sauerbrey mass calculation
- Pump and flow control
- TEC temperature control with PID parameters
- Serial communication with Teensy 4.0 firmware
- Sweep and peak finding functionality
