# -*- coding: utf-8 -*-

"""Implementations for the tools callable by the agent."""

from .file_tools import (
    read_file_tool,
    write_to_file_tool,
    list_files_tool,
    READ_FILE_TOOL_DEF,
    WRITE_TO_FILE_TOOL_DEF,
    LIST_FILES_TOOL_DEF,
)
from .apply_patch_tool import apply_patch, APPLY_PATCH_TOOL_DEF
from .apply_diff_tool import apply_diff_tool, APPLY_DIFF_TOOL_DEF
from .execute_command_tool import execute_command_tool, EXECUTE_COMMAND_TOOL_DEF


# --- Tool Registration ---
# Map tool names (used by the LLM) to their Python functions
TOOL_REGISTRY = {
    "execute_command": execute_command_tool,
    "read_file": read_file_tool,
    "write_to_file": write_to_file_tool,
    "list_files": list_files_tool,
    "apply_diff": apply_diff_tool,
    "apply_patch": apply_patch,
}

# Combine all tool definitions
AVAILABLE_TOOL_DEFS = [
    EXECUTE_COMMAND_TOOL_DEF,
    READ_FILE_TOOL_DEF,
    WRITE_TO_FILE_TOOL_DEF,
    LIST_FILES_TOOL_DEF,
    APPLY_DIFF_TOOL_DEF,
    APPLY_PATCH_TOOL_DEF,
]

__all__ = [
    "read_file_tool",
    "write_to_file_tool",
    "list_files_tool",
    "apply_patch",
    "apply_diff_tool",
    "execute_command_tool",
    "AVAILABLE_TOOL_DEFS",
    "TOOL_REGISTRY",
]
