"""Drag-and-drop intake zone for user-supplied document images and PDFs."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPen
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from db import get_connection


SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}
INTAKE_DIR = Path(__file__).resolve().parent.parent / "intake"


class IntakeWidget(QWidget):
    """Accept PDFs and image files, materialize them locally, and record them in Postgres."""

    ingested = Signal(int)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(220)

        self.message = QLabel("Drop documents here")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = QLabel("PDF, PNG, JPG, or TIFF")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browse_button = QPushButton("Browse Files")
        self.browse_button.clicked.connect(self.browse_files)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.message)
        layout.addWidget(self.hint)
        layout.addWidget(self.browse_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        files = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self._ingest(files)
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(self.palette().ColorRole.Midlight), 2, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(self.rect().adjusted(6, 6, -6, -6), 10, 10)

    def browse_files(self) -> None:
        """Select one or more supported source files without drag and drop."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose documents",
            str(Path.home()),
            "Documents (*.pdf *.png *.jpg *.jpeg *.tiff *.tif)",
        )
        self._ingest([Path(path) for path in paths])

    def _ingest(self, files: list[Path]) -> None:
        created: list[Path] = []
        try:
            for source in files:
                if source.suffix.lower() == ".pdf":
                    created.extend(self._render_pdf(source))
                elif source.suffix.lower() in SUPPORTED_IMAGES:
                    created.append(self._copy_image(source))
            self._record_documents(created)
        except (OSError, ValueError, RuntimeError) as error:
            self.status_changed.emit(f"Unable to ingest documents: {error}")
            return

        if created:
            count = len(created)
            self.message.setText(f"{count} document{'s' if count != 1 else ''} added")
            self.status_changed.emit(f"{count} documents added")
            self.ingested.emit(count)

    @staticmethod
    def _intake_path(source: Path, suffix: str | None = None) -> Path:
        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        extension = suffix or source.suffix.lower()
        destination = INTAKE_DIR / f"{source.stem}{extension}"
        number = 2
        while destination.exists():
            destination = INTAKE_DIR / f"{source.stem}-{number}{extension}"
            number += 1
        return destination

    def _copy_image(self, source: Path) -> Path:
        destination = self._intake_path(source)
        shutil.copy2(source, destination)
        return destination

    def _render_pdf(self, source: Path) -> list[Path]:
        document = QPdfDocument(self)
        document.load(str(source))
        if document.status() != QPdfDocument.Status.Ready:
            raise RuntimeError(f"could not open PDF {source.name}")

        rendered: list[Path] = []
        for page in range(document.pageCount()):
            image = document.render(page, QSize(1800, 2400))
            if image.isNull():
                raise RuntimeError(f"could not render page {page + 1} of {source.name}")
            destination = self._intake_path(Path(f"{source.stem}-page-{page + 1}"), ".png")
            if not image.save(str(destination), "PNG"):
                raise RuntimeError(f"could not save page {page + 1} of {source.name}")
            rendered.append(destination)
        return rendered

    @staticmethod
    def _record_documents(paths: list[Path]) -> None:
        if not paths:
            return
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for path in paths:
                    cursor.execute(
                        """
                        INSERT INTO arcillis.demo2_invoice
                            (filename, image_path, dataset_source, split)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (path.name, str(path), "user_upload", "intake"),
                    )
