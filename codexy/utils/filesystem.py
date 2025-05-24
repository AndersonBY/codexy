"""Filesystem and path related utility functions for codexy."""

import os
import subprocess
from pathlib import Path


def check_in_git(workdir: str | Path) -> bool:
    """
    Checks if the given directory is part of a Git repository.

    Uses `git rev-parse --is-inside-work-tree` command which exits with 0
    if inside a work tree, and non-zero otherwise.

    Args:
        workdir: The directory path (string or Path object) to check.

    Returns:
        True if the directory is inside a Git work tree, False otherwise
        (including if git command fails or git is not found).
    """
    workdir_path = Path(workdir).resolve()  # Ensure absolute path
    cmd = ["git", "rev-parse", "--is-inside-work-tree"]

    try:
        # Run the git command in the specified directory
        # Suppress stdout and stderr as we only care about the return code
        # check=False prevents raising CalledProcessError on non-zero exit
        result = subprocess.run(
            cmd,
            cwd=str(workdir_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,  # Do not raise an exception on non-zero exit
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,  # Hide console window on Windows
        )
        # Return True if the command executed successfully (exit code 0)
        return result.returncode == 0
    except FileNotFoundError:
        # Handle case where 'git' command is not found
        # print("Warning: 'git' command not found. Cannot check repository status.")
        return False
    except Exception:
        # Catch any other potential errors during subprocess execution
        # print(f"Warning: Error checking git status in {workdir_path}: {e}")
        return False


def shorten_path(p: str | Path, max_length: int = 40) -> str:
    """
    Shortens a path string for display, similar to codex-cli's behavior.

    1. Replaces the home directory prefix with '~'.
    2. If the path is still longer than max_length, it removes components
       from the middle, replacing them with '...', keeping the beginning
       (root or ~) and the end (filename and potentially some parent dirs).

    Args:
        p: The path (string or Path object) to shorten.
        max_length: The maximum desired length for the output string.

    Returns:
        The shortened path string.
    """
    try:
        abs_path = Path(p).resolve()
        home = Path.home()
    except Exception:
        # Fallback if path resolution fails
        return str(p)[:max_length] + ("..." if len(str(p)) > max_length else "")

    try:
        # Check if path is under home directory
        if abs_path == home or abs_path.is_relative_to(home):
            if abs_path == home:
                display_path = "~"
            else:
                # Use '/' for display consistency across platforms within '~' notation
                display_path = "~/" + str(abs_path.relative_to(home)).replace(os.sep, "/")
        else:
            display_path = str(abs_path)
    except ValueError:
        # is_relative_to throws ValueError if paths are on different drives (Windows)
        display_path = str(abs_path)
    except Exception:
        # Fallback for other potential errors
        display_path = str(abs_path)

    if len(display_path) <= max_length:
        return display_path

    # Path is too long, apply shortening logic using '/' as separator for consistency
    display_path_unix = display_path.replace(os.sep, "/")
    parts = display_path_unix.split("/")

    # Filter out empty parts that might result from leading/trailing slashes or '//'
    parts = [part for part in parts if part]

    # Determine the prefix (e.g., '~/', '/')
    prefix = ""
    path_parts_for_suffix = parts  # Assume we use all parts for suffix initially

    if display_path.startswith("~"):
        prefix = "~/"
        # parts already excludes '~', path_parts_for_suffix remains parts
    elif abs_path.is_absolute():
        prefix = "/"  # Simple root prefix for display
        # path_parts_for_suffix remains parts

    # Need to handle Windows drive letters specifically if not under home
    elif os.name == "nt" and len(str(abs_path)) > 2 and str(abs_path)[1] == ":":
        drive = str(abs_path)[:2]
        prefix = drive + "/"  # Display as C:/
        # Adjust parts if they include the drive
        if parts and parts[0] == drive:
            path_parts_for_suffix = parts[1:]

    # Iterate backwards, adding components until max_length is approached
    best_fit = ""
    # Keep at least the filename (last part)
    min_parts_to_keep = 1 if path_parts_for_suffix else 0

    # Iterate keeping at least `min_parts_to_keep` up to all parts
    for i in range(min_parts_to_keep, len(path_parts_for_suffix) + 1):
        # Take the last 'i' parts for the suffix
        suffix_parts = path_parts_for_suffix[len(path_parts_for_suffix) - i :]
        suffix = "/".join(suffix_parts)  # Use '/' for joining

        # Construct candidate string
        candidate = prefix
        # Add ellipsis only if parts were actually omitted
        # Check if the number of suffix parts is less than total available parts
        if i < len(path_parts_for_suffix):
            candidate += ".../"
        candidate += suffix

        if len(candidate) <= max_length:
            best_fit = candidate  # Found a candidate that fits
            # Continue loop to find the longest possible fit that still fits
        else:
            # If adding this part made it too long, the *previous* best_fit was optimal
            # If this was the *first* part tried (i == min_parts_to_keep) and it's already too long,
            # best_fit will still be empty.
            break

    # If no candidate ever fit (e.g., prefix + ... + filename was too long)
    if not best_fit:
        # Fallback: ellipsis + truncated filename
        filename = path_parts_for_suffix[-1] if path_parts_for_suffix else ""
        ellipsis_prefix = prefix + ".../" if prefix else ".../"
        available_chars = max_length - len(ellipsis_prefix)
        if available_chars < 1:
            return ellipsis_prefix[:max_length]  # Cannot even fit ellipsis+part
        return ellipsis_prefix + filename[-available_chars:]
    else:
        return best_fit


def short_cwd(max_length: int = 40) -> str:
    """Returns a shortened version of the current working directory."""
    return shorten_path(Path.cwd(), max_length)
