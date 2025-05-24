from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Label, Static


class HelpOverlay(Static):
    """An overlay that displays help information about commands and shortcuts."""

    DEFAULT_CSS = """
    HelpOverlay {
        layer: help_layer;
        display: none;
        align: center middle;
        width: 80%;
        max-width: 80;
        height: 80%;
        max-height: 25;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
        overflow-y: auto;
    }
    HelpOverlay.-active {
        display: block;
    }
    HelpOverlay #help-title {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    HelpOverlay .help-section-title {
        margin-top: 1;
        text-style: bold underline;
    }
    HelpOverlay Static.help-command .command {
        color: $secondary;
        text-style: bold;
        width: 15;
    }
    HelpOverlay Static.help-command .description {
        width: 1fr;
    }
    HelpOverlay Static.help-key .key {
        color: $accent;
        text-style: bold;
        width: 10;
    }
    HelpOverlay Static.help-key .description {
        width: 1fr;
    }
    HelpOverlay Static.help-line {
        height: 1;
        width: 100%;
        margin-bottom: 1;
    }
    HelpOverlay #help-footer {
        margin-top: 1;
        width: 100%;
        text-align: center;
        color: $text-muted;
    }
    """

    COMMANDS: list[tuple[str, str]] = [
        ("/help", "Show this help overlay"),
        ("/model", "Switch the LLM model in-session"),
        ("/approval", "Switch auto-approval mode"),
        ("/history", "Show command & file history for this session"),
        ("/clear", "Clear screen & context"),
        ("/clearhistory", "Clear command history from disk"),
        ("/bug", "File a bug report with session log"),
        ("/compact", "Condense context into a summary (not implemented)"),
        ("q | exit | :q", "Exit codexy"),
    ]

    KEYBINDINGS: list[tuple[str, str]] = [
        ("Ctrl+J/Ctrl+Enter", "Submit message / Approve command"),
        ("Up/Down", "Navigate history / options"),
        ("ESC", "Cancel input / Deny command / Close overlay"),
        ("Ctrl+Q", "Quit Application"),
        ("F1", "Show this help overlay"),
        ("F2", "Change Model (not implemented)"),
        ("F3", "Change Approval Mode (not implemented)"),
        ("F4", "Show Command History"),
        # ("Ctrl+X", "Open External Editor (not implemented)"),
    ]

    class ExitHelp(Message):
        """Message to signal exiting the help overlay."""

        pass

    def compose(self) -> ComposeResult:
        yield Label("Available Commands & Shortcuts", id="help-title")
        with VerticalScroll():
            yield Label("Slash Commands", classes="help-section-title")

            for command, description in self.COMMANDS:
                line_text = Text.assemble(
                    (f"{command:<15}", "bold"),
                    f" - {description}",
                )
                yield Static(line_text, classes="help-line help-command")

            yield Label("Keyboard Shortcuts", classes="help-section-title")

            for key, description in self.KEYBINDINGS:
                line_text = Text.assemble(
                    (f"{key:<10}", "bold"),
                    f" - {description}",
                )
                yield Static(line_text, classes="help-line help-key")

        yield Label("Press ESC to close", id="help-footer")

    def on_key(self, event: events.Key) -> None:
        """Handle key press to close the overlay."""
        if event.key == "escape":
            event.stop()
            # Post message to the App to handle closing
            self.post_message(self.ExitHelp())
