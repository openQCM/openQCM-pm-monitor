"""
Async Data Logger for openQCM Aerosol
======================================

Dedicated thread that writes measurement data to CSV incrementally.
Uses queue.Queue for thread-safe, non-blocking data transfer from
the main thread. Each row is flushed immediately to disk.

Author: Novaetech S.r.l. / openQCM Team
"""

import os
import csv
import queue
import threading


# Column names embed the SI / SI-derived unit as a suffix so any downstream
# tool (Excel, pandas, MATLAB, R, …) can read the file without an external
# legend. Naming follows the convention `<quantity>_<unit>` with ASCII-safe
# unit tokens (`_C` for °C, `_ug_m3` for µg/m³, `_ng_cm2` for ng/cm², ...).
LOG_COLUMNS = [
    'date', 'time', 'relative_time_s',
    'frequency_Hz', 'dissipation_ppm',
    'velocity_m_s', 'temperature_C',
]

CYCLE_COLUMNS = [
    'date', 'time', 'cycle',
    'frequency_Hz', 'dissipation_ppm',
    'velocity_m_s', 'temperature_C',
    'delta_f_Hz', 'delta_d_ppm', 'delta_m_ng_cm2',
    'volume_cm3', 'concentration_ug_m3',
]


class DataLogger:
    """Async CSV data logger backed by a daemon thread and queue.Queue."""

    def __init__(self, filepath, columns=None):
        self._filepath = filepath
        self._columns = columns or LOG_COLUMNS
        self._queue = queue.Queue()
        self._thread = None
        self._file = None

    @property
    def filepath(self):
        return self._filepath

    def start(self):
        """Open file, write header, start writer thread."""
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        self._file = open(self._filepath, 'w', newline='', encoding='utf-8')
        self._writer = csv.writer(self._file)
        self._writer.writerow(self._columns)
        self._file.flush()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, row_dict):
        """Put a measurement dict on the queue (non-blocking)."""
        self._queue.put_nowait(row_dict)

    def stop(self):
        """Signal shutdown, drain queue, close file."""
        if self._thread is None:
            return
        self._queue.put(None)  # sentinel
        self._thread.join(timeout=5)
        self._thread = None
        if self._file and not self._file.closed:
            self._file.close()
            self._file = None

    def _run(self):
        """Writer loop — runs on dedicated thread."""
        while True:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                # Sentinel received — drain remaining items then exit
                while not self._queue.empty():
                    try:
                        remaining = self._queue.get_nowait()
                        if remaining is not None:
                            self._write_row(remaining)
                    except queue.Empty:
                        break
                break

            self._write_row(item)

    def _write_row(self, row_dict):
        """Write a single row to CSV and flush."""
        row = [row_dict.get(col, '') for col in self._columns]
        self._writer.writerow(row)
        self._file.flush()
