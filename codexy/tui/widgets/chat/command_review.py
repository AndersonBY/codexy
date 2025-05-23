import json
import time
from typing import Optional, TypedDict, Union

from rich.text import Text
from rich.syntax import Syntax

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, RadioSet, RadioButton, Input, Button, Label

from ....approvals import ApprovalMode


class CommandReviewResult(TypedDict):
    approved: bool
    always_approve: bool
    feedback: Optional[str]


class CommandReviewWidget(Static):
    """Display command to be approved and get user's decision."""

    DEFAULT_CSS = """
    CommandReviewWidget {
        height: auto;
        max-height: 70%;
        width: 80%;
        background: $panel;
        padding: 1;
        overflow-y: auto;
        border: round $accent;
    }
    CommandReviewWidget > Vertical {
        height: auto;
    }
    CommandReviewWidget #command-display {
        margin-bottom: 1;
        height: auto;
        max-height: 15;
        overflow-y: auto;
        border: round $accent-lighten-2;
        background: $surface;
        padding: 1;
        border-title-align: left;
        border-title-style: bold;
        border-title-color: $text;
    }
    CommandReviewWidget #explanation-container {
        height: auto;
    }
    CommandReviewWidget #explanation-display {
        margin-top: 1;
        margin-bottom: 1;
        padding: 1;
        border: round $primary-lighten-1;
        height: auto;
        max-height: 15;
        overflow-y: auto;
        background: $boost;
    }
    CommandReviewWidget #explanation-display .explanation-title {
        margin-bottom: 1;
        text-style: bold;
    }
    CommandReviewWidget #approval-options {
        height: auto;
        border: none;
        margin-top: 1;
    }
    CommandReviewWidget RadioSet {
        width: 1fr;
        height: auto;
    }
    CommandReviewWidget RadioButton {
        height: 1;
        margin-bottom: 1;
    }
    CommandReviewWidget #feedback-container {
        height: auto;
    }
    CommandReviewWidget #feedback-input-label {
        margin-bottom: 1;
    }
    CommandReviewWidget #feedback-input {
        margin-top: 0;
        height: 3;
    }
    CommandReviewWidget #feedback-input Input {
        width: 1fr;
    }
    CommandReviewWidget #return-button {
        margin-top: 1;
    }
    """

    # --- State ---
    _tool_name: reactive[str] = reactive("")
    _command_display: reactive[str] = reactive("")
    _tool_id: reactive[Optional[str]] = reactive(None)
    _mode: reactive[str] = reactive("select")
    _explanation: reactive[Optional[str]] = reactive(None)
    _feedback: reactive[str] = reactive("")
    _approval_mode: ApprovalMode = ApprovalMode.SUGGEST

    # --- Messages ---
    class ReviewResult(Message):
        """Sent when the user makes an approval decision."""

        def __init__(self, approved: bool, tool_id: Optional[str], always_approve: bool = False, feedback: Optional[str] = None):
            self.approved = approved
            self.tool_id = tool_id
            self.always_approve = always_approve
            self.feedback = feedback
            super().__init__()

    # --- UI Composition & Updates ---
    def compose(self) -> ComposeResult:
        with Vertical():
            # Use Static to display the command, and set the border title
            yield Static("", id="command-display")
            with Vertical(id="explanation-container", classes="-hidden"):
                yield Label("Explanation:", classes="explanation-title")
                yield Static(id="explanation-display")
                yield Button("Back to Options", id="return-button", variant="default")
            yield RadioSet(id="approval-options")
            with Vertical(id="feedback-container", classes="-hidden"):
                yield Label("Provide feedback (optional, press Enter to deny):", id="feedback-input-label")
                yield Input(placeholder="Reason for denial...", id="feedback-input")

    def set_tool_info(
        self,
        tool_name: str,
        command_display: str,
        tool_id: str,
        approval_mode: ApprovalMode = ApprovalMode.SUGGEST,
    ):
        """Set the tool information to be reviewed."""
        self._tool_name = tool_name
        self._command_display = command_display
        self._tool_id = tool_id
        self._approval_mode = approval_mode
        self.update_command_display()
        self.set_mode("select")

    def set_explanation(self, explanation: str):
        """Set and display command explanation."""
        self._explanation = explanation
        self.set_mode("explanation")

    def set_mode(self, mode: str):
        """Switch the review component mode."""
        self._mode = mode
        is_select = mode == "select"
        is_input = mode == "input"
        is_explanation = mode == "explanation"

        self.query_one("#approval-options").display = is_select
        self.query_one("#feedback-container").display = is_input
        self.query_one("#explanation-container").display = is_explanation

        if is_select:
            self.build_radio_options()
            # Ensure RadioSet is visible后再聚焦
            self.call_later(lambda: self.query_one("#approval-options", RadioSet).focus())
        elif is_input:
            input_widget = self.query_one("#feedback-input", Input)
            input_widget.value = ""
            self.call_later(input_widget.focus)
        elif is_explanation:
            self.update_explanation_display()
            self.call_later(lambda: self.query_one("#return-button", Button).focus())

    def update_command_display(self):
        """Update command display area, with formatting."""
        display_content: Union[str, Syntax, Text]
        try:
            parsed = json.loads(self._command_display)
            pretty_json = json.dumps(parsed, indent=2)
            # If successful, use Syntax to highlight JSON
            display_content = Syntax(
                pretty_json,
                "json",
                theme="github-dark",  # Choose other themes
                line_numbers=False,
                word_wrap=True,
            )
        except json.JSONDecodeError:
            # If not JSON or contains special markers (like patch), handle it specially
            if "*** Begin Patch" in self._command_display or "<<<<<<< SEARCH" in self._command_display:
                # Colorize patch/diff text
                lines = []
                for line in self._command_display.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        lines.append(Text(line, style="green"))
                    elif line.startswith("-") and not line.startswith("---"):
                        lines.append(Text(line, style="red"))
                    elif line.startswith("@@"):
                        lines.append(Text(line, style="cyan"))
                    else:
                        lines.append(Text(line))
                display_content = Text("\n").join(lines)
            else:
                # For normal text, use Text and allow folding
                display_content = Text(self._command_display, overflow="fold")

        # Update Static component's content and border title
        command_static = self.query_one("#command-display", Static)
        # Set border title to tool name
        command_static.border_title = f"Tool: {self._tool_name}" if self._tool_name else "Command / Operation"
        command_static.update(display_content)

    def update_explanation_display(self):
        """Update explanation display area."""
        explanation_text = self._explanation or "Loading explanation..."
        self.query_one("#explanation-display", Static).update(explanation_text)

    def build_radio_options(self):
        """Build approval options RadioButton."""
        radioset = self.query_one("#approval-options", RadioSet)
        radioset.remove_children()

        # Use a unique timestamp or counter to ensure unique IDs
        unique_suffix = str(int(time.time() * 1000000) % 1000000)  # Use microseconds for uniqueness

        options = [RadioButton("Yes (y)", id=f"yes_{unique_suffix}", value=True)]
        if self._approval_mode != ApprovalMode.SUGGEST and self._tool_name == "execute_command":
            options.append(RadioButton("Yes, always approve this command for this session (a)", id=f"always_{unique_suffix}"))
        options.extend(
            [
                RadioButton("Edit / Provide Feedback (e)", id=f"edit_{unique_suffix}"),
                RadioButton("No, continue generation (n)", id=f"no_continue_{unique_suffix}"),
                RadioButton("No, stop generation (ESC)", id=f"no_stop_{unique_suffix}"),
            ]
        )

        radioset.mount_all(options)

    # --- Event Handlers ---
    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle the change in the RadioSet."""
        event.stop()
        selected_button = event.pressed
        if not selected_button:
            return

        decision_value = selected_button.id
        if decision_value:
            self.handle_decision(decision_value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle the submission event of the feedback input box (i.e. denial)."""
        if self._mode == "input":
            event.stop()
            feedback = event.value.strip() or "Denied by user via feedback input."
            self.post_message(self.ReviewResult(approved=False, tool_id=self._tool_id, feedback=feedback))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the "Return to Options" button."""
        if event.button.id == "return-button":
            event.stop()
            self.set_mode("select")

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard shortcuts."""
        key = event.key
        should_stop = False
        if self._mode == "select":
            if key == "y":
                self.handle_decision("yes")
                should_stop = True
            elif key == "a" and self._approval_mode != ApprovalMode.SUGGEST and self._tool_name == "execute_command":
                self.handle_decision("always")
                should_stop = True
            elif key == "e":
                self.handle_decision("edit")
                should_stop = True
            elif key == "n":
                self.handle_decision("no_continue")
                should_stop = True
            elif key == "escape":
                self.handle_decision("no_stop")
                should_stop = True
        elif self._mode == "explanation":
            # Allow ESC or Enter to go back
            if key == "escape" or key == "enter":
                self.set_mode("select")
                should_stop = True
        elif self._mode == "input":
            if key == "escape":
                # Get value from input box, use default denial message if empty
                feedback_input = self.query_one("#feedback-input", Input)
                feedback = feedback_input.value.strip() or "Denied by user via ESC."
                self.post_message(self.ReviewResult(approved=False, tool_id=self._tool_id, feedback=feedback))
                should_stop = True

        if should_stop:
            event.stop()

    def handle_decision(self, decision_id: str):
        """Handle user's decision (based on button ID)."""
        # Extract the base decision type by removing the unique suffix
        if "_" in decision_id:
            base_decision = decision_id.rsplit("_", 1)[0]
        else:
            base_decision = decision_id

        if base_decision == "yes":
            self.post_message(self.ReviewResult(approved=True, tool_id=self._tool_id))
        elif base_decision == "always":
            self.post_message(self.ReviewResult(approved=True, tool_id=self._tool_id, always_approve=True))
        elif base_decision == "edit":
            self.set_mode("input")
        elif base_decision == "no_continue":
            self.post_message(self.ReviewResult(approved=False, tool_id=self._tool_id, feedback="Denied by user (continue)."))
        elif base_decision == "no_stop":
            self.post_message(self.ReviewResult(approved=False, tool_id=self._tool_id, feedback="Denied by user (stop)."))
