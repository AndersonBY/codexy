import json
import time

import pyperclip
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Button, Label, Markdown, Static


class BaseMessageDisplay(Static):
    """Base class for message display."""

    DEFAULT_CSS = """
    BaseMessageDisplay {
        width: auto;
        max-width: 85%;
        min-width: 30%;
        height: auto;
    }
    """


class UserMessageDisplay(BaseMessageDisplay):
    """Display user messages, with text contained in a bordered container."""

    DEFAULT_CSS = """
    UserMessageDisplay {
        border: round green;
        padding: 0 1;
        width: auto;
        max-width: 85%;
        height: auto;
        background: $boost;
    }
    UserMessageDisplay > Label {
        height: auto;
    }
    """

    def __init__(self, text: str, **kwargs):
        self._text_content = text  # Store the raw text
        # Initialize Static without renderable, we use compose now
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Yields the actual Label widget that holds the text."""
        # Format the text for display within the inner Label
        formatted_text = Text.assemble(("User:", "bold green"), "\n", self._text_content)
        yield Label(formatted_text)

    # Optional: Method to update text if needed later
    def update_text(self, new_text: str) -> None:
        self._text_content = new_text
        formatted_text = Text.assemble(("User:", "bold green"), "\n", self._text_content)
        try:
            label = self.query_one(Label)
            label.update(formatted_text)
        except Exception as e:
            self.log.error(f"Error updating UserMessageDisplay: {e}")


class AssistantMessageDisplay(BaseMessageDisplay):
    """Display assistant messages, with Markdown support and a copy button."""

    DEFAULT_CSS = """
    AssistantMessageDisplay {
        padding: 0 1;
        border-left: thick $accent;
        width: auto;
        max-width: 85%;
        height: auto;
    }
    AssistantMessageDisplay > Vertical { /* Use Vertical to stack Markdown and Button */
        height: auto;
    }
    AssistantMessageDisplay > Vertical > Markdown {
        margin: 0;
        padding: 0;
        height: auto;
    }
    AssistantMessageDisplay > Vertical > Button.copy-button {
        display: none; /* Start hidden */
        width: auto;
        height: 1;
        min-width: 8; /* "Copy" + padding */
        margin-top: 1;
        padding: 0 1;
        border: none; /* Minimalist button style */
        background: $primary-background;
        color: $text;
    }
    AssistantMessageDisplay > Vertical > Button.copy-button:hover {
        background: $primary;
    }
    AssistantMessageDisplay > Vertical > Button.copy-button.copied {
        background: $success;
    }
    """

    THROTTLE_INTERVAL: float = 0.1
    _last_update_time: float = 0.0

    def __init__(self, initial_text: str = "", **kwargs):
        super().__init__(**kwargs)  # Initialize parent Static class
        self._full_text: str = initial_text
        self.styles.height = "auto"
        self._copy_button_text_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Markdown(self._full_text, id="assistant-markdown-content")
            yield Button("Copy", id="copy-text-button", classes="copy-button")

    def _update_markdown_widget(self):
        """Actual method to update the Markdown component content."""
        try:
            md_widget = self.query_one("#assistant-markdown-content", Markdown)
            # Use the latest _full_text to update
            md_widget.update(self._full_text)
            self.styles.height = "auto"  # Ensure parent container height adapts
        except Exception as e:
            # If an error occurs during lookup or update, record it
            # Check if self is mounted to prevent logging after unmount
            if self.is_mounted:
                self.log.error(f"Error updating Markdown widget: {e}")

    def append_text(self, delta: str):
        """
        Append text to internal state and update Markdown component
        based on throttling strategy.
        """
        # 1. Always update internal text buffer
        self._full_text += delta

        # 2. Check if UI should be updated (throttling)
        now = time.monotonic()
        if now - self._last_update_time >= self.THROTTLE_INTERVAL:
            # Use call_later to schedule UI update back to main thread
            self.app.call_later(self._update_markdown_widget)
            self._last_update_time = now

    def update_text(self, new_text: str):
        """
        Replace the content of the Markdown component completely
        and update the internal state.
        This method may be called on the main thread, directly updating.
        """
        # 1. Update internal state
        self._full_text = new_text
        # 2. Directly call the update method (since it's on the main thread)
        self._update_markdown_widget()

    def finalize_text(self):
        """Force final UI update and show the copy button."""
        self.app.call_later(self._show_final_content_and_button)

    def _show_final_content_and_button(self):
        """Helper to update UI on the main thread."""
        self._update_markdown_widget()
        try:
            copy_button = self.query_one("#copy-text-button", Button)
            copy_button.display = True  # Show the button
            copy_button.label = "Copy"  # Reset label
        except Exception as e:
            if self.is_mounted:
                self.log.error(f"Error showing copy button: {e}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-text-button":
            event.stop()
            if self._full_text:
                pyperclip.copy(self._full_text)
                event.button.label = "Copied!"
                event.button.add_class("copied")

                if self._copy_button_text_timer:
                    self._copy_button_text_timer.stop()
                self._copy_button_text_timer = self.set_timer(2.0, lambda: self._revert_copy_button_text(event.button))
            else:
                event.button.label = "Nothing to copy"
                self.set_timer(2.0, lambda: self._revert_copy_button_text(event.button))

    def _revert_copy_button_text(self, button: Button):
        if button.is_mounted:
            button.label = "Copy"
            button.remove_class("copied")
        self._copy_button_text_timer = None


# --- ToolCallDisplay, ToolOutputDisplay, SystemMessageDisplay ---


class ToolCallDisplay(BaseMessageDisplay):
    """Display tool call information."""

    DEFAULT_CSS = """
    ToolCallDisplay {
        padding: 1;
        border: round yellow;
        height: auto;
        width: auto;
        max-width: 85%;
        background: $panel-lighten-1;
    }
    ToolCallDisplay Horizontal { height: 1; }
    ToolCallDisplay .tool-name { text-style: bold; color: yellow; width: auto; padding: 0; margin: 0; }
    ToolCallDisplay .tool-id { color: $text-muted; text-align: right; width: 1fr; padding: 0; margin: 0; }
    ToolCallDisplay #args-display { margin-top: 1; padding: 1; background: $surface; border: solid $accent; height: auto; max-height: 15; overflow-y: auto; width: 1fr; }
    ToolCallDisplay #args-display Syntax { width: 100%; height: auto; }
    ToolCallDisplay #args-display .placeholder { color: $text-muted; text-style: italic; }
    """

    def __init__(self, function_name: str, tool_id: str, **kwargs):
        super().__init__(**kwargs)
        self.function_name = function_name
        self.tool_id = tool_id
        self._arguments = ""
        self._finalized = False
        self.styles.height = "auto"

    def compose(self) -> ComposeResult:
        # Use Horizontal container, it will automatically handle horizontal layout
        with Horizontal():
            yield Static(f"Tool Call: {self.function_name}", classes="tool-name")
            yield Static(f"ID: {self.tool_id}", classes="tool-id")

        yield Static(
            Text("(Receiving arguments...)"),
            id="args-display",
            expand=False,
            classes="placeholder",
        )

    def on_mount(self) -> None:
        if self._finalized:
            # It is necessary to manually update once here, because some model tool call parameters return too quickly
            # and complete within a few deltas, causing ToolCallDisplay to not be mounted yet,
            # which leads to an inability to correctly update args-display during finalize_arguments
            self._update_args_display(True)

    def append_arguments(self, delta: str):
        if not self._finalized:
            self._arguments += delta
            self._update_args_display()

    def finalize_arguments(self):
        self._finalized = True
        self._update_args_display(final=True)

    def _update_args_display(self, final: bool = False):
        try:
            args_static = self.query_one("#args-display", Static)
            args_static.styles.height = "auto"  # Ensure height recalculates
            display_content: Syntax | Text

            try:
                parsed_args = json.loads(self._arguments)
                pretty_json = json.dumps(parsed_args, indent=2)
                display_content = Syntax(
                    pretty_json,
                    "json",
                    theme="github-dark",  # 或者其他主题
                    line_numbers=False,
                    word_wrap=True,
                    # background_color="transparent", # <<< 移除此行
                )
                args_static.remove_class("placeholder")  # <<< 操作 Static 的类
            except json.JSONDecodeError:
                if final and self._arguments.strip():  # Only show error if final and not empty
                    display_content = Text(f"Invalid JSON:\n{self._arguments}", style="red", overflow="fold")
                    args_static.remove_class("placeholder")
                elif not self._arguments.strip() and not final:  # Still receiving
                    display_content = Text("(Receiving arguments...)")
                    args_static.add_class("placeholder")
                else:  # Empty or non-final invalid string
                    display_content = Text(self._arguments, overflow="fold")
                    if not self._arguments.strip():
                        args_static.add_class("placeholder")
                    else:
                        args_static.remove_class("placeholder")

            args_static.update(display_content)
            self.styles.height = "auto"  # Trigger parent resize

        except Exception as e:
            if self.is_mounted:
                try:
                    args_static = self.query_one("#args-display", Static)
                    if args_static.is_mounted:
                        self.log.error(f"Error updating args display for {self.tool_id}: {e}")
                except Exception:  # Guard against query failing too
                    self.log.error(f"Error updating args display (query failed) for {self.tool_id}: {e}")


class ToolOutputDisplay(BaseMessageDisplay):
    """Display the output of a tool execution."""

    DEFAULT_CSS = """
    ToolOutputDisplay {
        padding: 1;
        border: round $surface;
        height: auto;
        width: auto;
        max-width: 85%;
        background: $surface;
    }
    ToolOutputDisplay .tool-output-header { color: $text-muted; text-style: italic; margin-bottom: 1; height: 1; }
    ToolOutputDisplay .tool-output-content { margin-top: 1; max-height: 20; overflow-y: auto; width: 1fr; height: auto; }
    ToolOutputDisplay .tool-output-error { color: $error; border-left: thick $error; padding-left: 1; }
    """

    def __init__(self, tool_id: str, output: str, is_error: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.tool_id = tool_id
        self.output = output
        self.is_error = is_error
        self.styles.height = "auto"

    def compose(self) -> ComposeResult:
        yield Static(f"Output for tool call: {self.tool_id}", classes="tool-output-header")
        # Explicitly disable markup parsing for tool output content
        output_content = Static(self.output, classes="tool-output-content", expand=False, markup=False)
        if self.is_error:
            output_content.add_class("tool-output-error")
        yield output_content


class SystemMessageDisplay(BaseMessageDisplay):
    """Display system messages (e.g. errors, notifications)."""

    DEFAULT_CSS = """
    SystemMessageDisplay {
        color: $text-muted;
        text-style: italic;
        border: wide white; /* Ensure border color is explicitly not muted */
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(self, text: str, style: str = "dim", **kwargs):
        # Use Text object for potential styling
        super().__init__(Text(text, style=style), **kwargs)
        self.styles.height = "auto"
