from datetime import datetime
from typing import cast

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

from ....utils.storage import HistoryEntry


class HistoryOverlay(Static):
    """A floating layer for displaying and selecting command history."""

    DEFAULT_CSS = """
    HistoryOverlay ListView {
        border: none;
        background: $panel-darken-1;
    }
    HistoryOverlay Label {
        padding: 0 1;
        color: $text-muted;
        height: 1;
    }
    HistoryOverlay ListItem {
        padding: 0 1;
        height: 1;
    }
    HistoryOverlay ListItem > Static {
        height: 1;
    }
    HistoryOverlay ListItem :hover {
        background: $accent-darken-1;
    }
    HistoryOverlay ListItem.--highlight {
        background: $accent !important;
        color: $text !important;
    }
    HistoryOverlay ListItem.--highlight:focus {
        background: $accent-darken-1 !important;
    }
    """

    # --- Messages ---
    class SelectHistory(Message):
        """Sent when a user selects a history entry."""

        def __init__(self, command: str):
            self.command = command
            super().__init__()

    class ExitHistory(Message):
        """Sent when a user exits history view (e.g. by pressing ESC)."""

        pass

    # --- UI Composition & Updates ---
    def compose(self) -> ComposeResult:
        yield Label("Command History (↑/↓ Select, Enter Use, Esc Close)")
        yield ListView(id="history-list")

    def set_history(self, history_entries: list[HistoryEntry]):
        """Fill the list with history entries."""
        list_view = self.query_one("#history-list", ListView)
        list_view.clear()  # Clear old entries
        # Iterate in reverse to show latest at the top
        for entry in reversed(history_entries):
            # Format timestamp
            dt = datetime.fromtimestamp(entry["timestamp"])
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            # Create display text
            display_text = Text.assemble((f"{time_str} ", "dim"), (entry["command"], ""))
            # Create ListItem, storing original command as its value
            # Note: ListItem itself doesn't have a value property, we might need to subclass
            # Or use another way to store the original command. A simple method is to use ID.
            # Alternatively, when selected, extract from Label.
            # For simplicity, we will extract in on_list_view_selected.
            list_view.append(ListItem(Static(display_text)))  # Use Static to display Rich Text
        # If list is not empty, highlight first (latest)
        if len(list_view):
            list_view.index = 0

    # --- Event Handlers ---
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection event."""
        event.stop()
        selected_item = event.item
        if selected_item:
            # Extract original command text from Static component
            static_widget = selected_item.query_one(Static)
            rich_text = cast(Text, static_widget.renderable)  # Assuming it's Text
            # Extract command part (assuming timestamp followed by command)
            command_text = rich_text.plain.split(" ", 2)[-1]  # Simple split logic
            self.post_message(self.SelectHistory(command_text))

    # Allow closing via ESC
    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.post_message(self.ExitHistory())
