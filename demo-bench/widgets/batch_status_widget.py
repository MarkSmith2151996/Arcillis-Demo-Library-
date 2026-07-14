"""Placeholder batch progress widget for the next document-extraction task."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class BatchStatusWidget(QWidget):
    """Display idle or future batch-processing progress."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addStretch()

    def set_progress(self, current: int, total: int) -> None:
        """Provide the future extraction workflow a small update surface."""
        if total <= 0:
            self.status.setText("Ready")
            self.progress.setValue(0)
            return
        self.status.setText(f"Processing {current}/{total}...")
        self.progress.setValue(round(current / total * 100))
