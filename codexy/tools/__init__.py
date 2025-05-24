"""Implementations for the tools callable by the agent."""

from .apply_diff_tool import APPLY_DIFF_TOOL_DEF, apply_diff_tool
from .apply_patch_tool import APPLY_PATCH_TOOL_DEF, apply_patch
from .execute_command_tool import EXECUTE_COMMAND_TOOL_DEF, execute_command_tool
from .file_tools import (
    LIST_FILES_TOOL_DEF,
    READ_FILE_TOOL_DEF,
    WRITE_TO_FILE_TOOL_DEF,
    list_files_tool,
    read_file_tool,
    write_to_file_tool,
)

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
