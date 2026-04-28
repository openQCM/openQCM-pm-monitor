"""
OpenQCM Aerosol - Modern GUI for PM Sampling with QCM-D
======================================================

Interfaccia grafica moderna per il campionatore di particolato atmosferico
basato su tecnologia QCM (Quartz Crystal Microbalance) con:

- Monitoraggio frequenza e dissipazione in tempo reale
- Controllo pompa di aspirazione aria
- Misura velocità flusso aria (flowmeter)
- Controllo temperatura TEC
- Calcolo massa depositata (equazione Sauerbrey)
- Analisi QCM-D per caratterizzazione viscoelastica

FORMULA DISSIPAZIONE:
- D = Δf₋₃dB / f₀ (half-power bandwidth method)
- Q-factor = f0 / bandwidth

Author: Novaetech S.r.l. / openQCM Team
"""

import sys
import os
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QComboBox, QTextEdit, QGroupBox,
    QGridLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QMessageBox,
    QProgressBar, QTabWidget, QFrame, QFileDialog, QStatusBar,
    QSizePolicy, QScrollArea, QSplitter
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot, QThread, QObject, QMetaObject
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPixmap
import pyqtgraph as pg
from collections import deque
import numpy as np
import time
import json
import threading
from datetime import datetime
import pandas as pd

# Import openQCM package modules
from openqcm.core.sweep import OpenQCMSweepEnhanced
from openqcm.config import CRYSTAL_CONFIGS
from openqcm.gui.temperature_widget import TemperatureControlWidget
from openqcm.constants import (
    COLORS, CRYSTAL_OPTIONS,
    SAUERBREY_CONSTANT_5MHZ, SAUERBREY_CONSTANT_10MHZ, QUARTZ_AREA_CM2,
    OUTLET_DIAMETER_MM, FLOW_CALIBRATION_FACTOR,
    TEMPORAL_BUFFER_SIZE,
    MONITOR_WINDOW_SECONDS
)
import math
from openqcm.gui.styles import (
    NATIVE_STYLESHEET as MODERN_STYLESHEET,
    configure_plot_widget_native as configure_plot_widget,
    OneDecimalAxis,
    PEN_FREQ, PEN_DISS, PEN_TEMP, PEN_FLOW, PEN_MASS,
    PEN_RAW, SYMBOL_RAW, SURFACE, TEXT_DIM, ACCENT, RED, GREEN, YELLOW
)
from openqcm.gui.metric_card import MetricCard
from openqcm.gui.sweep_worker import CycleState, SweepWorker
from openqcm.core.tec_worker import TECWorker
from openqcm.core.data_logger import DataLogger, LOG_COLUMNS, CYCLE_COLUMNS

# Icons directory (sibling of gui/ inside the openqcm package)
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons')
APP_ICON_PATH = os.path.join(ICONS_DIR, 'icon.png')
APP_ICON_ICO = os.path.join(ICONS_DIR, 'icon.ico')
LOGO_PATH = os.path.join(ICONS_DIR, 'openqcm-logo.png')


class OpenQCMAerosolGUI(QMainWindow):

    def __init__(self):
        super().__init__()

        # State
        self.qcm = None
        self.monitoring_active = False
        self.pump_active = False
        self.current_data = None
        self.initial_frequency = None
        self.current_flow = 0.0          # m/s (raw sensor velocity)
        self.current_flow_rate = 0.0      # L/min (calculated volumetric flow)
        self.current_temperature = 0.0

        # Worker threads
        self.sweep_worker = None
        self.sweep_thread = None
        self.tec_worker = None
        self.tec_thread = None
        self.data_logger = None
        self.cycle_logger = None


        # Data storage — rolling window for real-time plots.
        # No maxlen: eviction is time-based (see _evict_old_samples), so the
        # visible window is exactly MONITOR_WINDOW_SECONDS regardless of sweep rate.
        # CSV logger keeps the full session history independently.
        self.time_data = deque()          # seconds since start_time
        self.freq_data = deque()          # Hz
        self.dissipation_data = deque()   # ppm
        self.mass_data = deque()          # ng/cm²
        self.flow_data = deque()          # m/s
        self.temperature_data = deque()   # °C
        self.start_time = time.time()
        self._last_sweep_time = None

        self.monitoring_history = []

        # Temporal smoothing ring buffers (from openQCM Next)
        self._freq_buffer = deque(maxlen=TEMPORAL_BUFFER_SIZE)
        self._diss_buffer = deque(maxlen=TEMPORAL_BUFFER_SIZE)
        self._temp_buffer = deque(maxlen=TEMPORAL_BUFFER_SIZE)
        self._sweep_count = 0

        # Measurement cycle state machine
        self.cycle_state = CycleState.IDLE
        self.cycle_active = False
        self.cycle_count = 0
        self.ref_frequency = None
        self.ref_dissipation = None
        self.cycle_freq_shifts = []
        self.cycle_diss_shifts = []
        self.cycle_mass_shifts = []
        self.cycle_concentrations = []
        self.cycle_meas_freqs = []        # median measured freq per cycle (trend)
        self.cycle_meas_disses = []       # median measured diss per cycle (trend, ppm)
        self._pump_flow_samples = []      # flow readings during PUMP_ON phase
        self._ref_freq_samples = []       # freq samples during REFERENCE phase
        self._ref_diss_samples = []       # diss samples during REFERENCE phase
        self._meas_freq_samples = []      # freq samples during WAITING phase
        self._meas_diss_samples = []      # diss samples during WAITING phase
        self._pump_start_time = None      # timestamp when pump actually started (s)
        self._pump_stop_time = None       # timestamp when pump actually stopped (s)

        # Setup
        self._init_ui()
        self._refresh_ports()

        # Timers
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self._update_plots)
        self.plot_timer.start(100)

        # Sweeps are chained from _on_sweep_finished (no periodic timer needed)
        # Flow readings come from TECWorker polling (_poll_cycle) when not monitoring,
        # and from sweep metadata during monitoring.

        self.cycle_timer = QTimer()
        self.cycle_timer.setSingleShot(True)
        self.cycle_timer.timeout.connect(self._cycle_timer_expired)

        self.cycle_elapsed_timer = QTimer()
        self.cycle_elapsed_timer.timeout.connect(self._update_cycle_elapsed)
        self.cycle_state_start_time = 0

    def _init_ui(self):
        self.setWindowTitle("openQCM Aerosol - PM Sampler with QCM-D Technology")
        if os.path.exists(APP_ICON_PATH):
            self.setWindowIcon(QIcon(APP_ICON_PATH))
        self.setMinimumSize(1024, 600)
        self.resize(1280, 750)
        self.setStyleSheet(MODERN_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # Splitter for resizable left / center / right panels
        self.main_splitter = QSplitter(Qt.Horizontal)

        # =====================================================================
        # LEFT PANEL - Configuration + Measurement Controls (scrollable)
        # =====================================================================
        left_inner = QWidget()
        left_layout = QVBoxLayout(left_inner)
        left_layout.setSpacing(4)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # openQCM logo at the top of the left panel
        if os.path.exists(LOGO_PATH):
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PATH)
            # Scale to panel width keeping aspect ratio
            scaled = pixmap.scaledToWidth(180, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setContentsMargins(0, 4, 0, 4)
            left_layout.addWidget(logo_label)

        left_layout.addWidget(self._create_connection_group())
        left_layout.addWidget(self._create_plot_control_group())
        left_layout.addWidget(self._create_peak_detection_group())
        left_layout.addWidget(self._create_monitoring_group())
        left_layout.addWidget(self._create_cycle_group())
        # Actual interval label (standalone, below cycle group)
        self.actual_interval_label = QLabel("")
        self.actual_interval_label.setAlignment(Qt.AlignLeft)
        left_layout.addWidget(self.actual_interval_label)
        left_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidget(left_inner)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setMinimumWidth(200)
        left_scroll.setMaximumWidth(242)

        self.main_splitter.addWidget(left_scroll)

        # =====================================================================
        # CENTER PANEL - Cards + Graphs
        # =====================================================================
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(4)
        center_layout.setContentsMargins(0, 0, 0, 0)

        # Metric cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(4)

        self.freq_card = MetricCard("Frequency", "Hz", COLORS['primary'])
        self.diss_card = MetricCard("Dissipation", "ppm", COLORS['error'])
        self.mass_card = MetricCard("Mass", "ng/cm²", COLORS['info'])
        self.conc_card = MetricCard("Concentration", "µg/m³", COLORS['warning'])
        self.flow_card = MetricCard("Velocity", "m/s", COLORS['accent'])
        self.flow_rate_card = MetricCard("Flow Rate", "L/min", COLORS['secondary'])
        self.temp_card = MetricCard("Temp", "°C", COLORS['temperature'])
        cards_layout.addWidget(self.freq_card)
        cards_layout.addWidget(self.diss_card)
        cards_layout.addWidget(self.mass_card)
        cards_layout.addWidget(self.conc_card)
        cards_layout.addWidget(self.flow_card)
        cards_layout.addWidget(self.flow_rate_card)
        cards_layout.addWidget(self.temp_card)

        center_layout.addLayout(cards_layout)

        # Tab widget for graphs
        self.tabs = QTabWidget()

        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        monitor_layout.setContentsMargins(4, 4, 4, 4)
        self._create_monitoring_plots(monitor_layout)
        self.tabs.addTab(monitor_tab, "Monitoring")

        sweep_tab = QWidget()
        sweep_layout = QVBoxLayout(sweep_tab)
        sweep_layout.setContentsMargins(4, 4, 4, 4)
        self._create_sweep_plots(sweep_layout)
        self.tabs.addTab(sweep_tab, "Sweep")

        console_tab = QWidget()
        console_layout = QVBoxLayout(console_tab)
        console_layout.setContentsMargins(4, 4, 4, 4)
        self._create_console(console_layout)
        self.tabs.addTab(console_tab, "Console")

        center_layout.addWidget(self.tabs, stretch=1)

        self.main_splitter.addWidget(center_widget)

        # =====================================================================
        # RIGHT PANEL - Temperature and Pump Controls
        # =====================================================================
        right_inner = QWidget()
        right_layout = QVBoxLayout(right_inner)
        right_layout.setSpacing(4)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Shared serial lock between sweep and TEC workers
        self._serial_lock = threading.Lock()

        # Temperature Control Widget + TEC Worker Thread
        self.temp_control = TemperatureControlWidget()
        self.temp_control.temperature_changed.connect(self._on_temperature_changed)
        self.temp_control.status_changed.connect(self._on_tec_status_changed)
        self._setup_tec_thread()
        right_layout.addWidget(self.temp_control)

        right_layout.addWidget(self._create_pump_group())
        right_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidget(right_inner)
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setMinimumWidth(170)
        right_scroll.setMaximumWidth(242)

        self.main_splitter.addWidget(right_scroll)

        # Set initial splitter proportions (left:center:right = 230:stretch:250)
        self.main_splitter.setStretchFactor(0, 0)  # left: no stretch
        self.main_splitter.setStretchFactor(1, 1)  # center: stretch
        self.main_splitter.setStretchFactor(2, 0)  # right: no stretch
        self.main_splitter.setSizes([220, 840, 220])

        main_layout.addWidget(self.main_splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status("Disconnected - Select a serial port")

        pg.setConfigOptions(antialias=True, background='w', foreground='k')

    def _setup_worker_thread(self):
        """Setup worker thread for sweep operations"""
        # Create worker and thread
        self.sweep_worker = SweepWorker()
        self.sweep_worker.serial_lock = self._serial_lock
        self.sweep_thread = QThread()

        # Move worker to thread
        self.sweep_worker.moveToThread(self.sweep_thread)

        # Connect signals (explicit QueuedConnection — worker thread → main thread)
        self.sweep_worker.sweep_finished.connect(self._on_sweep_finished, Qt.QueuedConnection)
        self.sweep_worker.sweep_error.connect(self._on_sweep_error, Qt.QueuedConnection)
        self.sweep_worker.peak_found.connect(self._on_peak_found, Qt.QueuedConnection)
        self.sweep_worker.peak_error.connect(self._on_peak_error, Qt.QueuedConnection)

        # Start thread
        self.sweep_thread.start()

    def _setup_tec_thread(self):
        """Setup dedicated thread for TEC serial communication."""
        self.tec_worker = TECWorker()
        self.tec_worker.set_serial_lock(self._serial_lock)
        self.tec_thread = QThread()
        self.tec_worker.moveToThread(self.tec_thread)

        # Widget → Worker (user commands, main → worker thread)
        self.temp_control.request_enable.connect(self._tec_enable_requested)
        self.temp_control.request_disable.connect(self._tec_disable_requested)
        self.temp_control.request_set_temp.connect(self.tec_worker.set_temperature, Qt.QueuedConnection)
        self.temp_control.request_reset.connect(self.tec_worker.reset_tec, Qt.QueuedConnection)

        # Worker → Widget (data updates, worker → main thread)
        self.tec_worker.readings_updated.connect(self.temp_control.on_readings_updated, Qt.QueuedConnection)
        self.tec_worker.command_done.connect(self.temp_control.on_command_done, Qt.QueuedConnection)
        self.tec_worker.flow_updated.connect(self._on_flow_updated, Qt.QueuedConnection)

        self.tec_thread.start()

    def _tec_invoke(self, method_name):
        """Invoke a TECWorker slot on the worker thread (thread-safe)."""
        QMetaObject.invokeMethod(self.tec_worker, method_name, Qt.QueuedConnection)

    def _tec_enable_requested(self):
        """Forward enable request with current PID params and setpoint."""
        pid = self.temp_control.get_pid_params()
        self.tec_worker._pid_params = pid
        self.tec_worker._setpoint_c = self.temp_control.get_setpoint()
        self.tec_worker._start_polling_after_enable = not self.monitoring_active
        self._tec_invoke("enable_tec")

    def _tec_disable_requested(self):
        """Forward disable request and stop polling."""
        self._tec_invoke("stop_polling")
        self._tec_invoke("disable_tec")

    # set_temperature is connected directly: request_set_temp → tec_worker.set_temperature
    # Qt auto-uses QueuedConnection across threads, and the float arg is passed correctly.

    def _create_connection_group(self):
        group = QGroupBox("Connection")
        layout = QGridLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(6, 12, 6, 4)

        layout.addWidget(QLabel("Port:"), 0, 0)
        self.port_combo = QComboBox()
        layout.addWidget(self.port_combo, 0, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(55)
        refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(refresh_btn, 0, 2)

        # Baudrate fixed at 115200 (hidden)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200"])
        self.baud_combo.setVisible(False)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_btn, 2, 0, 1, 3)

        self.conn_status = QLabel("Disconnected")
        self.conn_status.setStyleSheet(f"color: {COLORS['error']}; font-weight: bold; font-size: 10px;")
        layout.addWidget(self.conn_status, 3, 0, 1, 3)

        self.hw_status = QLabel("Hardware: N/A")
        self.hw_status.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9px;")
        layout.addWidget(self.hw_status, 4, 0, 1, 3)

        group.setLayout(layout)
        return group

    def _create_plot_control_group(self):
        group = QGroupBox("Plot Control")
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 12, 6, 4)

        self.clear_plots_btn = QPushButton("Clear")
        self.clear_plots_btn.setToolTip("Clear all plot data")
        self.clear_plots_btn.setEnabled(False)
        self.clear_plots_btn.clicked.connect(self._clear_all_plots)
        layout.addWidget(self.clear_plots_btn)

        self.autoscale_btn = QPushButton("Autoscale")
        self.autoscale_btn.setToolTip("Autoscale X and Y axes on all plots")
        self.autoscale_btn.clicked.connect(self._autoscale_all_plots)
        layout.addWidget(self.autoscale_btn)

        group.setLayout(layout)
        return group

    def _create_peak_detection_group(self):
        group = QGroupBox("Peak Detection")
        layout = QGridLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(6, 12, 6, 4)

        layout.addWidget(QLabel("Crystal:"), 0, 0)
        self.crystal_combo = QComboBox()
        self.crystal_combo.addItems(['5 MHz', '10 MHz'])
        self.crystal_combo.setCurrentText('10 MHz')
        self.crystal_combo.currentTextChanged.connect(self._on_crystal_changed)
        layout.addWidget(self.crystal_combo, 0, 1)

        # Hidden spinbox for internal frequency value
        self.center_freq = QDoubleSpinBox()
        self.center_freq.setRange(1.0, 50.0)
        self.center_freq.setValue(10.0)
        self.center_freq.setDecimals(3)
        self.center_freq.setVisible(False)

        layout.addWidget(QLabel("Range (±kHz):"), 1, 0)
        self.search_range = QSpinBox()
        self.search_range.setRange(1, 500)
        self.search_range.setValue(50)
        layout.addWidget(self.search_range, 1, 1)

        layout.addWidget(QLabel("Step (Hz):"), 2, 0)
        self.search_step = QSpinBox()
        self.search_step.setRange(1, 1000)
        self.search_step.setValue(100)
        layout.addWidget(self.search_step, 2, 1)

        self.find_peak_btn = QPushButton("Find Peak")
        self.find_peak_btn.setEnabled(False)
        self.find_peak_btn.clicked.connect(self._find_peak)
        layout.addWidget(self.find_peak_btn, 3, 0, 1, 2)

        group.setLayout(layout)
        return group

    def _create_monitoring_group(self):
        group = QGroupBox("Continuous Measurement")
        layout = QGridLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(6, 12, 6, 4)

        layout.addWidget(QLabel("Range (±kHz):"), 0, 0)
        self.fine_range = QSpinBox()
        self.fine_range.setRange(1, 100)
        self.fine_range.setValue(5)
        layout.addWidget(self.fine_range, 0, 1)

        layout.addWidget(QLabel("Step (Hz):"), 1, 0)
        self.fine_step = QSpinBox()
        self.fine_step.setRange(1, 100)
        self.fine_step.setValue(1)
        layout.addWidget(self.fine_step, 1, 1)

        self.monitor_btn = QPushButton("Start Monitor")
        self.monitor_btn.setEnabled(False)
        self.monitor_btn.clicked.connect(self._toggle_monitoring)
        layout.addWidget(self.monitor_btn, 2, 0, 1, 2)

        # Hidden widgets kept for compatibility
        self.sweep_btn = QPushButton("Sweep")
        self.sweep_btn.setEnabled(False)
        self.sweep_btn.clicked.connect(self._do_sweep)
        self.sweep_btn.setVisible(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        group.setLayout(layout)
        return group

    def _create_pump_group(self):
        """Pump control group for right panel"""
        group = QGroupBox("Pump & Flow")
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 12, 6, 4)

        # Start/Stop buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.pump_start_btn = QPushButton("Start")
        self.pump_start_btn.setEnabled(False)
        self.pump_start_btn.clicked.connect(self._start_pump)
        btn_row.addWidget(self.pump_start_btn)

        self.pump_stop_btn = QPushButton("Stop")
        self.pump_stop_btn.setEnabled(False)
        self.pump_stop_btn.clicked.connect(self._stop_pump)
        btn_row.addWidget(self.pump_stop_btn)

        layout.addLayout(btn_row)

        # Preset buttons (2x2 grid)
        preset_grid = QGridLayout()
        preset_grid.setSpacing(2)
        self.preset_buttons = []
        for i, (text, speed) in enumerate([("25%", 64), ("50%", 130), ("75%", 190), ("100%", 255)]):
            btn = QPushButton(text)
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, s=speed: self._set_pump_speed(s))
            self.preset_buttons.append(btn)
            preset_grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(preset_grid)

        # Slider + speed label
        slider_row = QHBoxLayout()
        slider_row.setSpacing(4)
        self.pump_slider = QSlider(Qt.Horizontal)
        self.pump_slider.setRange(30, 255)
        self.pump_slider.setValue(130)  # 50% default
        self.pump_slider.sliderReleased.connect(
            lambda: self._set_pump_speed(self.pump_slider.value()) if self.pump_active else None
        )
        slider_row.addWidget(self.pump_slider)
        layout.addLayout(slider_row)

        # Progress bar (current speed %)
        self.pump_progress = QProgressBar()
        self.pump_progress.setMaximum(100)
        self.pump_progress.setFormat("%v%")
        self.pump_progress.setFixedHeight(16)
        layout.addWidget(self.pump_progress)

        # ── Flow Calibration ──
        self.flow_mode_combo = QComboBox()
        self.flow_mode_combo.addItems(["Analytical (πD²/4)", "Calibrated (K·v)"])
        self.flow_mode_combo.currentIndexChanged.connect(self._on_flow_mode_changed)
        layout.addWidget(self.flow_mode_combo)

        # Outlet diameter (analytical mode)
        diam_row = QHBoxLayout()
        diam_row.setSpacing(4)
        self.outlet_diam_label = QLabel("⌀ mm:")
        diam_row.addWidget(self.outlet_diam_label)
        self.outlet_diam_spin = QDoubleSpinBox()
        self.outlet_diam_spin.setRange(0.1, 50.0)
        self.outlet_diam_spin.setValue(OUTLET_DIAMETER_MM)
        self.outlet_diam_spin.setSingleStep(0.1)
        self.outlet_diam_spin.setDecimals(1)
        diam_row.addWidget(self.outlet_diam_spin)
        layout.addLayout(diam_row)

        # K_cal (calibrated mode)
        kcal_row = QHBoxLayout()
        kcal_row.setSpacing(4)
        self.flow_kcal_label = QLabel("K_cal:")
        kcal_row.addWidget(self.flow_kcal_label)
        self.flow_kcal_spin = QDoubleSpinBox()
        self.flow_kcal_spin.setRange(0.001, 100.0)
        self.flow_kcal_spin.setValue(FLOW_CALIBRATION_FACTOR)
        self.flow_kcal_spin.setSingleStep(0.001)
        self.flow_kcal_spin.setDecimals(3)
        kcal_row.addWidget(self.flow_kcal_spin)
        layout.addLayout(kcal_row)

        # Initially hide K_cal (analytical mode is default)
        self.flow_kcal_label.setVisible(False)
        self.flow_kcal_spin.setVisible(False)

        # Flow rate display (L/min)
        self.flow_rate_label = QLabel("Q: --- L/min")
        self.flow_rate_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.flow_rate_label)

        group.setLayout(layout)
        return group

    def _create_cycle_group(self):
        """Pump cycle procedure controls"""
        group = QGroupBox("Pump Cycle Procedure")
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 12, 6, 4)

        # Cycle settings grid
        cycle_grid = QGridLayout()
        cycle_grid.setSpacing(4)

        cycle_grid.addWidget(QLabel("Pump On Time:"), 0, 0)
        self.pump_on_spin = QSpinBox()
        self.pump_on_spin.setRange(1, 600)
        self.pump_on_spin.setValue(30)
        self.pump_on_spin.setSuffix("s")
        self.pump_on_spin.setFixedWidth(65)
        self.pump_on_spin.setAlignment(Qt.AlignRight)
        cycle_grid.addWidget(self.pump_on_spin, 0, 1, Qt.AlignRight)

        cycle_grid.addWidget(QLabel("Waiting Time:"), 1, 0)
        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(1, 600)
        self.wait_spin.setValue(60)
        self.wait_spin.setSuffix("s")
        self.wait_spin.setFixedWidth(65)
        self.wait_spin.setAlignment(Qt.AlignRight)
        cycle_grid.addWidget(self.wait_spin, 1, 1, Qt.AlignRight)

        layout.addLayout(cycle_grid)

        layout.addSpacing(2)

        # Cycle count + elapsed time
        cycle_info_row = QHBoxLayout()
        cycle_info_row.setSpacing(4)
        self.cycle_count_label = QLabel("Cycle: 0")
        cycle_info_row.addWidget(self.cycle_count_label)
        cycle_info_row.addStretch()
        self.cycle_elapsed_label = QLabel("")
        cycle_info_row.addWidget(self.cycle_elapsed_label)
        layout.addLayout(cycle_info_row)

        # State indicator
        self.cycle_state_label = QLabel("IDLE")
        self.cycle_state_label.setAlignment(Qt.AlignCenter)
        self.cycle_state_label.setMinimumHeight(28)
        self.cycle_state_label.setStyleSheet("""
            font-size: 12px; font-weight: bold; color: white;
            background-color: #757575; border-radius: 3px;
            padding: 4px 6px;
        """)
        layout.addWidget(self.cycle_state_label)

        layout.addSpacing(2)

        self.cycle_btn = QPushButton("Start Cycle")
        self.cycle_btn.setEnabled(False)
        self.cycle_btn.clicked.connect(self._toggle_cycle)
        layout.addWidget(self.cycle_btn)

        group.setLayout(layout)
        return group

    def _create_monitoring_plots(self, layout):
        """Create monitoring plots."""

        # ROW 1: Frequency + Dissipation vs Time (real-time)
        self.freq_plot = pg.PlotWidget(title="Frequency and Dissipation vs Time")
        configure_plot_widget(self.freq_plot, left_label="Frequency (Hz)")
        self.freq_plot.getAxis('left').setTextPen(pg.mkPen(color=ACCENT))
        self.freq_plot.addLegend(offset=(60, 10))
        self.freq_curve = self.freq_plot.plot(pen=PEN_FREQ, name='Frequency')

        self.diss_viewbox = pg.ViewBox()
        self.freq_plot.scene().addItem(self.diss_viewbox)
        self.freq_plot.getAxis('right').linkToView(self.diss_viewbox)
        self.diss_viewbox.setXLink(self.freq_plot)
        self.freq_plot.getAxis('right').setLabel('Dissipation (ppm)', color=RED)
        self.freq_plot.getAxis('right').setPen(pg.mkPen(color=TEXT_DIM))
        self.freq_plot.getAxis('right').setTextPen(pg.mkPen(color=RED))
        self.freq_plot.getAxis('right').tickStrings = lambda values, scale, spacing: [f"{v:.1f}" for v in values]
        self.freq_plot.showAxis('right')
        self.diss_curve = pg.PlotCurveItem(pen=PEN_DISS, name='Dissipation')
        self.diss_viewbox.addItem(self.diss_curve)

        def updateViews():
            self.diss_viewbox.setGeometry(self.freq_plot.getViewBox().sceneBoundingRect())
            self.diss_viewbox.linkedViewChanged(self.freq_plot.getViewBox(), self.diss_viewbox.XAxis)
        self.freq_plot.getViewBox().sigResized.connect(updateViews)
        updateViews()
        layout.addWidget(self.freq_plot)

        # ROW 2: Δm per Cycle | Concentration per Cycle
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self.mass_plot = pg.PlotWidget(title="Δm per Cycle")
        configure_plot_widget(self.mass_plot, left_label="Δm (ng/cm²)", bottom_label="Cycle")
        self.mass_bars = pg.BarGraphItem(x=[], height=[], width=0.6, brush=PEN_MASS.color())
        self.mass_plot.addItem(self.mass_bars)
        row2.addWidget(self.mass_plot)

        self.conc_plot = pg.PlotWidget(title="Concentration per Cycle")
        configure_plot_widget(self.conc_plot, left_label="C (µg/m³)", bottom_label="Cycle")
        self.conc_bars = pg.BarGraphItem(x=[], height=[], width=0.6, brush=PEN_FLOW.color())
        self.conc_plot.addItem(self.conc_bars)
        row2.addWidget(self.conc_plot)

        layout.addLayout(row2)

        # ROW 3: Δf/ΔD vs Cycle | Measured Freq/Diss vs Cycle (trend)
        row3 = QHBoxLayout()
        row3.setSpacing(4)

        # Δf / ΔD per cycle
        self.cycle_plot = pg.PlotWidget(title="Δf / ΔD vs Cycle")
        configure_plot_widget(self.cycle_plot, left_label="Δf (Hz)", bottom_label="Cycle")
        self.cycle_plot.getAxis('left').setTextPen(pg.mkPen(color=ACCENT))
        self.cycle_plot.addLegend(offset=(60, 10))
        self.cycle_freq_curve = self.cycle_plot.plot(
            pen=PEN_FREQ, symbol='o', symbolSize=6, symbolBrush=ACCENT, name='Δf'
        )
        self.cycle_diss_viewbox = pg.ViewBox()
        self.cycle_plot.scene().addItem(self.cycle_diss_viewbox)
        self.cycle_plot.getAxis('right').linkToView(self.cycle_diss_viewbox)
        self.cycle_diss_viewbox.setXLink(self.cycle_plot)
        self.cycle_plot.getAxis('right').setLabel('ΔD (ppm)', color=RED)
        self.cycle_plot.getAxis('right').setPen(pg.mkPen(color=TEXT_DIM))
        self.cycle_plot.getAxis('right').setTextPen(pg.mkPen(color=RED))
        self.cycle_plot.getAxis('right').tickStrings = lambda values, scale, spacing: [f"{v:.1f}" for v in values]
        self.cycle_plot.showAxis('right')
        self.cycle_diss_curve = pg.PlotCurveItem(pen=PEN_DISS, name='ΔD')
        self.cycle_diss_viewbox.addItem(self.cycle_diss_curve)
        self.cycle_diss_scatter = pg.ScatterPlotItem(size=6, brush=pg.mkBrush(RED))
        self.cycle_diss_viewbox.addItem(self.cycle_diss_scatter)

        def updateCycleViews():
            self.cycle_diss_viewbox.setGeometry(self.cycle_plot.getViewBox().sceneBoundingRect())
            self.cycle_diss_viewbox.linkedViewChanged(self.cycle_plot.getViewBox(), self.cycle_diss_viewbox.XAxis)
        self.cycle_plot.getViewBox().sigResized.connect(updateCycleViews)
        updateCycleViews()
        row3.addWidget(self.cycle_plot)

        # Measured Freq / Diss trend per cycle
        self.trend_plot = pg.PlotWidget(title="Measured Freq / Diss vs Cycle")
        configure_plot_widget(self.trend_plot, left_label="Frequency (Hz)", bottom_label="Cycle")
        self.trend_plot.getAxis('left').setTextPen(pg.mkPen(color=ACCENT))
        self.trend_freq_curve = self.trend_plot.plot(
            pen=PEN_FREQ, symbol='o', symbolSize=6, symbolBrush=ACCENT, name='Freq'
        )
        self.trend_diss_viewbox = pg.ViewBox()
        self.trend_plot.scene().addItem(self.trend_diss_viewbox)
        self.trend_plot.getAxis('right').linkToView(self.trend_diss_viewbox)
        self.trend_diss_viewbox.setXLink(self.trend_plot)
        self.trend_plot.getAxis('right').setLabel('Dissipation (ppm)', color=RED)
        self.trend_plot.getAxis('right').setPen(pg.mkPen(color=TEXT_DIM))
        self.trend_plot.getAxis('right').setTextPen(pg.mkPen(color=RED))
        self.trend_plot.getAxis('right').tickStrings = lambda values, scale, spacing: [f"{v:.1f}" for v in values]
        self.trend_plot.showAxis('right')
        self.trend_diss_curve = pg.PlotCurveItem(pen=PEN_DISS, name='Diss')
        self.trend_diss_viewbox.addItem(self.trend_diss_curve)
        self.trend_diss_scatter = pg.ScatterPlotItem(size=6, brush=pg.mkBrush(RED))
        self.trend_diss_viewbox.addItem(self.trend_diss_scatter)

        def updateTrendViews():
            self.trend_diss_viewbox.setGeometry(self.trend_plot.getViewBox().sceneBoundingRect())
            self.trend_diss_viewbox.linkedViewChanged(self.trend_plot.getViewBox(), self.trend_diss_viewbox.XAxis)
        self.trend_plot.getViewBox().sigResized.connect(updateTrendViews)
        updateTrendViews()
        row3.addWidget(self.trend_plot)

        layout.addLayout(row3)

        # ROW 4: Flow | Temperature
        row4 = QHBoxLayout()
        row4.setSpacing(4)

        self.flow_plot = pg.PlotWidget(title="Air Flow")
        configure_plot_widget(self.flow_plot, left_label="Velocity (m/s)", axis_type="decimal")
        self.flow_curve = self.flow_plot.plot(pen=PEN_FLOW)
        row4.addWidget(self.flow_plot)

        self.temp_plot = pg.PlotWidget(title="Temperature (°C)")
        configure_plot_widget(self.temp_plot, left_label="T (°C)", axis_type="decimal")
        self.temp_curve = self.temp_plot.plot(pen=PEN_TEMP)
        row4.addWidget(self.temp_plot)

        layout.addLayout(row4)

    def _create_sweep_plots(self, layout):
        self.amp_plot = pg.PlotWidget(title="Amplitude Response")
        configure_plot_widget(self.amp_plot, left_label="Gain (dB)",
                              bottom_label="Frequency (MHz)", axis_type="decimal")
        self.amp_plot.addLegend(offset=(60, 10))

        # Raw data as scatter (yellow dots, from openQCM Double style)
        self.amp_raw_scatter = pg.ScatterPlotItem(
            size=2, pen=pg.mkPen(None),
            brush=pg.mkBrush(color=YELLOW),
            name='Raw data'
        )
        self.amp_plot.addItem(self.amp_raw_scatter)

        # Filtered curve (accent blue)
        self.amp_curve = self.amp_plot.plot(pen=PEN_FREQ, name='Filtered')

        self.amp_res_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color=RED, width=2, style=Qt.DashLine)
        )
        self.amp_plot.addItem(self.amp_res_line)

        self.bw_region = pg.LinearRegionItem(
            brush=pg.mkBrush(color=(166, 227, 161, 50)), movable=False  # green translucent
        )
        self.amp_plot.addItem(self.bw_region)
        self.bw_region.setVisible(False)

        # Gain peak marker (star)
        self.gain_peak_marker = pg.ScatterPlotItem(
            size=14, symbol='star', brush=pg.mkBrush(RED), pen=pg.mkPen('k', width=1)
        )
        self.amp_plot.addItem(self.gain_peak_marker)

        layout.addWidget(self.amp_plot)

        self.phase_plot = pg.PlotWidget(title="Phase Response")
        configure_plot_widget(self.phase_plot, left_label="Phase (deg)",
                              bottom_label="Frequency (MHz)", axis_type="decimal")
        self.phase_raw_scatter = pg.ScatterPlotItem(
            size=2, pen=pg.mkPen(None),
            brush=pg.mkBrush(color=YELLOW),
            name='Raw data'
        )
        self.phase_plot.addItem(self.phase_raw_scatter)
        self.phase_curve = self.phase_plot.plot(pen=pg.mkPen(color=GREEN, width=2))
        self.phase_res_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color=RED, width=2, style=Qt.DashLine)
        )
        self.phase_plot.addItem(self.phase_res_line)

        # Phase peak marker (square)
        self.phase_peak_marker = pg.ScatterPlotItem(
            size=12, symbol='s', brush=pg.mkBrush(RED), pen=pg.mkPen('k', width=1)
        )
        self.phase_plot.addItem(self.phase_peak_marker)

        layout.addWidget(self.phase_plot)

        # SNR plot (hidden)
        self.snr_plot = pg.PlotWidget(title="Signal-to-Noise Ratio")
        self.snr_plot.setLabel('left', 'SNR')
        self.snr_plot.setLabel('bottom', 'Frequency (MHz)')
        self.snr_plot.showGrid(x=True, y=True, alpha=0.3)
        self.snr_curve = self.snr_plot.plot(pen=pg.mkPen(color=COLORS['accent'], width=2))
        self.snr_threshold = pg.InfiniteLine(
            pos=3.0, angle=0, movable=False,
            pen=pg.mkPen(color=COLORS['text_secondary'], width=1, style=Qt.DashLine)
        )
        self.snr_plot.addItem(self.snr_threshold)
        self.snr_plot.setVisible(False)
        layout.addWidget(self.snr_plot)

        results_frame = QFrame()
        results_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['divider']};
                border-radius: 6px;
            }}
        """)
        results_layout = QVBoxLayout(results_frame)
        results_layout.setContentsMargins(8, 8, 8, 8)

        results_title = QLabel("QCM-D Analysis")
        results_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLORS['primary']};")
        results_layout.addWidget(results_title)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['surface']};
                border: none;
                color: {COLORS['text_primary']};
                font-family: 'Monaco', 'Consolas', monospace;
                font-size: 10px;
            }}
        """)
        self.results_text.setPlainText(
            "Run a sweep to see results.\n\n"
            "Formula: D = bandwidth / f0\n"
            "Q-Factor: Q = f0 / bandwidth"
        )
        results_layout.addWidget(self.results_text)

        results_frame.setVisible(False)
        layout.addWidget(results_frame)

    def _create_console(self, layout):
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        cmd_layout = QHBoxLayout()
        cmd_layout.setSpacing(8)

        self.cmd_combo = QComboBox()
        self.cmd_combo.setEditable(True)
        self.cmd_combo.addItems([
            "F", "B?", "B0", "B1", "B2", "B3", "B4",
            "G?", "Gr", "Gm", "Gs", "G0", "Gh",
            "Te?", "T?", "T25000", "A?", "E?",
            "X1", "X0", "C?", "P?", "I?", "D?"
        ])
        self.cmd_combo.setMinimumWidth(80)
        cmd_layout.addWidget(self.cmd_combo)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_command)
        cmd_layout.addWidget(send_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.console.clear)
        cmd_layout.addWidget(clear_btn)

        cmd_layout.addStretch()

        layout.addLayout(cmd_layout)

    # =========================================================================
    # CONNECTION METHODS
    # =========================================================================

    # USB Vendor ID for Teensy (PJRC / Van Ooijen Technische Informatica).
    # Cross-platform identifier from the USB descriptor — works on macOS,
    # Windows and Linux regardless of how the OS labels the COM port.
    TEENSY_VID = 0x16C0

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = [p for p in serial.tools.list_ports.comports()
                 if p.vid == self.TEENSY_VID]
        if ports:
            for p in ports:
                self.port_combo.addItem(f"{p.device} - {p.description}")
        else:
            self.port_combo.addItem("No Teensy device found")

    def _toggle_connection(self):
        if self.qcm is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self):
        port_text = self.port_combo.currentText()
        if not port_text or "No ports" in port_text:
            QMessageBox.warning(self, "Error", "Select a valid port!")
            return

        port = port_text.split(" - ")[0]

        try:
            self.qcm = OpenQCMSweepEnhanced(port=port)

            if self.qcm.connect():
                self.conn_status.setText("Connected")
                self.conn_status.setStyleSheet(f"color: {COLORS['secondary']}; font-weight: bold; font-size: 10px;")

                self.connect_btn.setText("Disconnect")

                self._enable_controls(True)
                self._update_status("Connected - Ready")
                self._log("Connected to " + port)

                # Setup worker thread with QCM reference
                self._setup_worker_thread()
                self.sweep_worker.set_qcm(self.qcm)

                self._check_hardware()

                saved = self.qcm.get_saved_resonance()
                if saved:
                    self.initial_frequency = saved
                    self._log(f"Saved resonance: {saved/1e6:.6f} MHz")

                # Pass serial to TEC worker and start hardware polling
                # (Te? + E? + A? + G? every 2s). Polling runs whenever connected
                # and not monitoring; readings are reported regardless of TEC state.
                self.tec_worker.set_serial(self.qcm.serial_connection)
                self._tec_invoke("start_polling")

            else:
                QMessageBox.critical(self, "Error", "Connection failed!")
                self.qcm = None

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.qcm = None

    def _disconnect(self):
        if self.monitoring_active:
            self._stop_monitoring()

        # Stop TEC worker
        self._tec_invoke("stop_polling")
        self.tec_worker.set_serial(None)

        # Stop worker thread
        if self.sweep_thread and self.sweep_thread.isRunning():
            self.sweep_thread.quit()
            self.sweep_thread.wait()
            self.sweep_thread = None
            self.sweep_worker = None

        if self.qcm:
            self.qcm.disconnect()
            self.qcm = None

        self.conn_status.setText("Disconnected")
        self.conn_status.setStyleSheet(f"color: {COLORS['error']}; font-weight: bold; font-size: 10px;")

        self.connect_btn.setText("Connect")

        self._enable_controls(False)
        self._update_status("Disconnected")
        self._log("Disconnected")

    def _enable_controls(self, enabled):
        self.find_peak_btn.setEnabled(enabled)
        self.sweep_btn.setEnabled(enabled)
        self.monitor_btn.setEnabled(enabled)
        self.cycle_btn.setEnabled(enabled)
        self.clear_plots_btn.setEnabled(enabled)

        self._set_pump_controls_enabled(enabled)

    def _set_pump_controls_enabled(self, enabled):
        """Enable/disable all manual pump controls.
        During cycle mode these must be disabled — the state machine owns the pump."""
        self.pump_start_btn.setEnabled(enabled)
        self.pump_stop_btn.setEnabled(enabled and self.pump_active)
        self.pump_slider.setEnabled(enabled)
        for btn in self.preset_buttons:
            btn.setEnabled(enabled)

    @staticmethod
    def _set_button_active(btn, active):
        """Toggle blue 'active' visual style on a toggle button."""
        btn.setProperty("active", "true" if active else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _check_hardware(self):
        if not self.qcm or not self.qcm.serial_connection:
            return
        try:
            with self._serial_lock:
                self.qcm.serial_connection.write(b'Gh\n')
                time.sleep(0.1)
                resp = None
                if self.qcm.serial_connection.in_waiting:
                    resp = self.qcm.serial_connection.readline().decode().strip()
            # Process response outside the lock (GUI updates don't need it)
            if resp:
                self._log(f"Hardware status: {resp}")
                if ';' in resp:
                    parts = resp.split(';')
                    if len(parts) >= 2:
                        motor_ok = parts[0].strip() == '1'
                        flow_ok = parts[1].strip() == '1'
                        if motor_ok and flow_ok:
                            self.hw_status.setText("HW: ✓ Motor | ✓ Flow")
                            self.hw_status.setStyleSheet(f"color: {COLORS['secondary']}; font-weight: bold; font-size: 9px;")
                        elif motor_ok:
                            self.hw_status.setText("HW: ✓ Motor | ✗ Flow")
                            self.hw_status.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; font-size: 9px;")
                        elif flow_ok:
                            self.hw_status.setText("HW: ✗ Motor | ✓ Flow")
                            self.hw_status.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; font-size: 9px;")
                        else:
                            self.hw_status.setText("HW: ✗ Motor | ✗ Flow")
                            self.hw_status.setStyleSheet(f"color: {COLORS['error']}; font-weight: bold; font-size: 9px;")
        except Exception as e:
            self._log(f"Hardware check failed: {str(e)}")

    # =========================================================================
    # FLOW READING
    # =========================================================================

    @pyqtSlot(float)
    def _on_flow_updated(self, flow_value):
        """Slot called from TECWorker polling with fresh flow reading (m/s)."""
        # Skip if monitoring active — flow comes from sweep metadata instead
        if self.monitoring_active:
            return
        self.current_flow = flow_value
        self.flow_card.set_value(flow_value, 3)
        self._calculate_flow_rate()

    def _read_flow_between_sweeps(self):
        """Read flow via G? command between sweeps (fallback when metadata is missing).

        Called from _on_sweep_finished (main thread) — sweep lock already released
        at this point, so a blocking acquire with short timeout is safe.
        """
        if not self.qcm or not self.qcm.serial_connection:
            return
        if not self._serial_lock.acquire(timeout=0.5):
            return
        try:
            self.qcm.serial_connection.reset_input_buffer()
            self.qcm.serial_connection.write(b'G?\n')
            time.sleep(0.05)
            resp = None
            if self.qcm.serial_connection.in_waiting:
                resp = self.qcm.serial_connection.readline().decode().strip()
        except Exception:
            resp = None
        finally:
            self._serial_lock.release()
        if resp:
            try:
                flow_value = float(resp)
                if 0 <= flow_value <= 20:
                    self.current_flow = flow_value
                    self._calculate_flow_rate()
            except ValueError:
                pass

    # =========================================================================
    # STATISTICAL HELPERS
    # =========================================================================

    @staticmethod
    def _median_last_third(samples):
        """Return median of the last third of samples (most stable portion)."""
        n = len(samples)
        if n == 0:
            return 0.0
        third = max(n // 3, 1)
        return float(np.median(samples[-third:]))

    @staticmethod
    def _trimmed_mean(values, trim_frac=0.10):
        """Mean after dropping `trim_frac` of values from each tail.

        Robust against ~10% outliers per side while preserving signal smoothness
        (no staircase artifact like median). For TEMPORAL_BUFFER_SIZE=10 with
        trim=10%, drops 1 value from each end, averages the middle 8.
        """
        n = len(values)
        k = int(n * trim_frac)
        if k == 0 or n <= 2 * k:
            return float(np.mean(values))
        return float(np.mean(np.sort(values)[k:n - k]))

    # =========================================================================
    # FLOW CALIBRATION
    # =========================================================================

    def _on_flow_mode_changed(self, index):
        """Toggle visibility of D / K_cal fields based on flow mode."""
        analytical = (index == 0)
        self.outlet_diam_label.setVisible(analytical)
        self.outlet_diam_spin.setVisible(analytical)
        self.flow_kcal_label.setVisible(not analytical)
        self.flow_kcal_spin.setVisible(not analytical)
        self._calculate_flow_rate()

    def _calculate_flow_rate(self):
        """Calculate volumetric flow rate (L/min) from sensor velocity."""
        v = self.current_flow  # m/s
        if self.flow_mode_combo.currentIndex() == 0:  # Analytical
            d_m = self.outlet_diam_spin.value() / 1000.0  # mm → m
            area = math.pi * d_m ** 2 / 4.0  # m²
            q_m3s = v * area  # m³/s
        else:  # Calibrated
            k_cal = self.flow_kcal_spin.value()
            q_m3s = k_cal * v / 60000.0  # K_cal in L/min/(m/s), convert to m³/s
        self.current_flow_rate = q_m3s * 60000.0  # m³/s → L/min
        self.flow_rate_label.setText(f"Q: {self.current_flow_rate:.3f} L/min")
        self.flow_rate_card.set_value(self.current_flow_rate, 3)

    # =========================================================================
    # MEASUREMENT METHODS
    # =========================================================================

    def _find_peak(self):
        """Start peak finding on worker thread"""
        if not self.qcm or not self.sweep_worker:
            return

        # serial_lock handles coordination with TEC worker

        self.progress.setVisible(True)
        self.find_peak_btn.setEnabled(False)
        self.sweep_btn.setEnabled(False)
        self._update_status("Searching for peak...")

        # Set parameters
        self.sweep_worker.peak_params = {
            'center_freq': int(self.center_freq.value() * 1e6),
            'search_range': self.search_range.value() * 1000,
            'search_step': self.search_step.value()
        }

        # Trigger on worker thread (invokeMethod ensures execution on sweep thread)
        QMetaObject.invokeMethod(self.sweep_worker, "do_find_peak", Qt.QueuedConnection)

    def _do_sweep(self):
        """Start single sweep on worker thread"""
        if not self.qcm or not self.qcm.resonance_freq or not self.sweep_worker:
            QMessageBox.warning(self, "Warning", "Find peak first!")
            return

        self.progress.setVisible(True)
        self.find_peak_btn.setEnabled(False)
        self.sweep_btn.setEnabled(False)
        self._update_status("Sweep in progress...")

        # Set parameters
        self.sweep_worker.sweep_params = {
            'sweep_range': self.fine_range.value() * 1000,
            'step_size': self.fine_step.value()
        }

        # Trigger on worker thread (invokeMethod ensures execution on sweep thread)
        QMetaObject.invokeMethod(self.sweep_worker, "do_sweep", Qt.QueuedConnection)

    def _toggle_monitoring(self):
        if not self.monitoring_active:
            self._start_monitoring()
        else:
            self._stop_monitoring()

    def _start_monitoring(self):
        if not self.qcm or not self.qcm.resonance_freq:
            QMessageBox.warning(self, "Warning", "Find peak first!")
            return

        if not self.sweep_worker:
            QMessageBox.warning(self, "Warning", "Worker thread not initialized!")
            return

        # Ask user for log file path before starting
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_dir = os.path.join(project_dir, 'data')
        os.makedirs(default_dir, exist_ok=True)
        default_name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.csv'
        default_path = os.path.join(default_dir, default_name)

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save monitoring data as...",
            default_path, "CSV (*.csv)"
        )
        if not filepath:
            return  # user cancelled

        self.data_logger = DataLogger(filepath)
        self.data_logger.start()
        self._log(f"Logging to: {filepath}")

        self._tec_invoke("stop_polling")

        self.monitoring_active = True
        self.monitor_btn.setText("Stop Monitor")
        self._set_button_active(self.monitor_btn, True)
        self.find_peak_btn.setEnabled(False)
        self.sweep_btn.setEnabled(False)
        self.cycle_btn.setEnabled(False)

        self.time_data.clear()
        self.freq_data.clear()
        self.dissipation_data.clear()
        self.mass_data.clear()
        self.flow_data.clear()
        self.temperature_data.clear()
        self.monitoring_history.clear()
        # Reset temporal smoothing buffers
        self._freq_buffer.clear()
        self._diss_buffer.clear()
        self._temp_buffer.clear()
        self._sweep_count = 0
        self.start_time = time.time()

        # Flush stale serial data (dialog may have blocked for seconds)
        if self.qcm and self.qcm.serial_connection:
            with self._serial_lock:
                self.qcm.serial_connection.reset_input_buffer()

        self._log("Monitoring started")
        self._update_status("Monitoring active...")
        # Launch first sweep immediately
        self._monitoring_cycle()

    def _stop_monitoring(self):
        self.monitoring_active = False

        # Stop data logger (drains queue, closes file)
        if self.data_logger:
            self.data_logger.stop()
            self._log(f"Data saved: {self.data_logger.filepath}")
            self.data_logger = None

        # Stop pump if running
        if self.pump_active:
            self._log("Auto-stopping pump at monitor stop")
            self._set_pump_speed(0)

        # Auto-disable TEC if active (counterpart to manual TEC enable during monitor)
        if self.temp_control.is_enabled():
            self._log("Auto-disabling TEC at monitor stop")
            self._tec_disable_requested()
        # Restart hardware polling so flow card keeps updating when idle
        self._tec_invoke("start_polling")

        self.monitor_btn.setText("Start Monitor")
        self._set_button_active(self.monitor_btn, False)
        self.find_peak_btn.setEnabled(True)
        self.sweep_btn.setEnabled(True)
        self.cycle_btn.setEnabled(True)
        n = len(self.monitoring_history)
        self._log(f"Monitoring stopped — {n} measurements logged")
        self._update_status("Monitoring stopped")

    # =========================================================================
    # MEASUREMENT CYCLE STATE MACHINE
    # =========================================================================

    def _toggle_cycle(self):
        if not self.cycle_active:
            self._start_cycle()
        else:
            self._stop_cycle()

    def _start_cycle(self):
        if not self.qcm or not self.qcm.resonance_freq:
            QMessageBox.warning(self, "Warning", "Find peak first!")
            return
        if not self.sweep_worker:
            QMessageBox.warning(self, "Warning", "Worker thread not initialized!")
            return

        # Ask user for log file base name
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_dir = os.path.join(project_dir, 'data')
        os.makedirs(default_dir, exist_ok=True)
        default_name = 'cycle_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.csv'
        default_path = os.path.join(default_dir, default_name)

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save cycle data as...",
            default_path, "CSV (*.csv)"
        )
        if not filepath:
            return  # user cancelled

        # Create two loggers: raw monitor + cycle measurements
        base, ext = os.path.splitext(filepath)
        raw_path = base + '_raw' + ext
        cycle_path = filepath

        self.data_logger = DataLogger(raw_path, LOG_COLUMNS)
        self.data_logger.start()
        self.cycle_logger = DataLogger(cycle_path, CYCLE_COLUMNS)
        self.cycle_logger.start()
        self._log(f"Logging raw: {raw_path}")
        self._log(f"Logging cycle: {cycle_path}")

        self.cycle_active = True
        self.cycle_count = 0
        self.ref_frequency = None
        self.ref_dissipation = None
        self.cycle_freq_shifts.clear()
        self.cycle_diss_shifts.clear()
        self.cycle_mass_shifts.clear()
        self.cycle_concentrations.clear()
        self.cycle_meas_freqs.clear()
        self.cycle_meas_disses.clear()
        self._pump_start_time = None
        self._pump_stop_time = None

        # Clear monitoring data and start continuous sweeps
        self.time_data.clear()
        self.freq_data.clear()
        self.dissipation_data.clear()
        self.mass_data.clear()
        self.flow_data.clear()
        self.temperature_data.clear()
        self.monitoring_history.clear()
        # Reset temporal smoothing buffers
        self._freq_buffer.clear()
        self._diss_buffer.clear()
        self._temp_buffer.clear()
        self._sweep_count = 0
        self.start_time = time.time()

        self._tec_invoke("stop_polling")
        self.monitoring_active = True  # drives the sweep timer

        # Flush stale serial data (dialog may have blocked for seconds)
        if self.qcm and self.qcm.serial_connection:
            with self._serial_lock:
                self.qcm.serial_connection.reset_input_buffer()

        self.cycle_btn.setText("Stop Cycle")
        self._set_button_active(self.cycle_btn, True)
        self.monitor_btn.setEnabled(False)
        self.find_peak_btn.setEnabled(False)
        self.pump_on_spin.setEnabled(False)
        self.wait_spin.setEnabled(False)
        # Disable manual pump controls — state machine owns the pump now
        self._set_pump_controls_enabled(False)

        # Auto-enable TEC if not already active (reads current setpoint from widget)
        if not self.temp_control.is_enabled():
            setpoint = self.temp_control.get_setpoint()
            self._log(f"Auto-enabling TEC at setpoint {setpoint}°C for cycle")
            self._tec_enable_requested()

        # Launch first sweep immediately (subsequent ones chain from _on_sweep_finished)
        self._monitoring_cycle()

        # Start elapsed time display
        self.cycle_elapsed_timer.start(1000)

        # Enter REFERENCE state — first sweep result captures baseline
        self._cycle_transition(CycleState.REFERENCE)
        self._log("Cycle started — acquiring reference...")

    def _stop_cycle(self):
        self.cycle_timer.stop()
        self.monitoring_active = False
        self.cycle_active = False
        self.cycle_state = CycleState.IDLE

        # Stop loggers
        if self.data_logger:
            self.data_logger.stop()
            self._log(f"Raw log saved: {self.data_logger.filepath}")
            self.data_logger = None
        if self.cycle_logger:
            self.cycle_logger.stop()
            self._log(f"Cycle log saved: {self.cycle_logger.filepath}")
            self.cycle_logger = None

        # Stop pump if running
        if self.pump_active:
            self._set_pump_speed(0)

        # Auto-disable TEC at end of cycle (counterpart to auto-enable in _start_cycle)
        if self.temp_control.is_enabled():
            self._log("Auto-disabling TEC at cycle end")
            self._tec_disable_requested()
        # Polling restart is handled by _tec_disable_requested if TEC was off,
        # otherwise disable_tec itself will stop polling via the widget.

        self.cycle_elapsed_timer.stop()
        self.cycle_elapsed_label.setText("")

        self.cycle_btn.setText("Start Cycle")
        self._set_button_active(self.cycle_btn, False)
        self.monitor_btn.setEnabled(True)
        self.find_peak_btn.setEnabled(True)
        self.pump_on_spin.setEnabled(True)
        self.wait_spin.setEnabled(True)
        # Re-enable manual pump controls — cycle no longer owns the pump
        self._set_pump_controls_enabled(True)

        # Restart hardware polling so flow card updates when idle (TEC is off,
        # but G? still comes through in _poll_cycle)
        self._tec_invoke("start_polling")

        self._update_cycle_status()
        self._log(f"Cycle stopped after {self.cycle_count} cycles")
        self._update_status("Cycle stopped")

    def _cycle_transition(self, new_state):
        self.cycle_state = new_state
        self._update_cycle_status()

        if new_state == CycleState.REFERENCE:
            self._ref_freq_samples.clear()
            self._ref_diss_samples.clear()
            duration = self.wait_spin.value()
            self.cycle_timer.start(duration * 1000)
            self._log(f"Reference: collecting {duration}s...")
            self._update_status(f"Cycle: reference ({duration}s)")

        elif new_state == CycleState.PUMP_ON:
            self._pump_flow_samples.clear()
            pump_speed = self.pump_slider.value()
            self._set_pump_speed(pump_speed)
            # Record actual pump-start time AFTER the serial command returns
            # (lock may have been held by a sweep — accounts for lock wait)
            self._pump_start_time = time.time()
            duration = self.pump_on_spin.value()
            self.cycle_timer.start(duration * 1000)
            self._log(f"Pump ON (speed={pump_speed}, {duration}s) @ t={self._pump_start_time:.3f}")
            self._update_status(f"Cycle: pump on ({duration}s)")

        elif new_state == CycleState.WAITING:
            self._set_pump_speed(0)
            # Record actual pump-stop time AFTER the serial command returns
            self._pump_stop_time = time.time()
            t_pump_actual = (self._pump_stop_time - self._pump_start_time
                             if self._pump_start_time else 0.0)
            t_pump_nominal = self.pump_on_spin.value()
            drift_ms = (t_pump_actual - t_pump_nominal) * 1000
            self._log(f"Pump OFF @ t={self._pump_stop_time:.3f}  "
                      f"actual={t_pump_actual:.3f}s  "
                      f"nominal={t_pump_nominal}s  drift={drift_ms:+.0f}ms")
            self._meas_freq_samples.clear()
            self._meas_diss_samples.clear()
            duration = self.wait_spin.value()
            self.cycle_timer.start(duration * 1000)
            self._log(f"Settling: collecting {duration}s...")
            self._update_status(f"Cycle: settling ({duration}s)")

    def _cycle_timer_expired(self):
        if not self.cycle_active:
            return
        t_fire = time.time()
        expected = getattr(self, 'cycle_state_start_time', t_fire)
        elapsed = t_fire - expected
        print(f"[CYCLE] timer_expired in state={self.cycle_state.name}  actual_elapsed={elapsed:.2f}s")

        if self.cycle_state == CycleState.REFERENCE:
            # Compute reference from median of last 1/3 of samples
            n = len(self._ref_freq_samples)
            self.ref_frequency = self._median_last_third(self._ref_freq_samples)
            self.ref_dissipation = self._median_last_third(self._ref_diss_samples)
            self._log(f"Reference: f0={self.ref_frequency:.2f} Hz, D0={self.ref_dissipation:.6e}  (median last 1/3 of {n} samples)")
            self._cycle_transition(CycleState.PUMP_ON)

        elif self.cycle_state == CycleState.PUMP_ON:
            self._cycle_transition(CycleState.WAITING)

        elif self.cycle_state == CycleState.WAITING:
            # Compute measurement from median of last 1/3 of samples
            n = len(self._meas_freq_samples)
            freq = self._median_last_third(self._meas_freq_samples)
            diss = self._median_last_third(self._meas_diss_samples)
            self._log(f"Measurement: f={freq:.2f} Hz, D={diss:.6e}  (median last 1/3 of {n} samples)")
            self._finalize_cycle_measurement(freq, diss)

    def _cycle_on_sweep_complete(self, results):
        """Called from _on_sweep_finished when cycle is active — accumulate samples."""
        freq = results.get('current_resonance_freq', 0)
        diss = results.get('dissipation_3sigma', 0)

        if self.cycle_state == CycleState.REFERENCE:
            self._ref_freq_samples.append(freq)
            self._ref_diss_samples.append(diss)
        elif self.cycle_state == CycleState.PUMP_ON:
            self._pump_flow_samples.append(self.current_flow)
        elif self.cycle_state == CycleState.WAITING:
            self._meas_freq_samples.append(freq)
            self._meas_diss_samples.append(diss)

    def _finalize_cycle_measurement(self, freq, diss):
        """Compute deltas, concentration, update plots and CSV after WAITING phase."""
        delta_f = freq - self.ref_frequency
        delta_d = (diss - self.ref_dissipation) * 1e6  # ppm
        # Mass from Sauerbrey equation
        if self.center_freq.value() >= 8:
            sauerbrey = SAUERBREY_CONSTANT_10MHZ
        else:
            sauerbrey = SAUERBREY_CONSTANT_5MHZ
        delta_m = -delta_f * sauerbrey * 1e9  # ng/cm²

        # Concentration: C = Δm_total / V_sampled
        # Use ACTUAL pump-on duration (measured), not nominal — accounts for
        # any lock-wait delays on pump ON/OFF commands, so volume is precise.
        if self._pump_start_time and self._pump_stop_time:
            t_pump = self._pump_stop_time - self._pump_start_time  # seconds (measured)
        else:
            t_pump = float(self.pump_on_spin.value())  # fallback to nominal
        if self._pump_flow_samples:
            v_avg = float(np.mean(self._pump_flow_samples))
        else:
            v_avg = 0.0
        n_flow = len(self._pump_flow_samples)
        flow_mode = "Analytical" if self.flow_mode_combo.currentIndex() == 0 else "Calibrated"
        if self.flow_mode_combo.currentIndex() == 0:  # Analytical
            d_m = self.outlet_diam_spin.value() / 1000.0
            area = math.pi * d_m ** 2 / 4.0
            q_m3s = v_avg * area
            print(f"[CONC] mode={flow_mode}  D={d_m*1000:.1f}mm  area={area:.6e} m²")
        else:  # Calibrated
            k_cal = self.flow_kcal_spin.value()
            q_m3s = k_cal * v_avg / 60000.0
            print(f"[CONC] mode={flow_mode}  K_cal={k_cal:.3f}")
        volume_m3 = q_m3s * t_pump  # m³
        mass_total_ug = delta_m * QUARTZ_AREA_CM2 / 1000.0  # ng/cm² × cm² → ng → µg
        concentration = mass_total_ug / volume_m3 if volume_m3 > 0 else 0.0  # µg/m³
        print(f"[CONC] v_avg={v_avg:.3f} m/s  (N={n_flow} flow samples)  Q={q_m3s:.6e} m³/s  Q={q_m3s*60000:.4f} L/min")
        print(f"[CONC] t_pump={t_pump:.3f}s (measured)  V={volume_m3:.6e} m³")
        print(f"[CONC] Δf={delta_f:.2f} Hz  Δm={delta_m:.4f} ng/cm²  area_qcm={QUARTZ_AREA_CM2} cm²")
        print(f"[CONC] mass_total={mass_total_ug:.6f} µg  C={concentration:.2f} µg/m³")
        n_ref = len(self._ref_freq_samples)
        n_meas = len(self._meas_freq_samples)
        print(f"[CONC] ref_samples={n_ref}  meas_samples={n_meas}  ref_f={self.ref_frequency:.2f}  meas_f={freq:.2f}")

        self.cycle_count += 1
        self.cycle_freq_shifts.append(delta_f)
        self.cycle_diss_shifts.append(delta_d)
        self.cycle_mass_shifts.append(delta_m)
        self.cycle_concentrations.append(concentration)
        self.cycle_meas_freqs.append(freq)
        self.cycle_meas_disses.append(diss * 1e6)  # ppm
        self.mass_card.set_value(delta_m, 2)
        self.conc_card.set_value(concentration, 1)
        self._log(f"Cycle {self.cycle_count}: Δf={delta_f:.1f} Hz, ΔD={delta_d:.2f} ppm, Δm={delta_m:.2f} ng/cm², C={concentration:.1f} µg/m³")
        self._update_cycle_plot()

        # Log cycle measurement to CSV
        if self.cycle_logger:
            now_dt = datetime.now()
            self.cycle_logger.enqueue({
                'date': now_dt.strftime('%Y-%m-%d'),
                'time': now_dt.strftime('%H:%M:%S.%f')[:-3],
                'cycle': str(self.cycle_count),
                'frequency': f"{freq:.2f}",
                'dissipation': f"{diss * 1e6:.6f}",
                'flow': f"{v_avg:.3f}",
                'temperature': f"{self.current_temperature:.2f}",
                'delta_f': f"{delta_f:.2f}",
                'delta_d': f"{delta_d:.6f}",
                'delta_m': f"{delta_m:.4f}",
                'volume': f"{volume_m3 * 1e6:.4f}",
                'concentration': f"{concentration:.2f}",
            })

        # The measured values become the reference for the next cycle
        # (no need to wait again — only first cycle does timed REFERENCE)
        self.ref_frequency = freq
        self.ref_dissipation = diss
        self._log(f"New reference (from measurement): f0={freq:.2f} Hz, D0={diss:.6e}")
        self._cycle_transition(CycleState.PUMP_ON)

    def _update_cycle_status(self):
        state_info = {
            CycleState.IDLE:      ("IDLE",      "#757575"),
            CycleState.REFERENCE: ("REFERENCE", "#2196F3"),
            CycleState.PUMP_ON:   ("PUMP ON",   "#4CAF50"),
            CycleState.WAITING:   ("WAITING",   "#FF9800"),
            CycleState.MEASURE:   ("MEASURE",   "#2196F3"),
        }
        name, color = state_info.get(self.cycle_state, ("?", "#757575"))
        self.cycle_state_label.setText(name)
        self.cycle_state_label.setStyleSheet(f"""
            font-size: 12px; font-weight: bold; color: white;
            background-color: {color}; border-radius: 3px;
            padding: 4px 6px;
        """)
        self.cycle_count_label.setText(f"Cycle: {self.cycle_count}")
        self.cycle_state_start_time = time.time()

    def _update_cycle_elapsed(self):
        if not self.cycle_active:
            self.cycle_elapsed_label.setText("")
            return
        elapsed = int(time.time() - self.cycle_state_start_time)
        # Show remaining time for timed states
        if self.cycle_state == CycleState.REFERENCE:
            total = self.wait_spin.value()
            remaining = max(0, total - elapsed)
            self.cycle_elapsed_label.setText(f"{remaining}s left")
        elif self.cycle_state == CycleState.PUMP_ON:
            total = self.pump_on_spin.value()
            remaining = max(0, total - elapsed)
            self.cycle_elapsed_label.setText(f"{remaining}s left")
        elif self.cycle_state == CycleState.WAITING:
            total = self.wait_spin.value()
            remaining = max(0, total - elapsed)
            self.cycle_elapsed_label.setText(f"{remaining}s left")
        else:
            self.cycle_elapsed_label.setText(f"{elapsed}s")

    def _update_cycle_plot(self):
        if not self.cycle_freq_shifts:
            return
        cycles = list(range(1, len(self.cycle_freq_shifts) + 1))
        self.cycle_freq_curve.setData(cycles, self.cycle_freq_shifts)
        self.cycle_diss_curve.setData(cycles, self.cycle_diss_shifts)
        self.cycle_diss_scatter.setData(cycles, self.cycle_diss_shifts)
        # Auto-scale ΔD viewbox
        diss_vals = self.cycle_diss_shifts
        if diss_vals:
            d_min = min(diss_vals)
            d_max = max(diss_vals)
            margin = max(abs(d_max - d_min) * 0.1, 1e-8)
            self.cycle_diss_viewbox.setYRange(d_min - margin, d_max + margin, padding=0)
        # Update mass bar chart
        if self.cycle_mass_shifts:
            self.mass_bars.setOpts(x=cycles, height=self.cycle_mass_shifts, width=0.6)
        if self.cycle_concentrations:
            self.conc_bars.setOpts(x=cycles, height=self.cycle_concentrations, width=0.6)
        # Update trend plot (absolute median values)
        if self.cycle_meas_freqs:
            self.trend_freq_curve.setData(cycles, self.cycle_meas_freqs)
            self.trend_diss_curve.setData(cycles, self.cycle_meas_disses)
            self.trend_diss_scatter.setData(cycles, self.cycle_meas_disses)
            # Auto-scale trend diss viewbox
            d_vals = self.cycle_meas_disses
            if d_vals:
                d_min = min(d_vals)
                d_max = max(d_vals)
                margin = max(abs(d_max - d_min) * 0.1, 1e-8)
                self.trend_diss_viewbox.setYRange(d_min - margin, d_max + margin, padding=0)

    # Delay between consecutive sweeps (ms)
    SWEEP_DELAY_MS = 100

    def _monitoring_cycle(self):
        """
        Launch a single monitoring sweep on worker thread.
        The next sweep is triggered from _on_sweep_finished after a short delay.
        """
        if not self.qcm or not self.monitoring_active:
            return

        # Set sweep parameters
        self.sweep_worker.sweep_params = {
            'sweep_range': self.fine_range.value() * 1000,
            'step_size': self.fine_step.value()
        }

        # Trigger sweep on worker thread (invokeMethod ensures execution on sweep thread)
        QMetaObject.invokeMethod(self.sweep_worker, "do_sweep", Qt.QueuedConnection)

    def _evict_old_samples(self):
        """Drop samples older than MONITOR_WINDOW_SECONDS from the display buffers.

        Called on the main thread right after each append — no lock needed.
        CSV logging is independent (async queue) and keeps the full session history.
        """
        if not self.time_data:
            return
        cutoff = self.time_data[-1] - MONITOR_WINDOW_SECONDS
        while self.time_data and self.time_data[0] < cutoff:
            self.time_data.popleft()
            self.freq_data.popleft()
            self.dissipation_data.popleft()
            self.mass_data.popleft()
            self.flow_data.popleft()
            self.temperature_data.popleft()

    def _on_sweep_finished(self, results):
        """
        Called when sweep completes on worker thread.
        Updates GUI with results.
        """

        # Drive cycle state machine before early-return check
        if self.cycle_active and results:
            self._cycle_on_sweep_complete(results)

        if not results or not self.monitoring_active:
            return
        if self.start_time is None:
            return

        try:
            t = time.time() - self.start_time
            freq = results.get('current_resonance_freq', 0) or 0
            diss = results.get('dissipation_3sigma', 0) or 0
            q = results.get('q_factor_3sigma', 0) or 0

            # Sweep interval
            now = time.time()
            dt = now - self._last_sweep_time if self._last_sweep_time else 0
            self._last_sweep_time = now
            if dt > 0:
                self.actual_interval_label.setText(f"Actual: {dt:.1f} s")

            # Sauerbrey constant for mass calculation
            if self.center_freq.value() >= 8:
                sauerbrey = SAUERBREY_CONSTANT_10MHZ
            else:
                sauerbrey = SAUERBREY_CONSTANT_5MHZ

            # Shift and mass are only meaningful during a measurement cycle
            # (relative to ref_frequency/ref_dissipation set at cycle start)
            if self.cycle_active and self.ref_frequency:
                shift = freq - self.ref_frequency
                mass = -shift * sauerbrey * 1e9
            else:
                shift = 0
                mass = 0

            # Get metadata from results
            metadata = results.get('metadata', {})

            if metadata.get('valid'):
                self.current_flow = metadata.get('flow', 0.0)
                self.current_temperature = metadata.get('temperature', 0.0)
                self._calculate_flow_rate()

                self.temp_control.update_from_sweep_data(
                    temperature=metadata.get('temperature'),
                    tec_status=metadata.get('tec_status')
                )
            else:
                # Metadata not valid — read flow explicitly via serial
                self._read_flow_between_sweeps()

            # Always update flow and temperature displays
            self.flow_card.set_value(self.current_flow, 3)
            self.temp_card.set_value(self.current_temperature, 1)

            # Temporal smoothing via ring buffer + SG filter
            diss_ppm = diss * 1e6
            self._freq_buffer.append(freq)
            self._diss_buffer.append(diss_ppm)
            self._temp_buffer.append(self.current_temperature)
            self._sweep_count += 1

            if self._sweep_count >= TEMPORAL_BUFFER_SIZE:
                # Trimmed mean (10% per tail) — robust to occasional outliers
                # without the staircase artifact of a median filter.
                freq = self._trimmed_mean(self._freq_buffer)
                diss_ppm = self._trimmed_mean(self._diss_buffer)
                self.current_temperature = self._trimmed_mean(self._temp_buffer)
                # Recalculate shift/mass with smoothed frequency (only during cycle)
                if self.cycle_active and self.ref_frequency:
                    shift = freq - self.ref_frequency
                    mass = -shift * sauerbrey * 1e9 if shift != 0 else 0

            # Store data in buffers (rolling window)
            self.time_data.append(t)
            self.freq_data.append(freq)
            self.dissipation_data.append(diss_ppm)
            self.mass_data.append(mass)
            self.flow_data.append(self.current_flow)
            self.temperature_data.append(self.current_temperature)
            # Evict samples older than MONITOR_WINDOW_SECONDS
            self._evict_old_samples()

            # Store in history for export
            self.monitoring_history.append({
                'time': t,
                'frequency': freq,
                'shift': shift,
                'dissipation': diss,
                'q_factor': q,
                'mass': mass,
                'flow': self.current_flow,
                'temperature': self.current_temperature,
                'tec_status': metadata.get('tec_status', 0) if metadata.get('valid') else 0,
                'tec_error': metadata.get('tec_error', 0) if metadata.get('valid') else 0,
                'pump_speed': metadata.get('pump_speed', 0) if metadata.get('valid') else 0
            })

            # Async data logging to CSV
            if self.data_logger:
                now_dt = datetime.now()
                self.data_logger.enqueue({
                    'date': now_dt.strftime('%Y-%m-%d'),
                    'time': now_dt.strftime('%H:%M:%S.%f')[:-3],
                    'relative_time': f"{t:.3f}",
                    'frequency': f"{freq:.2f}",
                    'dissipation': f"{diss_ppm:.6f}",
                    'mass': f"{mass:.4f}",
                    'flow': f"{self.current_flow:.3f}",
                    'temperature': f"{self.current_temperature:.2f}",
                })

            # Update UI cards
            self.freq_card.set_value_custom(freq, "{:,.0f}")
            self.diss_card.set_value(diss_ppm, 1)

            # Update sweep plots
            self._update_sweep_plots(results)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log(f"Error processing sweep results: {str(e)}")

        # Schedule next sweep after short delay
        if self.monitoring_active:
            QTimer.singleShot(self.SWEEP_DELAY_MS, self._monitoring_cycle)

    def _on_sweep_error(self, error_msg):
        """Called when sweep fails on worker thread"""
        pass  # error handled by GUI status bar
        self._log(f"Sweep error: {error_msg}")
        if self.cycle_active:
            self._log(f"Cycle state: {self.cycle_state.name} — sweep failed, retrying next cycle")
        # Retry on error during monitoring
        if self.monitoring_active:
            QTimer.singleShot(1000, self._monitoring_cycle)

    def _on_peak_found(self, data):
        """Called when peak finding completes on worker thread"""
        self.progress.setVisible(False)
        self.find_peak_btn.setEnabled(True)
        self.sweep_btn.setEnabled(True)
        self.monitor_btn.setEnabled(True)
        self.cycle_btn.setEnabled(True)

        resonance = data.get('resonance')
        sweep_data = data.get('sweep_data')

        if resonance:
            self.initial_frequency = resonance
            self.freq_card.set_value(resonance, 0)
            self.mass_card.set_value(0)
            self.conc_card.set_value(0)
            self._update_status(f"Resonance: {resonance/1e6:.6f} MHz")
            self._log(f"Peak found: {resonance/1e6:.6f} MHz")

            if sweep_data:
                self._update_sweep_plots(sweep_data)

    def _on_peak_error(self, error_msg):
        """Called when peak finding fails on worker thread"""
        self.progress.setVisible(False)
        self.find_peak_btn.setEnabled(True)
        self.sweep_btn.setEnabled(True)

        self._log(f"Peak finding error: {error_msg}")
        QMessageBox.warning(self, "Error", error_msg)

    # =========================================================================
    # PUMP METHODS
    # =========================================================================

    def _start_pump(self):
        self._set_pump_speed(self.pump_slider.value())

    def _stop_pump(self):
        self._set_pump_speed(0)

    def _set_pump_speed(self, speed):
        """Send pump speed command. Uses a guaranteed-delivery strategy to avoid
        dropping critical cycle commands (especially pump STOP at WAITING start).

        Retry up to 3 times with 10s timeout each — worst case ~30s block, but
        any skip is logged loudly. Typical lock wait is <100ms.
        """
        if not self.qcm or not self.qcm.serial_connection:
            return
        MAX_ATTEMPTS = 3
        TIMEOUT_S = 10.0
        t0 = time.time()
        lock_acquired = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._serial_lock.acquire(timeout=TIMEOUT_S):
                lock_acquired = True
                break
            wait = time.time() - t0
            self._log(f"[PUMP] B{speed} lock busy after {wait:.1f}s (attempt {attempt}/{MAX_ATTEMPTS})")
            time.sleep(0.2)
        if not lock_acquired:
            self._log(f"[PUMP] CRITICAL: B{speed} DROPPED after {time.time()-t0:.1f}s — pump state may be wrong!")
            return
        wait_s = time.time() - t0
        if wait_s > 0.5:
            self._log(f"[PUMP] B{speed} sent after {wait_s:.2f}s lock wait")
        try:
            self.qcm.serial_connection.write(f"B{speed}\n".encode())
            self._log(f"TX → B{speed}")
        except Exception as e:
            self._log(f"Error: {str(e)}")
            self._serial_lock.release()
            return
        self._serial_lock.release()
        # GUI updates outside the lock
        self.pump_progress.setValue(round(speed * 100 / 255))
        if speed > 0:
            self.pump_active = True
        else:
            self.pump_active = False
        # During cycle, the state machine owns the pump — don't toggle manual
        # buttons (they're kept disabled by _set_pump_controls_enabled(False)).
        if not self.cycle_active:
            if speed > 0:
                self.pump_start_btn.setEnabled(False)
                self.pump_stop_btn.setEnabled(True)
            else:
                self.pump_start_btn.setEnabled(True)
                self.pump_stop_btn.setEnabled(False)

    # =========================================================================
    # PLOT METHODS
    # =========================================================================

    def _update_plots(self):
        if len(self.time_data) > 0:
            times = list(self.time_data)

            # Frequency plot (primary axis)
            self.freq_curve.setData(times, list(self.freq_data))

            # Dissipation plot (secondary axis on same graph)
            self.diss_curve.setData(times, list(self.dissipation_data))

            # Auto-scale dissipation viewbox
            if len(self.dissipation_data) > 0:
                diss_values = list(self.dissipation_data)
                diss_min = min(diss_values)
                diss_max = max(diss_values)
                margin = max((diss_max - diss_min) * 0.1, 1.0)  # at least ±1 PPM
                self.diss_viewbox.setYRange(diss_min - margin, diss_max + margin, padding=0)

            # Temperature plot
            if len(self.temperature_data) > 0:
                self.temp_curve.setData(times, list(self.temperature_data))

            # Flow plot
            if len(self.flow_data) > 0:
                self.flow_curve.setData(times, list(self.flow_data))

    def _update_sweep_plots(self, data):
        if not data or 'frequencies' not in data:
            return
        freqs = data['frequencies'] / 1e6
        amps = data['amplitudes']
        phases = data['phases']

        edge = int(len(amps) * 0.1)
        noise = np.concatenate([amps[:edge], amps[-edge:]])
        noise_std = np.std(noise)
        noise_mean = np.mean(noise)
        snr = (amps - noise_mean) / noise_std if noise_std > 0 else np.zeros_like(amps)

        # Raw data as scatter points
        self.amp_raw_scatter.setData(freqs, amps)

        # SG-filtered curve (same frequency axis as raw)
        if 'amplitudes_filtered' in data:
            self.amp_curve.setData(freqs, data['amplitudes_filtered'])
        else:
            self.amp_curve.setData(freqs, amps)

        self.phase_raw_scatter.setData(freqs, phases)
        if 'phases_filtered' in data:
            self.phase_curve.setData(freqs, data['phases_filtered'])
        else:
            self.phase_curve.setData(freqs, phases)
        self.snr_curve.setData(freqs, snr)

        if 'resonance_freq' in data and data['resonance_freq']:
            res = data['resonance_freq'] / 1e6
            self.amp_res_line.setValue(res)
            self.phase_res_line.setValue(res)

        # Gain peak marker (star) — computed from displayed filtered data
        amp_display = data.get('amplitudes_filtered', amps)
        gain_idx = np.argmax(amp_display)
        self.gain_peak_marker.setData([freqs[gain_idx]], [amp_display[gain_idx]])

        # Phase peak marker (square) — computed from displayed filtered data
        phase_display = data.get('phases_filtered', phases)
        phase_idx = np.argmax(phase_display)
        self.phase_peak_marker.setData([freqs[phase_idx]], [phase_display[phase_idx]])

        if 'f_min' in data and 'f_max' in data:
            self.bw_region.setRegion([data['f_min']/1e6, data['f_max']/1e6])
            self.bw_region.setVisible(True)
        else:
            self.bw_region.setVisible(False)

        # TEC polling restart is handled by _stop_monitoring / _stop_cycle

    def _update_results(self, data):
        if not data:
            return
        freq = data.get('current_resonance_freq', data.get('resonance_freq', 0))
        self.freq_card.set_value(freq, 0)
        self.diss_card.set_value(data.get('dissipation_3sigma', 0), 2)
        self.q_card.set_value(data.get('q_factor_3sigma', 0), 0)

        lines = [
            "═" * 30,
            "  QCM-D RESULTS",
            "═" * 30,
            "",
            f"f₀:      {data.get('f0', 0)/1e6:.6f} MHz",
            f"f_min:   {data.get('f_min', 0)/1e6:.6f} MHz",
            f"f_max:   {data.get('f_max', 0)/1e6:.6f} MHz",
            "",
            f"Bandwidth:  {data.get('bandwidth', 0):.1f} Hz",
            f"Q-Factor:   {data.get('q_factor_3sigma', 0):.0f}",
            f"Diss:       {data.get('dissipation_3sigma', 0):.2f}",
            "",
            f"SNR:     {data.get('snr', 0):.2f}",
            f"Quality: {data.get('quality_level', 'N/A')}",
            f"Points:  {data.get('num_points', 0)}"
        ]
        self.results_text.setPlainText("\n".join(lines))

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _on_crystal_changed(self, crystal_type):
        if crystal_type in CRYSTAL_OPTIONS:
            cfg = CRYSTAL_OPTIONS[crystal_type]
            self.center_freq.setValue(cfg['center_freq'] / 1e6)
            self.search_range.setValue(cfg['search_range'] // 1000)
            self.search_step.setValue(cfg['search_step'])
            self.fine_range.setValue(cfg['fine_range'] // 1000)
            self.fine_step.setValue(cfg['fine_step'])

    # ── Plot management ──────────────────────────────────────────────
    def _clear_all_plots(self):
        """Clear all monitoring data and reset plots."""
        # Clear time-series buffers
        self.time_data.clear()
        self.freq_data.clear()
        self.dissipation_data.clear()
        self.mass_data.clear()
        self.flow_data.clear()
        self.temperature_data.clear()
        self.monitoring_history.clear()

        # Clear temporal smoothing buffers
        self._freq_buffer.clear()
        self._diss_buffer.clear()
        self._temp_buffer.clear()
        self._sweep_count = 0

        # Clear cycle data
        self.cycle_freq_shifts.clear()
        self.cycle_diss_shifts.clear()
        self.cycle_mass_shifts.clear()
        self.cycle_concentrations.clear()
        self.cycle_meas_freqs.clear()
        self.cycle_meas_disses.clear()

        # Reset time reference
        self.start_time = None

        # Clear all plot curves
        empty = []
        self.freq_curve.setData(empty, empty)
        self.diss_curve.setData(empty, empty)
        self.temp_curve.setData(empty, empty)
        self.flow_curve.setData(empty, empty)
        self.cycle_freq_curve.setData(empty, empty)
        self.cycle_diss_curve.setData(empty, empty)
        self.mass_bars.setOpts(x=[], height=[], width=0.6)
        self.conc_bars.setOpts(x=[], height=[], width=0.6)
        self.trend_freq_curve.setData(empty, empty)
        self.trend_diss_curve.setData(empty, empty)
        self.trend_diss_scatter.setData(empty, empty)

        # Reset cards
        self.freq_card.set_value(0)
        self.diss_card.set_value(0)
        self.mass_card.set_value(0)
        self.flow_card.set_value(0)

        self._log("All plots cleared")

    def _autoscale_all_plots(self):
        """Autoscale X and Y axes on all plots."""
        # Monitoring tab plots
        self.freq_plot.enableAutoRange()
        self.diss_viewbox.enableAutoRange()
        self.temp_plot.enableAutoRange()
        self.flow_plot.enableAutoRange()
        self.cycle_plot.enableAutoRange()
        self.cycle_diss_viewbox.enableAutoRange()
        self.mass_plot.enableAutoRange()

        # Sweep tab plots
        self.amp_plot.enableAutoRange()
        self.phase_plot.enableAutoRange()

        self._log("All plots autoscaled")

    def _clear_resonance(self):
        if self.qcm:
            reply = QMessageBox.question(
                self, "Confirm",
                "Clear saved frequency?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.qcm.clear_saved_resonance()
                self.initial_frequency = None
                self._log("Resonance cleared")

    def _send_command(self):
        if not self.qcm or not self.qcm.serial_connection:
            return
        cmd = self.cmd_combo.currentText().strip()
        if not cmd:
            return
        if not self._serial_lock.acquire(timeout=3.0):
            self._log(f"Command {cmd} skipped — serial busy")
            return
        try:
            self.qcm.serial_connection.write((cmd + '\n').encode())
            self._log(f"TX → {cmd}")
            time.sleep(0.1)
            resp = None
            if self.qcm.serial_connection.in_waiting:
                resp = self.qcm.serial_connection.readline().decode().strip()
        except Exception as e:
            self._log(f"Error: {str(e)}")
            resp = None
        finally:
            self._serial_lock.release()
        if resp:
            self._log(f"RX ← {resp}")

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.append(f"[{ts}] {msg}")
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_status(self, msg):
        self.status_bar.showMessage(msg)

    def _save_data(self):
        if not self.current_data:
            QMessageBox.warning(self, "Warning", "No data!")
            return
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save",
            f"qcm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON (*.json);;CSV (*.csv)"
        )
        if fn:
            try:
                if fn.endswith('.json'):
                    data = self.current_data.copy()
                    for k, v in data.items():
                        if isinstance(v, np.ndarray):
                            data[k] = v.tolist()
                    with open(fn, 'w') as f:
                        json.dump(data, f, indent=2)
                elif fn.endswith('.csv'):
                    df = pd.DataFrame({
                        'Frequency_Hz': self.current_data['frequencies'],
                        'Amplitude': self.current_data['amplitudes'],
                        'Phase': self.current_data['phases']
                    })
                    df.to_csv(fn, index=False)
                self._log(f"Saved: {fn}")
                QMessageBox.information(self, "Success", f"Saved to {fn}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _save_monitoring(self):
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save",
            f"monitoring_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV (*.csv)"
        )
        if fn:
            try:
                df = pd.DataFrame(self.monitoring_history)
                df.to_csv(fn, index=False)
                self._log(f"Saved: {fn}")
            except Exception as e:
                self._log(f"Error: {str(e)}")

    def _save_plots(self):
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save",
            f"plots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "PNG (*.png)"
        )
        if fn:
            try:
                from pyqtgraph.exporters import ImageExporter
                exp = ImageExporter(self.amp_plot.plotItem)
                exp.export(fn)
                self._log(f"Saved: {fn}")
                QMessageBox.information(self, "Success", f"Saved to {fn}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # =========================================================================
    # TEMPERATURE CONTROL CALLBACKS
    # =========================================================================

    def _on_temperature_changed(self, temperature):
        """Callback when temperature reading changes"""
        self.current_temperature = temperature
        self.temp_card.set_value(temperature, 1)

    def _on_tec_status_changed(self, status):
        """Callback when TEC status changes"""
        status_messages = {
            -1: "TEC Error",
            0: "TEC Inactive",
            1: "TEC Approaching target",
            2: "TEC In target"
        }
        msg = status_messages.get(status, "TEC Unknown")
        self._update_status(msg)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Confirm",
            "Are you sure you want to quit?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            event.ignore()
            return

        # Stop cycle, monitoring (flushes data logger) and pump
        if self.cycle_active:
            self._stop_cycle()
        if self.monitoring_active:
            self._stop_monitoring()
        if self.pump_active:
            self._stop_pump()

        # Stop TEC worker thread
        if self.tec_worker:
            self._tec_invoke("stop_polling")
        if self.tec_thread and self.tec_thread.isRunning():
            self.tec_thread.quit()
            self.tec_thread.wait()

        # Stop sweep worker thread
        if self.sweep_thread and self.sweep_thread.isRunning():
            self.sweep_thread.quit()
            self.sweep_thread.wait()

        # Disconnect QCM
        if self.qcm:
            self.qcm.disconnect()

        event.accept()


# =============================================================================
# MAIN
# =============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Application icon (Mac dock / Windows taskbar)
    # Prefer .ico on Windows, .png elsewhere (Qt handles both but .ico has multi-res)
    if sys.platform.startswith('win') and os.path.exists(APP_ICON_ICO):
        app.setWindowIcon(QIcon(APP_ICON_ICO))
        # Windows: required so the taskbar groups properly under our app ID
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                u'novaetech.openqcm.aerosol'
            )
        except Exception:
            pass
    elif os.path.exists(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS['background']))
    palette.setColor(QPalette.WindowText, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.Base, QColor(COLORS['surface']))
    palette.setColor(QPalette.Text, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.Button, QColor(COLORS['surface']))
    palette.setColor(QPalette.ButtonText, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.Highlight, QColor(COLORS['primary']))
    palette.setColor(QPalette.HighlightedText, QColor('#FFFFFF'))
    app.setPalette(palette)

    window = OpenQCMAerosolGUI()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
