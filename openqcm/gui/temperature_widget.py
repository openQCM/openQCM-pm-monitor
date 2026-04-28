#!/usr/bin/env python3
"""
Temperature Control Widget for openQCM Aerosol
==============================================

Pure GUI widget for TEC (Thermoelectric Cooler) control.
All serial I/O is handled by TECWorker on a dedicated QThread.

This widget:
- Displays temperature, status LED, TEC state
- Emits request signals when user clicks buttons
- Receives data updates from TECWorker or sweep metadata

Author: Novaetech S.r.l. / openQCM Team
Version: 2.0.0 (Refactored: no serial I/O, pure GUI)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFrame, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen

from openqcm.constants import COLORS


# =============================================================================
# STATUS LED COLORS (matching firmware RGB values)
# =============================================================================

TEC_COLORS = {
    'inactive': '#FFFFFF',      # White - TEC not active
    'in_target': '#008EC0',     # Blue openQCM
    'approaching': '#FF7D0A',   # Orange
    'error': '#FF0000',         # Red
}

TEC_STATUS_MESSAGES = {
    -1: "TEC Error",
    0: "TEC Inactive",
    1: "Approaching target",
    2: "In target",
}

# Default PID parameters
DEFAULT_PID = {
    'cycling_time': 50,
    'p_share': 500,
    'i_share': 50,
    'd_share': 300,
    'temperature': 25.0,
}

PID_PRESETS = {
    'Default #1': {'cycling_time': 50, 'p_share': 500, 'i_share': 50, 'd_share': 300},
    'Fast Response': {'cycling_time': 30, 'p_share': 800, 'i_share': 100, 'd_share': 200},
    'Stable': {'cycling_time': 100, 'p_share': 300, 'i_share': 30, 'd_share': 400},
    'Custom': None,
}


# =============================================================================
# STATUS LED WIDGET
# =============================================================================

class StatusLED(QFrame):
    """Circular LED indicator that matches the physical RGB LED on the device"""

    def __init__(self, parent=None, size=20):
        super().__init__(parent)
        self._color = QColor(TEC_COLORS['inactive'])
        self._size = size
        self.setFixedSize(size, size)

    def setColor(self, color):
        if isinstance(color, str):
            self._color = QColor(color)
        else:
            self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.darkGray, 1))
        painter.setBrush(QBrush(self._color))
        margin = 2
        painter.drawEllipse(margin, margin,
                            self._size - 2 * margin,
                            self._size - 2 * margin)
        painter.end()


# =============================================================================
# TEMPERATURE CONTROL WIDGET (Pure GUI — no serial I/O)
# =============================================================================

class TemperatureControlWidget(QWidget):
    """
    Temperature control widget — pure GUI.

    Signals emitted to notify main_window (which forwards to TECWorker):
        request_enable: user clicked "Temperature On"
        request_disable: user clicked "Temperature Off"
        request_set_temp(float): user clicked "Temperature Set"
        request_reset: user clicked "TEC Controller RESET"

    Signals for data consumers:
        temperature_changed(float): temperature reading updated
        status_changed(int): TEC status changed
    """

    # Request signals (→ main_window → TECWorker)
    request_enable = pyqtSignal()
    request_disable = pyqtSignal()
    request_set_temp = pyqtSignal(float)
    request_reset = pyqtSignal()

    # Data signals
    temperature_changed = pyqtSignal(float)
    status_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # State (updated from TECWorker or sweep metadata)
        self.tec_enabled = False
        self.current_temperature = 0.0
        self.current_status = 0
        self.current_error = 0

        self._setup_ui()

    def _setup_ui(self):
        """Create the widget UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Temperature Control")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)
        group_layout.setContentsMargins(8, 16, 8, 8)

        # =================================================================
        # ON/OFF Buttons
        # =================================================================
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_on = QPushButton("Temperature On")
        self.btn_on.clicked.connect(self._on_enable_clicked)
        btn_row.addWidget(self.btn_on)

        self.btn_off = QPushButton("Temperature Off")
        self.btn_off.clicked.connect(self._on_disable_clicked)
        btn_row.addWidget(self.btn_off)

        group_layout.addLayout(btn_row)

        # =================================================================
        # Status Display with LED
        # =================================================================
        status_frame = QFrame()
        status_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(8, 6, 8, 6)

        self.status_led = StatusLED(size=24)
        status_layout.addWidget(self.status_led)

        self.status_label = QLabel("TEC Inactive")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        group_layout.addWidget(status_frame)

        # =================================================================
        # TEC Controller Reset Button
        # =================================================================
        self.btn_reset = QPushButton("TEC Controller RESET")
        self.btn_reset.setEnabled(False)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        group_layout.addWidget(self.btn_reset)

        # =================================================================
        # PID Parameters Section (hidden)
        # =================================================================
        self.pid_container = QWidget()
        pid_grid = QGridLayout(self.pid_container)
        pid_grid.setSpacing(6)
        pid_grid.setContentsMargins(0, 0, 0, 0)

        pid_grid.addWidget(QLabel("PID Set"), 0, 0)
        self.pid_preset = QComboBox()
        self.pid_preset.addItems(list(PID_PRESETS.keys()))
        self.pid_preset.currentTextChanged.connect(self._on_preset_changed)
        pid_grid.addWidget(self.pid_preset, 0, 1)

        pid_grid.addWidget(QLabel("Cycling Time [msec]"), 1, 0)
        self.cycling_time = QSpinBox()
        self.cycling_time.setRange(10, 1000)
        self.cycling_time.setValue(DEFAULT_PID['cycling_time'])
        pid_grid.addWidget(self.cycling_time, 1, 1)

        pid_grid.addWidget(QLabel("P Share [mA/K]"), 2, 0)
        self.p_share = QSpinBox()
        self.p_share.setRange(0, 100000)
        self.p_share.setValue(DEFAULT_PID['p_share'])
        pid_grid.addWidget(self.p_share, 2, 1)

        pid_grid.addWidget(QLabel("I Share [mA/(K*sec)]"), 3, 0)
        self.i_share = QSpinBox()
        self.i_share.setRange(0, 100000)
        self.i_share.setValue(DEFAULT_PID['i_share'])
        pid_grid.addWidget(self.i_share, 3, 1)

        pid_grid.addWidget(QLabel("D Share [(mA*s)/K]"), 4, 0)
        self.d_share = QSpinBox()
        self.d_share.setRange(0, 100000)
        self.d_share.setValue(DEFAULT_PID['d_share'])
        pid_grid.addWidget(self.d_share, 4, 1)

        group_layout.addWidget(self.pid_container)
        self.pid_container.setVisible(False)

        # =================================================================
        # Temperature Setpoint
        # =================================================================
        temp_row = QHBoxLayout()
        temp_row.setSpacing(6)

        self.btn_set_temp = QPushButton("Temperature Set")
        self.btn_set_temp.clicked.connect(self._on_set_temp_clicked)
        temp_row.addWidget(self.btn_set_temp)

        self.temp_setpoint = QDoubleSpinBox()
        self.temp_setpoint.setRange(5.0, 45.0)
        self.temp_setpoint.setValue(DEFAULT_PID['temperature'])
        self.temp_setpoint.setDecimals(1)
        self.temp_setpoint.setSuffix(" °C")
        temp_row.addWidget(self.temp_setpoint)

        group_layout.addLayout(temp_row)

        # Current temperature display (hidden — shown in metric cards)
        current_temp_frame = QFrame()
        current_temp_frame.setVisible(False)
        group_layout.addWidget(current_temp_frame)

        main_layout.addWidget(group)

    # ── Button handlers (emit request signals) ──────────────────────

    def _on_enable_clicked(self):
        self.status_label.setText("Enabling TEC...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #FF9800;")
        self.request_enable.emit()

    def _on_disable_clicked(self):
        self.status_label.setText("Disabling TEC...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #FF9800;")
        self.request_disable.emit()

    def _on_set_temp_clicked(self):
        self.request_set_temp.emit(self.temp_setpoint.value())

    def _on_reset_clicked(self):
        self.btn_reset.setEnabled(False)
        self.status_label.setText("Resetting TEC...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #FF9800;")
        self.request_reset.emit()

    def _on_preset_changed(self, preset_name):
        preset = PID_PRESETS.get(preset_name)
        if preset:
            self.cycling_time.setValue(preset['cycling_time'])
            self.p_share.setValue(preset['p_share'])
            self.i_share.setValue(preset['i_share'])
            self.d_share.setValue(preset['d_share'])

    # ── Data update slots (called from main_window) ─────────────────

    def on_readings_updated(self, temp_c, status, error, current_mA):
        """
        Slot: receive data from TECWorker polling.
        Updates display without any serial I/O.
        """
        self.current_temperature = temp_c
        self.current_error = error
        self._apply_status(status, error)
        self.temperature_changed.emit(temp_c)

    def on_command_done(self, command, success, message):
        """Slot: receive command completion from TECWorker."""
        if command == 'X1' and success:
            self.tec_enabled = True
            self._set_tec_button_active(True)
            self._update_status_display()
        elif command == 'X0' and success:
            self.tec_enabled = False
            self._set_tec_button_active(False)
            self._update_status_display()
        elif command == 'RESET' and success:
            self.current_error = 0
            self._update_status_display()
        elif command == 'INIT' and success:
            # Worker read initial PID values — could update spinboxes here if needed
            pass

        if not success:
            print(f"[TEC Widget] Command {command} failed: {message}")

    def update_from_sweep_data(self, temperature=None, tec_status=None, tec_error=None):
        """
        Update widget state from sweep metadata.
        Called by main_window after each sweep — no serial I/O needed.
        """
        if temperature is not None:
            self.current_temperature = temperature
            self.temperature_changed.emit(temperature)

        if tec_error is not None:
            self.current_error = tec_error
            self.btn_reset.setEnabled(tec_error != 0)

        if tec_status is not None:
            self._apply_status(tec_status, self.current_error)

    # ── Status display logic ────────────────────────────────────────

    def _apply_status(self, status, error):
        """Apply status code to LED and label."""
        self.current_status = status

        if status == 0:
            self.tec_enabled = False
            self.status_led.setColor(TEC_COLORS['inactive'])
            self.status_label.setText(TEC_STATUS_MESSAGES[0])
            self.status_label.setStyleSheet(
                f"font-weight: bold; font-size: 11px; color: {COLORS['text_dim']};")
        elif status == -1:
            self.tec_enabled = True
            self.status_led.setColor(TEC_COLORS['error'])
            self.status_label.setText(TEC_STATUS_MESSAGES[-1])
            self.status_label.setStyleSheet(
                "font-weight: bold; font-size: 11px; color: #FF0000;")
            self.btn_reset.setEnabled(True)
        elif status == 2:
            self.tec_enabled = True
            self.status_led.setColor(TEC_COLORS['in_target'])
            self.status_label.setText(TEC_STATUS_MESSAGES[2])
            self.status_label.setStyleSheet(
                "font-weight: bold; font-size: 11px; color: #008EC0;")
        elif status == 1:
            self.tec_enabled = True
            self.status_led.setColor(TEC_COLORS['approaching'])
            self.status_label.setText(TEC_STATUS_MESSAGES[1])
            self.status_label.setStyleSheet(
                "font-weight: bold; font-size: 11px; color: #FF7D0A;")

        self.status_changed.emit(status)

    def _update_status_display(self):
        """Update LED/label based on current state (no serial I/O)."""
        if not self.tec_enabled:
            self._apply_status(0, self.current_error)
        elif self.current_error != 0:
            self._apply_status(-1, self.current_error)
        elif abs(self.current_temperature - self.temp_setpoint.value()) < 0.5:
            self._apply_status(2, 0)
        else:
            self._apply_status(1, 0)

    def _set_tec_button_active(self, active):
        """Toggle the 'active' property on Temperature On button for blue styling."""
        self.btn_on.setProperty("active", "true" if active else "false")
        # Re-polish to apply the new stylesheet property
        self.btn_on.style().unpolish(self.btn_on)
        self.btn_on.style().polish(self.btn_on)

    # ── Public getters ──────────────────────────────────────────────

    def get_current_temperature(self):
        return self.current_temperature

    def get_current_status(self):
        return self.current_status

    def is_enabled(self):
        return self.tec_enabled

    def get_pid_params(self):
        """Return current PID parameter values from spinboxes."""
        return {
            'C': self.cycling_time.value(),
            'P': self.p_share.value(),
            'I': self.i_share.value(),
            'D': self.d_share.value(),
        }

    def get_setpoint(self):
        """Return current temperature setpoint from spinbox."""
        return self.temp_setpoint.value()

    def stop(self):
        """Stop the widget — no timer to stop anymore."""
        pass
