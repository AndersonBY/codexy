import os
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

                # Ensure start_idx is not greater than end_idx
                if start_idx >= end_idx:
                    return f"Error: start_line ({start_line}) must be less than end_line ({end_line})."

                # Add line numbers for context when reading ranges
                numbered_lines = [
                    f"{i + start_idx + 1} | {line.rstrip()}" for i, line in enumerate(lines[start_idx:end_idx])
                ]  # Correct line numbering
                content = "\n".join(numbered_lines)
                if not content:
                    return f"Note: Line range {start_line}-{end_line} is empty or invalid for file {path}."
                return content
            else:
                # Read entire file
                content = f.read()
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
        print(
            f"Warning: Provided line_count ({line_count}) does not match actual lines ({actual_lines}) for path '{path}'. Proceeding anyway."
        )
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


def _should_ignore_path(path: str, ignore_patterns: List[str]) -> bool:
    """Check if the path should be ignored"""
    path = path.replace("\\", "/")  # Normalize to forward slashes

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

            # Check directory path match (ensure directory patterns match correctly)
            if pattern.endswith("/"):
                if fnmatch.fnmatch(current_path + "/", pattern):
                    return True

    return False


def get_gitignore_patterns() -> List[str]:
    """Get patterns from .gitignore file in the project root."""
    patterns: List[str] = []
    gitignore_path = PROJECT_ROOT / ".gitignore"

    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                patterns = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        except Exception as e:
            print(f"Warning: Failed to read .gitignore file: {e}")

    return patterns


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

    # Get gitignore patterns if needed
    ignore_patterns: List[str] = []
    if use_gitignore:
        ignore_patterns = get_gitignore_patterns()
        # 确保.git/也在忽略列表中
        if ".git/" not in ignore_patterns and ".git" not in ignore_patterns:
            ignore_patterns.append(".git/")

    try:
        entries = []
        if recursive:
            # Use os.walk for potentially better performance and handling of symlink loops etc.
            for root, dirs, files in os.walk(target_path):
                current_root = Path(root)

                # 优先过滤掉.git目录，避免遍历内部
                if ".git" in dirs:
                    dirs.remove(".git")

                # Filter directories to avoid traversing ignored directories
                if use_gitignore and ignore_patterns:
                    dirs_to_remove = []
                    for dir_name in dirs:
                        dir_path = current_root / dir_name
                        rel_path = dir_path.relative_to(PROJECT_ROOT)
                        rel_path_str = str(rel_path).replace("\\", "/")

                        if _should_ignore_path(rel_path_str, ignore_patterns):
                            dirs_to_remove.append(dir_name)

                    # Remove ignored directories from dirs list to prevent traversal
                    for dir_name in dirs_to_remove:
                        dirs.remove(dir_name)

                # Add directories
                for name in dirs:
                    entry_path = current_root / name
                    relative_path = entry_path.relative_to(PROJECT_ROOT)
                    rel_path_str = str(relative_path).replace("\\", "/")

                    # 确保.git目录不被添加到结果中
                    if (
                        not rel_path_str.startswith(".git/")
                        and rel_path_str != ".git"
                        and (not use_gitignore or not _should_ignore_path(rel_path_str, ignore_patterns))
                    ):
                        entries.append("[D] " + rel_path_str)

                # Add files
                for name in files:
                    entry_path = current_root / name
                    relative_path = entry_path.relative_to(PROJECT_ROOT)
                    rel_path_str = str(relative_path).replace("\\", "/")

                    # 确保.git目录内的文件不被添加到结果中
                    if not rel_path_str.startswith(".git/") and (
                        not use_gitignore or not _should_ignore_path(rel_path_str, ignore_patterns)
                    ):
                        entries.append("[F] " + rel_path_str)
        else:
            for entry in target_path.iterdir():  # iterdir for non-recursive
                relative_path = entry.relative_to(PROJECT_ROOT)
                rel_path_str = str(relative_path).replace("\\", "/")

                # 确保.git目录和其内容不被添加到结果中
                if (
                    rel_path_str != ".git"
                    and not rel_path_str.startswith(".git/")
                    and (not use_gitignore or not _should_ignore_path(rel_path_str, ignore_patterns))
                ):
                    prefix = "[D] " if entry.is_dir() else "[F] "
                    entries.append(prefix + rel_path_str)  # Normalize slashes

        if not entries:
            return f"Directory '{display_path}' is empty."

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
                "line_count": {  # Add line_count as in the original tool spec
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
