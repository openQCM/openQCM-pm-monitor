"""Sweep worker thread and measurement cycle state machine."""

from enum import Enum, auto
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class CycleState(Enum):
    IDLE = auto()
    REFERENCE = auto()
    PUMP_ON = auto()
    WAITING = auto()
    MEASURE = auto()


class SweepWorker(QObject):
    """
    Worker thread for QCM sweep operations.
    Runs serial communication in background, keeping GUI responsive.

    Uses a shared threading.Lock (serial_lock) to coordinate serial
    access with TECWorker.
    """

    sweep_finished = pyqtSignal(dict)
    sweep_error = pyqtSignal(str)
    peak_found = pyqtSignal(dict)
    peak_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.qcm = None
        self.sweep_params = {}
        self.peak_params = {}
        self.serial_lock = None  # threading.Lock shared with TECWorker

    def set_qcm(self, qcm):
        """Set QCM controller reference"""
        self.qcm = qcm

    @pyqtSlot()
    def do_sweep(self):
        """Execute sweep in worker thread.

        Non-blocking lock acquisition with 2s timeout: if serial is busy
        (e.g. TEC command in progress), skip this sweep cycle and emit error.
        The main window will schedule the next sweep normally.
        """
        if not self.qcm:
            self.sweep_error.emit("QCM not connected")
            return

        lock_acquired = False
        if self.serial_lock:
            lock_acquired = self.serial_lock.acquire(timeout=2.0)
            if not lock_acquired:
                self.sweep_error.emit("Serial busy — sweep skipped")
                return

        try:
            results = self.qcm.sweep_around_resonance(
                sweep_range=self.sweep_params.get('sweep_range', 10000),
                step_size=self.sweep_params.get('step_size', 10)
            )

            if results and results.get('num_points', 0) > 0:
                metadata = self.qcm.get_last_sweep_metadata()
                results['metadata'] = metadata
                self.sweep_finished.emit(results)
            else:
                n = results.get('num_points', 0) if results else 0
                self.sweep_error.emit(f"Sweep returned {n} points")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.sweep_error.emit(str(e))
        finally:
            if lock_acquired:
                self.serial_lock.release()

    @pyqtSlot()
    def do_find_peak(self):
        """Execute peak finding in worker thread.

        Find Peak is an explicit user action — wait up to 5s for the lock
        (longer than do_sweep since user expects a result, not a skip).
        """
        if not self.qcm:
            self.peak_error.emit("QCM not connected")
            return

        lock_acquired = False
        if self.serial_lock:
            lock_acquired = self.serial_lock.acquire(timeout=5.0)
            if not lock_acquired:
                self.peak_error.emit("Serial busy — Find Peak aborted")
                return

        try:
            result = self.qcm.find_resonance_peak(
                center_freq=self.peak_params.get('center_freq', 5000000),
                search_range=self.peak_params.get('search_range', 50000),
                search_step=self.peak_params.get('search_step', 100)
            )

            if result:
                self.peak_found.emit({
                    'resonance': result,
                    'sweep_data': self.qcm.last_sweep_data
                })
            else:
                self.peak_error.emit("No peak found")

        except Exception as e:
            self.peak_error.emit(str(e))
        finally:
            if lock_acquired:
                self.serial_lock.release()
