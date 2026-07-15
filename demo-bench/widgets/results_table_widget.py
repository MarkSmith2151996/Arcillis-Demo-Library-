"""Extraction result table and field-level comparison dialog for Demo Bench."""

from __future__ import annotations

import json
import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db import get_connection


QUERY = """
SELECT e.id, e.invoice_id, e.run_id, e.model_used, e.extracted_data,
       e.field_scores, e.overall_accuracy, e.processing_time_ms, e.extracted_at,
       i.filename, i.dataset_source, i.image_path, i.ground_truth
FROM arcillis.demo2_extraction e
JOIN arcillis.demo2_invoice i ON e.invoice_id = i.id
ORDER BY e.extracted_at DESC
"""

HEADERS = ["", "#", "Filename", "Dataset", "Grade", "Model", "Run", "Fields", "Extracted"]
GRADE_COLORS = ((95.0, "#d4edda"), (80.0, "#fff3cd"), (0.0, "#f8d7da"))


class SelectionHeader(QHeaderView):
    """A horizontal header with a checkbox in its first section."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.checked = False
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logical_index: int) -> None:  # type: ignore[no-untyped-def]
        super().paintSection(painter, rect, logical_index)
        if logical_index == 0:
            self.style().drawPrimitive(
                self.style().PrimitiveElement.PE_IndicatorCheckBox,
                self._checkbox_option(rect),
                painter,
                self,
            )

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.logicalIndexAt(event.position().toPoint()) == 0:
            self.checked = not self.checked
            self.toggled.emit(self.checked)
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def set_checked(self, checked: bool) -> None:
        if self.checked != checked:
            self.checked = checked
            self.viewport().update()

    def _checkbox_option(self, rect):  # type: ignore[no-untyped-def]
        from PySide6.QtWidgets import QStyleOptionButton

        option = QStyleOptionButton()
        option.rect = self.style().subElementRect(
            self.style().SubElement.SE_CheckBoxIndicator, option, self
        )
        option.rect.moveCenter(rect.center())
        option.state = (
            self.style().StateFlag.State_Enabled
            | (self.style().StateFlag.State_On if self.checked else self.style().StateFlag.State_Off)
        )
        return option


class ResultsTableWidget(QWidget):
    """Display stored extraction results and expose checked rows for export."""

    invoice_selected = Signal(int)
    selection_changed = Signal(int)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[dict[str, Any]] = []
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.header = SelectionHeader(self.table)
        self.table.setHorizontalHeader(self.header)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 42)
        self.table.setColumnWidth(3, 82)
        self.table.setColumnWidth(4, 76)
        self.table.setColumnWidth(7, 72)

        self.header.toggled.connect(self._set_all_checked)
        self.table.itemChanged.connect(self._checkbox_changed)
        self.table.cellClicked.connect(self._select_invoice)
        self.table.cellDoubleClicked.connect(self._show_detail)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.table)
        self.reload()

    def reload(self) -> None:
        """Fetch every extraction with its invoice metadata from Postgres."""
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(QUERY)
                    columns = [column.name for column in cursor.description]
                    self.rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        except Exception as error:
            self.rows = []
            self.status_changed.emit(f"Could not load extraction results: {error}")
        self._populate()

    def get_selected_data(self) -> list[dict[str, Any]]:
        """Return checked extraction rows in their current visible table order."""
        return [self.rows[self._row_index(row)] for row in range(self.table.rowCount()) if self._is_checked(row)]

    def get_all_data(self) -> list[dict[str, Any]]:
        """Return every loaded extraction row in its current visible table order."""
        return [self.rows[self._row_index(row)] for row in range(self.table.rowCount())]

    def _populate(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            checkbox.setData(Qt.ItemDataRole.UserRole, row_index)
            checkbox.setBackground(QBrush(QColor(self._grade_color(self._accuracy(row)))))
            self.table.setItem(row_index, 0, checkbox)
            values = [
                str(row_index + 1),
                os.path.basename(str(row["filename"])),
                str(row["dataset_source"] or ""),
                f"{self._accuracy(row):.1f}%",
                str(row["model_used"] or ""),
                str(row["run_id"] or ""),
                f"{len(self._json(row['field_scores']))} fields",
                str(row["extracted_at"] or "")[:10],
            ]
            color = QBrush(QColor(self._grade_color(self._accuracy(row))))
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row_index)
                item.setBackground(color)
                self.table.setItem(row_index, column, item)
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.header.set_checked(False)
        self.selection_changed.emit(0)

    def _row_index(self, table_row: int) -> int:
        item = self.table.item(table_row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _is_checked(self, table_row: int) -> bool:
        return self.table.item(table_row, 0).checkState() == Qt.CheckState.Checked

    def _set_all_checked(self, checked: bool) -> None:
        self.table.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)
        self.table.blockSignals(False)
        self.selection_changed.emit(self.table.rowCount() if checked else 0)

    def _checkbox_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        checked_count = sum(self._is_checked(row) for row in range(self.table.rowCount()))
        self.header.set_checked(checked_count == self.table.rowCount() and bool(checked_count))
        self.selection_changed.emit(checked_count)

    def _select_invoice(self, table_row: int, _: int) -> None:
        self.invoice_selected.emit(int(self.rows[self._row_index(table_row)]["invoice_id"]))

    def _show_detail(self, table_row: int, _: int) -> None:
        row = self.rows[self._row_index(table_row)]
        extracted = self._flatten(self._json(row["extracted_data"]))
        ground_truth = self._flatten(self._json(row["ground_truth"]))
        scores = self._json(row["field_scores"])

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Field Detail: {os.path.basename(str(row['filename']))}")
        detail = QTableWidget(0, 3)
        detail.setHorizontalHeaderLabels(["Field", "Extracted Value", "Ground Truth"])
        detail.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for field, value in extracted.items():
            detail.insertRow(detail.rowCount())
            passed = bool(scores.get(field))
            color = QBrush(QColor("#d4edda" if passed else "#f8d7da"))
            for column, cell_value in enumerate((field, self._display(value), self._display(ground_truth.get(field, "")))):
                item = QTableWidgetItem(cell_value)
                item.setBackground(color)
                detail.setItem(detail.rowCount() - 1, column, item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Green fields matched ground truth; red fields did not."))
        layout.addWidget(detail)
        layout.addWidget(buttons)
        dialog.resize(900, 600)
        dialog.exec()

    @staticmethod
    def _json(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}

    @classmethod
    def _flatten(cls, value: Any, prefix: str = "") -> dict[str, Any]:
        if isinstance(value, dict):
            return {key: child for name, item in value.items() for key, child in cls._flatten(item, f"{prefix}.{name}" if prefix else name).items()}
        if isinstance(value, list):
            return {key: child for index, item in enumerate(value) for key, child in cls._flatten(item, f"{prefix}[{index}]").items()}
        return {prefix: value}

    @staticmethod
    def _display(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _accuracy(row: dict[str, Any]) -> float:
        try:
            return float(row["overall_accuracy"])
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _grade_color(accuracy: float) -> str:
        return next(color for threshold, color in GRADE_COLORS if accuracy >= threshold)
