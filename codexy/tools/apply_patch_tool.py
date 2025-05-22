# -*- coding: utf-8 -*-

"""
Tool for applying patches in a specific text format.
Based on the logic from codex-cli/src/utils/agent/apply-patch.ts
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Union, cast, Tuple
from dataclasses import dataclass, field

from openai.types.chat import ChatCompletionToolParam

from ..exceptions import ToolError


PROJECT_ROOT = Path.cwd()

# --- Constants for Patch Format ---
PATCH_PREFIX = "*** Begin Patch\n"
PATCH_SUFFIX = "\n*** End Patch"
ADD_FILE_PREFIX = "*** Add File: "
DELETE_FILE_PREFIX = "*** Delete File: "
UPDATE_FILE_PREFIX = "*** Update File: "
MOVE_FILE_TO_PREFIX = "*** Move to: "
END_OF_FILE_PREFIX = "*** End of File"
HUNK_ADD_LINE_PREFIX = "+"
HUNK_DEL_LINE_PREFIX = "-"
HUNK_CONTEXT_LINE_PREFIX = " "
HUNK_HEADER_PREFIX = "@@"


# --- Data Structures for Parsed Operations ---
@dataclass
class AddOp:
    type: str = field(default="add", init=False)
    path: str
    content: str


@dataclass
class DeleteOp:
    type: str = field(default="delete", init=False)
    path: str


@dataclass
class UpdateOp:
    type: str = field(default="update", init=False)
    path: str
    diff_hunk: str  # Store the raw diff hunk lines as a single string
    move_to: Optional[str] = None


ParsedOperation = Union[AddOp, DeleteOp, UpdateOp]

# --- Core Parsing Logic ---


def _parse_patch_text(patch_text: str) -> List[ParsedOperation]:
    """
    Parses the custom patch format text into a list of structured operations.
    Raises ToolError on parsing issues.
    """
    if not patch_text.startswith(PATCH_PREFIX):
        raise ToolError(f"Invalid patch format: Must start with '{PATCH_PREFIX.strip()}'")
    # Allow flexibility with trailing whitespace in suffix
    cleaned_patch_text = patch_text.rstrip()
    if not cleaned_patch_text.endswith(PATCH_SUFFIX.strip()):
        raise ToolError(f"Invalid patch format: Must end with '{PATCH_SUFFIX.strip()}'")

    # Adjust slicing to account for potential trailing whitespace before suffix
    patch_body = patch_text[len(PATCH_PREFIX) : patch_text.rfind(PATCH_SUFFIX.strip())].strip("\n")

    lines = patch_body.splitlines()

    operations: List[ParsedOperation] = []
    current_op: Optional[ParsedOperation] = None
    line_buffer: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        # is_command = False

        if line.startswith(ADD_FILE_PREFIX):
            # is_command = True
            path = line[len(ADD_FILE_PREFIX) :].strip()
            current_op = AddOp(path=path, content="")
            operations.append(current_op)
            line_buffer = []
        elif line.startswith(DELETE_FILE_PREFIX):
            # is_command = True
            path = line[len(DELETE_FILE_PREFIX) :].strip()
            current_op = DeleteOp(path=path)
            operations.append(current_op)
            line_buffer = []
        elif line.startswith(UPDATE_FILE_PREFIX):
            # is_command = True
            path = line[len(UPDATE_FILE_PREFIX) :].strip()
            current_op = UpdateOp(path=path, diff_hunk="")
            operations.append(current_op)
            line_buffer = []
        elif line.startswith(MOVE_FILE_TO_PREFIX) and isinstance(current_op, UpdateOp):
            current_op.move_to = line[len(MOVE_FILE_TO_PREFIX) :].strip()
            # Move modifies the current op, doesn't reset buffer or op
        elif line.strip() == END_OF_FILE_PREFIX.strip():
            if isinstance(current_op, (AddOp, UpdateOp)):
                if isinstance(current_op, AddOp):
                    current_op.content = "\n".join(line[1:] for line in line_buffer if line.startswith(HUNK_ADD_LINE_PREFIX))
                elif isinstance(current_op, UpdateOp):
                    current_op.diff_hunk = "\n".join(line_buffer)
                line_buffer = []
            current_op = None  # Prepare for next command block
            i += 1
            continue  # Move to next line after processing marker
        elif current_op is not None:
            # Append line to the buffer for the current Add or Update operation
            if isinstance(current_op, (AddOp, UpdateOp)):
                line_buffer.append(line)
            # For DeleteOp, ignore lines until next command or EOF marker
        elif line.strip():  # If not a command, not part of an op, and not empty
            raise ToolError(f"Unexpected line outside operation block: '{line}' at line index {i}")

        i += 1  # Move to the next line

    # Final check in case patch ends without explicit EOF marker before suffix
    if line_buffer and isinstance(current_op, (AddOp, UpdateOp)):
        print(f"Warning: Patch for '{current_op.path}' might be missing '{END_OF_FILE_PREFIX.strip()}' before suffix.")
        if isinstance(current_op, AddOp):
            current_op.content = "\n".join(line[1:] for line in line_buffer if line.startswith(HUNK_ADD_LINE_PREFIX))
        elif isinstance(current_op, UpdateOp):
            current_op.diff_hunk = "\n".join(line_buffer)

    return operations


# --- Diff Application Logic ---


def _parse_hunk_header(line: str) -> Optional[Tuple[int, int]]:
    """Parses '@@ -old_start,old_count +new_start,new_count @@'"""
    match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if match:
        old_start = int(match.group(1))
        # old_count = int(match.group(2) or 1) # Not strictly needed for application
        new_start = int(match.group(3))
        # new_count = int(match.group(4) or 1) # Not strictly needed for application
        # Return 0-based index for original file
        return (old_start - 1, new_start - 1)
    return None


def _apply_diff_hunk(original_content: str, diff_hunk: str) -> str:
    """
    Applies a standard unified diff hunk to the original content.
    This version correctly handles context lines.
    """
    orig_lines = original_content.splitlines(keepends=True)
    hunk_lines = diff_hunk.splitlines(keepends=True)
    result_lines: List[str] = []
    orig_idx = 0
    hunk_idx = 0

    while hunk_idx < len(hunk_lines):
        hunk_line = hunk_lines[hunk_idx]

        if hunk_line.startswith(HUNK_HEADER_PREFIX):
            header_info = _parse_hunk_header(hunk_line)
            if header_info:
                expected_orig_start_idx = header_info[0]
                # Add lines from original up to the start index defined by the hunk header
                if expected_orig_start_idx > orig_idx:
                    result_lines.extend(orig_lines[orig_idx:expected_orig_start_idx])
                    orig_idx = expected_orig_start_idx
            else:
                raise ToolError(f"Invalid hunk header format: '{hunk_line.strip()}'")
            hunk_idx += 1
        elif hunk_line.startswith(HUNK_ADD_LINE_PREFIX):
            result_lines.append(hunk_line[1:])
            hunk_idx += 1
        elif hunk_line.startswith(HUNK_DEL_LINE_PREFIX):
            if orig_idx >= len(orig_lines):
                raise ToolError(f"Patch error: Trying to delete line {orig_idx + 1} but original only has {len(orig_lines)} lines. Hunk line: '{hunk_line.strip()}'")
            # Verify context (optional but recommended for robustness)
            expected_deleted = hunk_line[1:]
            actual_original = orig_lines[orig_idx]
            # Simple comparison (might need more sophisticated whitespace handling)
            if actual_original.rstrip("\r\n") != expected_deleted.rstrip("\r\n"):
                print(f"Warning: Mismatch deleting line {orig_idx + 1}. Expected content differs from actual.")
                # Depending on strictness, could raise ToolError here
                # raise ToolError(f"Patch mismatch: Deleting line {orig_idx + 1}, content differs. Expected:\n'{expected_deleted.strip()}'\nActual:\n'{actual_original.strip()}'")
            orig_idx += 1  # Consume the line from original
            hunk_idx += 1
        elif hunk_line.startswith(HUNK_CONTEXT_LINE_PREFIX):
            if orig_idx >= len(orig_lines):
                raise ToolError(f"Patch error: Trying to match context line {orig_idx + 1} but original only has {len(orig_lines)} lines. Hunk line: '{hunk_line.strip()}'")
            # Verify context
            expected_context = hunk_line[1:]
            actual_original = orig_lines[orig_idx]
            # Simple comparison
            if actual_original.rstrip("\r\n") != expected_context.rstrip("\r\n"):
                raise ToolError(f"Patch mismatch: Context line {orig_idx + 1} differs. Expected:\n'{expected_context.strip()}'\nActual:\n'{actual_original.strip()}'")
            result_lines.append(actual_original)  # Add the original line
            orig_idx += 1
            hunk_idx += 1
        elif not hunk_line.strip() and hunk_idx == len(hunk_lines) - 1:
            # Ignore potential empty last line often added by splitlines
            hunk_idx += 1
        else:
            raise ToolError(f"Invalid line prefix or unexpected content in diff hunk: '{hunk_line.strip()}' at hunk line index {hunk_idx}")

    # Append any remaining lines from the original file
    result_lines.extend(orig_lines[orig_idx:])

    return "".join(result_lines)


# --- Filesystem Interaction and Safety ---


def _resolve_and_check_path(relative_path: str, base_dir: Path = PROJECT_ROOT) -> Path:
    """Resolves a relative path against the base directory and performs safety checks."""
    if not relative_path:
        raise ToolError("Path cannot be empty.")

    # Disallow absolute paths provided by the LLM
    if Path(relative_path).is_absolute():  # Use Pathlib's is_absolute
        raise ToolError(f"Absolute paths are not allowed: '{relative_path}'")

    # Join with project root and resolve symlinks etc.
    # Important: Resolve *after* joining with base_dir
    target_path = (base_dir / relative_path).resolve()

    # Check if the resolved path is still within the project root directory
    if not str(target_path).startswith(str(base_dir.resolve()) + os.sep) and target_path != base_dir.resolve():
        raise ToolError(f"Attempted file access outside of project root: '{relative_path}' resolved to '{target_path}'")

    return target_path


# --- Main Tool Function ---


def apply_patch(patch_text: str) -> str:
    """
    Parses a patch string in the custom format and applies the changes
    to the filesystem relative to the project root.
    """
    if not patch_text or not isinstance(patch_text, str):
        return "Error: patch_text argument is required and must be a string."

    try:
        operations = _parse_patch_text(patch_text)
    except ToolError as e:
        return f"Error parsing patch: {e}"
    except Exception as e:
        return f"Unexpected error during patch parsing: {e}"

    if not operations:
        return "Patch parsed successfully, but contained no operations."

    results = []
    errors = []

    for op in operations:
        try:
            target_path = _resolve_and_check_path(op.path)

            if op.type == "add":
                op = cast(AddOp, op)
                # Check if file already exists before adding
                if target_path.exists():
                    raise ToolError(f"Cannot add file, path already exists: '{op.path}'")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(op.content, encoding="utf-8")
                results.append(f"Created file: {op.path}")
            elif op.type == "delete":
                op = cast(DeleteOp, op)
                if target_path.is_file():
                    target_path.unlink()
                    results.append(f"Deleted file: {op.path}")
                elif target_path.is_dir():
                    errors.append(f"Skipped delete: Path '{op.path}' is a directory, not a file.")
                else:
                    results.append(f"Info: File to delete not found (already deleted?): {op.path}")
            elif op.type == "update":
                op = cast(UpdateOp, op)
                if not target_path.is_file():
                    raise ToolError(f"File to update not found: '{op.path}'")

                original_content = target_path.read_text(encoding="utf-8")
                # Use the corrected diff application logic
                new_content = _apply_diff_hunk(original_content, op.diff_hunk)

                if op.move_to:
                    new_target_path = _resolve_and_check_path(op.move_to)
                    # Check if the destination exists and is not the same file
                    if new_target_path.exists() and not new_target_path.samefile(target_path):
                        raise ToolError(f"Cannot move file, destination already exists: '{op.move_to}'")
                    new_target_path.parent.mkdir(parents=True, exist_ok=True)
                    new_target_path.write_text(new_content, encoding="utf-8")
                    target_path.unlink()  # Delete the original file after successful write+move
                    results.append(f"Updated and moved '{op.path}' to '{op.move_to}'")
                else:
                    target_path.write_text(new_content, encoding="utf-8")
                    results.append(f"Updated file: {op.path}")

        except FileNotFoundError:
            errors.append(f"Error processing '{op.path}': File not found (might be an issue with resolving).")
        except IsADirectoryError:
            # This might happen if trying to read/write a dir as a file
            errors.append(f"Error processing '{op.path}': Path is a directory, expected a file.")
        except PermissionError:
            errors.append(f"Error processing '{op.path}': Permission denied.")
        except ToolError as e:
            errors.append(f"Error processing '{op.path}': {e}")
        except Exception as e:
            # Catch unexpected errors during file operations
            errors.append(f"Unexpected error processing '{op.path}': {type(e).__name__}: {e}")

    # --- Format Final Result ---
    summary = "\n".join(results)
    if errors:
        error_summary = "\n".join(errors)
        final_message = f"Patch applied with errors:\n--- Successes ---\n{summary if summary else 'None'}\n--- Errors ---\n{error_summary}"
        return final_message
    else:
        return f"Patch applied successfully:\n{summary}"


# --- Tool Definition for Agent ---
APPLY_PATCH_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "apply_patch",
        "description": "Apply modifications to files using a specific text-based patch format containing standard diff hunks. Handles creating, updating, deleting, and moving files based on the patch instructions.",
        "parameters": {
            "type": "object",
            "properties": {
                "patch_text": {
                    "type": "string",
                    "description": f"""The patch content, adhering to a specific format:
1.  Must start with '{PATCH_PREFIX.strip()}'.
2.  Must end with '{PATCH_SUFFIX.strip()}'.
3.  Operations are defined by commands:
    - '{ADD_FILE_PREFIX}<path>': Adds a new file. Content lines follow, each prefixed by '{HUNK_ADD_LINE_PREFIX}'.
    - '{DELETE_FILE_PREFIX}<path>': Deletes a file. No content follows this command for the operation itself.
    - '{UPDATE_FILE_PREFIX}<path>': Updates an existing file. May be followed by '{MOVE_FILE_TO_PREFIX}<new_path>'. The changes are described in a diff hunk.
4.  Diff Hunks for Updates:
    - Start with a header: '{HUNK_HEADER_PREFIX} -old_start[,old_count] +new_start[,new_count] {HUNK_HEADER_PREFIX}'.
    - Followed by hunk lines:
        - Lines to be added: Start with '{HUNK_ADD_LINE_PREFIX}'.
        - Lines to be deleted: Start with '{HUNK_DEL_LINE_PREFIX}'.
        - Context lines (unchanged): Start with '{HUNK_CONTEXT_LINE_PREFIX}' (a space).
5.  For '{ADD_FILE_PREFIX}' and '{UPDATE_FILE_PREFIX}' operations, the content/hunk block MUST be terminated by '{END_OF_FILE_PREFIX.strip()}' on its own line before the next command or the final '{PATCH_SUFFIX.strip()}'.""",
                },
            },
            "required": ["patch_text"],
        },
    },
}
