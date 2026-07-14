"""Zoomable image viewer for the currently selected source document."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from db import image_path_to_url


LOCAL_UPLOAD_PREFIX = "mac-local://"


class DocumentViewerWidget(QWidget):
    """Show one image at a time with fit, 100 percent, and incremental zoom."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.filename = QLabel("No document selected")
        self.filename.setWordWrap(True)
        self.image_label = QLabel("Choose a document from File Browser")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(300, 240)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(False)
        self._original = QPixmap()
        self._zoom = 1.0
        self._network = QNetworkAccessManager(self)
        self._image_reply: QNetworkReply | None = None

        toolbar = QToolBar()
        fit_action = QAction("Fit width", self, triggered=self.fit_to_width)
        zoom_out_action = QAction("-", self, triggered=lambda: self._adjust_zoom(0.8))
        actual_action = QAction("100%", self, triggered=self.actual_size)
        zoom_in_action = QAction("+", self, triggered=lambda: self._adjust_zoom(1.25))
        for action in (fit_action, zoom_out_action, actual_action, zoom_in_action):
            toolbar.addAction(action)

        layout = QVBoxLayout(self)
        layout.addWidget(self.filename)
        layout.addWidget(toolbar)
        layout.addWidget(self.scroll_area)

    def show_document(self, image_path: str, filename: str) -> None:
        """Load a selected document over HTTP and fit it into the viewer width."""
        self.filename.setText(filename)
        self._original = QPixmap()
        previous_reply = self._image_reply
        if previous_reply is not None:
            previous_reply.abort()
            previous_reply.deleteLater()
        if image_path.startswith(LOCAL_UPLOAD_PREFIX):
            self.image_label.setText("This Mac-only upload is not available from the file server")
            return
        self.image_label.setText("Loading document...")
        url = image_path_to_url(image_path)
        print(f"Document request: {url}")
        reply = self._network.get(QNetworkRequest(QUrl(url)))
        self._image_reply = reply
        reply.finished.connect(lambda: self._document_loaded(reply, filename))

    def fit_to_width(self) -> None:
        """Scale the displayed document to the available content width."""
        if self._original.isNull():
            return
        width = max(1, self.scroll_area.viewport().width() - 12)
        self._zoom = width / self._original.width()
        self._apply_zoom()

    def actual_size(self) -> None:
        """Restore the document's native image size."""
        self._zoom = 1.0
        self._apply_zoom()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if not self._original.isNull() and self._zoom < 1:
            self.fit_to_width()

    def _adjust_zoom(self, multiplier: float) -> None:
        self._zoom = min(4.0, max(0.1, self._zoom * multiplier))
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        size = self._original.size() * self._zoom
        self.image_label.setPixmap(
            self._original.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self.image_label.resize(self.image_label.pixmap().size())

    def _document_loaded(self, reply: QNetworkReply, filename: str) -> None:
        if reply is not self._image_reply:
            reply.deleteLater()
            return
        self._image_reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.image_label.setText(f"Cannot load {filename}")
            print(f"Document failed ({reply.errorString()}): {reply.url().toString()}")
            reply.deleteLater()
            return
        print(
            f"Document response {reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 200}: "
            f"{reply.url().toString()}"
        )
        self._original = QPixmap()
        if not self._original.loadFromData(reply.readAll()):
            self.image_label.setText(f"Cannot load {filename}")
            reply.deleteLater()
            return
        reply.deleteLater()
        self.fit_to_width()
