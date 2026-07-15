"""Workflow navigation for the Document Extractor demo."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class NavToolbar(QWidget):
    """Expose the Document Extractor workflow stages as styled navigation tabs."""

    tab_changed = Signal(str)

    _ACTIVE_STYLE = """
        QPushButton {
            background: #2878c7;
            color: white;
            border: none;
            border-radius: 4px;
            font-weight: bold;
            padding: 0 16px;
        }
        QPushButton:hover { background: #3a8ad9; }
    """
    _INACTIVE_STYLE = """
        QPushButton {
            background: transparent;
            color: #aab2bd;
            border: none;
            border-radius: 4px;
            padding: 0 16px;
        }
        QPushButton:hover { background: #2a2f38; }
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("background: #20242b;")
        self._active_tab = ""
        self.buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        for tab, label in (
            ("intake", "Intake"),
            ("browse", "Browse"),
            ("results", "Results"),
            ("export", "Export"),
        ):
            button = QPushButton(label)
            button.setFlat(True)
            button.clicked.connect(lambda checked=False, name=tab: self.set_active_tab(name))
            self.buttons[tab] = button
            layout.addWidget(button)
        layout.addStretch()
        self._update_button_styles()

    def set_active_tab(self, tab: str) -> None:
        """Highlight and announce a selected workflow stage."""
        if tab not in self.buttons:
            return
        self._active_tab = tab
        self._update_button_styles()
        self.tab_changed.emit(tab)

    def _update_button_styles(self) -> None:
        for tab, button in self.buttons.items():
            button.setStyleSheet(self._ACTIVE_STYLE if tab == self._active_tab else self._INACTIVE_STYLE)
