import fnmatch
from pathlib import Path
from typing import Optional, List

from openai.types.chat import ChatCompletionToolParam

# Define a base directory for safety, operations should be relative to this.
# For now, assume the CWD where the script is run is the project root.
PROJECT_ROOT = Path.cwd()


def read_file_tool(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Reads content from a file, potentially a specific line range."""
    if not path:
        return "Error: 'path' argument is required."

    file_path = PROJECT_ROOT / path  # Ensure path is relative to project root

    # Basic path traversal check (can be improved)
    try:
        resolved_path = file_path.resolve(strict=True)  # Check existence and resolve symlinks
        # Check if the resolved path is within the project root directory
        if not str(resolved_path).startswith(str(PROJECT_ROOT)):
            return f"Error: Attempted to read file outside of project root: {path}"
    except FileNotFoundError:
        return f"Error: File not found at '{path}' (resolved to '{file_path}')"
    except Exception as e:  # Catch other resolution errors
        return f"Error resolving path '{path}': {e}"

    if not resolved_path.is_file():
        return f"Error: Path '{path}' is not a file."

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            if start_line is not None or end_line is not None:
                lines = f.readlines()
                start_idx = (start_line - 1) if start_line is not None and start_line > 0 else 0
                end_idx = end_line if end_line is not None and end_line <= len(lines) else len(lines)

                if start_line and start_line > len(lines):
                    return f"Error: start_line ({start_line}) is greater than the number of lines in the file ({len(lines)})."

                # Ensure start_idx is not greater than end_idx
                if start_idx >= end_idx:
                    return f"Error: start_line ({start_line}) must be less than end_line ({end_line})."

                # Add line numbers for context when reading ranges
                numbered_lines = [f"{i + start_idx + 1} | {line.rstrip()}" for i, line in enumerate(lines[start_idx:end_idx])]
                content = "\n".join(numbered_lines)
                if not content:
                    return f"Note: Line range {start_line}-{end_line} is empty or invalid for file {path}."
                return content
            else:
                # Read entire file
                lines = f.readlines()
                # Add line numbers for context when reading entire file
                numbered_lines = [f"{i + 1} | {line.rstrip()}" for i, line in enumerate(lines)]
                content = "\n".join(numbered_lines)
                # TODO: Add truncation for very large files?
                # max_chars = 10000
                # if len(content) > max_chars:
                #    content = content[:max_chars] + "\n... (file truncated)"
                return content
    except Exception as e:
        return f"Error reading file '{path}': {e}"


def write_to_file_tool(path: str, content: str, line_count: int) -> str:
    """Writes content to a file, creating directories if needed."""
    if not path:
        return "Error: 'path' argument is required."
    if content is None:  # Check for None explicitly, empty string is valid content
        return "Error: 'content' argument is required."
    if line_count is None:
        return "Error: 'line_count' argument is required."  # Enforce line_count

    file_path = PROJECT_ROOT / path  # Ensure path is relative to project root

    # Basic path traversal check (similar to read_file)
    try:
        # Resolve the intended *parent* directory to check containment
        resolved_parent = file_path.parent.resolve(strict=False)  # Allow parent not to exist yet
        # Check if the intended parent directory is within the project root
        if not str(resolved_parent).startswith(str(PROJECT_ROOT)):
            return f"Error: Attempted to write file outside of project root: {path}"
    except Exception as e:
        return f"Error resolving path '{path}': {e}"

    # Validate line count (basic check)
    actual_lines = len(content.splitlines())
    # Allow some flexibility (e.g., trailing newline might differ)
    if abs(actual_lines - line_count) > 1:
        print(f"Warning: Provided line_count ({line_count}) does not match actual lines ({actual_lines}) for path '{path}'. Proceeding anyway.")
        # Could return an error here if strict matching is desired:
        # return f"Error: Provided line_count ({line_count}) does not match actual lines ({actual_lines})."

    try:
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            bytes_written = f.write(content)  # write returns number of characters (similar to bytes for utf-8)

        return f"Successfully wrote {bytes_written} characters ({line_count} lines reported) to '{path}'."
    except Exception as e:
        return f"Error writing to file '{path}': {e}"


def _should_ignore_path(path: str, ignore_patterns: List[str], current_dir: Optional[Path] = None) -> bool:
    """Check if the path should be ignored

    Args:
        path: The path to check (relative to the project root)
        ignore_patterns: The list of ignore patterns
        current_dir: The current directory being processed (for subdirectory .gitignore matching)
    """
    path = path.replace("\\", "/")  # Normalize to forward slashes

    if current_dir is not None:
        rel_to_current = None
        try:
            full_path = PROJECT_ROOT / path
            if full_path.exists() and str(full_path).startswith(str(current_dir)):
                rel_to_current = str(full_path.relative_to(current_dir)).replace("\\", "/")
        except Exception:
            pass

    # Check if each part of the path should be ignored
    path_parts = Path(path).parts
    for i in range(len(path_parts)):
        current_path = str(Path(*path_parts[: i + 1])).replace("\\", "/")

        for pattern in ignore_patterns:
            pattern = pattern.replace("\\", "/")

            # Handle relative paths in patterns
            if pattern.startswith("./"):
                pattern = pattern[2:]
            if current_path.startswith("./"):
                current_path = current_path[2:]

            # Check full path match
            if fnmatch.fnmatch(current_path, pattern):
                return True

            # Check directory name match
            if fnmatch.fnmatch(path_parts[i], pattern):
                return True

            # Check if the last part of the path matches (handles ignores in subdirectories)
            if i == len(path_parts) - 1:
                last_part = path_parts[i]
                if fnmatch.fnmatch(last_part, pattern):
                    return True

            # Check directory path match (ensure directory patterns match correctly)
            if pattern.endswith("/"):
                if fnmatch.fnmatch(current_path + "/", pattern):
                    return True

                if i == len(path_parts) - 1 and fnmatch.fnmatch(path_parts[i] + "/", pattern):
                    return True

            # If there is a relative path, check if it matches
            if current_dir is not None and rel_to_current is not None:
                if pattern.endswith("/") and isinstance(rel_to_current, str):
                    if fnmatch.fnmatch(rel_to_current + "/", pattern):
                        return True
                if isinstance(rel_to_current, str) and fnmatch.fnmatch(rel_to_current, pattern):
                    return True

    return False


def collect_gitignore_patterns(directory_path: Path) -> List[str]:
    """Collect .gitignore rules from the specified directory and all its parent directories."""
    patterns: List[str] = []

    # Start from the current directory and collect all parent directory's .gitignore rules
    current_dir = directory_path
    while str(current_dir).startswith(str(PROJECT_ROOT)):
        gitignore_path = current_dir / ".gitignore"

        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    dir_patterns = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
                    patterns.extend(dir_patterns)
            except Exception as e:
                print(f"Warning: Failed to read .gitignore file: {e}")

        # If we've reached the project root, stop
        if current_dir == PROJECT_ROOT:
            break

        # Move to the parent directory
        current_dir = current_dir.parent

    # Add some common directories that should be ignored
    common_ignores = [".git/", "node_modules/", "dist/", "__pycache__/", "*.pyc", "*.pyo", "build/", "venv/", ".env"]

    for pattern in common_ignores:
        if pattern not in patterns:
            patterns.append(pattern)

    return patterns


def _recursive_list_files(current_path: Path, root_path: Path, parent_ignore_patterns: List[str], use_gitignore: bool, entries: List[str]) -> None:
    """Recursively traverse directories, checking if they should be ignored before processing."""

    # Check if this directory itself should be ignored (using parent directory's ignore rules)
    rel_path = current_path.relative_to(PROJECT_ROOT)
    rel_path_str = str(rel_path).replace("\\", "/")

    # If this is the project root, don't check if it should be ignored
    if current_path != PROJECT_ROOT and use_gitignore:
        if _should_ignore_path(rel_path_str, parent_ignore_patterns):
            return  # If the directory should be ignored, return without processing further

    # Check if the current directory has its own .gitignore file, merge it into the parent rules
    current_ignore_patterns = parent_ignore_patterns.copy()
    local_patterns = []
    if use_gitignore:
        gitignore_path = current_path / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    local_patterns = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
                    current_ignore_patterns.extend(local_patterns)
            except Exception as e:
                print(f"Error reading local .gitignore file: {e}")

    try:
        # Get all directories and files
        dirs = []
        files = []

        for entry in current_path.iterdir():
            if entry.is_dir():
                dirs.append(entry)
            else:
                files.append(entry)

        # Process files
        for file_path in files:
            # Skip .gitignore files
            if file_path.name == ".gitignore" and use_gitignore:
                continue

            rel_file_path = file_path.relative_to(PROJECT_ROOT)
            rel_file_path_str = str(rel_file_path).replace("\\", "/")

            # Check if the file should be ignored (using merged rules)
            if use_gitignore:
                # Pass current directory for local rules
                if _should_ignore_path(rel_file_path_str, current_ignore_patterns, current_path if local_patterns else None):
                    continue

            # Add file to results
            entries.append("[F] " + rel_file_path_str)

        # Process directories
        for dir_path in dirs:
            # Skip .git directory
            if dir_path.name == ".git":
                continue

            rel_dir_path = dir_path.relative_to(PROJECT_ROOT)
            rel_dir_path_str = str(rel_dir_path).replace("\\", "/")

            # Check if the directory should be ignored (using merged rules)
            should_ignore = False
            if use_gitignore:
                # Pass current directory for local rules
                if _should_ignore_path(rel_dir_path_str, current_ignore_patterns, current_path if local_patterns else None):
                    should_ignore = True

            # If the directory should not be ignored, add it to results and recursively process
            if not should_ignore:
                entries.append("[D] " + rel_dir_path_str)
                # Recursively process subdirectories (pass current merged ignore rules)
                _recursive_list_files(dir_path, root_path, current_ignore_patterns, use_gitignore, entries)

    except Exception as e:
        print(f"Error traversing directory {current_path}: {e}")


def list_files_tool(path: str, recursive: bool = False, use_gitignore: bool = True) -> str:
    """Lists files and directories within the specified path."""

    if not path:
        # Default to listing the project root if path is empty or '.'
        target_path = PROJECT_ROOT
        display_path = "."  # Display '.' for clarity when listing root
    else:
        target_path = (PROJECT_ROOT / path).resolve()  # Resolve the path
        display_path = path  # Use the provided path for display

    # Security check: Ensure the target path is within the project root
    if not str(target_path).startswith(str(PROJECT_ROOT)):
        return f"Error: Attempted to list files outside of project root: {path}"

    if not target_path.is_dir():
        return f"Error: Path '{display_path}' is not a valid directory."

    # Get gitignore patterns if needed - 使用新的父目录收集函数
    ignore_patterns: List[str] = []
    if use_gitignore:
        ignore_patterns = collect_gitignore_patterns(target_path)

    try:
        entries = []

        if recursive:
            # Use recursive traversal
            _recursive_list_files(target_path, PROJECT_ROOT, ignore_patterns, use_gitignore, entries)
        else:
            # Non-recursive mode - list files and directories in current directory
            for entry in target_path.iterdir():
                relative_path = entry.relative_to(PROJECT_ROOT)
                rel_path_str = str(relative_path).replace("\\", "/")

                # Check if it should be ignored
                if use_gitignore and _should_ignore_path(rel_path_str, ignore_patterns):
                    continue

                # Add paths that should not be ignored
                if rel_path_str != ".git" and not rel_path_str.startswith(".git/"):
                    prefix = "[D] " if entry.is_dir() else "[F] "
                    entries.append(prefix + rel_path_str)  # Normalize slashes

        if not entries:
            return f"Directory '{display_path}' is empty or all entries are ignored."

        # Sort entries for consistent output
        entries.sort()
        # Limit the number of entries returned to prevent overwhelming the context
        max_entries = 500
        if len(entries) > max_entries:
            entries = entries[:max_entries] + [f"... (truncated, {len(entries) - max_entries} more entries)"]

        gitignore_status = f"(gitignore={'enabled' if use_gitignore else 'disabled'})"
        return f"Contents of '{display_path}' {gitignore_status} (Recursive={recursive}):\n" + "\n".join(entries)

    except Exception as e:
        return f"Error listing files in '{display_path}': {e}"


READ_FILE_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the contents of a file at the specified path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative path of the file to read from the project root.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional starting line number (1-based).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional ending line number (1-based, inclusive).",
                },
            },
            "required": ["path"],
        },
    },
}

WRITE_TO_FILE_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "write_to_file",
        "description": "Write content to a file at the specified path. Overwrites if the file exists, creates it otherwise. Creates necessary directories.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative path of the file to write to (from project root).",
                },
                "content": {
                    "type": "string",
                    "description": "The complete content to write to the file.",
                },
                "line_count": {
                    "type": "integer",
                    "description": "The total number of lines in the provided content.",
                },
            },
            "required": ["path", "content", "line_count"],
        },
    },
}

LIST_FILES_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files and directories within a specified path relative to the project root.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative path of the directory to list.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list files recursively (default: false).",
                    "default": False,
                },
                "use_gitignore": {
                    "type": "boolean",
                    "description": "Whether to respect .gitignore patterns (default: true).",
                    "default": True,
                },
            },
            "required": ["path"],
        },
    },
}
