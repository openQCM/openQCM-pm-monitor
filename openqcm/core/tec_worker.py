#!/usr/bin/env python3
"""
TEC Worker Thread for openQCM Aerosol
======================================

Handles all serial communication with the MTD415T TEC controller
on a dedicated QThread, keeping the GUI responsive.

Commands supported (firmware v0.2.1-PM):
  Te? → actual temperature (mK)
  T?  → setpoint (mK), Txxxxx → set setpoint
  X1  → enable TEC, X0 → disable TEC
  E?  → error register
  A?  → TEC current (mA)
  C/P/I/D → PID parameters

Serial coordination:
  The serial port is shared with SweepWorker. A threading.Lock (serial_lock)
  is shared between both workers. Any serial I/O must hold the lock.
  This guarantees mutual exclusion without race conditions.

Author: Novaetech S.r.l. / openQCM Team
"""

import time
import threading
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot


class TECWorker(QObject):
    """
    Worker that runs on a dedicated QThread.
    All serial I/O (including time.sleep) happens here — never on the main thread.
    """

    # ── Signals (delivered to main thread) ──────────────────────────
    readings_updated = pyqtSignal(float, int, int, float)
    #                              temp_c, status, error, current_mA
    flow_updated = pyqtSignal(float)
    #                         flow velocity (m/s)
    command_done = pyqtSignal(str, bool, str)
    #                         command, success, message
    error_occurred = pyqtSignal(str)

    # Polling interval (ms)
    POLL_INTERVAL = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.serial_connection = None
        self._serial_lock = None  # threading.Lock shared with SweepWorker
        self._polling = False
        self._poll_timer = None

        # TEC state (tracked on worker thread)
        self._tec_enabled = False
        self._ignore_errors_cycles = 0
        self._last_logged_status = None  # for change-only [TEC] polling print
        self._pid_params = {'C': 50, 'P': 500, 'I': 50, 'D': 300}
        self._setpoint_c = 25.0
        self._start_polling_after_enable = False

    # ── Serial connection ───────────────────────────────────────────

    def set_serial_lock(self, lock):
        """Set the shared serial lock (called from main_window at setup)."""
        self._serial_lock = lock

    @pyqtSlot(object)
    def set_serial(self, serial_obj):
        """Receive serial connection from main window.

        Note: caller is responsible for calling stop_polling via QMetaObject
        (queued) before passing None — we must not call stop_polling here
        because this method may run on the main thread, and the poll timer
        lives on the worker thread (Qt rejects cross-thread timer control).
        """
        self.serial_connection = serial_obj

    # ── Polling ─────────────────────────────────────────────────────

    @pyqtSlot()
    def start_polling(self):
        """Start periodic hardware readings (Te? + E? + A? + G?)."""
        if self._polling:
            return
        self._polling = True
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._poll_cycle)
        self._poll_timer.start(self.POLL_INTERVAL)

    @pyqtSlot()
    def stop_polling(self):
        """Stop periodic TEC readings."""
        self._polling = False
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()

    def _poll_cycle(self):
        """One polling cycle: read temperature, error, current, flow. Runs on worker thread."""
        if not self.serial_connection or not self._serial_lock:
            return

        # Try to acquire lock — if sweep is running, skip this cycle
        if not self._serial_lock.acquire(blocking=False):
            return

        try:
            # Flush stale data ONCE at start of cycle
            self.serial_connection.reset_input_buffer()

            temp_mk = self._send_query('Te?')
            temp_c = temp_mk / 1000.0 if temp_mk is not None else -999.0

            error_val = self._send_query('E?')
            error = int(error_val) if error_val is not None else 0

            current_val = self._send_query('A?')
            current_mA = float(current_val) if current_val is not None else 0.0

            # Flow sensor reading (G? returns velocity in m/s)
            flow_val = self._send_query('G?')
            flow = flow_val if (flow_val is not None and 0 <= flow_val <= 20) else None

            if self._ignore_errors_cycles > 0:
                self._ignore_errors_cycles -= 1
                error = 0

            status = self._determine_status(temp_c, error)
            # Print only when status changes (avoids 1 line every 2s spam)
            if self._tec_enabled and status != self._last_logged_status:
                print(f"[TEC] Te={temp_c:.1f}°C  E={error}  A={current_mA:.1f}mA  status={status}")
                self._last_logged_status = status
            self.readings_updated.emit(temp_c, status, error, current_mA)
            if flow is not None:
                self.flow_updated.emit(flow)

        except Exception as e:
            print(f"[TEC] Poll error: {e}")
            self.error_occurred.emit(str(e))
        finally:
            self._serial_lock.release()

    def _determine_status(self, temp_c, error):
        """Determine TEC status code from readings."""
        if not self._tec_enabled:
            return 0   # Inactive
        if error != 0:
            return -1  # Error
        if abs(temp_c - self._setpoint_c) < 0.5:
            return 2   # In target
        return 1       # Approaching

    # ── TEC Commands ────────────────────────────────────────────────

    # Stabilisation delay after TEC enable (seconds).
    # The MTD415T error register may report transient values right after X1.
    TEC_STABILISE_DELAY = 1.0

    @pyqtSlot()
    def enable_tec(self):
        """Enable TEC: X1 + PID params + temperature setpoint, then start polling."""
        if not self.serial_connection:
            self.command_done.emit('X1', False, 'No serial connection')
            return

        with self._serial_lock:
            try:
                self._send_cmd('X1')
                self._tec_enabled = True
                self._ignore_errors_cycles = 2
                time.sleep(0.05)

                temp_mk = int(self._setpoint_c * 1000)
                self._send_cmd(f'T{temp_mk}')

                # Wait for TEC controller to stabilise before first poll
                time.sleep(self.TEC_STABILISE_DELAY)

                self.command_done.emit('X1', True,
                                      f'TEC enabled, T={self._setpoint_c}°C')
                print(f"[TEC] Enabled, setpoint={self._setpoint_c}°C")

            except Exception as e:
                self.command_done.emit('X1', False, str(e))
                print(f"[TEC] Enable error: {e}")

        # Start polling after enable (on worker thread, lock released)
        if getattr(self, '_start_polling_after_enable', False):
            self._start_polling_after_enable = False
            self.start_polling()

    @pyqtSlot()
    def disable_tec(self):
        """Disable TEC: X0."""
        if not self.serial_connection:
            self._tec_enabled = False
            self.command_done.emit('X0', False, 'No serial connection')
            return

        with self._serial_lock:
            try:
                self._send_cmd('X0')
                self._tec_enabled = False
                self.command_done.emit('X0', True, 'TEC disabled')
                print("[TEC] Disabled")

            except Exception as e:
                self.command_done.emit('X0', False, str(e))

    @pyqtSlot(float)
    def set_temperature(self, temp_c):
        """Set temperature setpoint: Txxxxx (in mK)."""
        self._setpoint_c = temp_c
        if not self.serial_connection:
            self.command_done.emit('T', False, 'No serial connection')
            return

        with self._serial_lock:
            try:
                temp_mk = int(temp_c * 1000)
                self._send_cmd(f'T{temp_mk}')
                self.command_done.emit('T', True,
                                      f'Setpoint={temp_c}°C ({temp_mk} mK)')
                print(f"[TEC] Setpoint={temp_c}°C")

            except Exception as e:
                self.command_done.emit('T', False, str(e))

    @pyqtSlot(dict)
    def set_pid(self, params):
        """Set PID parameters: C, P, I, D with delays."""
        self._pid_params.update(params)
        if not self.serial_connection:
            return

        with self._serial_lock:
            try:
                for param in ['C', 'P', 'I', 'D']:
                    if param in params:
                        self._send_cmd(f'{param}{params[param]}')
                        time.sleep(0.05)
                self.command_done.emit('PID', True, f'PID updated: {params}')

            except Exception as e:
                self.command_done.emit('PID', False, str(e))

    @pyqtSlot()
    def reset_tec(self):
        """Reset TEC: X0 → wait → X1. Blocking but on worker thread."""
        if not self.serial_connection:
            self.command_done.emit('RESET', False, 'No serial connection')
            return

        with self._serial_lock:
            try:
                self._send_cmd('X0')
                time.sleep(0.5)

                if self._tec_enabled:
                    time.sleep(1.0)
                    self._send_cmd('X1')
                    time.sleep(0.05)

                    for param in ['C', 'P', 'I', 'D']:
                        self._send_cmd(f'{param}{self._pid_params[param]}')
                        time.sleep(0.05)

                    temp_mk = int(self._setpoint_c * 1000)
                    self._send_cmd(f'T{temp_mk}')

                self.command_done.emit('RESET', True, 'TEC reset complete')
                print("[TEC] Reset complete")

            except Exception as e:
                self.command_done.emit('RESET', False, str(e))

    @pyqtSlot()
    def read_initial_values(self):
        """Read PID params + temperature on first connection."""
        if not self.serial_connection:
            return

        with self._serial_lock:
            try:
                temp_mk = self._send_query('Te?')
                if temp_mk is not None:
                    self._setpoint_c = temp_mk / 1000.0

                time.sleep(0.1)

                for param, key in [('C?', 'C'), ('P?', 'P'), ('I?', 'I'), ('D?', 'D')]:
                    time.sleep(0.05)
                    val = self._send_query(param)
                    if val is not None:
                        self._pid_params[key] = int(val)

                self.command_done.emit('INIT', True,
                                      f'T={self._setpoint_c:.1f}°C, PID={self._pid_params}')

            except Exception as e:
                self.command_done.emit('INIT', False, str(e))

    # ── Low-level serial I/O ────────────────────────────────────────
    # NOTE: These methods assume the caller already holds _serial_lock.

    def _send_cmd(self, cmd):
        """Send command, no response expected."""
        self.serial_connection.reset_input_buffer()
        self.serial_connection.write((cmd + '\n').encode())

    def _send_query(self, cmd, timeout=0.5):
        """
        Send command and read numeric response.
        Firmware v0.2.1 returns only numeric values (no debug strings).

        NOTE: Does NOT call reset_input_buffer() — caller must flush once
        before a sequence of queries to avoid clearing valid responses.
        """
        time.sleep(0.05)
        self.serial_connection.write((cmd + '\n').encode())
        time.sleep(0.1)

        start = time.time()
        while (time.time() - start) < timeout:
            if self.serial_connection.in_waiting:
                try:
                    line = self.serial_connection.readline().decode().strip()
                    if line:
                        if line.startswith('reading'):
                            continue
                        val = float(line)
                        return val
                except (ValueError, UnicodeDecodeError):
                    continue
            else:
                time.sleep(0.02)

        print(f"[TEC] No response for {cmd}")
        return None
