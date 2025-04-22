# -*- coding: utf-8 -*-
from textual.containers import VerticalScroll, Container
from .message_display import (
    BaseMessageDisplay,
    UserMessageDisplay,
    AssistantMessageDisplay,
    ToolCallDisplay,
    ToolOutputDisplay,
    SystemMessageDisplay,
)


class ChatHistoryView(VerticalScroll):
    """Display the scrollable area for chat message history."""

    DEFAULT_CSS = """
    ChatHistoryView {
        border: none;
        padding: 0 1;
    }
    ChatHistoryView > Container {
        /* Ensure containers take full width for alignment */
        width: 100%;
        height: auto;
        /* Add some spacing between message containers */
        margin-bottom: 1;
    }
    ChatHistoryView > .user-message-container {
        align-horizontal: right; /* Align user messages to the right */
    }
    ChatHistoryView > .assistant-message-container,
    ChatHistoryView > .tool-call-container,
    ChatHistoryView > .tool-output-container,
    ChatHistoryView > .system-message-container {
        align-horizontal: left; /* Align others to the left */
    }
    """

    def add_message(self, message_widget: BaseMessageDisplay):
        """
        Add a new message component to the history view.
        Now wraps the message component in a Container to control alignment.
        """
        # Create a container to wrap the message component
        container = Container(message_widget)
        container.styles.height = "auto"  # Ensure container height adapts

        # Add CSS class based on message type
        if isinstance(message_widget, UserMessageDisplay):
            container.add_class("user-message-container")
        elif isinstance(message_widget, AssistantMessageDisplay):
            container.add_class("assistant-message-container")
        elif isinstance(message_widget, ToolCallDisplay):
            container.add_class("tool-call-container")
        elif isinstance(message_widget, ToolOutputDisplay):
            container.add_class("tool-output-container")
        elif isinstance(message_widget, SystemMessageDisplay):
            container.add_class("system-message-container")
        else:
            container.add_class("other-message-container")

        # Mount the wrapped container, not the message component directly
        self.mount(container)
        # Scroll to the bottom, ensuring new messages are visible
        self.call_after_refresh(self.scroll_end, animate=True)

    def clear(self):
        """Clear all history messages."""
        self.remove_children()
