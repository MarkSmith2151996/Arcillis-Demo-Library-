"""Lazy thumbnail browser backed by the Demo 2 invoice table."""

from __future__ import annotations

from dataclasses import dataclass
from PySide6.QtCore import QEvent, Qt, QUrl, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from db import FILE_SERVER_URL, get_connection


BATCH_SIZE = 50
LOCAL_UPLOAD_PREFIX = "mac-local://"


def image_path_to_url(image_path: str) -> str:
    """Map a database WSL path onto the PC's HTTP file server."""
    base = "/home/dev/projects/Arcillis-Demo-Library/"
    relative = image_path[len(base) :] if image_path.startswith(base) else image_path
    return f"{FILE_SERVER_URL}/{relative}"


@dataclass(frozen=True)
class DocumentRecord:
    """One browser item returned by the source-document query."""

    id: int
    filename: str
    image_path: str
    dataset_source: str | None
    split: str | None


class ThumbnailCell(QFrame):
    """A thumbnail whose body opens a document while its checkbox supports batching."""

    viewed = Signal(DocumentRecord)
    checked = Signal(int, bool)

    def __init__(self, record: DocumentRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = record
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(120, 120)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setText("Loading...")
        self._network = QNetworkAccessManager(self)
        self.name = QLabel(record.filename)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setWordWrap(True)
        self.checkbox = QCheckBox("Select")
        self.checkbox.toggled.connect(lambda checked: self.checked.emit(record.id, checked))
        self.thumbnail.installEventFilter(self)
        self.name.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.thumbnail, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name)

        self._load_thumbnail()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.checkbox.geometry().contains(event.position().toPoint()):
            self.viewed.emit(self.record)
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched in (self.thumbnail, self.name) and event.type() == QEvent.Type.MouseButtonRelease:
            self.viewed.emit(self.record)
            return True
        return super().eventFilter(watched, event)

    def set_selected(self, selected: bool) -> None:
        palette = self.palette()
        role = self.backgroundRole()
        palette.setColor(role, palette.color(palette.ColorRole.Highlight if selected else palette.ColorRole.Window))
        self.setPalette(palette)

    def _load_thumbnail(self) -> None:
        if self.record.image_path.startswith(LOCAL_UPLOAD_PREFIX):
            self.thumbnail.setText("Mac-only upload")
            return
        reply = self._network.get(QNetworkRequest(QUrl(image_path_to_url(self.record.image_path))))
        reply.finished.connect(lambda: self._thumbnail_loaded(reply))

    def _thumbnail_loaded(self, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                self.thumbnail.setPixmap(
                    pixmap.scaled(
                        114,
                        114,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.thumbnail.setText("Invalid image")
        else:
            self.thumbnail.setText("Preview unavailable")
        reply.deleteLater()


class FileBrowserWidget(QWidget):
    """Filter and lazily render document thumbnails from Postgres."""

    document_selected = Signal(str, str)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.records: list[DocumentRecord] = []
        self.loaded = 0
        self.total = 0
        self.selected_ids: set[int] = set()
        self.cells: dict[int, ThumbnailCell] = {}

        self.source_filter = QComboBox()
        self.source_filter.addItems(["All sources", "donut", "mychen76", "user_upload"])
        self.split_filter = QComboBox()
        self.split_filter.addItems(["All splits", "train", "test", "validation", "intake"])
        self.source_filter.currentIndexChanged.connect(self.reload)
        self.split_filter.currentIndexChanged.connect(self.reload)
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_loaded)
        self.deselect_all_button = QPushButton("Deselect All")
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.selection_label = QLabel("0 of 0 selected")

        filters = QHBoxLayout()
        filters.addWidget(self.source_filter)
        filters.addWidget(self.split_filter)
        filters.addWidget(self.select_all_button)
        filters.addWidget(self.deselect_all_button)
        filters.addStretch()
        filters.addWidget(self.selection_label)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(10)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.grid_widget)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._maybe_load_more)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.scroll_area)
        self.reload()

    def reload(self, *_: object) -> None:
        """Refresh the filtered source list and render its first thumbnail batch."""
        self.records = []
        self.loaded = 0
        self.total = 0
        self.selected_ids.clear()
        self.cells.clear()
        self._clear_grid()
        try:
            clauses, params = self._filters()
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*) FROM arcillis.demo2_invoice{where}", params)
                    self.total = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT id, filename, image_path, dataset_source, split "
                        f"FROM arcillis.demo2_invoice{where} ORDER BY id DESC",
                        params,
                    )
                    self.records = [DocumentRecord(*row) for row in cursor.fetchall()]
        except Exception as error:  # UI remains usable when the remote database is down.
            self.status_changed.emit(f"Could not load documents: {error}")
        self._load_more()
        self._update_selection_label()

    def select_loaded(self) -> None:
        """Select every filtered item without forcing every thumbnail to load."""
        self.selected_ids.update(record.id for record in self.records)
        for cell in self.cells.values():
            cell.checkbox.blockSignals(True)
            cell.checkbox.setChecked(True)
            cell.checkbox.blockSignals(False)
            cell.set_selected(True)
        self._update_selection_label()

    def deselect_all(self) -> None:
        self.selected_ids.clear()
        for cell in self.cells.values():
            cell.checkbox.blockSignals(True)
            cell.checkbox.setChecked(False)
            cell.checkbox.blockSignals(False)
            cell.set_selected(False)
        self._update_selection_label()

    def _filters(self) -> tuple[list[str], list[str]]:
        clauses: list[str] = []
        params: list[str] = []
        if self.source_filter.currentIndex() > 0:
            clauses.append("dataset_source = %s")
            params.append(self.source_filter.currentText())
        if self.split_filter.currentIndex() > 0:
            clauses.append("split = %s")
            params.append(self.split_filter.currentText())
        return clauses, params

    def _maybe_load_more(self, value: int) -> None:
        bar = self.scroll_area.verticalScrollBar()
        if value >= bar.maximum() - 100:
            self._load_more()

    def _load_more(self) -> None:
        batch = self.records[self.loaded : self.loaded + BATCH_SIZE]
        for record in batch:
            cell = ThumbnailCell(record)
            cell.viewed.connect(self._view_document)
            cell.checked.connect(self._toggle_selected)
            if record.id in self.selected_ids:
                cell.checkbox.blockSignals(True)
                cell.checkbox.setChecked(True)
                cell.checkbox.blockSignals(False)
                cell.set_selected(True)
            position = self.loaded
            self.grid.addWidget(cell, position // 4, position % 4)
            self.cells[record.id] = cell
            self.loaded += 1

    def _view_document(self, record: DocumentRecord) -> None:
        self.document_selected.emit(record.image_path, record.filename)

    def _toggle_selected(self, document_id: int, selected: bool) -> None:
        if selected:
            self.selected_ids.add(document_id)
        else:
            self.selected_ids.discard(document_id)
        self.cells[document_id].set_selected(selected)
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        self.selection_label.setText(f"{len(self.selected_ids)} of {self.total} selected")

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
