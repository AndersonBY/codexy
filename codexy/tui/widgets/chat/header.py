from typing import Optional, cast

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, Label
from textual.containers import Horizontal

from ....config import AppConfig
from ....utils.filesystem import short_cwd


class ChatHeader(Static):
    """Display the title bar for chat session information."""

    DEFAULT_CSS = """
    ChatHeader {
        dock: top;
        width: 100%;
        background: $accent-darken-2; /* Use theme color */
        color: $text;
        height: auto;
        padding: 0 1;
        border-bottom: thick $accent; /* Add bottom border */
    }
    ChatHeader Horizontal {
        width: 1fr;
        height: 1; /* Force height to 1 for single line */
        align: left middle;
        overflow: hidden; /* Hide overflow if content is too long */
    }
    ChatHeader Label {
        margin-right: 2;
        height: 1;
        text-style: bold;
        content-align: left middle;
        overflow: hidden; /* Prevent label content itself from wrapping */
        text-overflow: ellipsis; /* Add ellipsis if label content is too long */
    }
    ChatHeader .info {
        color: $text-muted;
        text-style: none;
        width: auto; /* Let info labels take their needed width */
    }
    ChatHeader .value {
        color: $text;
        text-style: bold;
        width: auto; /* Let value labels take their needed width */
        max-width: 25%; /* Limit max width of value labels */
    }
    ChatHeader #session-label {
        /* Allow session ID to take more space if needed, but still limit */
        max-width: 35%;
        width: 1fr; /* Allow it to shrink if needed */
        text-align: right; /* Align session ID to the right */
    }
    """

    # Keep its own reactives to display the data
    session_id: reactive[str] = reactive("N/A")
    cwd: reactive[str] = reactive("N/A")
    model: reactive[str] = reactive("N/A")
    approval_mode: reactive[str] = reactive("N/A")

    # Store config for reference if needed, but maybe not necessary
    _app_config: Optional[AppConfig] = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("Dir:", classes="info")
            yield Label(self.cwd, classes="value")
            yield Label("Model:", classes="info")
            yield Label(self.model, classes="value")
            yield Label("Approval:", classes="info")
            yield Label(self.approval_mode, classes="value", id="approval-label")
            # Use remaining space for session ID, aligned right
            yield Label("Session:", classes="info", shrink=True)  # Allow info label to shrink
            yield Label(self.session_id, classes="value", id="session-label")

    def update_info(self, config: AppConfig, session_id: Optional[str] = None):
        """Update Header display info (called once on mount usually)."""
        self._app_config = config
        self.session_id = session_id or "N/A"
        self.cwd = short_cwd()
        self.model = config.get("model", "N/A")
        self.approval_mode = config.get("effective_approval_mode", "N/A")

    # Watchers update the specific Label widgets
    def watch_cwd(self, new_cwd: str) -> None:
        try:
            label = cast(Label, self.query("Label").filter(".value").first())
            label.update(new_cwd)
        except Exception:
            pass

    def watch_model(self, new_model: str) -> None:
        try:
            model_label = cast(Label, self.query("Label").filter(".value")[1])  # Assume Model is the second value
            model_label.update(new_model)
        except Exception:
            pass

    def watch_approval_mode(self, new_mode: str) -> None:
        try:
            approval_label = cast(Label, self.query("Label").filter(".value")[2])  # Assume Approval is the third value
            approval_label.update(new_mode)
        except Exception:
            pass

    def watch_session_id(self, new_id: str) -> None:
        try:
            session_label = cast(Label, self.query_one("#session-label", Label))
            session_label.update(new_id)
        except Exception:
            pass
