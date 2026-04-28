# Known Issues and Improvement Areas

Status as of v4.3.1 (2026-04-21). All structural issues identified during the package restructure (March–April 2026) have been resolved.

---

## Resolved

### ~~Duplicate `TECControlWidget` code~~
**Resolved.** The legacy `pump_flowmeter_control_v3.py` with the duplicated class is no longer part of the restructured project. The temperature widget lives in a single place: `openqcm/gui/temperature_widget.py`.

### ~~Two parallel worker systems~~
**Resolved.** The legacy `QCMWorker` is gone. Only `SweepWorker` remains, in `openqcm/gui/sweep_worker.py`, executed on a dedicated `QThread`.

### ~~Bare `except` clauses~~
**Resolved.** All `except` blocks specify the exception type (`Exception`, `ValueError`, …). No bare `except:` remains.

### ~~`time.sleep()` on the main thread~~
**Resolved (v4.1.0).** All TEC-related `time.sleep()` calls were moved into `TECWorker`, which runs on a dedicated `QThread`. `temperature_widget.py` is now pure GUI — no serial I/O, no sleeps.

### ~~Bypass of `set_serial_connection()`~~
**Resolved (v4.1.0).** The serial connection is passed only to `TECWorker` via `set_serial()`. The temperature widget no longer touches the serial port directly.

### ~~Cross-module access to private methods~~
**Resolved (v4.1.0).** `main_window.py` no longer calls private methods of the temperature widget. Communication happens through Qt signals: the widget emits `request_enable`, `request_disable`, etc. and receives data via slots `on_readings_updated`, `on_command_done`.

### ~~Dedicated TEC worker thread~~
**Resolved (v4.1.0, hardened in v4.1.1).** `TECWorker` in `openqcm/core/tec_worker.py` handles all TEC serial I/O on a dedicated `QThread`. Coordination with `SweepWorker` is via a shared `threading.Lock` mutex (introduced in v4.1.1, replacing the older acquire/release pattern).

### ~~Decentralised serial access~~
**Resolved (v4.3.1).** The Phase-1 work of the serial-I/O consolidation plan wraps every main-thread serial access (`_check_hardware`, `_set_pump_speed`, `_send_command`, `_read_flow_between_sweeps`, the `reset_input_buffer` calls in `_start_monitoring` / `_start_cycle`) in `with self._serial_lock:` or non-blocking acquires with timeout.

  - `SweepWorker` now acquires the lock with `timeout=2.0 s` (`5.0 s` for `do_find_peak`) and emits a clean `sweep_error` if the lock is busy — no more deadlocks.
  - Pump commands have a guaranteed-delivery strategy (3 attempts × 10 s timeout) to ensure that pump STOP at WAITING start is never silently dropped.
  - The legacy `serial_manager.py` was dead code and has been deleted.

### ~~Blocking serial fallback for flow~~
**Resolved (v4.3.1).** `_read_flow_between_sweeps()` is still kept as a metadata fallback, but it now uses `self._serial_lock.acquire(timeout=0.5)`. Real-time flow polling has been moved into `TECWorker._poll_cycle` (`Te? + E? + A? + G?` in a single locked session), emitted to the GUI via the `flow_updated(float)` signal. The GUI side `flow_timer` was removed entirely.

---

## Pending

| # | Issue | Priority | Notes |
|---|-------|----------|-------|
| 1 | `pandas` imported at module level | Low | Used only in CSV/JSON export helpers. Lazy import would let the app start without pandas installed. |
| 2 | Sweep parameter validation | Low | No UI guard on extreme range/step combinations that produce hundreds of thousands of points. |
| 3 | Firmware TEC error register | Low | The MTD415T returns spurious `error=1` when TEC is OFF. Already masked GUI-side (status forced to `Inactive`); ideal fix is in firmware. |

See `doc/TODO.md` for the live engineering backlog.
