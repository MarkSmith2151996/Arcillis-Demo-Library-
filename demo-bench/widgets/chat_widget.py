"""Floating, threaded assistant chat for the Document Extractor demo."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from openai import OpenAI
from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


SYSTEM_PROMPT = """You are an AI assistant embedded in a document extraction demo application.
You help users understand extraction results, investigate accuracy issues,
and take actions like exporting data or reprocessing invoices.

You have access to tools that let you query the extraction database,
get detailed results, export data, and control the application.

Be concise and practical. When a user asks about data, use your query
tools rather than guessing. When showing numbers, format them clearly."""

LOCAL_UI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "highlight_invoice",
            "description": "Select an invoice in the results table and load its source document.",
            "parameters": {
                "type": "object",
                "properties": {"invoice_id": {"type": "integer"}},
                "required": ["invoice_id"],
            },
        },
    }
]


def _post_json(url: str, payload: dict[str, Any], timeout: int = 20) -> Any:
    """POST JSON without adding another HTTP dependency to the desktop app."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP server returned HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach MCP server: {error.reason}") from error


class ToolDiscoveryWorker(QThread):
    """Fetch tool definitions without blocking Demo Bench startup."""

    tools_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, demo_name: str, server_url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.demo_name = demo_name
        self.server_url = server_url.rstrip("/")

    def run(self) -> None:
        try:
            tools = _post_json(f"{self.server_url}/mcp/tools/list", {"demo": self.demo_name})
            if not isinstance(tools, list):
                raise RuntimeError("MCP tool discovery returned an invalid response.")
            self.tools_ready.emit(tools)
        except Exception as error:
            self.error_occurred.emit(str(error))


class ChatWorker(QThread):
    """Run DeepSeek and MCP tool calls outside the Qt event loop."""

    response_ready = Signal(str, list)
    tool_started = Signal(str)
    tool_result_ready = Signal(str, dict)
    error_occurred = Signal(str)
    highlight_requested = Signal(int)

    def __init__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        demo_name: str,
        server_url: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.messages = messages
        self.tools = tools
        self.demo_name = demo_name
        self.server_url = server_url.rstrip("/")

    def run(self) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            self.error_occurred.emit("DEEPSEEK_API_KEY is not set.")
            return
        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.messages[-20:]]
            for _ in range(6):
                request: dict[str, Any] = {"model": "deepseek-v4-flash", "messages": messages}
                if self.tools:
                    request["tools"] = self.tools
                response = client.chat.completions.create(**request)
                message = response.choices[0].message
                tool_calls = message.tool_calls or []
                if not tool_calls:
                    text = message.content or "I completed that request."
                    messages.append({"role": "assistant", "content": text})
                    self.response_ready.emit(text, messages[1:])
                    return

                messages.append(message.model_dump(exclude_none=True))
                for tool_call in tool_calls:
                    name = tool_call.function.name
                    self.tool_started.emit(name)
                    try:
                        arguments = json.loads(tool_call.function.arguments or "{}")
                        result = self._call_tool(name, arguments)
                    except (json.JSONDecodeError, ValueError, RuntimeError) as error:
                        result = {"error": str(error)}
                    self.tool_result_ready.emit(name, result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            self.error_occurred.emit("The assistant exceeded the tool-call limit for this request.")
        except Exception as error:
            self.error_occurred.emit(str(error))

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "highlight_invoice":
            invoice_id = arguments.get("invoice_id")
            if not isinstance(invoice_id, int):
                raise ValueError("highlight_invoice requires an integer invoice_id.")
            self.highlight_requested.emit(invoice_id)
            return {"status": "highlighted", "invoice_id": invoice_id}
        result = _post_json(
            f"{self.server_url}/mcp/tools/call",
            {"demo": self.demo_name, "tool": name, "args": arguments},
        )
        return result if isinstance(result, dict) else {"error": "MCP tool returned an invalid response."}


class ChatWidget(QObject):
    """Manage a bottom-right chat bubble and its floating conversation panel."""

    highlight_requested = Signal(int)

    def __init__(self, main_window: QWidget, demo_name: str, mcp_server_url: str) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.demo_name = demo_name
        self.mcp_server_url = mcp_server_url.rstrip("/")
        self.history: list[dict[str, Any]] = []
        self.mcp_tools: list[dict[str, Any]] = []
        self._worker: ChatWorker | None = None

        self.bubble = QPushButton("💬", main_window)
        self.bubble.setFixedSize(48, 48)
        self.bubble.setToolTip("Ask about extraction results")
        self.bubble.setStyleSheet("border-radius: 24px; background: #2878c7; color: white; font-size: 20px;")
        self.bubble.clicked.connect(self._expand)

        self.panel = QFrame(main_window, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel.setStyleSheet("QFrame { background: #252a32; border: 1px solid #4a5360; border-radius: 8px; }")
        self._build_panel()
        self.panel.hide()
        main_window.installEventFilter(self)
        self._position_overlays()
        self._discover_tools()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.main_window and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            QTimer.singleShot(0, self._position_overlays)
        return super().eventFilter(watched, event)

    def show(self) -> None:
        self.bubble.show()
        if self.panel.isVisible():
            self.panel.show()
        self._position_overlays()

    def hide(self) -> None:
        self.bubble.hide()
        self.panel.hide()

    def _build_panel(self) -> None:
        title = QLabel(f"{self.demo_name.replace('_', ' ').title()} Assistant")
        title.setStyleSheet("font-weight: bold; border: none;")
        close = QPushButton("×")
        close.setFixedSize(28, 28)
        close.setStyleSheet("border: none; font-size: 20px;")
        close.clicked.connect(self._collapse)
        title_bar = QHBoxLayout()
        title_bar.addWidget(title)
        title_bar.addStretch()
        title_bar.addWidget(close)

        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("border: none;")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(8, 8, 8, 8)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.messages_widget)
        self.scroll_area.setStyleSheet("border: none; background: #1d2127;")

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about your extraction results...")
        self.input.returnPressed.connect(self._send)
        send = QPushButton("Send")
        send.clicked.connect(self._send)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(send)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.addLayout(title_bar)
        layout.addWidget(self.scroll_area, 1)
        layout.addLayout(input_row)
        self._add_message("assistant", "Ask me about extraction accuracy, invoices, or exports.")

    def _discover_tools(self) -> None:
        self.discovery = ToolDiscoveryWorker(self.demo_name, self.mcp_server_url, self)
        self.discovery.tools_ready.connect(self._set_tools)
        self.discovery.error_occurred.connect(self._tool_discovery_failed)
        self.discovery.start()

    def _set_tools(self, tools: list[dict[str, Any]]) -> None:
        self.mcp_tools = [{"type": "function", "function": tool} for tool in tools]
        self.bubble.setToolTip("Ask about extraction results")

    def _tool_discovery_failed(self, error: str) -> None:
        self.bubble.setToolTip(f"MCP tools unavailable: {error}")

    def _expand(self) -> None:
        self.panel.show()
        self.panel.raise_()
        self.bubble.hide()
        self.input.setFocus()

    def _collapse(self) -> None:
        self.panel.hide()
        self.bubble.show()
        self.bubble.raise_()

    def _position_overlays(self) -> None:
        margin = 16
        bubble_x = max(margin, self.main_window.width() - self.bubble.width() - margin)
        bubble_y = max(margin, self.main_window.height() - self.bubble.height() - margin)
        self.bubble.move(bubble_x, bubble_y)
        panel_width = min(400, max(280, self.main_window.width() - margin * 2))
        panel_height = min(500, max(300, self.main_window.height() - margin * 2))
        self.panel.resize(panel_width, panel_height)
        global_pos = self.main_window.mapToGlobal(self.main_window.rect().bottomRight())
        self.panel.move(global_pos.x() - panel_width - margin, global_pos.y() - panel_height - margin)

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text or self._worker is not None:
            return
        self.input.clear()
        self.history.append({"role": "user", "content": text})
        self.history = self.history[-20:]
        self._add_message("user", text)
        self._worker = ChatWorker(
            self.history.copy(),
            [*self.mcp_tools, *LOCAL_UI_TOOLS],
            self.demo_name,
            self.mcp_server_url,
            self,
        )
        self._worker.tool_started.connect(self._show_tool_started)
        self._worker.tool_result_ready.connect(self._show_tool_result)
        self._worker.highlight_requested.connect(self.highlight_requested.emit)
        self._worker.response_ready.connect(self._receive_response)
        self._worker.error_occurred.connect(self._receive_error)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _show_tool_started(self, name: str) -> None:
        label = name.replace("_", " ")
        self._add_message("tool", f"🔧 {label.title()}...")

    def _show_tool_result(self, name: str, result: dict[str, Any]) -> None:
        if "error" in result:
            self._add_message("tool", f"{name}: {result['error']}")

    def _receive_response(self, text: str, history: list[dict[str, Any]]) -> None:
        self.history = history[-20:]
        self._add_message("assistant", text)

    def _receive_error(self, error: str) -> None:
        self._add_message("assistant", f"I could not complete that request: {error}")

    def _worker_finished(self) -> None:
        if self._worker:
            self._worker.deleteLater()
        self._worker = None

    def _add_message(self, role: str, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == "user":
            color, alignment = "#d8ecff", Qt.AlignmentFlag.AlignRight
        elif role == "tool":
            color, alignment = "#252a32", Qt.AlignmentFlag.AlignLeft
            label.setStyleSheet("font-style: italic; color: #b9c3d0; border: none;")
        else:
            color, alignment = "#e2e5e9", Qt.AlignmentFlag.AlignLeft
        if role != "tool":
            label.setStyleSheet(f"background: {color}; color: #1d2127; border-radius: 8px; padding: 7px;")
        label.setMaximumWidth(300)
        row = QHBoxLayout()
        if alignment == Qt.AlignmentFlag.AlignRight:
            row.addStretch()
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch()
        self.messages_layout.insertLayout(self.messages_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
