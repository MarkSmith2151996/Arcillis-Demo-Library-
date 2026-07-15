"""Document Extractor demo plugin and its dockable data-display widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow

from db import resolve_local_image_path
from plugins.base import DemoPlugin
from widgets.batch_status_widget import BatchStatusWidget
from widgets.chat_widget import ChatWidget
from widgets.document_viewer_widget import DocumentViewerWidget
from widgets.file_browser_widget import FileBrowserWidget
from widgets.intake_widget import IntakeWidget
from widgets.export_widget import ExportWidget
from widgets.results_table_widget import ResultsTableWidget


class DocumentExtractorPlugin(DemoPlugin):
    """Provide the initial document intake and inspection workspace."""

    name = "Document Extractor"
    icon = "DOC"

    def __init__(self, window: QMainWindow) -> None:
        self.window = window
        self.intake = IntakeWidget()
        self.intake.setMaximumWidth(300)
        self.browser = FileBrowserWidget()
        self.viewer = DocumentViewerWidget()
        self.batch_status = BatchStatusWidget()
        self.results_table = ResultsTableWidget()
        self.export = ExportWidget(self.results_table)
        self.chat = ChatWidget(
            window,
            demo_name="document_extractor",
            mcp_server_url="http://100.95.20.98:8098",
        )
        self.widgets = [
            self._dock("Intake", self.intake),
            self._dock("Document Viewer", self.viewer),
            self._dock("Batch Status", self.batch_status),
            self._dock("Results Table", self.results_table),
            self._dock("Export", self.export),
        ]
        self.widgets[0].setMaximumWidth(320)
        self._added = False
        self.intake.ingested.connect(lambda _: self.browser.reload())
        self.intake.status_changed.connect(window.statusBar().showMessage)
        self.browser.status_changed.connect(window.statusBar().showMessage)
        self.browser.document_selected.connect(self.viewer.show_document)
        self.results_table.status_changed.connect(window.statusBar().showMessage)
        self.results_table.invoice_selected.connect(self._show_result_document)
        self.chat.highlight_requested.connect(self._highlight_invoice)

    def activate(self) -> None:
        if not self._added:
            self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.widgets[0])
            self.window.setCentralWidget(self.browser)
            self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.widgets[1])
            self.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.widgets[2])
            self.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.widgets[3])
            self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.widgets[4])
            self.window.resizeDocks(self.widgets[:2], [300, 300], Qt.Orientation.Horizontal)
            self.window.resizeDocks(self.widgets[2:4], [180, 240], Qt.Orientation.Vertical)
            self._added = True
        self.browser.show()
        for widget in self.widgets:
            widget.show()
        self.chat.show()

    def deactivate(self) -> None:
        self.browser.hide()
        for widget in self.widgets:
            widget.hide()
        self.chat.hide()

    def _show_result_document(self, invoice_id: int) -> None:
        """Load the source image stored alongside the clicked extraction result."""
        for row in self.results_table.rows:
            if row["invoice_id"] == invoice_id:
                self.viewer.show_document(resolve_local_image_path(row["image_path"]), row["filename"])
                return

    def _highlight_invoice(self, invoice_id: int) -> None:
        """Select an invoice from assistant output and display its source document."""
        for table_row in range(self.results_table.table.rowCount()):
            item = self.results_table.table.item(table_row, 0)
            if item is None:
                continue
            row_index = int(item.data(Qt.ItemDataRole.UserRole))
            if self.results_table.rows[row_index]["invoice_id"] == invoice_id:
                self.results_table.table.selectRow(table_row)
                self.results_table.table.scrollToItem(item)
                self._show_result_document(invoice_id)
                return
        self.window.statusBar().showMessage(f"Invoice {invoice_id} is not loaded in Results Table.")

    @staticmethod
    def _dock(title: str, content) -> QDockWidget:  # type: ignore[no-untyped-def]
        dock = QDockWidget(title)
        dock.setObjectName(f"documentExtractor{title.replace(' ', '')}Dock")
        dock.setWidget(content)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        return dock
