"""Core agent logic for interacting with OpenAI API."""

import asyncio
import inspect
import json
import os
import sys
import traceback
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    RateLimitError,
)
from openai._types import NOT_GIVEN
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_param import ChatCompletionContentPartParam
from openai.types.chat.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
from openai.types.chat.chat_completion_message_tool_call import Function as OpenAIFunction

from ..config import DEFAULT_FULL_STDOUT, AppConfig
from ..tools import AVAILABLE_TOOL_DEFS, TOOL_REGISTRY

# Constants for retry logic
MAX_RETRIES = 5
INITIAL_RETRY_DELAY_SECONDS = 1.0  # Initial delay for retries
MAX_RETRY_DELAY_SECONDS = 30.0  # Maximum delay between retries


class StreamEvent(TypedDict):
    type: str
    content: str | None
    tool_call_id: str | None
    tool_function_name: str | None
    # Reverted: Use tool_arguments_delta as the key name expected by the TUI
    tool_arguments_delta: str | None


def create_stream_event(
    type: str,
    content: str | None = None,
    tool_call_id: str | None = None,
    tool_function_name: str | None = None,
    tool_arguments_delta: str | None = None,  # Use delta here
) -> StreamEvent:
    return {
        "type": type,
        "content": content,
        "tool_call_id": tool_call_id,
        "tool_function_name": tool_function_name,
        "tool_arguments_delta": tool_arguments_delta,  # Use delta key
        # 'tool_arguments_complete' is no longer yielded in this event type
    }


class Agent:
    """Handles interaction with the OpenAI API, including tool calls and error handling."""

    def __init__(self, config: AppConfig):
        self.config = config
        # Ensure API key is fetched correctly, considering potential None
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # Handle missing API key scenario, perhaps raise an error or log warning
            print("Warning: OpenAI API key is not configured.", file=sys.stderr)
            # Depending on desired behavior, you might raise an exception here
            # raise ValueError("OpenAI API key is required.")

        self.async_client = AsyncOpenAI(
            api_key=api_key,  # Pass the resolved API key
            base_url=config.get("base_url") or os.environ.get("OPENAI_BASE_URL"),
            timeout=config.get("timeout") or float(os.environ.get("OPENAI_TIMEOUT_MS", 60000)) / 1000.0,
            max_retries=0,  # Disable automatic retries in the client, we handle it manually
        )
        self.history: list[ChatCompletionMessageParam] = []
        self.available_tools: list[ChatCompletionToolParam] = AVAILABLE_TOOL_DEFS
        self._cancelled: bool = False
        self._current_stream = None
        self.session_id: str | None = None
        self.pending_tool_calls: list[ChatCompletionMessageToolCall] | None = None
        self.last_response_id: str | None = None  # Track the last response ID

    def cancel(self):
        """Set the cancellation flag to interrupt the current Agent processing flow."""
        print("[Agent] Received cancellation request.", file=sys.stderr)
        self._cancelled = True
        self._current_stream = None  # Clear reference

    def clear_history(self):
        """Clears the in-memory conversation history for the agent."""
        self.history = []
        self.pending_tool_calls = None
        self.last_response_id = None  # Clear last response ID too
        print("[Agent] In-memory conversation history cleared.", file=sys.stderr)

    def _prepare_messages(self) -> list[ChatCompletionMessageParam]:
        """Prepares the message history for the API call, including system prompt."""
        api_messages: list[ChatCompletionMessageParam] = []
        system_prompt = self.config.get("instructions")
        if system_prompt:
            # Ensure only one system message at the beginning
            api_messages.append({"role": "system", "content": system_prompt})

        # Add history, filtering out any previous system messages if necessary
        for msg in self.history:
            if isinstance(msg, dict) and "role" in msg:
                api_messages.append(msg)
            else:
                print(f"Warning: Skipping invalid message format in history: {type(msg)}", file=sys.stderr)

        # Filter out potentially problematic None content in tool messages right before sending
        cleaned_messages = []
        for msg in api_messages:
            if msg.get("role") == "tool":
                # Tool message content MUST be a string. Ensure it is.
                content = msg.get("content")
                if content is None:
                    print(f"Warning: Filtering out tool message with None content: {msg}", file=sys.stderr)
                elif not isinstance(content, str):
                    print(f"Warning: Converting non-string tool content to string: {msg}", file=sys.stderr)
                    cleaned_messages.append({**msg, "content": str(content)})
                else:
                    cleaned_messages.append(msg)
            else:
                cleaned_messages.append(msg)

        # Debug: Print messages being sent
        # print("DEBUG: Sending messages to API:", file=sys.stderr)
        # pprint.pprint(cleaned_messages, stream=sys.stderr, indent=2)

        return cleaned_messages

    # Internal implementation only, called by the CLI after approval.
    def _execute_tool_implementation(
        self,
        tool_call: ChatCompletionMessageToolCall,
        is_sandboxed: bool = False,
        allowed_write_paths: list[Path] | None = None,
    ) -> str:
        """
        Internal implementation to execute a tool call.
        This should be called by the CLI/controller after approval.
        Passes sandboxing context if executing 'execute_command'.
        """
        if self._cancelled:
            print(f"[Agent] Tool execution cancelled: {tool_call.function.name}", file=sys.stderr)
            return "Error: Tool execution cancelled by user."

        function_name = tool_call.function.name
        try:
            if not isinstance(tool_call.function.arguments, str):
                # Attempt to convert if it's a dict (might happen due to internal state issues)
                if isinstance(tool_call.function.arguments, dict):
                    args_str = json.dumps(tool_call.function.arguments)
                else:
                    return f"Error: Invalid argument type for tool {function_name}. Expected string, got {type(tool_call.function.arguments).__name__}"
            else:
                args_str = tool_call.function.arguments

            arguments = json.loads(args_str) if args_str else {}
            if not isinstance(arguments, dict):
                raise json.JSONDecodeError("Arguments are not a dictionary", tool_call.function.arguments or "{}", 0)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON arguments for {function_name}: {e}", file=sys.stderr)
            print(f"Raw arguments: {tool_call.function.arguments}", file=sys.stderr)
            return f"Error: Invalid JSON arguments received for tool {function_name}: {e.msg}"  # More specific error
        except Exception as e:  # Catch other potential errors during parsing/loading
            print(f"Unexpected error preparing arguments for {function_name}: {e}", file=sys.stderr)
            return f"Error: Could not prepare arguments for tool {function_name}: {e}"

        print(f"[Agent] Executing approved tool: {function_name}")  # Log approved execution

        try:
            if function_name in TOOL_REGISTRY:
                tool_func = TOOL_REGISTRY[function_name]
                sig = inspect.signature(tool_func)
                valid_params = set(sig.parameters.keys())

                call_args = {}
                for k, v in arguments.items():
                    if k in valid_params:
                        call_args[k] = v

                # --- Pass sandbox and write paths specifically to execute_command ---
                if function_name == "execute_command":
                    if "is_sandboxed" in valid_params:
                        call_args["is_sandboxed"] = is_sandboxed
                    if "allowed_write_paths" in valid_params:
                        call_args["allowed_write_paths"] = allowed_write_paths
                    if "full_stdout" in valid_params:
                        # Get the flag from config, default if not set
                        call_args["full_stdout"] = self.config.get("full_stdout", DEFAULT_FULL_STDOUT)

                    if is_sandboxed:
                        print(
                            f"  [Agent] Passing sandbox context: is_sandboxed={is_sandboxed}, allowed_paths={allowed_write_paths}"
                        )
                # --- End sandbox/write path passing ---

                print(f"  [Agent] Calling {function_name} with args: {call_args}")
                return tool_func(**call_args)
            else:
                return f"Error: Unknown or not implemented tool function '{function_name}'"
        except Exception as e:
            print(f"Error during tool '{function_name}' execution: {e}", file=sys.stderr)
            formatted_traceback = traceback.format_exc()
            print(f"Traceback:\n{formatted_traceback}", file=sys.stderr)
            return f"Error during execution of tool '{function_name}': {e}\n\nTraceback:\n{formatted_traceback}"

    async def process_turn_stream(
        self, prompt: str | None = None, image_paths: list[str] | None = None
    ) -> AsyncIterator[StreamEvent]:
        """
        Processes one turn of interaction with streaming.
        Yields StreamEvent objects for text deltas, tool calls, and errors.
        """
        self._cancelled = False
        self._current_stream = None
        self.pending_tool_calls = None

        if prompt:
            user_content: str | Sequence[ChatCompletionContentPartParam]
            if image_paths:
                print("Warning: Image input processing is not fully implemented yet.", file=sys.stderr)
                text_part: ChatCompletionContentPartTextParam = {"type": "text", "text": prompt}
                user_content = [text_part]
            else:
                user_content = prompt
            user_message: ChatCompletionUserMessageParam = {"role": "user", "content": user_content}
            self.history.append(user_message)
        elif not self.history:
            yield create_stream_event(type="error", content="Error: No history or prompt.")
            return

        if self._cancelled:
            yield create_stream_event(type="cancelled", content="Cancelled before API call.")
            return

        service_tier = NOT_GIVEN
        if self.config.get("flex_mode", False):
            # Ensure the model supports flex mode (optional check)
            allowed_flex_models = {"o3", "o4-mini"}
            if self.config["model"] in allowed_flex_models:
                service_tier = "flex"  # Add flex tier
                print("[Agent] Using flex service tier.", file=sys.stderr)
            else:
                print(
                    f"[Agent] Warning: flex_mode enabled but model '{self.config['model']}' may not support it.",
                    file=sys.stderr,
                )

        api_messages = self._prepare_messages()
        # print("DEBUG: Sending messages to API:", file=sys.stderr)
        # pprint.pprint(api_messages, stream=sys.stderr, indent=2)
        print(f"DEBUG: api_messages: {api_messages}", file=sys.stderr)

        current_retry_delay = INITIAL_RETRY_DELAY_SECONDS
        last_error = None
        for attempt in range(MAX_RETRIES):
            if self._cancelled:
                yield create_stream_event(type="cancelled", content="Cancelled before API retry.")
                return

            try:
                print(f"[Agent] Attempt {attempt + 1}/{MAX_RETRIES} sending request...", file=sys.stderr)
                stream = await self.async_client.chat.completions.create(
                    model=self.config["model"],
                    messages=api_messages,
                    tools=self.available_tools,
                    tool_choice="auto",
                    stream=True,
                    service_tier=service_tier,
                    # --- Added experimental feature ---
                    # stream_options={"include_usage": True}, # Uncomment if needed later
                )
                self._current_stream = stream
                print("[Agent] Stream connection established.", file=sys.stderr)

                assistant_message_accumulator: dict[str, Any] = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [],
                }
                started_tool_call_indices: set[int] = set()
                tool_arguments_complete: dict[int, str] = {}
                next_tool_index = 0  # Counter for assigning index if missing

                async for chunk in stream:
                    if self._cancelled:
                        yield create_stream_event(type="cancelled", content="Cancelled during stream.")
                        # await stream.close() # If supported
                        return

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    if delta:
                        if delta.content:
                            text_delta = delta.content
                            if assistant_message_accumulator["content"] is None:
                                assistant_message_accumulator["content"] = ""
                            assistant_message_accumulator["content"] += text_delta
                            yield create_stream_event(type="text_delta", content=text_delta)

                        if delta.tool_calls:
                            if not isinstance(assistant_message_accumulator.get("tool_calls"), list):
                                assistant_message_accumulator["tool_calls"] = []
                            tool_calls_list = assistant_message_accumulator["tool_calls"]

                            for tool_call_chunk in delta.tool_calls:
                                # --- Handle missing index ---
                                index: int
                                if tool_call_chunk.index is None:
                                    # Assign the next available index
                                    index = next_tool_index
                                    next_tool_index += 1
                                    print(
                                        f"Warning: Tool call chunk missing index, assigned index {index}",
                                        file=sys.stderr,
                                    )
                                else:
                                    index = tool_call_chunk.index
                                    # Update next_tool_index if we receive an explicit index
                                    next_tool_index = max(next_tool_index, index + 1)
                                # ------------------------------

                                # Ensure list is long enough
                                while len(tool_calls_list) <= index:
                                    tool_calls_list.append(
                                        {"id": None, "type": "function", "function": {"name": None, "arguments": ""}}
                                    )
                                current_call_entry = tool_calls_list[index]

                                # --- Handle missing ID ---
                                if tool_call_chunk.id:
                                    current_call_entry["id"] = tool_call_chunk.id
                                elif (
                                    current_call_entry["id"] is None and tool_call_chunk.function
                                ):  # Generate only if not already assigned
                                    # Generate a temporary ID if missing
                                    temp_id = f"tool_call_id_{index}-{uuid.uuid4()}"
                                    current_call_entry["id"] = temp_id
                                    print(
                                        f"Warning: Tool call chunk missing ID at index {index}, generated temporary ID: {temp_id}",
                                        file=sys.stderr,
                                    )
                                # -------------------------

                                # Update Name if present
                                if tool_call_chunk.function and tool_call_chunk.function.name:
                                    current_call_entry["function"]["name"] = tool_call_chunk.function.name

                                # Yield start event only once when ID and Name are first known
                                current_id = current_call_entry.get("id")
                                current_name = current_call_entry.get("function", {}).get("name")
                                if index not in started_tool_call_indices and current_id and current_name:
                                    started_tool_call_indices.add(index)
                                    yield create_stream_event(
                                        type="tool_call_start",
                                        tool_call_id=current_id,
                                        tool_function_name=current_name,
                                    )

                                # Handle arguments
                                if tool_call_chunk.function and tool_call_chunk.function.arguments is not None:  # Check for None
                                    args_chunk = tool_call_chunk.function.arguments
                                    # Accumulate/store complete arguments
                                    tool_arguments_complete[index] = tool_arguments_complete.get(index, "") + args_chunk
                                    # Update the main accumulator immediately
                                    current_call_entry["function"]["arguments"] = tool_arguments_complete[index]

                                    if current_id:  # Yield delta only if we have an ID
                                        yield create_stream_event(
                                            type="tool_call_delta",
                                            tool_call_id=current_id,
                                            tool_arguments_delta=args_chunk,
                                        )

                    # Check finish_reason *after* processing delta
                    if finish_reason:
                        print(f"[Agent] Stream chunk finished with reason: {finish_reason}", file=sys.stderr)
                        # <<< Break the loop on ANY finish reason >>>
                        break

                # <<< AFTER the async for loop (stream finished or break) >>>
                if self._cancelled:
                    yield create_stream_event(type="cancelled", content="Cancelled after stream.")
                    return

                # <<< CONSOLIDATED FINALIZATION of Tool Calls >>>
                final_tool_calls_for_history: list[ChatCompletionMessageToolCall] = []
                if isinstance(assistant_message_accumulator.get("tool_calls"), list):
                    for index, tool_call_data in enumerate(assistant_message_accumulator["tool_calls"]):
                        # Use assigned ID and check for name
                        final_id = tool_call_data.get("id")
                        final_name = tool_call_data.get("function", {}).get("name")

                        if final_id and final_name:
                            # Use the potentially complete arguments buffer
                            final_args = tool_arguments_complete.get(index, tool_call_data["function"].get("arguments", ""))
                            # Ensure final args are stored in the accumulator entry
                            tool_call_data["function"]["arguments"] = final_args
                            if not isinstance(final_args, str):
                                final_args = str(final_args)  # Ensure string

                            try:
                                final_call = ChatCompletionMessageToolCall(
                                    id=str(final_id),
                                    function=OpenAIFunction(name=str(final_name), arguments=final_args),
                                    type="function",
                                )
                                # Yield end event if it was started
                                if index in started_tool_call_indices:
                                    yield create_stream_event(type="tool_call_end", tool_call_id=final_call.id)
                                final_tool_calls_for_history.append(final_call)
                            except Exception as e:
                                print(f"Error creating final tool call object post-loop: {e}", file=sys.stderr)
                        else:
                            print(
                                f"Warning: Skipping incomplete tool call at index {index} in final assembly post-loop: {tool_call_data}",
                                file=sys.stderr,
                            )

                # <<< Assemble final message for history >>>
                final_assistant_msg_dict: dict[str, Any] = {"role": "assistant"}
                content = assistant_message_accumulator.get("content")
                if content:
                    final_assistant_msg_dict["content"] = content
                if final_tool_calls_for_history:
                    final_assistant_msg_dict["tool_calls"] = final_tool_calls_for_history

                # <<< Add to history and set pending calls >>>
                if "content" in final_assistant_msg_dict or "tool_calls" in final_assistant_msg_dict:
                    self.history.append(cast(ChatCompletionMessageParam, final_assistant_msg_dict))
                    # Set pending calls based on the *finalized* list from this turn
                    self.pending_tool_calls = final_tool_calls_for_history if final_tool_calls_for_history else None
                    print(
                        f"[Agent] Final message added. Pending tools: {len(self.pending_tool_calls or [])}",
                        file=sys.stderr,
                    )
                    # Capture last response ID if available (might need specific event handling)
                    # Example: self.last_response_id = get_response_id_from_stream_end(stream)
                else:
                    # No actual content or tool calls produced by the assistant
                    self.pending_tool_calls = None  # Ensure pending calls are cleared
                    print("[Agent] Assistant produced no text or tool calls.", file=sys.stderr)

                yield create_stream_event(type="response_end")
                return  # Success, exit retry loop

            # --- Error Handling within Retry Loop ---
            except (
                APITimeoutError,
                APIConnectionError,
                RateLimitError,
                APIStatusError,
                APIError,
                BadRequestError,
            ) as e:
                last_error = e
                error_msg = f"{type(e).__name__}: {e}"
                print(f"[Agent] Attempt {attempt + 1} failed: {error_msg}", file=sys.stderr)
                status_code = getattr(e, "status_code", None)
                should_retry = (
                    isinstance(e, APITimeoutError | APIConnectionError)
                    or isinstance(e, RateLimitError)
                    or (isinstance(e, APIStatusError) and status_code and status_code >= 500)
                ) and attempt < MAX_RETRIES - 1
                if isinstance(e, BadRequestError) and status_code == 400:
                    error_body = getattr(e, "body", {})
                    error_detail = error_body.get("error", {}).get("message", "") if isinstance(error_body, dict) else str(e)
                    if "context_length_exceeded" in error_detail or "maximum context length" in error_detail:
                        yield create_stream_event(
                            type="error",
                            content="Error: The conversation history and prompt exceed the model's maximum context length. Please clear the history (/clear) or start a new session.",
                        )
                        return
                    else:
                        print("[Agent] Non-retryable 400 Bad Request error.", file=sys.stderr)
                if should_retry:
                    print(f"[Agent] Retrying in {current_retry_delay:.2f} seconds...", file=sys.stderr)
                    await asyncio.sleep(current_retry_delay)
                    current_retry_delay = min(current_retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
                    continue
                else:
                    friendly_error = error_msg
                    if isinstance(e, APIStatusError):
                        try:
                            error_body = e.response.json()
                            message = (
                                error_body.get("error", {}).get("message", e.response.text)
                                if isinstance(error_body, dict)
                                else e.response.text
                            )
                            friendly_error = f"API Error (Status {e.status_code}): {message}"
                        except Exception:
                            pass
                    elif isinstance(e, RateLimitError):
                        friendly_error = f"API Rate Limit Error: {e}"
                    elif isinstance(e, BadRequestError):
                        friendly_error = f"API Bad Request Error: {e}"
                    yield create_stream_event(type="error", content=f"Error: {friendly_error}")
                    return
            except Exception as e:
                last_error = e
                print(f"[Agent] Attempt {attempt + 1} failed: An unexpected error occurred: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if attempt == MAX_RETRIES - 1:
                    yield create_stream_event(type="error", content=f"Error: Max retries reached. Unexpected error: {e}")
                    return
                if attempt < 1:
                    print(f"[Agent] Retrying unexpected error in {current_retry_delay:.2f} seconds...", file=sys.stderr)
                    await asyncio.sleep(current_retry_delay)
                    current_retry_delay = min(current_retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
                    continue
                else:
                    yield create_stream_event(type="error", content=f"Error: Failed after unexpected error: {e}")
                    return

        # If loop finishes without returning (all retries failed)
        yield create_stream_event(
            type="error", content=f"Error: Agent failed after {MAX_RETRIES} retries. Last error: {last_error}"
        )
        self._current_stream = None

    async def continue_with_tool_results_stream(
        self, tool_results: list[ChatCompletionToolMessageParam]
    ) -> AsyncIterator[StreamEvent]:
        """
        Adds tool results to history and yields subsequent stream events from the API.
        """
        self._cancelled = False  # Reset cancel flag for this continuation
        self.pending_tool_calls = None

        if self._cancelled:
            yield create_stream_event(type="cancelled", content="Cancelled before processing results.")
            return

        if not tool_results:
            yield create_stream_event(type="error", content="Error: No tool results provided.")
            return

        # Add results to history
        for result in tool_results:
            if (
                isinstance(result, dict)
                and result.get("role") == "tool"
                and "tool_call_id" in result
                and "content" in result
                # Tool content MUST be a string for OpenAI API
                and isinstance(result.get("content"), str)
            ):
                self.history.append(result)
            else:
                content_val = result.get("content") if isinstance(result, dict) else "N/A"
                content_type = type(content_val).__name__
                print(
                    f"Warning: Skipping invalid tool result format or non-string content (type: {content_type}): {result}",
                    file=sys.stderr,
                )

        # Call process_turn_stream without prompt to continue
        async for event in self.process_turn_stream():
            yield event
