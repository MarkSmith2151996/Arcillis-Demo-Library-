"""Launch the dockable Arcillis Demo Bench desktop application."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QMainWindow, QMessageBox, QStatusBar

from db import is_available
from plugins.base import DemoPlugin
from plugins.document_extractor import DocumentExtractorPlugin


class DemoBench(QMainWindow):
    """Host registered demos in a stable shell with dockable work areas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Arcillis Demo Bench")
        self.resize(1440, 900)
        self.setDockNestingEnabled(True)
        self.plugins: list[DemoPlugin] = [DocumentExtractorPlugin(self)]
        self.active_plugin: DemoPlugin | None = None
        self._setup_demo_selector()
        self._setup_menu()
        self._setup_status_bar()
        self._activate_plugin(0)
        self._default_layout = self.saveState()

    def _setup_demo_selector(self) -> None:
        self.demo_selector = QListWidget()
        self.demo_selector.setMinimumWidth(190)
        self.demo_selector.addItems([f"{plugin.icon}  {plugin.name}" for plugin in self.plugins])
        self.demo_selector.currentRowChanged.connect(self._activate_plugin)
        selector_dock = self._make_selector_dock()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, selector_dock)
        self.demo_selector.setCurrentRow(0)

    def _make_selector_dock(self):  # type: ignore[no-untyped-def]
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("Demos", self)
        dock.setObjectName("demoSelectorDock")
        dock.setWidget(self.demo_selector)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        return dock

    def _setup_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(QAction("Quit", self, shortcut="Ctrl+Q", triggered=self.close))
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(QAction("Reset Layout", self, triggered=self._reset_layout))
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(QAction("About", self, triggered=self._show_about))

    def _setup_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        available = is_available()
        indicator = QLabel("●")
        indicator.setForegroundRole(QPalette.ColorRole.BrightText if available else QPalette.ColorRole.Text)
        indicator.setStyleSheet(f"color: {'#45c26b' if available else '#db5a5a'};")
        status_bar.addPermanentWidget(indicator)
        status_bar.addPermanentWidget(QLabel("Postgres connected" if available else "Postgres unavailable"))

    def _activate_plugin(self, index: int) -> None:
        if index < 0 or index >= len(self.plugins):
            return
        if self.active_plugin:
            self.active_plugin.deactivate()
        self.active_plugin = self.plugins[index]
        self.active_plugin.activate()

    def _reset_layout(self) -> None:
        """Restore the original dock areas, tabs, and visibility for this shell."""
        self.restoreState(self._default_layout)
        if self.active_plugin:
            self.active_plugin.activate()

    def _show_about(self) -> None:
        QMessageBox.about(self, "About Arcillis Demo Bench", "Arcillis Demo Bench\nDocument automation demonstrations.")


def apply_dark_palette(app: QApplication) -> None:
    """Set a restrained dark client-facing palette without external stylesheets."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#20242b"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f1f3f5"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#181b20"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#292e36"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#f1f3f5"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#20242b"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#f1f3f5"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#303640"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f1f3f5"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2878c7"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#6f7783"))
    app.setPalette(palette)


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_palette(app)
    window = DemoBench()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
