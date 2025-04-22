# -*- coding: utf-8 -*-

"""Utilities for persistent storage like command history."""

import sys
import json
import time
from typing import List, TypedDict, Optional

from ..config import CONFIG_DIR
from ..utils.security_check import SecurityChecker


security_checker = SecurityChecker()


# Assuming config types might be shared or defined elsewhere,
# but defining locally for clarity if not.
# If AppConfig/HistoryConfig are defined in config.py, import them instead.
class HistoryConfig(TypedDict, total=False):
    max_size: int
    save_history: bool


class HistoryEntry(TypedDict):
    command: str
    timestamp: float


# Default history config
DEFAULT_HISTORY_CONFIG: HistoryConfig = {
    "max_size": 1000,
    "save_history": True,
}


HISTORY_FILE = CONFIG_DIR / "history.json"


def is_sensitive_command(command: str) -> bool:
    """Checks if a command contains potential secrets using detect-secrets."""
    messages = security_checker.check_line(command)
    if messages:
        # Log sensitivity check failure to stderr for debugging/awareness
        print(
            f"[History] Command '{command[:20]}...' potentially sensitive, skipping save.",
            file=sys.stderr,
        )
        return True
    return False


# --- Command History Functions ---


def load_command_history() -> List[HistoryEntry]:
    """Loads command history from the history file."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history_data = json.load(f)
        # Basic validation: check if it's a list
        if isinstance(history_data, list):
            # Further validation could be added here to check structure of entries
            # For now, assume the structure is correct if it's a list
            return history_data
        else:
            print(
                f"Warning: History file {HISTORY_FILE} does not contain a valid list. Starting fresh.", file=sys.stderr
            )
            return []
    except (IOError, json.JSONDecodeError) as e:
        # Use stderr for warnings/errors that shouldn't pollute normal output
        print(
            f"Warning: Failed to load command history from {HISTORY_FILE}. Starting fresh. Error: {e}", file=sys.stderr
        )
        return []
    except Exception as e:  # Catch unexpected errors
        print(
            f"Warning: An unexpected error occurred loading history {HISTORY_FILE}. Starting fresh. Error: {e}",
            file=sys.stderr,
        )
        return []


def save_command_history(history: List[HistoryEntry], config: Optional[HistoryConfig] = None):
    """Saves command history to the history file."""
    cfg_to_use = config if config else DEFAULT_HISTORY_CONFIG
    max_size = cfg_to_use.get("max_size", DEFAULT_HISTORY_CONFIG.get("max_size", 1000))

    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        trimmed_history = history[-max_size:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed_history, f, indent=2)
    except IOError as e:
        print(f"Error: Failed to save command history to {HISTORY_FILE}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error: An unexpected error occurred saving history to {HISTORY_FILE}: {e}", file=sys.stderr)


def add_to_history(
    command: str,
    history: List[HistoryEntry],
    config: Optional[HistoryConfig] = None,
) -> List[HistoryEntry]:
    """
    Adds a command to the history list if configured to save, it's not sensitive (using detect-secrets),
    and it's not an immediate duplicate. Saves the updated history to disk.

    Returns:
        The potentially updated history list.
    """
    cfg_to_use = config if config else DEFAULT_HISTORY_CONFIG
    should_save = cfg_to_use.get("save_history", DEFAULT_HISTORY_CONFIG.get("save_history", True))

    if not should_save:
        return history

    trimmed_command = command.strip()
    if not trimmed_command:
        return history

    # Check for sensitivity using detect-secrets
    if is_sensitive_command(trimmed_command):
        return history  # Don't save sensitive commands

    # Check for immediate duplicate
    if history and history[-1]["command"] == trimmed_command:
        return history

    new_entry: HistoryEntry = {
        "command": trimmed_command,
        "timestamp": time.time(),
    }

    new_history = history + [new_entry]
    save_command_history(new_history, cfg_to_use)  # Save handles trimming

    max_size = cfg_to_use.get("max_size", DEFAULT_HISTORY_CONFIG.get("max_size", 1000))
    return new_history[-max_size:]


def clear_command_history():
    """Clears the command history by overwriting the file with an empty list."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        # Removed print statement - feedback should be in TUI
        # print(f"Command history cleared ({HISTORY_FILE})")
    except IOError as e:
        print(f"Error: Failed to clear command history file {HISTORY_FILE}: {e}", file=sys.stderr)
        # Re-raise or handle more gracefully depending on requirements
        raise  # Or return False/status code
    except Exception as e:
        print(f"Error: An unexpected error occurred clearing history {HISTORY_FILE}: {e}", file=sys.stderr)
        raise  # Or return False/status code
