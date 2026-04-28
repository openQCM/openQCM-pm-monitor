"""Dark theme stylesheet and plot utilities for openQCM Aerosol GUI."""

import pyqtgraph as pg
from openqcm.constants import COLORS

# Shorthand aliases
BG      = COLORS['background']
SURFACE = COLORS['surface']
BORDER  = COLORS['border']
TEXT    = COLORS['text']
TEXT_DIM = COLORS['text_dim']
ACCENT  = COLORS['accent']
ACCENT_H = COLORS['accent_hover']
RED     = COLORS['red']
GREEN   = COLORS['green']
YELLOW  = COLORS['yellow']

# ── Plot pens / symbols ────────────────────────────────────────────
PEN_RAW = None   # no line for raw dots
SYMBOL_RAW = {"symbol": "o", "symbolSize": 1.5, "symbolBrush": YELLOW, "symbolPen": None}
PEN_FREQ = pg.mkPen(color=ACCENT, width=2)
PEN_DISS = pg.mkPen(color=RED, width=2)
PEN_TEMP = pg.mkPen(color=RED, width=2)
PEN_FLOW = pg.mkPen(color=GREEN, width=2)
PEN_MASS = pg.mkPen(color=ACCENT_H, width=2)

# ── Qt stylesheet ──────────────────────────────────────────────────
MODERN_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "SF Pro Text", "Segoe UI", "Roboto", sans-serif;
    font-size: 11px;
}}

/* --- Sidebar --- */
QWidget#sidebar {{
    background-color: {SURFACE};
    border-right: 1px solid {BORDER};
}}

/* --- Status bar --- */
QWidget#status_bar {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
}}

/* --- Group boxes --- */
QGroupBox {{
    font-weight: bold;
    font-size: 10px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 12px;
    padding: 8px 4px 4px 4px;
    background-color: {SURFACE};
    color: {TEXT};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 6px;
    margin-left: 6px;
    margin-top: 2px;
    background-color: {BORDER};
    color: {TEXT};
    border-radius: 3px;
    font-size: 10px;
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {SURFACE};
    margin-top: -1px;
}}
QTabBar::tab {{
    background: {BG};
    color: {TEXT_DIM};
    padding: 6px 16px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 10px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 10px;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {BORDER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT};
    color: {BG};
}}
QPushButton:disabled {{
    background-color: {BG};
    color: {TEXT_DIM};
    border-color: {BORDER};
}}

/* --- Inputs --- */
QComboBox {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    font-size: 10px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox::down-arrow {{
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {TEXT_DIM};
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: {BG};
    border: 1px solid {BORDER};
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 20px;
    font-size: 10px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}

/* --- Slider --- */
QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    border: none;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* --- Labels --- */
QLabel {{
    color: {TEXT};
    font-size: 10px;
    padding: 0px;
    margin: 0px;
}}
QLabel#section_label {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 8px 0 2px 0;
}}
QLabel#measurement_title {{
    color: {TEXT_DIM};
    font-size: 11px;
    padding: 4px 0 0 0;
}}
QLabel#measurement_value {{
    color: {ACCENT};
    font-size: 16px;
    font-weight: 600;
    padding: 0 0 4px 0;
}}

/* --- Progress bar --- */
QProgressBar {{
    border: none;
    border-radius: 3px;
    text-align: center;
    font-size: 9px;
    background-color: {BORDER};
    color: {TEXT};
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* --- Console --- */
QTextEdit {{
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {BG};
    color: {TEXT};
    font-family: 'Monaco', 'Consolas', 'Courier New', monospace;
    font-size: 10px;
    padding: 4px;
}}

/* --- Checkbox --- */
QCheckBox {{
    font-size: 10px;
    spacing: 4px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 12px;
    height: 12px;
    border-radius: 2px;
    border: 1px solid {BORDER};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* --- Status bar --- */
QStatusBar {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
    font-size: 10px;
    padding: 2px 6px;
    min-height: 18px;
    color: {TEXT};
}}

/* --- Splitter --- */
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:horizontal:hover {{
    background-color: {ACCENT};
}}
QSplitter::handle:vertical {{
    height: 1px;
}}

/* --- Scrollbar --- */
QScrollBar:vertical {{
    border: none;
    background: {BG};
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    border: none;
    background: {BG};
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* --- Separator --- */
QFrame#separator {{
    color: {BORDER};
    margin: 6px 0;
}}

/* --- Message box (quit dialog etc.) --- */
QMessageBox {{
    background-color: {SURFACE};
    color: {TEXT};
}}
"""


# ── Custom axis classes ────────────────────────────────────────────

class NonScientificAxis(pg.AxisItem):
    """Axis that displays values as plain integers — no scientific notation."""

    def tickStrings(self, values, scale, spacing):
        return [f"{int(v)}" for v in values]


class OneDecimalAxis(pg.AxisItem):
    """Axis that displays values with exactly 1 decimal place."""

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.1f}" for v in values]


# ── Plot configuration helpers ─────────────────────────────────────

def configure_plot_widget(pw, left_label="", bottom_label="Time (s)",
                          axis_type="integer"):
    """Apply dark theme styling to a pyqtgraph PlotWidget.

    axis_type: "integer" for NonScientificAxis, "decimal" for OneDecimalAxis, None to skip
    """
    # Replace left axis with custom axis
    if axis_type == "decimal":
        custom_axis = OneDecimalAxis(orientation="left")
        pw.setAxisItems({"left": custom_axis})
    elif axis_type == "integer":
        custom_axis = NonScientificAxis(orientation="left")
        pw.setAxisItems({"left": custom_axis})

    # Disable SI prefix AFTER axis is attached
    pw.getAxis("left").enableAutoSIPrefix(False)

    pw.setBackground(SURFACE)
    pw.getAxis("left").setPen(pg.mkPen(color=TEXT_DIM))
    pw.getAxis("bottom").setPen(pg.mkPen(color=TEXT_DIM))
    pw.getAxis("left").setTextPen(pg.mkPen(color=TEXT_DIM))
    pw.getAxis("bottom").setTextPen(pg.mkPen(color=TEXT_DIM))
    pw.setLabel("left", left_label, color=TEXT_DIM)
    pw.setLabel("bottom", bottom_label, color=TEXT_DIM)
    pw.showGrid(x=True, y=True, alpha=0.15)

    # Install custom right-click context menu
    _install_context_menu(pw)


def _install_context_menu(pw):
    """Replace pyqtgraph's default right-click menu with a themed one."""
    from PyQt5 import QtCore, QtWidgets

    plot_item = pw.getPlotItem()
    plot_item.setMenuEnabled(False)
    plot_item.getViewBox().setMenuEnabled(False)

    def on_right_click(event):
        if event.button() != QtCore.Qt.RightButton:
            return

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: {ACCENT};
                color: {BG};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER};
                margin: 4px 8px;
            }}
        """)

        act_autoscale = menu.addAction("Auto-scale")
        act_reset = menu.addAction("Reset Zoom")
        menu.addSeparator()
        act_pan = menu.addAction("Pan Mode")
        act_select = menu.addAction("Select Mode")

        pos = event.screenPos()
        action = menu.exec_(QtCore.QPoint(int(pos.x()), int(pos.y())))

        if action == act_autoscale:
            pw.enableAutoRange()
        elif action == act_reset:
            pw.getViewBox().autoRange()
        elif action == act_pan:
            pw.getViewBox().setMouseMode(pg.ViewBox.PanMode)
        elif action == act_select:
            pw.getViewBox().setMouseMode(pg.ViewBox.RectMode)

        event.accept()

    plot_item.scene().sigMouseClicked.connect(on_right_click)


# ── Native (no-style) alternative ─────────────────────────────────
# Minimal stylesheet: only sets font. Everything else is native PyQt5.

NATIVE_STYLESHEET = """
QWidget {
    font-family: "SF Pro Text", "Segoe UI", "Roboto", sans-serif;
    font-size: 11px;
}

/* Fixed height for all push buttons — uniform across enabled/disabled/active states. */
QPushButton {
    min-height: 20px;
    max-height: 20px;
}

/* Disabled controls appear clearly grey.
   Note: QSlider is intentionally NOT styled here — applying any QSS rule to
   QSlider breaks the native macOS look and shows a grey groove even when
   enabled. The native platform greys out disabled sliders automatically. */
QPushButton:disabled {
    color: #9A9A9A;
    background-color: #E8E8E8;
    border: 1px solid #CFCFCF;
}
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #9A9A9A;
    background-color: #F2F2F2;
}

/* Toggle buttons highlighted blue when "active" (Temperature On, Start Monitor, Start Cycle).
   NOTE: no padding/border-radius override so button dimensions match the default (non-active) state. */
QPushButton[active="true"] {
    background-color: #008EC0;
    color: white;
    font-weight: bold;
}
QPushButton[active="true"]:hover {
    background-color: #0A9FD4;
}
QPushButton[active="true"]:pressed {
    background-color: #006E96;
}
"""


def configure_plot_widget_native(pw, left_label="", bottom_label="Time (s)",
                                 axis_type="integer"):
    """Apply native (light) styling to a pyqtgraph PlotWidget."""
    if axis_type == "decimal":
        pw.setAxisItems({"left": OneDecimalAxis(orientation="left")})
    elif axis_type == "integer":
        pw.setAxisItems({"left": NonScientificAxis(orientation="left")})

    pw.getAxis("left").enableAutoSIPrefix(False)
    pw.setBackground("w")
    for axis_name in ("left", "bottom"):
        ax = pw.getAxis(axis_name)
        ax.setPen(pg.mkPen(color="#444444"))
        ax.setTextPen(pg.mkPen(color="#444444"))
    pw.setLabel("left", left_label, color="#444444")
    pw.setLabel("bottom", bottom_label, color="#444444")
    pw.showGrid(x=True, y=True, alpha=0.2)
