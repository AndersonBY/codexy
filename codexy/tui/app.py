import json
import traceback
from pathlib import Path
from typing import List, Dict, Optional, AsyncIterator

from openai.types.chat import ChatCompletionMessageToolCall, ChatCompletionToolMessageParam
from openai.types.chat.chat_completion_message_tool_call import Function as OpenAIFunction

from textual.timer import Timer
from textual.reactive import reactive
from textual.app import App, ComposeResult
from textual.widgets import Footer, ListView
from textual.containers import Container, VerticalScroll

from .. import PACKAGE_NAME
from ..core.agent import Agent, StreamEvent
from ..config import AppConfig, load_config
from ..approvals import ApprovalMode, can_auto_approve, add_to_always_approved
from ..utils.storage import (
    load_command_history,
    add_to_history,
    clear_command_history,
    HistoryEntry,
    DEFAULT_HISTORY_CONFIG,
)
from ..utils.filesystem import check_in_git
from ..utils.update_checker import check_for_updates, UpdateInfo
from ..utils.model_utils import get_available_models
from .widgets.chat.history_view import ChatHistoryView
from .widgets.chat.input_area import ChatInputArea
from .widgets.chat.command_review import CommandReviewWidget
from .widgets.chat.message_display import (
    UserMessageDisplay,
    AssistantMessageDisplay,
    ToolCallDisplay,
    ToolOutputDisplay,
    SystemMessageDisplay,
)
from .widgets.chat.header import ChatHeader
from .widgets.chat.thinking_indicator import ThinkingIndicator
from .widgets.overlays import HelpOverlay, HistoryOverlay, ModelOverlay, ApprovalModeOverlay


class CodexTuiApp(App[None]):
    """Textual application for codexy TUI."""

    DEFAULT_CSS = """
    Screen {
        layers: default history command_review_layer help_layer model_overlay_layer approval_overlay_layer;
        align: center middle;
    }
    ChatHistoryView {
        border: none;
        padding: 0;
        margin: 0;
        height: 1fr;
        scrollbar-gutter: stable;
    }
    ChatInputArea {
        dock: bottom;
        height: auto;
        max-height: 50%;
    }
    CommandReviewWidget {
        layer: command_review_layer;
        overlay: screen;
        align: center middle;
        border: round $accent;
        padding: 1;
        width: 80%;
        max-width: 80;
        height: auto;
        max-height: 70%;
        background: $panel;
        &.-hidden {
            display: none;
        }
    }
    HistoryOverlay {
        layer: history;
        display: none;
        align: center middle;
        width: 80%;
        max-width: 100;
        height: 80%;
        max-height: 40;
        border: thick $accent;
        background: $panel;
    }
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
         display: block !important;
    }
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
        display: block !important;
    }
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
        display: block !important;
    }
    ThinkingIndicator {
        width: 1fr;
        &.-hidden {
            display: none;
        }
        padding: 1;
        border: none;
        color: $text-muted;
        background: $surface;
    }
    #main-content {
        border: none;
        padding: 0;
        height: 1fr;
        overflow: hidden;
    }
    ChatHeader {
        height: auto; 
        dock: top;
    }
    Footer {
        height: 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),  # Standard quit binding
        ("ctrl+p", "show_command_palette", "Command Palette"),
        ("f1", "show_help_overlay", "Help"),
        ("f2", "show_model_overlay", "Model"),
        ("f3", "show_approval_overlay", "Approval"),
        ("f4", "show_history_overlay", "History"),
    ]

    # --- Reactives ---
    # Use reactive properties to manage state, Textual will automatically update UI when they change
    is_loading: reactive[bool] = reactive(False)
    current_model: reactive[str] = reactive("")
    approval_mode: reactive[ApprovalMode] = reactive(ApprovalMode.SUGGEST)
    show_command_review: reactive[bool] = reactive(False)
    show_history_overlay: reactive[bool] = reactive(False)
    show_help_overlay: reactive[bool] = reactive(False)
    show_model_overlay: reactive[bool] = reactive(False)
    show_approval_overlay: reactive[bool] = reactive(False)
    _fetching_models: bool = False
    available_models: reactive[List[str]] = reactive(list)
    thinking_seconds: reactive[int] = reactive(0)

    # --- State ---
    agent: Optional[Agent] = None
    app_config: Optional[AppConfig] = None
    pending_tool_calls: Optional[List[ChatCompletionMessageToolCall]] = None
    tool_call_results: List[ChatCompletionToolMessageParam] = []
    current_tool_call_index: int = 0
    command_history: List[HistoryEntry] = []
    history_config = DEFAULT_HISTORY_CONFIG
    initial_prompt: Optional[str] = None
    initial_images: Optional[List[str]] = None
    _thinking_timer: Optional[Timer] = None

    # --- Initialization & Setup ---
    def __init__(
        self,
        config: Optional[AppConfig] = None,
        initial_prompt: Optional[str] = None,
        initial_images: Optional[List[str]] = None,
    ):
        super().__init__()
        self.app_config = config or load_config(cwd=Path.cwd())
        self.initial_prompt = initial_prompt
        self.initial_images = initial_images or []
        if self.app_config:
            self.current_model = self.app_config.get("model", "")
            try:
                mode_str = self.app_config.get("effective_approval_mode", ApprovalMode.SUGGEST.value)
                self.approval_mode = ApprovalMode(mode_str)
            except ValueError:
                self.log.warning(f"Invalid approval mode in config: '{mode_str}'. Defaulting to 'suggest'.")
                self.approval_mode = ApprovalMode.SUGGEST
            self.history_config = self.app_config.get("history") or DEFAULT_HISTORY_CONFIG
        else:
            self.current_model = "unknown"
            self.approval_mode = ApprovalMode.SUGGEST
            self.history_config = DEFAULT_HISTORY_CONFIG
            self.log.error("Critical: App config failed to load during initialization.")

    async def on_mount(self) -> None:
        """Called when the application is mounted."""
        self.log.info("Codex TUI App Mounted")
        if not self.app_config:
            self.log.error("App config not loaded!")
            self.exit(message="Error: App config failed to load.")
            return

        self.agent = Agent(self.app_config)
        if self.agent:
            self.agent.session_id = self.app_config.get("sessionId", None)

        self.current_model = self.agent.config["model"]

        try:
            # Ensure sync from agent's final config to approval_mode
            mode_str = self.agent.config.get("effective_approval_mode", ApprovalMode.SUGGEST.value)
            self.approval_mode = ApprovalMode(mode_str)
        except ValueError:
            self.approval_mode = ApprovalMode.SUGGEST

        header = self.query_one(ChatHeader)
        header.update_info(self.app_config, self.agent.session_id if self.agent else None)

        # --- Git Check ---
        try:
            cwd = Path.cwd()
            in_git = check_in_git(cwd)
            if not in_git and self.approval_mode != ApprovalMode.SUGGEST:
                warning_message = (
                    f"Warning: Running with approval mode '{self.approval_mode.value}' "
                    f"outside a Git repository ({cwd}). Changes cannot be easily reverted."
                )
                self.log.warning(warning_message)
                history_view = self.query_one(ChatHistoryView)
                self.call_later(history_view.add_message, SystemMessageDisplay(warning_message, style="bold yellow"))
        except Exception as e:
            self.log.error(f"Error checking Git status: {e}")
        # --- End Git Check ---

        self.command_history = load_command_history()
        self.query_one(ChatInputArea).set_history(self.command_history)

        self.run_worker(self.run_update_check(), group="update_check", name="Update Checker")
        self.run_worker(self.load_available_models(), group="init_load", name="Model Loader")

        if self.initial_prompt:
            self.call_later(self.process_input, self.initial_prompt, self.initial_images)
            self.initial_prompt = None
            self.initial_images = []

        if not self.is_loading:
            self.call_later(self.query_one(ChatInputArea).focus_input)

    async def run_update_check(self):
        """Worker function to perform the update check."""
        try:
            update_info: Optional[UpdateInfo] = await check_for_updates()
            if update_info:
                self.call_later(self._notify_update, update_info)
        except Exception as e:
            self.log.error(f"Error during background update check: {e}")

    async def load_available_models(self):
        """Worker function to load available models."""
        if not self.agent or self._fetching_models:
            return
        self._fetching_models = True
        try:
            models = await get_available_models(self.agent.async_client)
            if models:
                self.call_later(setattr, self, "available_models", models)
            else:
                self.log.warning("No models loaded from API.")
        except Exception as e:
            self.log.error(f"Error loading available models: {e}", exc_info=True)
        finally:
            self._fetching_models = False

    def _notify_update(self, update_info: UpdateInfo):
        """Displays the update notification."""
        message = (
            f"Update available! {update_info['current_version']} -> {update_info['latest_version']}.\n"
            f"Run: [b]pip install --upgrade {PACKAGE_NAME}[/b]"
        )
        self.notify(
            message,
            title="codexy Update",
            severity="information",
            timeout=15.0,  # Show for longer
        )

    # --- UI Composition ---
    def compose(self) -> ComposeResult:
        """Create the UI layout for the application."""
        yield ChatHeader()
        # Main content area for message history and thinking indicator
        # This container will occupy the space between Header and Footer/InputArea
        with Container(id="main-content"):
            yield ChatHistoryView(id="chat-history")
            # ThinkingIndicator and CommandReviewWidget are placed here, but will be shown/hidden based on state
            yield ThinkingIndicator(id="thinking", classes="-hidden")  # Start hidden
        # CommandReviewWidget and HistoryOverlay are direct children of the screen, using layers to control
        yield CommandReviewWidget(id="command-review", classes="-hidden")
        yield HistoryOverlay(id="history-overlay")
        yield HelpOverlay(id="help-overlay")
        yield ModelOverlay(id="model-overlay")
        yield ApprovalModeOverlay(id="approval-overlay")
        yield ChatInputArea(id="chat-input")
        yield Footer()

    # --- Helper to check if any overlay is active ---
    def _is_any_overlay_active(self) -> bool:
        """Checks if any major overlay is currently active."""
        return (
            self.show_command_review
            or self.show_history_overlay
            or self.show_help_overlay
            or self.show_model_overlay
            or self.show_approval_overlay
        )

    # --- Dynamic UI Updates ---
    def watch_is_loading(self, loading: bool) -> None:
        """Switch between showing input box or indicator based on loading state, and focus when loading is finished."""
        was_loading = not loading  # Infer previous state
        try:
            thinking_indicator = self.query_one(ThinkingIndicator)
            input_area = self.query_one(ChatInputArea)

            thinking_indicator.set_class(not loading, "-hidden")  # Use class to hide/show
            input_area.display = not loading

            if loading:
                self.log.info("watch_is_loading: Loading started.")
                self.thinking_seconds = 0
                thinking_indicator.set_thinking_seconds(0)  # Reset indicator seconds
                if self._thinking_timer:
                    self._thinking_timer.stop()
                self._thinking_timer = self.set_interval(1.0, self._update_thinking_timer)
            else:
                self.log.info("watch_is_loading: Loading finished.")
                if self._thinking_timer:
                    self._thinking_timer.stop()
                    self._thinking_timer = None

                # Only focus input box when review widget is not visible
                if was_loading and not self.show_command_review and input_area.is_mounted:
                    self.call_later(input_area.focus_input)

        except Exception as e:
            if self.is_mounted:
                self.log.error(f"Error in watch_is_loading: {e}")

    def _update_thinking_timer(self):
        """Update the thinking timer."""
        if self.is_loading:
            self.thinking_seconds += 1
            try:
                # Update the indicator directly if it exists
                thinking_indicator = self.query_one(ThinkingIndicator)
                if thinking_indicator.is_mounted:
                    thinking_indicator.set_thinking_seconds(self.thinking_seconds)
            except Exception:
                # Stop timer if component is gone
                if self._thinking_timer:
                    self._thinking_timer.stop()
                    self._thinking_timer = None
        else:
            # Stop timer if loading becomes false unexpectedly
            if self._thinking_timer:
                self._thinking_timer.stop()
                self._thinking_timer = None

    def watch_show_command_review(self, show: bool) -> None:
        """Switch between showing command review component and input area."""
        try:
            review_widget = self.query_one(CommandReviewWidget)
            input_area = self.query_one(ChatInputArea)
            thinking_indicator = self.query_one(ThinkingIndicator)
            review_widget.set_class(not show, "-hidden")

            # --- Focus Management ---
            if show:
                input_area.display = False
                thinking_indicator.set_class(True, "-hidden")
                self.log.info("Showing Command Review.")
                self.call_later(review_widget.focus)
            else:
                self.log.info("Hiding Command Review.")
                should_show_input = not self.is_loading and not self._is_any_overlay_active()  # <-- 使用助手
                input_area.display = should_show_input
                thinking_indicator.set_class(not self.is_loading, "-hidden")
                if should_show_input and input_area.is_mounted:
                    self.call_later(input_area.focus_input)
        except Exception as e:
            self.log.error(f"Error in watch_show_command_review: {e}", exc_info=True)

    def watch_show_history_overlay(self, show: bool) -> None:
        """Show or hide the history overlay and manage focus."""
        try:
            history_overlay = self.query_one(HistoryOverlay)
            input_area = self.query_one(ChatInputArea)
            thinking_indicator = self.query_one(ThinkingIndicator)
            history_overlay.set_class(show, "-active")
            history_overlay.display = show
            if show:
                history_overlay.set_history(self.command_history)
                input_area.display = False
                thinking_indicator.set_class(True, "-hidden")
                self.call_later(lambda: history_overlay.query_one(ListView).focus())
            else:
                should_show_input = not self.is_loading and not self._is_any_overlay_active()
                input_area.display = should_show_input
                thinking_indicator.set_class(not self.is_loading, "-hidden")
                if should_show_input and input_area.is_mounted:
                    self.call_later(input_area.focus_input)
        except Exception as e:
            self.log.warning(f"Error toggling history overlay: {e}")

    def watch_show_help_overlay(self, show: bool) -> None:
        """Show or hide the help overlay and manage focus."""
        self.log.info(f"watch_show_help_overlay: show={show}")
        try:
            help_overlay = self.query_one(HelpOverlay)
            input_area = self.query_one(ChatInputArea)
            thinking_indicator = self.query_one(ThinkingIndicator)
            help_overlay.set_class(show, "-active")
            help_overlay.display = show
            if show:
                input_area.display = False
                thinking_indicator.set_class(True, "-hidden")
                self.call_later(lambda: help_overlay.query_one(VerticalScroll).focus())
            else:
                should_show_input = not self.is_loading and not self._is_any_overlay_active()
                input_area.display = should_show_input
                thinking_indicator.set_class(not self.is_loading, "-hidden")
                if should_show_input and input_area.is_mounted:
                    self.call_later(input_area.focus_input)

        except Exception as e:
            self.log.warning(f"Error toggling help overlay: {e}")

    def watch_current_model(self, new_model: str) -> None:
        """Update the ChatHeader when the app's current_model changes."""
        self.log.info(f"App's current_model changed to: {new_model}. Updating header.")
        try:
            # Find the header and update its model reactive property
            header = self.query_one(ChatHeader)
            if header.is_mounted:
                header.model = new_model  # This will trigger the header's own watcher
        except Exception as e:
            self.log.error(f"Error updating header model in watch_current_model: {e}")

    def action_show_model_overlay(self) -> None:
        """Toggle the model overlay."""
        if not self.agent:
            self.notify("Agent not initialized.", severity="error")
            return
        # Only show if not already showing another major overlay
        if not self.show_history_overlay and not self.show_command_review and not self.show_help_overlay:
            # Ensure models are loaded before showing
            if not self.available_models and not self._fetching_models:
                self.notify("Loading available models...", severity="information")
                self.run_worker(self.load_available_models(), group="model_load", name="Model Loader Background")

            model_overlay = self.query_one(ModelOverlay)
            # Check if switching is allowed (e.g., if agent has a last_response_id)
            can_switch_now = not bool(self.agent.last_response_id)
            self.log.info(f"Model overlay requested. Can switch: {can_switch_now}")
            model_overlay.can_switch = can_switch_now
            model_overlay.available_models = self.available_models
            model_overlay.current_model = self.current_model
            self.show_model_overlay = True  # Toggle visibility last
        elif self.show_model_overlay:  # Allow closing
            self.show_model_overlay = False

    def watch_show_model_overlay(self, show: bool) -> None:
        """Show or hide the model overlay and manage focus."""
        self.log.info(f"watch_show_model_overlay: show={show}")
        try:
            model_overlay = self.query_one(ModelOverlay)
            input_area = self.query_one(ChatInputArea)
            thinking_indicator = self.query_one(ThinkingIndicator)

            model_overlay.set_class(show, "-active")
            model_overlay.display = show

            if show:
                # Ensure models are available before showing
                if not self.available_models and not self._fetching_models:
                    self.notify("Loading available models...", severity="information")
                    self.run_worker(self.load_available_models(), group="model_load", name="Model Loader Background")

                input_area.display = False
                thinking_indicator.set_class(True, "-hidden")
                # Update overlay state just before showing
                model_overlay.can_switch = not bool(self.agent.last_response_id if self.agent else True)
                model_overlay.available_models = self.available_models
                model_overlay.current_model = self.current_model
                self.call_later(model_overlay.focus_list)  # Focus after potential list update
            else:
                should_show_input = not self.is_loading and not self._is_any_overlay_active()
                input_area.display = should_show_input
                thinking_indicator.set_class(not self.is_loading, "-hidden")
                if should_show_input and input_area.is_mounted:
                    self.call_later(input_area.focus_input)
        except Exception as e:
            self.log.warning(f"Error toggling model overlay: {e}", exc_info=True)

    def watch_show_approval_overlay(self, show: bool) -> None:
        """Show or hide the approval mode overlay and manage focus."""
        self.log.info(f"watch_show_approval_overlay: show={show}")
        try:
            approval_overlay = self.query_one(ApprovalModeOverlay)
            input_area = self.query_one(ChatInputArea)
            thinking_indicator = self.query_one(ThinkingIndicator)

            approval_overlay.set_class(show, "-active")
            approval_overlay.display = show

            if show:
                input_area.display = False
                thinking_indicator.set_class(True, "-hidden")
                # Update overlay state just before showing
                approval_overlay.current_mode = self.approval_mode
                self.call_later(approval_overlay.focus_list)  # Focus after potential list update
            else:
                should_show_input = not self.is_loading and not self._is_any_overlay_active()
                input_area.display = should_show_input
                thinking_indicator.set_class(not self.is_loading, "-hidden")
                if should_show_input and input_area.is_mounted:
                    self.call_later(input_area.focus_input)

        except Exception as e:
            self.log.warning(f"Error toggling approval overlay: {e}", exc_info=True)

    def watch_approval_mode(self, new_mode: ApprovalMode) -> None:
        """Update the header and potentially the overlay when approval mode changes."""
        self.log.info(f"App's approval_mode changed to: {new_mode.value}. Updating UI.")
        try:
            header = self.query_one(ChatHeader)
            if header.is_mounted:
                header.approval_mode = new_mode.value  # Update header

            # Update the overlay if it's currently visible
            approval_overlay = self.query_one(ApprovalModeOverlay)
            if approval_overlay.is_mounted and approval_overlay.display:
                approval_overlay.current_mode = new_mode

            # Update agent config if agent exists
            if self.agent and self.app_config:
                self.agent.config["effective_approval_mode"] = new_mode.value
                # Also update the agent's internal state if it uses it directly
                # self.agent.approval_policy = new_mode
                self.log.info(f"Agent approval mode potentially updated to {new_mode.value}")

        except Exception as e:
            self.log.error(f"Error in watch_approval_mode: {e}")

    # --- Event Handlers & Actions ---

    def action_show_approval_overlay(self) -> None:
        """Toggle the approval mode overlay."""
        # Only show if not already showing another major overlay
        if not self._is_any_overlay_active():
            self.show_approval_overlay = True
        elif self.show_approval_overlay:  # Allow closing if it's the one showing
            self.show_approval_overlay = False

    # --- Event Handlers & Actions ---
    def action_show_help_overlay(self) -> None:
        """Toggle the help overlay."""
        # Only show if not already showing another major overlay
        if not self.show_history_overlay and not self.show_command_review:
            self.show_help_overlay = not self.show_help_overlay
        elif self.show_help_overlay:  # Allow closing even if others are technically visible but hidden
            self.show_help_overlay = False

    def action_show_history_overlay(self) -> None:
        """Toggle the history overlay."""
        self.show_history_overlay = not self.show_history_overlay

    async def on_chat_input_area_submit(self, message: ChatInputArea.Submit) -> None:
        """Handle submit events from the input area."""
        # Don't process if an overlay is active
        if self.show_command_review or self.show_history_overlay or self.show_help_overlay:
            return
        await self.process_input(message.value)
        # Clear input after processing in process_input

    async def process_input(self, user_input: str, image_paths: Optional[List[str]] = None):
        """Process user input, handle special commands, and start Agent."""
        if not self.agent or not user_input.strip():
            return

        command = user_input.strip().lower()
        history_view = self.query_one(ChatHistoryView)
        input_area = self.query_one(ChatInputArea)

        # Handle special commands BEFORE adding to history or displaying
        if command == "/help":  # <-- Handle /help
            self.action_show_help_overlay()
            input_area.clear_input()
            return
        if command == "/history":
            self.action_show_history_overlay()
            input_area.clear_input()  # Clear after handling
            return
        if command == "/clear":
            if self.agent:
                self.agent.clear_history()
            history_view.clear()
            history_view.add_message(SystemMessageDisplay("Context cleared.", style="italic green"))
            self.pending_tool_calls = None
            self.tool_call_results = []
            self.current_tool_call_index = 0
            input_area.clear_input()
            return
        if command == "/clearhistory":
            try:
                clear_command_history()
                self.command_history = []
                input_area.set_history(self.command_history)
                history_view.add_message(SystemMessageDisplay("Command history cleared.", style="italic green"))
            except Exception as e:
                self.log.error(f"Failed to clear command history: {e}")
                history_view.add_message(SystemMessageDisplay(f"Error clearing history: {e}", style="bold red"))
            input_area.clear_input()
            return
        if command == "/compact":
            # TODO: Implement context compaction
            self.notify("Context compaction not implemented yet.")
            input_area.clear_input()
            return
        if command == "/bug":
            # TODO: Implement bug report URL generation
            self.notify("Bug reporting not implemented yet.")
            input_area.clear_input()
            return
        if command == "/help":
            self.action_show_help_overlay()
            input_area.clear_input()
            return
        if command.startswith("/model"):
            self.action_show_model_overlay()
            input_area.clear_input()
            return
        if command.startswith("/approval"):
            self.action_show_approval_overlay()
            input_area.clear_input()
            return

        # --- Process as normal input ---
        history_view.add_message(UserMessageDisplay(user_input))  # Show original input

        if not hasattr(self, "history_config") or not self.history_config:
            self.history_config = DEFAULT_HISTORY_CONFIG
        self.command_history = add_to_history(user_input, self.command_history, self.history_config)
        input_area.set_history(self.command_history)  # Update input area's history copy
        input_area.clear_input()  # Clear input *after* adding to history

        self.is_loading = True
        self.pending_tool_calls = None
        self.tool_call_results = []
        self.current_tool_call_index = 0
        self.run_worker(
            self.handle_agent_stream(prompt=user_input, image_paths=image_paths), exclusive=True, group="agent_main"
        )

    async def handle_agent_stream(
        self,
        prompt: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        tool_results: Optional[List[ChatCompletionToolMessageParam]] = None,
    ):
        """Handle the agent's stream in a background worker."""
        if not self.agent:
            self.is_loading = False
            return

        self.log.info(
            f"--- Starting handle_agent_stream (prompt={'yes' if prompt else 'no'}, tool_results={'yes' if tool_results else 'no'}) ---"
        )

        history_view = self.query_one(ChatHistoryView)
        current_assistant_message: Optional[AssistantMessageDisplay] = None
        current_tool_displays: Dict[str, ToolCallDisplay] = {}

        try:
            stream_iterator: AsyncIterator[StreamEvent]
            if tool_results:
                stream_iterator = self.agent.continue_with_tool_results_stream(tool_results)
            elif prompt:
                # Pass images to the initial turn if they exist
                stream_iterator = self.agent.process_turn_stream(prompt, image_paths=image_paths)
            else:
                self.log.error("Agent stream handling called without prompt or tool results.")
                self.is_loading = False
                self.call_later(
                    history_view.add_message,
                    SystemMessageDisplay("Internal error: Agent processing failed.", style="bold red"),
                )
                return

            async for event in stream_iterator:
                if event["type"] == "text_delta":
                    delta = event["content"] or ""
                    if current_assistant_message is None:
                        current_assistant_message = AssistantMessageDisplay("")
                        self.call_later(history_view.add_message, current_assistant_message)
                    self.call_later(current_assistant_message.append_text, delta)
                    self.call_later(history_view.scroll_end, animate=False)
                elif event["type"] == "tool_call_start":
                    tool_id = event["tool_call_id"]
                    func_name = event["tool_function_name"]
                    if tool_id and func_name:
                        tool_display = ToolCallDisplay(func_name, tool_id)
                        current_tool_displays[tool_id] = tool_display
                        self.call_later(history_view.add_message, tool_display)
                        self.call_later(history_view.scroll_end, animate=False)
                elif event["type"] == "tool_call_delta":
                    tool_id = event["tool_call_id"]
                    args_delta = event["tool_arguments_delta"]
                    if tool_id and args_delta and tool_id in current_tool_displays:
                        self.call_later(current_tool_displays[tool_id].append_arguments, args_delta)
                        self.call_later(history_view.scroll_end, animate=False)
                elif event["type"] == "tool_call_end":
                    tool_id = event["tool_call_id"]
                    if tool_id and tool_id in current_tool_displays:
                        self.call_later(current_tool_displays[tool_id].finalize_arguments)
                        self.call_later(history_view.scroll_end, animate=False)
                elif event["type"] == "response_end":
                    if current_assistant_message:
                        current_assistant_message.finalize_text()
                    self.log.info("[Agent] Received response_end event from stream iterator.")
                    self.call_later(history_view.scroll_end, animate=False)
                    break
                elif event["type"] == "error":
                    self.call_later(
                        history_view.add_message,
                        SystemMessageDisplay(f"Agent Error: {event['content']}", style="bold red"),
                    )
                    self.is_loading = False
                    return
                elif event["type"] == "cancelled":
                    self.call_later(
                        history_view.add_message, SystemMessageDisplay("Operation Cancelled.", style="yellow")
                    )
                    self.is_loading = False
                    return

            self.log.info("--- Stream processing loop finished ---")

            if self.agent and self.agent.pending_tool_calls:
                self.log.info(f"Agent has {len(self.agent.pending_tool_calls)} pending tool calls after stream.")
                self.pending_tool_calls = list(self.agent.pending_tool_calls)
                self.agent.pending_tool_calls = None
                self.current_tool_call_index = 0
                self.tool_call_results = []
                self.call_later(self.process_next_tool_call)
            else:
                self.log.info("Agent turn completed (no pending tool calls detected after stream).")
                self.is_loading = False

        except Exception as e:
            self.log.error(f"Traceback: {traceback.format_exc()}")
            self.log.error(f"Error handling agent stream: {e}", exc_info=True)
            self.call_later(history_view.add_message, SystemMessageDisplay(f"Critical Error: {e}", style="bold red"))
            self.is_loading = False

    def process_next_tool_call(self):
        """Process the next tool call in the pending list."""
        self.log.info(
            f"--- process_next_tool_call: index={self.current_tool_call_index}, "
            f"pending_count={len(self.pending_tool_calls) if self.pending_tool_calls else 0} ---"
        )

        if (
            not self.agent
            or self.pending_tool_calls is None
            or self.current_tool_call_index >= len(self.pending_tool_calls)
        ):
            if self.tool_call_results:
                self.log.info(f"All tools processed. Sending {len(self.tool_call_results)} result(s) back to agent.")
                self.is_loading = True
                results_to_send = list(self.tool_call_results)
                self.pending_tool_calls = None
                self.tool_call_results = []
                self.run_worker(
                    self.handle_agent_stream(tool_results=results_to_send), exclusive=True, group="agent_continuation"
                )
            else:
                self.log.info("All tools processed, but no results to send.")
                self.pending_tool_calls = None
                self.is_loading = False
            return

        tool_request = self.pending_tool_calls[self.current_tool_call_index]
        tool_id = tool_request.id
        func_data = tool_request.function
        func_name = func_data.name
        func_args_str = func_data.arguments
        tool_args = {}
        run_in_sandbox = False

        if not tool_id or not func_name:
            self.log.error(f"Invalid tool request structure at index {self.current_tool_call_index}: {tool_request}")
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)
            return

        try:
            if not isinstance(func_args_str, str):
                raise ValueError("Args not string")
            tool_args = json.loads(func_args_str) if func_args_str else {}
            if not isinstance(tool_args, dict):
                raise ValueError("Args not dict")
        except Exception as e:
            result_content = f"Error: Could not parse tool arguments: {e}"
            self.log.error(f"Failed to parse args for tool {tool_id}: {e}")
            self.call_later(
                self.query_one(ChatHistoryView).add_message, ToolOutputDisplay(tool_id, result_content, is_error=True)
            )
            self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)
            return

        if not self.app_config:
            self.log.error("App config not available for approval check.")
            result_content = "Error: Configuration unavailable for approval."
            self.call_later(
                self.query_one(ChatHistoryView).add_message, SystemMessageDisplay(result_content, style="bold red")
            )
            self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)
            return

        self.log.info(f"Checking approval for tool '{func_name}' with mode '{self.approval_mode}'")
        safety_assessment = can_auto_approve(func_name, tool_args, self.approval_mode, self.app_config)
        run_in_sandbox = safety_assessment.get("run_in_sandbox", False)
        self.log.info(f"Safety assessment result for {tool_id} ({func_name}): {safety_assessment}")

        if safety_assessment["type"] == "auto-approve":
            self.log.info(f"Auto-approving tool call {tool_id} ({func_name}). Reason: {safety_assessment['reason']}")
            self.run_worker(
                self.execute_tool(tool_request, tool_args, run_in_sandbox), exclusive=False, group=f"tool-{tool_id}"
            )
        elif safety_assessment["type"] == "reject":
            result_content = f"Tool call rejected by safety system: {safety_assessment['reason']}"
            self.log.warning(f"Rejecting tool call {tool_id} ({func_name}). Reason: {safety_assessment['reason']}")
            self.call_later(
                self.query_one(ChatHistoryView).add_message, ToolOutputDisplay(tool_id, result_content, is_error=True)
            )
            self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)
        else:  # ask-user
            self.log.info(f"Ask user approval required for tool call {tool_id} ({func_name})")
            try:
                review_widget = self.query_one(CommandReviewWidget)
                display_args_str = func_data.arguments if isinstance(func_data.arguments, str) else "{}"
                review_widget.set_tool_info(func_name, display_args_str, tool_id, self.approval_mode)
                self.is_loading = False
                self.show_command_review = True
            except Exception as e:
                self.log.error(f"Error preparing command review UI for {tool_id}: {e}", exc_info=True)
                result_content = f"Error showing review prompt: {e}"
                self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
                self.current_tool_call_index += 1
                self.call_later(self.process_next_tool_call)

    def on_command_review_widget_review_result(self, message: CommandReviewWidget.ReviewResult) -> None:
        """Handle the result from the command review widget."""
        self.show_command_review = False
        if not self.agent or self.pending_tool_calls is None:
            self.log.error("Received review result but no pending tool call found.")
            return

        if self.current_tool_call_index >= len(self.pending_tool_calls):
            self.log.error("Received review result but index out of bounds.")
            return

        tool_request = self.pending_tool_calls[self.current_tool_call_index]
        tool_id = tool_request.id
        func_name = tool_request.function.name
        func_args_str = tool_request.function.arguments
        tool_args = {}
        run_in_sandbox = False

        try:
            if not isinstance(func_args_str, str):
                raise ValueError("Args not string")
            tool_args = json.loads(func_args_str) if func_args_str else {}
            if not isinstance(tool_args, dict):
                raise ValueError("Args not dict")
            if self.app_config:
                safety_assessment = can_auto_approve(func_name, tool_args, self.approval_mode, self.app_config)
                run_in_sandbox = safety_assessment.get("run_in_sandbox", False)
        except Exception as e:
            self.log.error(f"Error re-parsing args for {tool_id}: {e}")
            result_content = (
                f"Error processing tool arguments: {e}" if message.approved else message.feedback or "Denied by user."
            )
            self.call_later(
                self.query_one(ChatHistoryView).add_message, ToolOutputDisplay(tool_id, result_content, is_error=True)
            )
            self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)
            return

        if message.approved:
            self.log.info(f"User approved tool call {tool_id} ({func_name}). Always: {message.always_approve}")
            if message.always_approve and func_name:
                add_to_always_approved(func_name, tool_args)
            self.run_worker(
                self.execute_tool(tool_request, tool_args, run_in_sandbox), exclusive=False, group=f"tool-{tool_id}"
            )
        else:
            result_content = message.feedback or "Denied by user."
            self.log.info(f"User denied tool call {tool_id} ({func_name}). Feedback: '{result_content}'")
            self.call_later(
                self.query_one(ChatHistoryView).add_message, ToolOutputDisplay(tool_id, result_content, is_error=True)
            )
            self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
            self.current_tool_call_index += 1
            self.call_later(self.process_next_tool_call)

    async def execute_tool(self, tool_request: ChatCompletionMessageToolCall, tool_args: Dict, is_sandboxed: bool):
        """Execute the tool in a background worker and handle results."""
        if not self.agent or not self.app_config:
            self.log.error("Agent or AppConfig not available for tool execution.")
            return
        tool_id = tool_request.id
        func_name = tool_request.function.name
        func_args_str = tool_request.function.arguments
        result_content = f"Error: Tool '{func_name}' execution failed internally."
        final_exception = None

        self.log.info(
            f"--- execute_tool worker started: tool_id={tool_id}, func_name={func_name}, is_sandboxed={is_sandboxed} ---"
        )

        try:
            if not isinstance(func_args_str, str):
                raise TypeError("Args must be string")
            mock_tool_call = ChatCompletionMessageToolCall(
                id=tool_id, function=OpenAIFunction(name=func_name, arguments=func_args_str), type="function"
            )
            allowed_paths_config = self.app_config.get("writable_roots")
            allowed_paths = [Path(p) for p in allowed_paths_config] if allowed_paths_config else None
            self.log.info(f"Calling agent._execute_tool_implementation for {tool_id}...")
            result_content = self.agent._execute_tool_implementation(
                mock_tool_call, is_sandboxed=is_sandboxed, allowed_write_paths=allowed_paths
            )
        except Exception as e:
            final_exception = e
            self.log.error(f"Error executing tool {tool_id} ({func_name}): {e}", exc_info=True)
            result_content = f"Error executing tool: {e}"
        finally:

            def update_ui_and_state():
                try:
                    is_error = final_exception is not None
                    self.log.info(f"Tool {tool_id} ({func_name}) execution finished (Error={is_error}). Updating UI.")
                    history_view = self.query_one(ChatHistoryView)
                    self.call_later(
                        history_view.add_message,
                        ToolOutputDisplay(tool_id, result_content, is_error=is_error),
                    )
                    self.call_later(history_view.scroll_end, animate=False)

                    self.tool_call_results.append({"role": "tool", "tool_call_id": tool_id, "content": result_content})
                    self.current_tool_call_index += 1
                    self.log.info(
                        f"Finished processing tool index {self.current_tool_call_index - 1}. Calling process_next_tool_call..."
                    )
                    self.process_next_tool_call()
                except Exception as ui_e:
                    self.log.error(f"Error updating UI after tool execution: {ui_e}", exc_info=True)
                    self.current_tool_call_index += 1
                    self.process_next_tool_call()

            self.call_later(update_ui_and_state)
            self.log.info(f"--- execute_tool worker finished: tool_id={tool_id} ---")

    def on_history_overlay_select_history(self, message: HistoryOverlay.SelectHistory) -> None:
        """Handle history command selection from the overlay."""
        self.show_history_overlay = False
        try:
            input_area = self.query_one(ChatInputArea)
            input_area.set_input_value(message.command)
            if not self.is_loading and not self.show_command_review:
                self.call_later(input_area.focus_input)
        except Exception as e:
            self.log.warning(f"Error handling history selection: {e}")

    def on_history_overlay_exit_history(self) -> None:
        """Handle closing the history overlay."""
        self.show_history_overlay = False
        try:
            input_area = self.query_one(ChatInputArea)
            if not self.is_loading and not self.show_command_review:
                self.call_later(input_area.focus_input)
        except Exception as e:
            self.log.warning(f"Error focusing input after closing history: {e}")

    def on_help_overlay_exit_help(self) -> None:
        """Handle closing the help overlay."""
        self.show_help_overlay = False

    def on_model_overlay_selected(self, message: ModelOverlay.Selected) -> None:
        """Handle model selection from the overlay."""
        selected_model = message.model_id
        self.log.info(f"Received model selection: {selected_model}")

        # Hide overlay first
        self.show_model_overlay = False

        if not self.agent:
            self.notify("Agent not available.", severity="error")
            return

        if self.agent.last_response_id and selected_model != self.current_model:
            self.notify("Cannot switch model after conversation has started.", severity="warning")
            # Refocus input area even if selection failed
            self.call_later(self.query_one(ChatInputArea).focus_input)
            return

        if selected_model != self.current_model:
            self.log.info(f"Switching model from {self.current_model} to {selected_model}")
            self.agent.cancel()
            self.is_loading = False  # Ensure loading state is reset

            # Update state and agent config
            self.current_model = selected_model

            # Update config dictionaries directly
            if self.app_config:
                self.app_config["model"] = selected_model
            self.agent.config["model"] = selected_model
            self.agent.last_response_id = None  # Reset last response ID

            # Add system message (no need to update header explicitly here)
            history_view = self.query_one(ChatHistoryView)
            history_view.add_message(SystemMessageDisplay(f"Switched model to {selected_model}", style="italic blue"))
            self.notify(f"Model switched to {selected_model}")
        else:
            self.log.info("Selected model is the same as current, no change.")

        # Refocus input area
        self.call_later(self.query_one(ChatInputArea).focus_input)

    def on_model_overlay_exit(self, message: ModelOverlay.Exit) -> None:
        """Handle exiting the model overlay without selection."""
        self.log.info("Model overlay exited without selection.")
        self.show_model_overlay = False
        # Refocus input area
        input_area = self.query_one(ChatInputArea)
        if input_area.is_mounted:
            self.call_later(input_area.focus_input)

    def on_approval_mode_overlay_approval_mode_selected(
        self, message: ApprovalModeOverlay.ApprovalModeSelected
    ) -> None:
        """Handle mode selection from the approval overlay."""
        selected_mode = message.mode
        self.log.info(f"Received approval mode selection: {selected_mode.value}")

        # Hide overlay first
        self.show_approval_overlay = False

        if not self.agent or not self.app_config:
            self.notify("Agent or config not available.", severity="error")
            # Refocus input even on error
            if not self._is_any_overlay_active() and self.query_one(ChatInputArea).is_mounted:
                self.call_later(self.query_one(ChatInputArea).focus_input)
            return

        if selected_mode != self.approval_mode:
            self.log.info(f"Switching approval mode from {self.approval_mode.value} to {selected_mode.value}")
            self.agent.cancel()  # Cancel any ongoing agent work
            self.is_loading = False  # Ensure loading state is reset

            # Update state - this triggers the watcher which updates header, agent, etc.
            self.approval_mode = selected_mode

            # Add system message
            history_view = self.query_one(ChatHistoryView)
            history_view.add_message(
                SystemMessageDisplay(f"Switched approval mode to {selected_mode.value}", style="italic blue")
            )
            self.notify(f"Approval mode switched to {selected_mode.value}")
        else:
            self.log.info("Selected approval mode is the same as current, no change.")

        # Refocus input area (watcher should handle if conditions met, but call here as fallback)
        if not self._is_any_overlay_active():
            input_area = self.query_one(ChatInputArea)
            if input_area.is_mounted:
                self.call_later(input_area.focus_input)

    def on_approval_mode_overlay_exit_approval_overlay(self) -> None:
        """Handle exiting the approval overlay without selection."""
        self.log.info("Approval overlay exited without selection.")
        self.show_approval_overlay = False
        # Refocus input area (watcher should handle if conditions met, but call here as fallback)
        if not self._is_any_overlay_active():
            input_area = self.query_one(ChatInputArea)
            if input_area.is_mounted:
                self.call_later(input_area.focus_input)


if __name__ == "__main__":
    app = CodexTuiApp(initial_prompt="Hello!")
    app.run()
