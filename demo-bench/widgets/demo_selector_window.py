"""Landing dialog for choosing an Arcillis demo workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QVBoxLayout


class DemoCard(QFrame):
    """A dark-theme clickable demo tile with distinct label hierarchy."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setObjectName("demoCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(360, 180)
        self.setStyleSheet(
            "QFrame#demoCard { background: #292e36; border: 1px solid #414955; border-radius: 12px; } "
            "QFrame#demoCard:hover { background: #303b48; border: 2px solid #2878c7; }"
        )

        icon = QLabel("DOC")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("color: #74b5ef; font-size: 16px; font-weight: 700;")
        title = QLabel("Document Extractor")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        description = QLabel("AI-powered invoice and receipt data extraction")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet("color: #aeb7c4; font-size: 13px;")
        for label in (icon, title, description):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(8)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(description)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class DemoSelectorWindow(QDialog):
    """Present available demos before the main workspace is created."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.selected_index: int | None = None
        self.setWindowTitle("Arcillis Demo Bench")
        self.setModal(True)
        self.setFixedSize(600, 400)

        title = QLabel("Arcillis Demo Bench")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 600;")
        subtitle = QLabel("Choose a demo workspace")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #aeb7c4;")

        card = DemoCard()
        card.clicked.connect(lambda: self._select_demo(0))

        cards = QGridLayout()
        cards.addWidget(card, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 44, 48, 44)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
        layout.addLayout(cards)
        layout.addStretch()

    def _select_demo(self, index: int) -> None:
        self.selected_index = index
        self.accept()
