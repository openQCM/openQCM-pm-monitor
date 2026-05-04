# openQCM-pm-monitor

**PM Sampler with QCM-D Technology**

A Python desktop application for real-time atmospheric particulate matter sampling using Quartz Crystal Microbalance with Dissipation monitoring (QCM-D). Designed for the openQCM hardware platform with Teensy 4.0 firmware.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green)
![License](https://img.shields.io/badge/License-TBD-lightgrey)

## Features

- **Real-time monitoring** — Frequency, dissipation (PPM), deposited mass, concentration (µg/m³), velocity, flow rate (L/min) and temperature
- **Particulate concentration** — Volumetric flow calibration (analytical πD²/4 or calibrated K·v) and per-cycle concentration calculation
- **Robust measurements** — Median over the last third of timed REFERENCE/WAITING phases + temporal trimmed-mean (10% per tail) on the live signal
- **Automated cycles** — Multi-step state machine (Reference → Pump → Wait → next Pump) with measured pump duration for accurate volume
- **Auto TEC at cycle** — TEC turned on/off automatically when a cycle starts/stops, using the current setpoint from the Temperature widget
- **Rolling-window plots** — Real-time charts retain only the last hour (configurable); CSV logging keeps the full session
- **Async data logging** — Daemon thread + queue.Queue keeps disk I/O off the GUI thread; dual CSV during cycles (raw monitor + cycle results with `volume`, `concentration`)
- **Robust serial I/O** — Single shared `threading.Lock` coordinates SweepWorker, TECWorker and main-thread commands; pump commands have retry/timeout for guaranteed delivery
- **Sweep analysis** — Amplitude and phase response visualization with resonance peak finding (SG + spline + `find_peaks` with prominence + phase cross-check)
- **TEC temperature control** — Setpoint, PID parameters, ON/OFF with live status (status code translated to UI labels)
- **Mass calculation** — Sauerbrey equation for 5 MHz and 10 MHz crystals

## Requirements

- Python 3.8+
- openQCM Aerosol hardware with Teensy 4.0
- Serial connection (USB)

## Installation

```bash
git clone https://github.com/openQCM/openQCM-pm-monitor.git
cd openQCM-pm-monitor
pip install -r requirements.txt
```

## Usage

```bash
python run.py
```

### Quick Start

1. Select the serial port and click **Connect**
2. Choose crystal type (5 MHz / 10 MHz)
3. Click **Find Peak** to locate the resonance frequency
4. Optional: click **Start Monitor** for continuous real-time monitoring
5. Configure pump on/waiting times and click **Start Cycle** for automated particulate measurement (TEC is auto-enabled)

### Measurement Cycle

The cycle state machine automates particulate deposition measurement:

| State | Duration | Description |
|---|---|---|
| **REFERENCE** | `wait_spin` (only first cycle) | Accumulates sweep data; median of last 1/3 of samples → baseline `f₀`, `D₀` |
| **PUMP ON** | `pump_on_spin` | Pump runs at set speed; flow velocity samples accumulated for volume calculation |
| **WAITING** | `wait_spin` | Pump off, system stabilizes; median of last 1/3 → measured `f`, `D` |
| _(loop)_ | — | Measured values become new reference; cycle continues from PUMP ON |

After WAITING, the measured `(f, D)` becomes the new reference for the next cycle (no second timed REFERENCE wait). Each cycle records: Δf, ΔD, Δm (Sauerbrey), volume sampled, concentration.

## User Manual

A printable end-user manual is available in the [`doc/`](doc/) folder:

- [`doc/user_manual.pdf`](doc/user_manual.pdf) — printable PDF
- [`doc/user_manual.docx`](doc/user_manual.docx) — Word source for further edits
- [`doc/screenshots/`](doc/screenshots/) — GUI screenshots referenced by the manual

## Project Structure

```
openQCM-pm-monitor/
├── run.py                          # Application entry point
├── requirements.txt                # Python dependencies
├── CHANGELOG.md
├── data/                           # Default location for CSV logs
├── openqcm/
│   ├── __init__.py
│   ├── constants.py                # Colors, crystals, physical & flow constants, signal-processing params
│   ├── config.py                   # Crystal configuration presets
│   ├── core/
│   │   ├── sweep.py                # OpenQCMSweepEnhanced — sweep protocol, peak detection, dissipation
│   │   ├── tec_worker.py           # TECWorker (QThread) — TEC + flow polling on shared serial lock
│   │   └── data_logger.py          # DataLogger — async CSV writer (daemon thread + queue.Queue)
│   ├── gui/
│   │   ├── main_window.py          # OpenQCMAerosolGUI — main window, state machines, plots
│   │   ├── styles.py               # Native stylesheet, plot helpers, axis classes
│   │   ├── metric_card.py          # MetricCard widget
│   │   ├── sweep_worker.py         # CycleState enum + SweepWorker (QThread)
│   │   └── temperature_widget.py   # TemperatureControlWidget — pure GUI, no serial I/O
│   ├── icons/                      # Application icon + openQCM logo
│   └── data/
│       └── resonance_config.json   # Persisted resonance frequency
└── firmware/
    └── Firmware-QCM_aerosol/       # Teensy 4.0 Arduino IDE project
        ├── Firmware-QCM_aerosol.ino
        └── src/                    # ADC, temperature sensor libraries
```

## Hardware

- **QCM**: 5 MHz or 10 MHz AT-cut quartz crystal
- **Controller**: Teensy 4.0 with AD9851 DDS + AD8302 gain/phase detector
- **TEC**: MTD415T thermoelectric cooler controller
- **Pump**: DC motor with PWM speed control (0–255)
- **Flow sensor**: Renesas FS3000 — air velocity in m/s

## Serial Protocol

The Teensy firmware (v0.2.2-PM) communicates via USB serial at 115200 baud:

| Command | Description |
|---|---|
| `freq_start;freq_stop;freq_step` | Execute frequency sweep — returns N×`amp;phase` lines + final metadata `T;status;error;flow;pump_speed;s` |
| `B0` … `B255` | Set pump speed (0 stops, 30 minimum running) |
| `B?` | Query current pump speed |
| `G?` | Read current flow velocity (m/s) |
| `Gh` | Hardware status: `motor_ok;flow_ok` (1 or 0) |
| `Te?` / `T{mK}` | Read / set TEC temperature (millikelvin) |
| `T?` | Query setpoint |
| `X1` / `X0` | Enable / disable TEC |
| `A?` | Read TEC current (mA) |
| `E?` | Read MTD415T error register |
| `L{mA}` | Set TEC current limit (200–1500 mA) |
| `C/P/I/D` | Read or set PID parameters |
| `F` | Read firmware version (returns `0.2.2-PM`) |
| `m?`, `u?`, `c`, … | Pass-through to MTD415T (added in firmware v0.2.2-PM for diagnostic access) |

## Key Formulas

- **Dissipation** (-3 dB method): `D = Δf₋₃dB / f₀` (displayed in PPM = `D × 10⁶`)
- **Q-Factor**: `Q = f₀ / Δf₋₃dB`
- **Sauerbrey mass**: `Δm = -Δf × C × 10⁹` ng/cm²
  - C₅MHz = 17.7 × 10⁻⁹ Hz⁻¹·cm²
  - C₁₀MHz = 4.42 × 10⁻⁹ Hz⁻¹·cm²
- **Volumetric flow**: `Q = v × π·D² / 4` (analytical) or `Q = K_cal × v` (calibrated)
- **Sampled volume**: `V = Q × t_pump` (t_pump measured, not nominal)
- **Concentration**: `C = (Δm × A_quartz) / V` (µg/m³)

## CSV output format

CSV column names embed the SI / SI-derived unit as a suffix
(`<quantity>_<unit>`) so the file is self-describing in any tool
(Excel, pandas, R, MATLAB, …) without needing an external legend.

### Monitoring CSV (every sweep)

Created when **Start Monitor** is pressed, or as `<name>_raw.csv`
during a measurement cycle.

| Column | Unit | Notes |
|---|---|---|
| `date` | YYYY-MM-DD | local date |
| `time` | HH:MM:SS.fff | local time, millisecond precision |
| `relative_time_s` | s | seconds since the monitor session started |
| `frequency_Hz` | Hz | resonance frequency (smoothed: trimmed-mean of last 10 sweeps) |
| `dissipation_ppm` | ppm | D = Δf₋₃dB / f₀ × 10⁶ |
| `velocity_m_s` | m/s | FS3000 sensor reading (point velocity, **not** volumetric flow rate) |
| `temperature_C` | °C | from sweep metadata |

### Cycle CSV (one row per completed cycle)

Created alongside the monitoring CSV when a measurement cycle is started.

| Column | Unit | Notes |
|---|---|---|
| `date` | YYYY-MM-DD | local date of the cycle finalisation |
| `time` | HH:MM:SS.fff | local time of the cycle finalisation |
| `cycle` | count | sequential cycle number, starts at 1 |
| `frequency_Hz` | Hz | measured frequency (median over last 1/3 of WAITING-phase samples) |
| `dissipation_ppm` | ppm | measured dissipation (median over same samples) |
| `velocity_m_s` | m/s | average velocity during the PUMP_ON phase |
| `temperature_C` | °C | last reading at finalisation |
| `delta_f_Hz` | Hz | f − f₀ (measured − reference) |
| `delta_d_ppm` | ppm | D − D₀ |
| `delta_m_ng_cm2` | ng/cm² | Sauerbrey mass: Δm = −Δf × C × 10⁹ |
| `volume_cm3` | cm³ | sampled air volume = Q × t_pump (measured) |
| `concentration_ug_m3` | µg/m³ | C = (Δm × A_quartz) / V |

## Architecture Highlights

- **Three-thread design**: GUI main thread + SweepWorker (QThread) + TECWorker (QThread); single `threading.Lock` for serial coordination
- **Median-based filtering**: REFERENCE / WAITING phases compute the median over the last 1/3 of accumulated sweeps for noise rejection
- **Trimmed mean (10% / 10%)**: real-time monitoring values are smoothed with a 10-sweep ring buffer + trimmed mean — robust to occasional outliers without staircase artifacts
- **Time-based eviction**: real-time plot buffers retain exactly `MONITOR_WINDOW_SECONDS` of data regardless of sweep rate
- **Measured pump time**: cycle volume is computed from the actual pump-on duration (`time.time()` between B{speed} and B0 commands), making lock-wait jitter irrelevant to the result

## Author

**Novaetech S.r.l.** / openQCM Team

## License

TBD
