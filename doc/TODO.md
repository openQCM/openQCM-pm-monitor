# TODO

## Production-readiness reminders

- Default cycle timing: pump-on 30 s and waiting 30 s for testing the correct cycle duration. Adjust as needed for production.
- The rolling-window plot is configured for 1 hour by default (`MONITOR_WINDOW_SECONDS = 3600` in `openqcm/constants.py`). Switch to a smaller value (e.g. 600 = 10 min) when iterating on the GUI.

## Pending work

### Firmware — TEC error register

The MTD415T can report `error=1` in the metadata stream when the TEC is OFF. The GUI already masks this case (status code returned as `Inactive` regardless of error bit), but ideally the firmware should not propagate spurious bits when `X0` is active. To investigate together with the firmware team.

### Pandas top-level import

`pandas` is imported at module level in `openqcm/gui/main_window.py` but used only in CSV/JSON export helpers. If pandas is not installed the application fails to start. Consider a lazy import with a clean error message.

### Sweep parameter validation

Sweep range and step are read from spinboxes without validation. Extreme combinations (large range + small step) generate hundreds of thousands of points, slowing the device and the post-processing. Add a UI check that warns the user when the point count exceeds a reasonable threshold.

## Recently completed (v4.3.x)

- Particulate concentration calculation (analytical πD²/4 and calibrated K·v modes)
- Median-based REFERENCE / WAITING phases (last 1/3 of accumulated samples)
- Trimmed-mean (10 %/10 %) temporal smoothing on the live signal — outlier-robust without staircase artifacts
- Rolling-window plot (configurable `MONITOR_WINDOW_SECONDS`)
- Async CSV logger (daemon thread + `queue.Queue`) with dual logging during cycles
- Serial I/O consolidation (single `threading.Lock` shared by all workers, pump-command guaranteed delivery)
- Auto-TEC at cycle start/stop
- Peak detection simplification (SG + spline + `find_peaks` with prominence + phase cross-check)
- MTD415T pass-through commands in firmware (`m?`, `u?`, `c`, …) for diagnostic access
