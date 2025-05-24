"""Utilities for estimating token usage."""

import json
import math
from collections.abc import Sequence

from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam, ChatCompletionMessageToolCall

# Simple approximation: 4 characters per token on average
CHARS_PER_TOKEN_ESTIMATE = 4


def _count_chars_in_content(content: str | Sequence[ChatCompletionContentPartParam] | None) -> int:
    """Counts characters in message content, handling different formats."""
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        count = 0
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text" or part_type == "input_text" or part_type == "output_text":
                    text_part = part.get("text")
                    if isinstance(text_part, str):
                        count += len(text_part)
                elif part_type == "input_file":  # As in codex-cli
                    filename_part = part.get("filename")
                    if isinstance(filename_part, str):
                        count += len(filename_part)
                # Ignore image URLs for token count approximation
                # elif part_type == "image_url":
                #     pass
                # Handle refusal type if present in history items (like in TS version)
                elif part_type == "refusal":
                    refusal_part = part.get("refusal")
                    if isinstance(refusal_part, str):
                        count += len(refusal_part)
        return count
    return 0


def _count_chars_in_tool_calls(tool_calls: list[ChatCompletionMessageToolCall] | None) -> int:
    """Counts characters in tool call names and arguments."""
    count = 0
    if tool_calls and isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                function_data = tool_call.get("function")
                if isinstance(function_data, dict):
                    count += len(function_data.get("name", ""))
                    # Arguments might be stored differently, handle safely
                    args = function_data.get("arguments", "")
                    if isinstance(args, str):
                        count += len(args)
                    elif isinstance(args, dict):  # Handle if arguments are dict
                        try:
                            count += len(json.dumps(args))
                        except TypeError:
                            count += len(str(args))  # Fallback
    return count


def approximate_tokens_used(history: list[ChatCompletionMessageParam]) -> int:
    """
    Roughly estimates the number of tokens used by the message history.
    Excludes system messages from the count, includes tool calls and outputs.
    """
    char_count = 0
    for message in history:
        # Ensure message is a dictionary before proceeding
        if not isinstance(message, dict):
            continue

        role = message.get("role")

        # Only count user and assistant messages for context usage approximation
        if role == "user" or role == "assistant":
            message_content = message.get("content", "")
            if isinstance(message_content, str):
                char_count += _count_chars_in_content(message_content)
            elif isinstance(message_content, list):
                for part in message_content:
                    if isinstance(part, dict):
                        part_type = part.get("type")
                        if part_type == "text":
                            char_count += _count_chars_in_content(part.get("text", ""))
                        # Add handling for other part types if needed
            # Add contribution from tool calls if present
            tool_calls = message.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        function_data = tool_call.get("function")
                        if isinstance(function_data, dict):
                            char_count += len(function_data.get("name", ""))
                            char_count += len(function_data.get("arguments", ""))
        elif role == "tool":
            # Also count tool responses (content field)
            tool_content = message.get("content")
            if isinstance(tool_content, str):
                char_count += len(tool_content)
            elif isinstance(tool_content, list):
                for part in tool_content:
                    if isinstance(part, dict):
                        part_type = part.get("type")
                        if part_type == "text":
                            char_count += _count_chars_in_content(part.get("text", ""))

    # Estimate tokens based on character count
    return math.ceil(char_count / CHARS_PER_TOKEN_ESTIMATE)
