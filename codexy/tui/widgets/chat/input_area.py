from typing import List, Optional, cast

from rich.text import Text
from textual import events
from textual.timer import Timer
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import TextArea, Static
from textual.containers import Container, Horizontal

from .thinking_indicator import ThinkingIndicator
from ....utils.storage import HistoryEntry


class ChatInputArea(Container):
    """Component containing input field and thinking indicator."""

    DEFAULT_CSS = """
    ChatInputArea {
        height: auto;
        max-height: 50%;
        border-top: thick $accent;
        padding: 0;
        background: $panel;
        margin-bottom: 1;
    }
    ChatInputArea > TextArea {
        height: auto;
        min-height: 3;
        max-height: 20;
        border: none;
        margin: 0;
        background: $surface;
        scrollbar-gutter: stable;
    }
    ChatInputArea > TextArea:focus {
        border: none;
    }
    ChatInputArea > ThinkingIndicator {
        border: none;
        padding: 1;
        color: $text-muted;
        height: 3; /* Match help bar height */
        background: $surface;
    }
    /* Style the container for help text and tokens */
    ChatInputArea > #input-help-container {
        height: 1;
        background: $surface;
        padding: 0 1; /* Add padding */
        width: 1fr;
        /* We don't need layout: horizontal here, Container default is vertical, */
        /* but the items inside will determine layout */
    }
    ChatInputArea > #input-help-container Horizontal { /* Style the inner Horizontal */
        align: left middle; /* Vertically align items */
        height: 1;
    }
    ChatInputArea > #input-help-container #input-help-text { /* Style the help text Static */
        width: 1fr; /* Allow it to take up remaining space */
        color: $text-muted;
        text-overflow: ellipsis;
        overflow: hidden;
        height: 1;
    }
    ChatInputArea > #input-help-container #input-help-tokens { /* Style the token count Static */
        width: auto; /* Take only needed space */
        color: $accent; /* Use accent color for visibility */
        text-style: bold;
        margin-left: 1; /* Space between help and tokens */
        height: 1;
        text-align: right; /* Align token count to the right */
    }
    """

    BINDINGS = [
        Binding("up", "history_prev", "Prev History", show=False, priority=True),
        Binding("down", "history_next", "Next History", show=False, priority=True),
    ]

    # --- Reactives ---
    is_loading: reactive[bool] = reactive(False)
    thinking_seconds: reactive[int] = reactive(0)
    token_usage_percent: reactive[float] = reactive(100.0)

    # --- State ---
    _command_history: List[HistoryEntry] = []
    _history_index: Optional[int] = None
    _draft_input: str = ""
    _thinking_timer: Optional[Timer] = None

    # --- Messages ---
    class Submit(Message):
        """Sent when user submits input."""

        def __init__(self, value: str):
            self.value = value
            super().__init__()

    # --- UI Composition ---
    def compose(self) -> ComposeResult:
        yield TextArea(language=None, theme="css", soft_wrap=True, show_line_numbers=False, id="input-textarea")
        yield ThinkingIndicator(id="thinking")
        # -- Updated help section --
        with Container(id="input-help-container"):
            with Horizontal():
                yield Static(
                    "\[Ctrl+J] Submit | \[Up/Down] History | \[ESC] Cancel/Close",
                    classes="input-help-text",  # Use class for easier targeting
                    id="input-help-text",
                )
                yield Static("", id="input-help-tokens")  # Placeholder for token count

    def on_mount(self) -> None:
        """Set initial state and focus when mounted."""
        # Ensure TextArea exists before focusing
        try:
            self.query_one("#input-textarea", TextArea).focus()
        except Exception as e:
            self.log.warning(f"Could not focus input textarea on mount: {e}")

    def on_unmount(self) -> None:
        """Ensure timer is stopped when component unmounts."""
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None

    def watch_token_usage_percent(self, new_value: float) -> None:
        """Update the token usage display."""
        try:
            token_widget = self.query_one("#input-help-tokens", Static)
            if token_widget.is_mounted:
                percent_str = f"{new_value:.0f}%"
                # Add color coding based on percentage
                style = ""
                if new_value < 10:
                    style = "bold red"
                elif new_value < 25:
                    style = "bold yellow"
                elif new_value < 50:
                    style = "yellow"
                # Update with Rich Text for styling
                token_widget.update(Text(f"Ctx: {percent_str}", style=style))
        except Exception as e:
            if self.is_mounted:
                self.log.error(f"Error updating token usage display: {e}")

    # --- Public API ---
    def set_loading(self, loading: bool):
        """Set loading state."""
        self.is_loading = loading

    def set_history(self, history: List[HistoryEntry]):
        """Set command history."""
        self._command_history = history
        self._history_index = None

    def get_input_value(self) -> str:
        """Get current input value."""
        try:
            textarea = cast(TextArea, self.query_one("#input-textarea"))
            if textarea.is_mounted:
                return textarea.text
        except Exception:
            pass
        return ""

    def set_input_value(self, value: str):
        """Set input value and move cursor to end."""
        try:
            textarea = cast(TextArea, self.query_one("#input-textarea"))
            if textarea.is_mounted:
                textarea.load_text(value)
                # Delay moving cursor to ensure text is loaded
                self.call_after_refresh(lambda: textarea.move_cursor(textarea.document.end))
        except Exception:
            pass

    def focus_input(self):
        """Focus on input field."""
        try:
            if self.is_mounted:
                textarea = self.query_one("#input-textarea", TextArea)
                if textarea.is_mounted:
                    textarea.focus()
        except Exception:
            pass

    def clear_input(self):
        """Clear input field."""
        self.set_input_value("")
        self._draft_input = ""
        self._history_index = None

    # --- Watchers ---
    def watch_is_loading(self, loading: bool) -> None:
        """Switch between input field and indicator based on loading state."""
        try:
            thinking_indicator = cast(ThinkingIndicator, self.query_one("#thinking"))
            textarea = cast(TextArea, self.query_one("#input-textarea"))
            help_container = self.query_one("#input-help-container")

            thinking_indicator.display = loading
            textarea.display = not loading
            help_container.display = not loading

            if loading:
                self.thinking_seconds = 0
                thinking_indicator.set_thinking_seconds(0)
                if self._thinking_timer:
                    self._thinking_timer.stop()
                self._thinking_timer = self.set_interval(1.0, self._update_thinking_timer)
            else:
                if self._thinking_timer:
                    self._thinking_timer.stop()
                    self._thinking_timer = None
                if textarea.is_mounted:
                    self.call_after_refresh(textarea.focus)

        except Exception as e:
            if self.is_mounted:
                self.log.error(f"Error in watch_is_loading: {e}")

    def _update_thinking_timer(self):
        """Update thinking timer."""
        if self.is_loading:
            self.thinking_seconds += 1
            try:
                thinking_indicator = cast(ThinkingIndicator, self.query_one("#thinking"))
                if thinking_indicator.is_mounted:
                    thinking_indicator.set_thinking_seconds(self.thinking_seconds)
            except Exception:
                # If component is unmounted, stop timer
                if self._thinking_timer:
                    self._thinking_timer.stop()
                    self._thinking_timer = None
        else:
            if self._thinking_timer:
                self._thinking_timer.stop()
                self._thinking_timer = None

    # --- Actions and Event Handlers ---
    def action_submit(self):
        """Handle submit action (e.g. Ctrl+J)."""
        if not self.is_loading:
            try:
                textarea = cast(TextArea, self.query_one("#input-textarea"))
                value = textarea.text.strip()
                if value:
                    self.log(f"Submitting value: {value!r}")
                    self.post_message(self.Submit(value))
                    # Clear operation moved to App level
                else:
                    self.log("Submit ignored, value is empty.")
            except Exception as e:
                self.log.error(f"Error during submit action: {e}")

    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially Ctrl+J."""
        if event.key == "ctrl+j":
            if not self.is_loading:
                self.log.info("Ctrl+J detected, stopping event and calling action_submit.")
                event.stop()
                self.action_submit()

    def action_history_prev(self):
        """Handle navigating up through the command history"""
        if self.is_loading:
            return

        try:
            textarea = cast(TextArea, self.query_one("#input-textarea"))
            # Only trigger history when cursor is on the first line
            if textarea.cursor_location[0] != 0:
                return  # Cursor is not on the first line, let TextArea handle the up arrow

            if not self._command_history:
                return

            if self._history_index is None:
                self._draft_input = textarea.text
                new_index = len(self._command_history) - 1
            else:
                new_index = max(0, self._history_index - 1)

            if new_index != self._history_index:
                self._history_index = new_index
                self.set_input_value(self._command_history[self._history_index]["command"])
        except Exception as e:
            self.log.error(f"Error in action_history_prev: {e}")

    def action_history_next(self):
        """Handle navigating down through the command history"""
        if self.is_loading:
            return

        try:
            textarea = cast(TextArea, self.query_one("#input-textarea"))
            # Only trigger history when cursor is on the last line
            if textarea.cursor_location[0] != textarea.document.line_count - 1:
                return  # Cursor is not on the last line, let TextArea handle the down arrow

            if self._history_index is None:
                return

            new_index = self._history_index + 1

            if new_index >= len(self._command_history):
                self._history_index = None
                self.set_input_value(self._draft_input)
            else:
                self._history_index = new_index
                self.set_input_value(self._command_history[self._history_index]["command"])
        except Exception as e:
            self.log.error(f"Error in action_history_next: {e}")
