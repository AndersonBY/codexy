import re
from pathlib import Path

from openai.types.chat import ChatCompletionToolParam


PROJECT_ROOT = Path.cwd()


def parse_diff_blocks(diff_text: str) -> list[tuple[int, str, str]]:
    """Parses the multi-block diff string into individual (start_line, search, replace) tuples."""
    blocks = []
    # Regex to find SEARCH blocks with start_line, search content, and replace content
    # It handles potential variations in whitespace and the presence of the ------- and ======= markers.
    # It uses non-greedy matching (.*?) to avoid consuming subsequent blocks.
    pattern = re.compile(
        r"^\s*<<<<<<<\s*SEARCH\s*\n"  # Start marker
        r":start_line:(\d+)\s*\n"  # Capture start line number
        r"-------\s*\n"  # Separator
        r"(.*?)"  # Capture search content (non-greedy)
        r"=======\s*\n"  # Separator
        r"(.*?)"  # Capture replace content (non-greedy)
        r">>>>>>>\s*REPLACE\s*$",  # End marker
        re.MULTILINE | re.DOTALL,  # Multiline and Dotall flags
    )

    for match in pattern.finditer(diff_text):
        start_line = int(match.group(1))
        search_content = match.group(2)
        replace_content = match.group(3)
        # Important: Normalize line endings in search/replace content for comparison
        search_content = search_content.replace("\r\n", "\n")
        replace_content = replace_content.replace("\r\n", "\n")
        blocks.append((start_line, search_content, replace_content))

    if not blocks and diff_text.strip():  # Check if parsing failed but diff wasn't empty
        raise ValueError("Diff text provided but could not parse any valid SEARCH/REPLACE blocks.")

    # Sort blocks by start line descending to apply changes from bottom up,
    # which avoids messing up line numbers for subsequent changes in the same file.
    blocks.sort(key=lambda x: x[0], reverse=True)
    return blocks


def apply_diff_tool(path: str, diff: str) -> str:
    """Applies changes to a file based on a diff string."""
    if not path:
        return "Error: 'path' argument is required."
    if not diff:
        return "Error: 'diff' argument is required and cannot be empty."

    file_path = PROJECT_ROOT / path

    # --- Path Validation ---
    try:
        resolved_path = file_path.resolve(strict=True)  # Must exist for diff
        if not str(resolved_path).startswith(str(PROJECT_ROOT)):
            return f"Error: Attempted to modify file outside of project root: {path}"
        if not resolved_path.is_file():
            return f"Error: Path '{path}' is not a file."
    except FileNotFoundError:
        return f"Error: File not found at '{path}' (resolved to '{file_path}')"
    except Exception as e:
        return f"Error resolving path '{path}': {e}"

    # --- Parse Diff Blocks ---
    try:
        diff_blocks = parse_diff_blocks(diff)
        if not diff_blocks:
            return "Error: No valid SEARCH/REPLACE blocks found in the provided diff."
    except ValueError as e:
        return f"Error parsing diff: {e}"
    except Exception as e:
        return f"Unexpected error parsing diff: {e}"

    # --- Read File Content ---
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()  # Read lines into a list
    except Exception as e:
        return f"Error reading file '{path}' for diff application: {e}"

    # --- Apply Changes (Bottom-Up) ---
    modified_lines = list(original_lines)  # Create a mutable copy
    applied_count = 0
    errors = []

    for start_line, search_content, replace_content in diff_blocks:
        start_idx = start_line - 1  # Convert to 0-based index

        if "\n" not in search_content:
            if start_idx < len(modified_lines):
                current_line = modified_lines[start_idx].rstrip("\r\n")
                if current_line == search_content:
                    modified_lines[start_idx] = replace_content + "\n"
                    applied_count += 1
                    print(f"Successfully applied single-line diff block at line {start_line} to {path}")
                    continue
                else:
                    print(f"Single line mismatch - expected: '{search_content}', actual: '{current_line}'")

            errors.append(f"Error applying block starting at line {start_line}: SEARCH content does not exactly match file content.")
            continue

        # Multi-line processing
        search_lines = search_content.splitlines()
        num_search_lines = len(search_lines)

        # Check bounds
        if start_idx < 0 or start_idx + num_search_lines > len(modified_lines):
            errors.append(
                f"Error applying block starting at line {start_line}: Line range [{start_line}-{start_line + num_search_lines - 1}] is out of bounds (file has {len(modified_lines)} lines)."
            )
            continue  # Skip this block

        # Extract corresponding lines from file and remove line endings for content comparison
        match = True
        for i, search_line in enumerate(search_lines):
            file_line = modified_lines[start_idx + i].rstrip("\r\n")
            if file_line != search_line:
                print(f"Line {start_line + i} mismatch: '{file_line}' != '{search_line}'")
                match = False
                break

        if match:
            # Apply replacement
            replace_lines = [line + "\n" for line in replace_content.splitlines()]
            if not replace_lines:  # Handle empty replacement content
                replace_lines = [""]

            modified_lines[start_idx : start_idx + num_search_lines] = replace_lines
            applied_count += 1
            print(f"Successfully applied multi-line diff block starting at line {start_line} to {path}")
        else:
            errors.append(f"Error applying block starting at line {start_line}: SEARCH content does not exactly match file content.")

    # --- Write Modified Content Back ---
    if applied_count > 0 and not errors:  # Only write if at least one block applied and no errors occurred
        try:
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.writelines(modified_lines)
            return f"Successfully applied {applied_count} diff block(s) to '{path}'."
        except Exception as e:
            return f"Error writing modified content back to '{path}' after applying diffs: {e}"
    elif errors:
        error_summary = "\n".join(errors)
        return f"Failed to apply diff to '{path}'. {applied_count} block(s) applied before encountering errors:\n{error_summary}"
    else:  # No blocks applied (e.g., all failed matching)
        return f"Failed to apply diff to '{path}'. No matching SEARCH blocks found or all blocks failed."


APPLY_DIFF_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "apply_diff",
        "description": "Apply a specific change to a file using a search/replace block format. The SEARCH block must exactly match existing content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative path of the file to modify.",
                },
                "diff": {
                    "type": "string",
                    "description": "The diff string defining the changes. It must strictly follow the search/replace block format. Each block must be structured exactly as follows, using '\\n' for newlines:\n1. '<<<<<<< SEARCH\\n'\n2. ':start_line:NUMBER\\n' (where NUMBER is the 1-based starting line number in the original file)\n3. '-------\\n' (crucial separator)\n4. '[CONTENT_TO_FIND]\\n' (the exact content to be replaced)\n5. '=======\\n' (crucial separator)\n6. '[REPLACEMENT_CONTENT]\\n' (the new content to insert)\n7. '>>>>>>> REPLACE'\nMultiple such blocks can be concatenated in the diff string. Ensure '[CONTENT_TO_FIND]' precisely matches the existing file content, including leading/trailing whitespace on lines, for the change to be applied.",
                },
            },
            "required": ["path", "diff"],
        },
    },
}
