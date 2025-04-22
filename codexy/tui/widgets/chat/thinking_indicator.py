from typing import Optional

from textual.reactive import reactive
from textual.widgets import Static
from textual.timer import Timer


class ThinkingIndicator(Static):
    """Display "Thinking..." animation and timer."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: auto;
        padding: 1;
    }
    """

    message: reactive[str] = reactive("Thinking")
    thinking_seconds: reactive[int] = reactive(0)
    _dots: reactive[str] = reactive(".")
    _timer: Optional[Timer] = None

    def on_mount(self) -> None:
        """Start animation timer."""
        self.update_display()
        self._timer = self.set_interval(0.5, self.update_dots)

    def on_unmount(self) -> None:
        """Stop timer."""
        if self._timer:
            self._timer.stop()

    def update_dots(self) -> None:
        """Update animation dots."""
        if len(self._dots) < 3:
            self._dots += "."
        else:
            self._dots = "."
        self.update_display()

    def watch_thinking_seconds(self, seconds: int) -> None:
        """Update display when seconds change."""
        self.update_display()

    def update_display(self) -> None:
        """Update displayed text."""
        display_text = f"{self.message}{self._dots} ({self.thinking_seconds}s)"
        self.update(display_text)

    def set_thinking_seconds(self, seconds: int):
        """External call to update seconds."""
        self.thinking_seconds = seconds
