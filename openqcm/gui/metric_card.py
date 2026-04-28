"""MetricCard widget for displaying real-time metrics."""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt

from openqcm.constants import COLORS


class MetricCard(QFrame):
    def __init__(self, title, unit="", color=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.color = color or COLORS['primary']
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(56)
        self.setMinimumWidth(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['divider']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        title_label = QLabel(self.title)
        title_label.setStyleSheet(f"""
            font-size: 8px;
            color: {COLORS['text_secondary']};
            background: transparent;
            border: none;
        """)
        layout.addWidget(title_label)

        value_layout = QHBoxLayout()
        value_layout.setSpacing(2)

        self.value_label = QLabel("---")
        self.value_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {self.color};
            background: transparent;
            border: none;
        """)
        value_layout.addWidget(self.value_label)

        unit_label = QLabel(self.unit)
        unit_label.setStyleSheet(f"""
            font-size: 8px;
            color: {COLORS['text_secondary']};
            background: transparent;
            border: none;
        """)
        value_layout.addWidget(unit_label, alignment=Qt.AlignBottom)
        value_layout.addStretch()

        layout.addLayout(value_layout)

    def set_value(self, value, decimals=2):
        if isinstance(value, (int, float)):
            if abs(value) >= 1e6:
                text = f"{value/1e6:.{decimals}f}M"
            elif abs(value) >= 1e3:
                text = f"{value/1e3:.{decimals}f}k"
            else:
                text = f"{value:.{decimals}f}"
        else:
            text = str(value) if value else "---"
        self.value_label.setText(text)

    def set_value_custom(self, value, format_str):
        """Set value with custom format string"""
        if isinstance(value, (int, float)):
            try:
                text = format_str.format(value)
            except (ValueError, TypeError):
                text = str(value)
        else:
            text = str(value) if value else "---"
        self.value_label.setText(text)

    def set_color(self, color):
        self.value_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {color};
            background: transparent;
            border: none;
        """)
