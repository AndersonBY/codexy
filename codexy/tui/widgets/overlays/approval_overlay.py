from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from ....approvals import ApprovalMode


# --- Widget ---
class ApprovalModeOverlay(Static):
    """A component for selecting an approval mode."""

    # --- Messages ---
    class ApprovalModeSelected(Message):
        """Sent when a user selects a new approval mode."""

        def __init__(self, mode: ApprovalMode):
            self.mode: ApprovalMode = mode
            super().__init__()

    class ExitApprovalOverlay(Message):
        """Sent when a user cancels selection, closing the overlay."""

        pass

    DEFAULT_CSS = """
    ApprovalModeOverlay {
        layer: approval_overlay_layer;
        display: none;
        align: center middle;
        width: 80%;
        max-width: 60;
        height: auto;
        max-height: 15;
        border: thick $accent;
        background: $panel;
        padding: 1;
    }
    ApprovalModeOverlay.-active {
        display: block;
    }
    ApprovalModeOverlay #approval-overlay-title {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    ApprovalModeOverlay #current-mode-label {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    ApprovalModeOverlay OptionList {
        border: none;
        background: $panel-darken-1;
        max-height: 10;
        height: auto;
        min-height: 1;
    }
    ApprovalModeOverlay #approval-overlay-footer {
        margin-top: 1;
        width: 100%;
        text-align: center;
        color: $text-muted;
    }
    ApprovalModeOverlay OptionList Option {
        padding: 0 1;
        height: 1;
    }
    ApprovalModeOverlay OptionList Option :hover {
        background: $accent-darken-1;
    }
    ApprovalModeOverlay OptionList Option.--highlight {
        background: $accent !important;
        color: $text !important;
    }
    ApprovalModeOverlay OptionList Option.--highlight:focus {
         background: $accent-darken-1 !important;
    }
    """

    # --- Reactives ---
    current_mode: reactive[ApprovalMode] = reactive(ApprovalMode.SUGGEST)
    _option_list_id = "approval-mode-option-list"

    def compose(self) -> ComposeResult:
        """Build the UI elements of the overlay."""
        yield Label("Switch Approval Mode", id="approval-overlay-title")
        yield Label(f"Current: {self.current_mode.value}", id="current-mode-label")
        # Use OptionList to display options
        yield OptionList(id=self._option_list_id)
        yield Label("↑/↓ Select, Enter Confirm, Esc Cancel", id="approval-overlay-footer")

    def on_mount(self) -> None:
        """Mounted, fill the list and set focus."""
        self.log.info("ApprovalModeOverlay mounted.")
        # Use call_later to schedule _populate_list and focus_list
        self.call_later(self._populate_list)
        self.call_later(self.focus_list)

    def focus_list(self) -> None:
        """Safely focus the OptionList."""
        try:
            option_list = self.query_one(f"#{self._option_list_id}", OptionList)
            if option_list.is_mounted:
                self.log.info("Focusing approval mode OptionList.")
                option_list.focus()
            else:
                self.log.warning("Attempted to focus OptionList but it was not mounted.")
        except Exception as e:
            self.log.error(f"Error focusing approval mode list: {e}")

    # --- Watchers ---
    def watch_current_mode(self, new_mode: ApprovalMode) -> None:
        """When current_mode changes, update the label and repopulate the list to update the highlight."""
        self.log.info(f"Watched current_mode change to {new_mode.value}. Repopulating list.")
        try:
            label = self.query_one("#current-mode-label", Label)
            label.update(f"Current: {new_mode.value}")
            # Repopulate the list to ensure the highlight is correct
            self._populate_list()
        except Exception as e:
            # If this happens during unmount, ignore the error
            if self.is_mounted:
                self.log.warning(f"Could not update current mode label or list: {e}")

    # --- Internal Methods ---
    def _populate_list(self):
        """Populate the OptionList with approval modes."""
        if not self.is_mounted:
            self.log.warning("Attempted to populate list, but overlay is not mounted.")
            return
        self.log.info(f"Executing _populate_list for mode {self.current_mode.value}")
        try:
            option_list = self.query_one(f"#{self._option_list_id}", OptionList)
            self.log.info(f"Found OptionList widget: {option_list}")
            option_list.clear_options()
            self.log.info("Cleared existing options.")

            highlighted_index: int | None = None
            options_to_add = []

            # Create Option for each approval mode
            for index, mode in enumerate(ApprovalMode):
                description = ""
                style = ""
                if mode == ApprovalMode.SUGGEST:
                    description = "Ask for edits & commands"
                elif mode == ApprovalMode.AUTO_EDIT:
                    description = "Auto-edit files, ask for commands"
                elif mode == ApprovalMode.FULL_AUTO:
                    description = "Auto-edit & sandboxed commands"
                elif mode == ApprovalMode.DANGEROUS_AUTO:
                    description = "Auto-approve all (UNSAFE)"
                    style = "bold red"

                display_text = Text.assemble(
                    (f"{mode.value}", "bold" if mode == self.current_mode else ""),
                    (f" - {description}", f"dim {style}" if style else "dim"),
                )
                options_to_add.append(Option(display_text, id=mode.value))
                if mode == self.current_mode:
                    highlighted_index = index

            self.log.info(f"Prepared {len(options_to_add)} options to add.")
            option_list.add_options(options_to_add)
            self.log.info(f"Called add_options. OptionList now has {option_list.option_count} options.")

            if highlighted_index is not None and option_list.option_count > 0:
                try:
                    self.log.info(f"Attempting to highlight index: {highlighted_index}")
                    option_list.highlighted = highlighted_index
                    self.log.info(f"Highlighted index set to {highlighted_index}")
                except OptionDoesNotExist:
                    # If the index is invalid (should not happen unless the list is empty), record a warning
                    self.log.warning(f"Could not highlight approval mode index {highlighted_index}")
                except Exception as high_e:
                    self.log.error(f"Error setting highlighted index: {high_e}")

        except Exception as e:
            if self.is_mounted:
                self.log.error(f"Error populating approval mode list: {e}")

    # --- Event Handlers ---
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle the selection event in the OptionList."""
        event.stop()
        option_id = event.option.id
        if option_id is not None:
            try:
                selected_mode = ApprovalMode(option_id)
                self.log.info(f"Approval mode selected: {selected_mode.value}")
                self.post_message(self.ApprovalModeSelected(selected_mode))
            except ValueError:
                self.log.error(f"Invalid approval mode ID selected: {option_id}")
                self.post_message(self.ExitApprovalOverlay())
        else:
            # If the option has no ID (should not happen), also exit
            self.log.warning("Selected option has no ID.")
            self.post_message(self.ExitApprovalOverlay())

    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially Escape key."""
        if event.key == "escape":
            event.stop()
            self.log.info("Approval overlay exited via Escape.")
            self.post_message(self.ExitApprovalOverlay())
