"""Minimal contract for demos hosted by Demo Bench."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PySide6.QtWidgets import QDockWidget


class DemoPlugin(ABC):
    """A dock-widget based demo that can be selected in the main shell."""

    name: str
    icon: str
    widgets: list[QDockWidget]

    @abstractmethod
    def activate(self) -> None:
        """Show this demo's widgets when it becomes the active demo."""

    @abstractmethod
    def deactivate(self) -> None:
        """Hide this demo's widgets before another demo is activated."""
