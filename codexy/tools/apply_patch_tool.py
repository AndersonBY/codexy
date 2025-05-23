# -*- coding: utf-8 -*-

"""
Enhanced tool for applying patches with context-based matching.
Inspired by codex-cli with fuzzy matching and Unicode handling.
"""

import os
import unicodedata
from pathlib import Path
from typing import List, Optional, Union, cast, Tuple, Dict
from dataclasses import dataclass, field

from openai.types.chat import ChatCompletionToolParam

from ..exceptions import ToolError

# Re-export for convenience
__all__ = ["apply_patch", "ToolError", "APPLY_PATCH_TOOL_DEF"]

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

# --- Unicode Normalization for Better Matching ---
# Handle common punctuation look-alikes that AI models often confuse
PUNCT_EQUIV: Dict[str, str] = {
    # Hyphen/dash variants
    "-": "-",  # HYPHEN-MINUS
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NO-BREAK HYPHEN
    "\u2012": "-",  # FIGURE DASH
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u2212": "-",  # MINUS SIGN
    # Double quotes
    '"': '"',  # QUOTATION MARK
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "\u00ab": '"',  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\u00bb": '"',  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    # Single quotes
    "'": "'",  # APOSTROPHE
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    # Spaces
    "\u00a0": " ",  # NO-BREAK SPACE
    "\u202f": " ",  # NARROW NO-BREAK SPACE
}


def normalize_text_for_matching(text: str) -> str:
    """
    Normalize text for better matching, handling Unicode equivalents.
    Based on codex-cli's canonicalization strategy.
    """
    # First apply Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)

    # Then replace punctuation look-alikes
    result = ""
    for char in normalized:
        result += PUNCT_EQUIV.get(char, char)

    return result


# --- Data Structures for Parsed Operations ---


def decode_escape_sequences(text: str) -> str:
    """
    Decode common escape sequences in patch content.
    Handles \\n, \\t, \\r, etc.
    """
    # Use Python's built-in string escape decoding
    # But be careful with quotes to avoid issues
    try:
        # Handle the most common escape sequences manually for safety
        result = text
        result = result.replace("\\n", "\n")
        result = result.replace("\\t", "\t")
        result = result.replace("\\r", "\r")
        result = result.replace("\\\\", "\\")  # Handle escaped backslashes
        return result
    except Exception:
        # If decoding fails, return original text
        return text


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
class Chunk:
    """Represents a modification chunk with line indices and content changes."""

    orig_index: int  # 0-based line index in original file where chunk starts
    del_lines: List[str] = field(default_factory=list)  # Lines to delete
    ins_lines: List[str] = field(default_factory=list)  # Lines to insert


@dataclass
class UpdateOp:
    type: str = field(default="update", init=False)
    path: str
    chunks: List[Chunk] = field(default_factory=list)  # Use chunks instead of raw diff_hunk
    move_to: Optional[str] = None


ParsedOperation = Union[AddOp, DeleteOp, UpdateOp]


# --- Enhanced Context Finding with Fuzzy Matching ---


def find_context_core(file_lines: List[str], context_lines: List[str], start_from: int) -> Tuple[int, int]:
    """
    Find context in file with multiple matching strategies.
    Returns (line_index, fuzz_score) where fuzz_score indicates match quality.
    Based on codex-cli's find_context_core with three-pass matching.
    """
    if not context_lines:
        return start_from, 0

    # Pass 1: Exact match after Unicode normalization
    normalized_context = [normalize_text_for_matching(line) for line in context_lines]
    for i in range(start_from, len(file_lines) - len(context_lines) + 1):
        if i < 0:
            continue
        segment = [normalize_text_for_matching(file_lines[i + j]) for j in range(len(context_lines))]
        if segment == normalized_context:
            return i, 0

    # Pass 2: Ignore trailing whitespace
    for i in range(start_from, len(file_lines) - len(context_lines) + 1):
        if i < 0:
            continue
        segment = [normalize_text_for_matching(file_lines[i + j].rstrip()) for j in range(len(context_lines))]
        context_trimmed = [normalize_text_for_matching(line.rstrip()) for line in context_lines]
        if segment == context_trimmed:
            return i, 1

    # Pass 3: Ignore all surrounding whitespace
    for i in range(start_from, len(file_lines) - len(context_lines) + 1):
        if i < 0:
            continue
        segment = [normalize_text_for_matching(file_lines[i + j].strip()) for j in range(len(context_lines))]
        context_stripped = [normalize_text_for_matching(line.strip()) for line in context_lines]
        if segment == context_stripped:
            return i, 100

    return -1, 0


def find_context_with_eof_handling(file_lines: List[str], context_lines: List[str], start_from: int, is_eof: bool) -> Tuple[int, int]:
    """
    Find context with special handling for end-of-file context.
    """
    if is_eof:
        # For EOF context, try from the end first
        eof_start = max(0, len(file_lines) - len(context_lines))
        result, fuzz = find_context_core(file_lines, context_lines, eof_start)
        if result != -1:
            return result, fuzz

        # If EOF matching failed, try from start with penalty
        result, fuzz = find_context_core(file_lines, context_lines, start_from)
        if result != -1:
            return result, fuzz + 10000

        return -1, 0
    else:
        return find_context_core(file_lines, context_lines, start_from)


def parse_traditional_patch_section(lines: List[str], start_idx: int) -> Tuple[List[str], List[Chunk], int, bool]:
    """
    Parse traditional unified diff format.
    This is the original logic that worked before.
    """
    context_lines = []
    chunks = []
    current_chunk = None
    i = start_idx
    is_eof = False
    current_mode = "keep"  # "keep", "add", "delete"
    orig_line_index = 0

    while i < len(lines):
        line = lines[i]

        # Check for section terminators
        terminator_prefixes = [PATCH_SUFFIX.strip(), UPDATE_FILE_PREFIX, DELETE_FILE_PREFIX, ADD_FILE_PREFIX, END_OF_FILE_PREFIX.strip()]
        if any(line.strip().startswith(prefix.strip()) for prefix in terminator_prefixes):
            break

        if line.strip().startswith("***"):
            break

        # Skip unified diff hunk headers like "@@ -1,3 +1,3 @@"
        if line.strip().startswith("@@") and line.strip().endswith("@@") and len(line.strip()) > 2:
            i += 1
            continue

        # Handle different line types
        previous_mode = current_mode
        actual_line = line

        if line.startswith(HUNK_ADD_LINE_PREFIX):
            current_mode = "add"
            actual_line = line[1:]
        elif line.startswith(HUNK_DEL_LINE_PREFIX):
            current_mode = "delete"
            actual_line = line[1:]
        elif line.startswith(HUNK_CONTEXT_LINE_PREFIX):
            current_mode = "keep"
            actual_line = line[1:]
        else:
            # Tolerate lines without prefix (treat as context)
            current_mode = "keep"
            # Don't modify actual_line - use as-is

        # Handle mode transitions - finalize current chunk when switching to "keep"
        if current_mode == "keep" and previous_mode != "keep":
            if current_chunk and (current_chunk.del_lines or current_chunk.ins_lines):
                chunks.append(current_chunk)
            current_chunk = None

        # Process line based on mode
        if current_mode == "delete":
            if current_chunk is None:
                current_chunk = Chunk(orig_index=orig_line_index)
            current_chunk.del_lines.append(decode_escape_sequences(actual_line))
            # Deleted lines count towards original file position
            orig_line_index += 1
            context_lines.append(decode_escape_sequences(actual_line))  # Keep for context, but don't double-count
        elif current_mode == "add":
            if current_chunk is None:
                current_chunk = Chunk(orig_index=orig_line_index)
            current_chunk.ins_lines.append(decode_escape_sequences(actual_line))
            # Added lines don't exist in original file, so don't increment orig_line_index
        else:  # keep
            context_lines.append(decode_escape_sequences(actual_line))
            orig_line_index += 1

        i += 1

    # Handle final chunk
    if current_chunk and (current_chunk.del_lines or current_chunk.ins_lines):
        chunks.append(current_chunk)

    # Check for EOF marker
    if i < len(lines) and lines[i].strip() == END_OF_FILE_PREFIX.strip():
        is_eof = True
        i += 1

    return context_lines, chunks, i, is_eof


def parse_enhanced_patch_section(lines: List[str], start_idx: int) -> Tuple[List[str], List[Chunk], int, bool]:
    """
    Parse a section of patch lines into context and chunks.
    Supports both traditional unified diff format and enhanced @@ block format.
    Returns (context_lines, chunks, next_index, is_eof).
    """
    chunks = []
    i = start_idx
    is_eof = False

    # Check if this is traditional unified diff format (has @@ -x,y +a,b @@)
    has_traditional_format = any(
        line.strip().startswith("@@") and line.strip().endswith("@@") and ("-" in line and "+" in line) and len(line.strip()) > 2
        for line in lines[start_idx : start_idx + 5]  # Check first few lines
    )

    if has_traditional_format:
        # Use original logic for traditional format
        return parse_traditional_patch_section(lines, start_idx)

    # Enhanced format with independent @@ blocks
    # In this format:
    # - "@@" alone is a block separator
    # - "@@ context_info" provides context but is also a separator
    # - Each block between separators contains -/+ lines

    while i < len(lines):
        line = lines[i]

        # Check for section terminators
        terminator_prefixes = [PATCH_SUFFIX.strip(), UPDATE_FILE_PREFIX, DELETE_FILE_PREFIX, ADD_FILE_PREFIX, END_OF_FILE_PREFIX.strip()]
        if any(line.strip().startswith(prefix.strip()) for prefix in terminator_prefixes):
            break

        if line.strip().startswith("***"):
            break

        # Handle @@ markers (both standalone and with context)
        if line.strip().startswith("@@"):
            # This starts a new block, parse until next @@ or terminator
            block_lines, next_i = parse_enhanced_at_block(lines, i + 1)
            if block_lines:
                # Convert the block into a chunk
                chunk = parse_enhanced_at_block_to_chunk(block_lines)
                if chunk:
                    chunks.append(chunk)
            i = next_i
            continue

        # Skip any other lines outside of @@ blocks
        i += 1

    # Check for EOF marker
    if i < len(lines) and lines[i].strip() == END_OF_FILE_PREFIX.strip():
        is_eof = True
        i += 1

    # For enhanced format, we don't return context_lines since each chunk is independent
    return [], chunks, i, is_eof


def parse_enhanced_at_block(lines: List[str], start_idx: int) -> Tuple[List[str], int]:
    """
    Parse a single enhanced @@ block until the next @@ or section terminator.
    This handles the user's format where @@ separates independent blocks.
    Returns (block_lines, next_index).
    """
    block_lines = []
    i = start_idx

    while i < len(lines):
        line = lines[i]

        # Stop at the next @@ block (either "@@" or "@@ context")
        if line.strip().startswith("@@"):
            break

        # Stop at section terminators
        if line.strip().startswith("***") or any(
            line.strip().startswith(prefix.strip()) for prefix in [PATCH_SUFFIX.strip(), UPDATE_FILE_PREFIX, DELETE_FILE_PREFIX, ADD_FILE_PREFIX, END_OF_FILE_PREFIX.strip()]
        ):
            break

        block_lines.append(line)
        i += 1

    return block_lines, i


def parse_enhanced_at_block_to_chunk(block_lines: List[str]) -> Optional[Chunk]:
    """
    Convert a single enhanced @@ block into a Chunk object.
    This processes -/+ lines from the user's format.
    """
    if not block_lines:
        return None

    del_lines = []
    ins_lines = []

    for line in block_lines:
        if line.startswith(HUNK_DEL_LINE_PREFIX):
            del_lines.append(decode_escape_sequences(line[1:]))
        elif line.startswith(HUNK_ADD_LINE_PREFIX):
            ins_lines.append(decode_escape_sequences(line[1:]))
        # For enhanced format, we ignore context lines in individual blocks
        # The context matching will be done separately

    # Only create a chunk if there are actual changes
    if del_lines or ins_lines:
        # For enhanced format, we'll determine orig_index during application
        return Chunk(orig_index=0, del_lines=del_lines, ins_lines=ins_lines)

    return None


# --- Core Parsing Logic ---


def _parse_patch_text(patch_text: str) -> List[ParsedOperation]:
    """
    Parses the patch format text into a list of structured operations.
    Enhanced with better error handling and flexibility.
    """
    if not patch_text.startswith(PATCH_PREFIX):
        raise ToolError(f"Invalid patch format: Must start with '{PATCH_PREFIX.strip()}'")

    cleaned_patch_text = patch_text.rstrip()
    if not cleaned_patch_text.endswith(PATCH_SUFFIX.strip()):
        raise ToolError(f"Invalid patch format: Must end with '{PATCH_SUFFIX.strip()}'")

    patch_body = patch_text[len(PATCH_PREFIX) : patch_text.rfind(PATCH_SUFFIX.strip())].strip("\n")
    lines = patch_body.splitlines()

    operations: List[ParsedOperation] = []
    current_op: Optional[ParsedOperation] = None
    line_buffer: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith(ADD_FILE_PREFIX):
            # Process previous operation if exists
            if current_op and line_buffer:
                _finalize_operation(current_op, line_buffer)
                line_buffer = []

            path = line[len(ADD_FILE_PREFIX) :].strip()
            current_op = AddOp(path=path, content="")
            operations.append(current_op)

        elif line.startswith(DELETE_FILE_PREFIX):
            # Process previous operation if exists
            if current_op and line_buffer:
                _finalize_operation(current_op, line_buffer)
                line_buffer = []

            path = line[len(DELETE_FILE_PREFIX) :].strip()
            current_op = DeleteOp(path=path)
            operations.append(current_op)

        elif line.startswith(UPDATE_FILE_PREFIX):
            # Process previous operation if exists
            if current_op and line_buffer:
                _finalize_operation(current_op, line_buffer)
                line_buffer = []

            path = line[len(UPDATE_FILE_PREFIX) :].strip()
            current_op = UpdateOp(path=path, chunks=[])
            operations.append(current_op)

        elif line.startswith(MOVE_FILE_TO_PREFIX) and isinstance(current_op, UpdateOp):
            current_op.move_to = line[len(MOVE_FILE_TO_PREFIX) :].strip()

        elif line.strip() == END_OF_FILE_PREFIX.strip():
            # Traditional format with explicit End of File marker
            if current_op:
                _finalize_operation(current_op, line_buffer)
                line_buffer = []
                current_op = None

        elif current_op is not None:
            if isinstance(current_op, (AddOp, UpdateOp)):
                line_buffer.append(line)
        elif line.strip():
            # Provide context for debugging
            context_lines = []
            start_idx = max(0, i - 2)
            end_idx = min(len(lines), i + 3)
            for idx in range(start_idx, end_idx):
                prefix = ">>>" if idx == i else "   "
                context_lines.append(f"{prefix} {idx}: {repr(lines[idx])}")
            context = "\n".join(context_lines)
            raise ToolError(
                f"Unexpected line outside operation block: '{line}' at line index {i}\n\nContext:\n{context}\n\nCurrent operation: {current_op.path if current_op else 'None'}"
            )

        i += 1

    # Final processing for operations that might end without explicit EOF marker
    if current_op and line_buffer:
        _finalize_operation(current_op, line_buffer)

    return operations


def _finalize_operation(current_op: ParsedOperation, line_buffer: List[str]) -> None:
    """Helper function to finalize an operation with its accumulated lines."""
    if isinstance(current_op, AddOp):
        # For ADD operations, collect + lines as content
        content_lines = [decode_escape_sequences(line[1:]) for line in line_buffer if line.startswith(HUNK_ADD_LINE_PREFIX)]
        current_op.content = "\n".join(content_lines)
    elif isinstance(current_op, UpdateOp):
        # For UPDATE operations, parse the enhanced patch format
        context_lines, chunks, _, is_eof = parse_enhanced_patch_section(line_buffer, 0)
        current_op.chunks.extend(chunks)


# --- Enhanced Diff Application with Context Matching ---


def _apply_enhanced_update(original_content: str, update_op: UpdateOp) -> str:
    """
    Apply an update operation using enhanced context-based matching.
    Now properly handles both traditional and enhanced formats.
    """
    file_lines = original_content.splitlines()
    result_lines = file_lines.copy()

    # Track how much fuzz we accumulated for reporting
    total_fuzz = 0

    # Check if this looks like traditional format (chunks have meaningful orig_index)
    has_traditional_chunks = any(chunk.orig_index > 0 for chunk in update_op.chunks)

    if has_traditional_chunks:
        # Use original context-based logic for traditional format
        return _apply_traditional_update(original_content, update_op)

    # Enhanced format with @@ blocks, each chunk is independent
    # We need to find and apply each chunk separately
    # Process chunks in reverse order to avoid index shifting issues
    chunks_to_apply = []

    # First, find the positions of all chunks
    for chunk in update_op.chunks:
        if not chunk.del_lines and not chunk.ins_lines:
            continue

        # Strategy 1: Direct text search for deletion content
        if chunk.del_lines:
            target_text = chunk.del_lines[0].strip()  # Use first deletion line as search target

            for i, line in enumerate(result_lines):
                if normalize_text_for_matching(line.strip()) == normalize_text_for_matching(target_text):
                    # Found potential match, verify the entire deletion block
                    match_valid = True

                    # Check if we have enough lines for the full deletion
                    if i + len(chunk.del_lines) > len(result_lines):
                        continue

                    # Verify all deletion lines match
                    for j, del_line in enumerate(chunk.del_lines):
                        if i + j >= len(result_lines):
                            match_valid = False
                            break

                        actual_line = result_lines[i + j].strip()
                        expected_line = del_line.strip()

                        if normalize_text_for_matching(actual_line) != normalize_text_for_matching(expected_line):
                            # Try more fuzzy matching
                            if normalize_text_for_matching(actual_line.replace(" ", "")) == normalize_text_for_matching(expected_line.replace(" ", "")):
                                total_fuzz += 50  # Whitespace difference
                            else:
                                match_valid = False
                                break

                    if match_valid:
                        # Record this chunk for application
                        chunks_to_apply.append((i, chunk))
                        break

        # Strategy 2: If no deletions, try to find insertion point by context
        elif chunk.ins_lines:
            # For insertion-only chunks, we need to be more careful about placement
            # Try to find a good insertion point (this is more complex and may need refinement)
            print(f"Warning: Insertion-only chunk not implemented for enhanced format: {chunk.ins_lines}")

    # Sort chunks by position in reverse order to avoid index shifting
    chunks_to_apply.sort(key=lambda x: x[0], reverse=True)

    # Apply chunks in reverse order
    for position, chunk in chunks_to_apply:
        # Apply the chunk at this location
        original_indentation = ""
        if position < len(result_lines) and chunk.ins_lines:
            # Preserve the original indentation of the first line being replaced
            original_line = result_lines[position]
            leading_spaces = len(original_line) - len(original_line.lstrip())
            original_indentation = " " * leading_spaces

        # Remove the deletion lines
        for _ in range(len(chunk.del_lines)):
            if position < len(result_lines):
                result_lines.pop(position)

        # Insert the new lines with preserved indentation
        for j, ins_line in enumerate(chunk.ins_lines):
            # For the enhanced @@ format, insertion lines already have their intended indentation
            # Don't add extra indentation unless the line is completely unindented
            if ins_line.strip() and not ins_line.startswith(" "):
                # Only apply original indentation if the insertion line has no indentation
                formatted_line = original_indentation + ins_line
            else:
                # Use the line as-is (it already has proper indentation)
                formatted_line = ins_line

            result_lines.insert(position + j, formatted_line)

    # Report any chunks that couldn't be applied
    applied_count = len(chunks_to_apply)
    total_count = len([c for c in update_op.chunks if c.del_lines or c.ins_lines])

    if applied_count != total_count:
        missing_chunks = total_count - applied_count
        print(f"Warning: Could not apply {missing_chunks} out of {total_count} chunks")

    if total_fuzz > 0:
        print(f"Applied update with fuzz factor: {total_fuzz}")

    return "\n".join(result_lines)


def _apply_traditional_update(original_content: str, update_op: UpdateOp) -> str:
    """
    Apply traditional format update using the original context-based logic.
    """
    file_lines = original_content.splitlines()
    result_lines = file_lines.copy()

    # Track how much fuzz we accumulated for reporting
    total_fuzz = 0

    # Sort chunks by original index in reverse order to avoid index shifting issues
    sorted_chunks = sorted(update_op.chunks, key=lambda c: c.orig_index, reverse=True)

    for chunk in sorted_chunks:
        # Find the actual location of this chunk in the file using context
        search_context = []

        # Build context around this chunk location
        context_start = max(0, chunk.orig_index - 2)  # 2 lines before
        context_end = min(len(file_lines), chunk.orig_index + len(chunk.del_lines) + 2)  # 2 lines after

        if context_start < len(file_lines):
            search_context = file_lines[context_start:context_end]

        # Try to find this context in the current state of result_lines
        if search_context:
            found_index, fuzz = find_context_core(result_lines, search_context, 0)
            if found_index != -1:
                # Adjust chunk position based on found context
                adjusted_chunk_start = found_index + (chunk.orig_index - context_start)
                total_fuzz += fuzz
            else:
                # Fallback to original position if context not found
                adjusted_chunk_start = chunk.orig_index
                print(f"Warning: Could not find context for chunk at line {chunk.orig_index + 1}, using original position")
        else:
            adjusted_chunk_start = chunk.orig_index

        # Validate bounds
        if adjusted_chunk_start < 0:
            adjusted_chunk_start = 0

        # Apply deletions
        for i in range(len(chunk.del_lines)):
            delete_index = adjusted_chunk_start + i
            if delete_index < len(result_lines):
                # Verify the content matches (with fuzzy matching)
                expected = normalize_text_for_matching(chunk.del_lines[i].rstrip())
                actual = normalize_text_for_matching(result_lines[delete_index].rstrip())

                if expected != actual:
                    # Try with more aggressive normalization
                    expected_stripped = normalize_text_for_matching(chunk.del_lines[i].strip())
                    actual_stripped = normalize_text_for_matching(result_lines[delete_index].strip())

                    if expected_stripped == actual_stripped:
                        total_fuzz += 100  # High fuzz for whitespace differences
                    else:
                        print(f"Warning: Line content mismatch at {delete_index + 1}. Expected: {repr(chunk.del_lines[i])}, Got: {repr(result_lines[delete_index])}")

                result_lines.pop(adjusted_chunk_start)  # Always remove from start of chunk

        # Apply insertions
        for i, ins_line in enumerate(chunk.ins_lines):
            result_lines.insert(adjusted_chunk_start + i, ins_line)

    if total_fuzz > 0:
        print(f"Applied update with fuzz factor: {total_fuzz}")

    return "\n".join(result_lines)


# --- Filesystem Interaction and Safety ---


def _resolve_and_check_path(relative_path: str, base_dir: Path = PROJECT_ROOT) -> Path:
    """Resolves a relative path against the base directory and performs safety checks."""
    if not relative_path:
        raise ToolError("Path cannot be empty.")

    if Path(relative_path).is_absolute():
        raise ToolError(f"Absolute paths are not allowed: '{relative_path}'")

    target_path = (base_dir / relative_path).resolve()

    if not str(target_path).startswith(str(base_dir.resolve()) + os.sep) and target_path != base_dir.resolve():
        raise ToolError(f"Attempted file access outside of project root: '{relative_path}' resolved to '{target_path}'")

    return target_path


# --- Main Tool Function ---


def _merge_update_operations(operations: List[ParsedOperation]) -> List[ParsedOperation]:
    """
    Merges multiple UPDATE operations for the same file into a single operation.
    """
    merged_operations: List[ParsedOperation] = []
    update_groups: Dict[str, List[UpdateOp]] = {}

    for op in operations:
        if op.type == "update":
            update_op = cast(UpdateOp, op)
            if update_op.path not in update_groups:
                update_groups[update_op.path] = []
            update_groups[update_op.path].append(update_op)
        else:
            merged_operations.append(op)

    # Merge UPDATE operations for each file
    for file_path, update_ops in update_groups.items():
        if len(update_ops) == 1:
            merged_operations.append(update_ops[0])
        else:
            # Merge multiple operations
            merged_chunks = []
            move_to = None

            for update_op in update_ops:
                merged_chunks.extend(update_op.chunks)
                if update_op.move_to:
                    move_to = update_op.move_to

            merged_op = UpdateOp(path=file_path, chunks=merged_chunks, move_to=move_to)
            merged_operations.append(merged_op)

    return merged_operations


def apply_patch(patch_text: str) -> str:
    """
    Parses a patch string and applies the changes to the filesystem.
    Enhanced with fuzzy matching and Unicode normalization.
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

    # Merge multiple UPDATE operations for the same file
    operations = _merge_update_operations(operations)

    results = []
    errors = []

    for op in operations:
        try:
            target_path = _resolve_and_check_path(op.path)

            if op.type == "add":
                op = cast(AddOp, op)
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

                # Use enhanced update application
                new_content = _apply_enhanced_update(original_content, op)

                if op.move_to:
                    new_target_path = _resolve_and_check_path(op.move_to)
                    if new_target_path.exists() and not new_target_path.samefile(target_path):
                        raise ToolError(f"Cannot move file, destination already exists: '{op.move_to}'")
                    new_target_path.parent.mkdir(parents=True, exist_ok=True)
                    new_target_path.write_text(new_content, encoding="utf-8")
                    target_path.unlink()
                    results.append(f"Updated and moved '{op.path}' to '{op.move_to}'")
                else:
                    target_path.write_text(new_content, encoding="utf-8")
                    results.append(f"Updated file: {op.path}")

        except FileNotFoundError:
            errors.append(f"Error processing '{op.path}': File not found.")
        except IsADirectoryError:
            errors.append(f"Error processing '{op.path}': Path is a directory, expected a file.")
        except PermissionError:
            errors.append(f"Error processing '{op.path}': Permission denied.")
        except ToolError as e:
            errors.append(f"Error in '{op.path}': {e}")
        except Exception as e:
            errors.append(f"Unexpected error processing '{op.path}': {type(e).__name__}: {e}")

    # Format final result
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
        "description": "Apply file modifications using a patch format with context-based matching.",
        "parameters": {
            "type": "object",
            "properties": {
                "patch_text": {
                    "type": "string",
                    "description": f"""Patch content in the following format:

{PATCH_PREFIX.strip()}
*** [ACTION] File: [path/to/file]
[patch content]
{PATCH_SUFFIX.strip()}

ACTION can be Add, Update, or Delete.

For Update operations, provide context around changes:
[context_before]
- [old_code]
+ [new_code] 
[context_after]

Use @@ markers to specify location when needed:
@@ class ClassName
@@ def method_name():
[context lines]
- [old_code]
+ [new_code]
[context lines]

Example:
{PATCH_PREFIX.strip()}
{UPDATE_FILE_PREFIX}src/main.py
@@ class Application:
@@     def start(self):
        print("Starting...")
-       self.old_method()
+       self.new_method()
        print("Started")
{PATCH_SUFFIX.strip()}

File paths must be relative. Provide 2-3 lines of context around changes.""",
                },
            },
            "required": ["patch_text"],
        },
    },
}
