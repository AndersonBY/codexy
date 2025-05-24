from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Label, ListItem, ListView, Static

from ....utils.model_utils import format_model_for_display, sort_models_for_display


# Type for list items carrying the model ID
class ModelItem(ListItem):
    def __init__(self, model_id: str, display_text: Text):
        super().__init__(Label(display_text))
        self.model_id = model_id


class ModelOverlay(Static):
    """An overlay for selecting an OpenAI model."""

    DEFAULT_CSS = """
    ModelOverlay {
        layer: model_overlay_layer;
        display: none;
        align: center middle;
        width: 80%;
        max-width: 60;
        height: 80%;
        max-height: 25;
        border: thick $accent;
        background: $panel;
        padding: 1;
    }
    ModelOverlay.-active {
        display: block;
    }
    ModelOverlay #model-overlay-title {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    ModelOverlay #model-list-view {
        border: none;
        background: $panel-darken-1;
    }
    ModelOverlay #model-overlay-footer {
        margin-top: 1;
        width: 100%;
        text-align: center;
        color: $text-muted;
    }
    ModelOverlay #model-overlay-error {
        margin-top: 1;
        text-align: center;
        color: $error;
    }
    ModelOverlay ListItem {
        padding: 0 1;
        height: 1;
    }
    ModelOverlay ListItem Label {
        height: 1;
    }
    ModelOverlay ListItem :hover {
        background: $accent-darken-1;
    }
    ModelOverlay ListItem.--highlight {
        background: $accent !important;
        color: $text !important;
    }
    ModelOverlay ListItem.--highlight:focus {
        background: $accent-darken-1 !important;
    }
    """

    # --- Reactives ---
    available_models: reactive[list[str]] = reactive(list)
    current_model: reactive[str] = reactive("")
    can_switch: reactive[bool] = reactive(True)  # Controls if switching is allowed

    # --- Messages ---
    class Selected(Message):
        """Sent when a model is selected."""

        def __init__(self, model_id: str):
            self.model_id = model_id
            super().__init__()

    class Exit(Message):
        """Sent when the overlay is exited without selection."""

        pass

    def compose(self) -> ComposeResult:
        yield Label("Switch Model", id="model-overlay-title")
        yield Label("Cannot switch model after conversation starts.", id="model-overlay-error", classes="-hidden")
        with VerticalScroll():
            yield ListView(id="model-list-view")
        yield Label("↑/↓ Select, Enter Confirm, Esc Cancel", id="model-overlay-footer")

    def on_mount(self) -> None:
        """Focus the list view when mounted."""
        self.call_later(self.focus_list)

    def focus_list(self) -> None:
        """Safely focus the ListView."""
        try:
            list_view = self.query_one(ListView)
            if list_view.is_mounted:
                list_view.focus()
        except Exception as e:
            self.log.error(f"Error focusing model list: {e}")

    def watch_can_switch(self, can_switch: bool) -> None:
        """Update UI based on whether switching is allowed."""
        self.query_one("#model-list-view").display = can_switch
        self.query_one("#model-overlay-error").set_class(not can_switch, "-active")
        self.query_one("#model-overlay-error").display = not can_switch  # Ensure it's visible

    def watch_available_models(self, new_models: list[str]) -> None:
        """Update the list view when available models change."""
        self._populate_list()

    def watch_current_model(self, new_current_model: str) -> None:
        """Update the list view when the current model changes."""
        self._populate_list()

    def _populate_list(self):
        """Populate the ListView with models."""
        if not self.is_mounted:  # Don't populate if not mounted
            return

        list_view = self.query_one("#model-list-view", ListView)
        list_view.clear()

        if not self.can_switch:
            return  # Don't populate if switching isn't allowed

        sorted_list = sort_models_for_display(self.available_models, self.current_model)
        highlighted_index: int | None = None

        for index, model_id in enumerate(sorted_list):
            display_text = format_model_for_display(model_id, self.current_model)
            rich_text = Text.from_markup(display_text)  # Convert potentially marked-up string
            list_view.append(ModelItem(model_id, rich_text))
            if model_id == self.current_model:
                highlighted_index = index

        if highlighted_index is not None and len(list_view) > 0:
            list_view.index = highlighted_index

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection from the list view."""
        event.stop()
        if self.can_switch and isinstance(event.item, ModelItem):
            selected_model_id = event.item.model_id
            self.log(f"Model selected: {selected_model_id}")
            self.post_message(self.Selected(selected_model_id))

    def on_key(self, event: events.Key) -> None:
        """Handle key presses, specifically Escape."""
        if event.key == "escape":
            event.stop()
            self.log("Model overlay exited via Escape.")
            self.post_message(self.Exit())
