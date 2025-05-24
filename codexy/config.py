"""Configuration handling for codexy."""

import json
import os
from pathlib import Path
from typing import TypedDict

import yaml
from dotenv import load_dotenv

from .approvals import ApprovalMode

load_dotenv(Path.cwd() / ".env")

# Default values
DEFAULT_AGENTIC_MODEL = "o4-mini"
DEFAULT_FULL_CONTEXT_MODEL = "gpt-4.1"
DEFAULT_INSTRUCTIONS = ""
DEFAULT_APPROVAL_MODE = ApprovalMode.SUGGEST.value  # Default to suggest
DEFAULT_FULL_AUTO_ERROR_MODE = "ask-user"
DEFAULT_NOTIFY = False
DEFAULT_HISTORY_MAX_SIZE = 1000
DEFAULT_HISTORY_SAVE = True
DEFAULT_SAFE_COMMANDS: list[str] = []
DEFAULT_FULL_STDOUT = False

# Configuration directories and files
HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".codexy"  # Use a different directory for the Python version
CONFIG_JSON_FILEPATH = CONFIG_DIR / "config.json"
CONFIG_YAML_FILEPATH = CONFIG_DIR / "config.yaml"
CONFIG_YML_FILEPATH = CONFIG_DIR / "config.yml"
INSTRUCTIONS_FILEPATH = CONFIG_DIR / "instructions.md"

# Environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_TIMEOUT_MS = int(os.environ.get("OPENAI_TIMEOUT_MS", 0)) or None

# Project doc settings
PROJECT_DOC_FILENAMES = ["codex.md", ".codex.md", "CODEX.md"]
PROJECT_DOC_MAX_BYTES = 32 * 1024  # 32 kB

# Type definitions for configuration structures


class HistoryConfig(TypedDict, total=False):
    """Configuration for command history persistence."""

    max_size: int  # Default: 1000
    save_history: bool  # Default: True
    # sensitivePatterns are handled by detect-secrets in Python version


class MemoryConfig(TypedDict, total=False):
    """Configuration for agent memory (if implemented)."""

    enabled: bool


class StoredConfig(TypedDict, total=False):
    """Represents config as stored in JSON/YAML files."""

    model: str | None
    approval_mode: str | None
    full_auto_error_mode: str | None
    memory: MemoryConfig | None
    notify: bool | None
    history: HistoryConfig | None
    safe_commands: list[str] | None
    # writable_roots is a runtime parameter, removed from stored config
    # flex_mode is runtime, not stored
    # full_stdout is runtime, not stored


class AppConfig(TypedDict):
    """Represents the fully resolved runtime configuration."""

    api_key: str | None
    model: str
    instructions: str
    full_auto_error_mode: str | None
    memory: MemoryConfig | None
    notify: bool
    history: HistoryConfig  # Resolved history config with defaults
    safe_commands: list[str]
    effective_approval_mode: str  # Resolved approval mode after considering CLI args etc.
    # Runtime flags, not stored in config file:
    flex_mode: bool
    full_stdout: bool
    writable_roots: list[str]
    base_url: str | None
    timeout: float | None


# Minimal config written on first run.
EMPTY_STORED_CONFIG: StoredConfig = {
    "model": "",  # Empty string ensures default is used on load
    "approval_mode": DEFAULT_APPROVAL_MODE,
    "full_auto_error_mode": DEFAULT_FULL_AUTO_ERROR_MODE,
    "notify": DEFAULT_NOTIFY,
    "history": {
        "max_size": DEFAULT_HISTORY_MAX_SIZE,
        "save_history": DEFAULT_HISTORY_SAVE,
    },
    "safe_commands": DEFAULT_SAFE_COMMANDS,
}


# --- Helper Functions ---


def _discover_project_doc_path(start_dir: Path) -> Path | None:
    """
    Finds the project documentation file (codex.md or similar) by searching
    upwards from the starting directory until the Git root is found.
    """
    current_dir = start_dir.resolve()

    # 1. Check in the starting directory itself
    for name in PROJECT_DOC_FILENAMES:
        direct_path = current_dir / name
        if direct_path.is_file():
            return direct_path

    # 2. Walk up towards the root, looking for .git
    while True:
        git_path = current_dir / ".git"
        if git_path.exists():  # Found .git directory (or file in submodules)
            # Check for codex.md in the git root directory
            for name in PROJECT_DOC_FILENAMES:
                root_doc_path = current_dir / name
                if root_doc_path.is_file():
                    return root_doc_path
            # Found git root, but no doc file there
            return None

        parent = current_dir.parent
        if parent == current_dir:
            # Reached the filesystem root
            return None
        current_dir = parent


def _load_project_doc(doc_path: Path | None) -> str:
    """Loads the project documentation, truncating if necessary."""
    if not doc_path or not doc_path.is_file():
        return ""
    try:
        # Read as bytes first to check size accurately
        content_bytes = doc_path.read_bytes()
        if len(content_bytes) > PROJECT_DOC_MAX_BYTES:
            print(f"Warning: Project doc '{doc_path}' exceeds {PROJECT_DOC_MAX_BYTES} bytes – truncating.")
            # Truncate the byte string before decoding
            content_bytes = content_bytes[:PROJECT_DOC_MAX_BYTES]
        # Decode after potential truncation
        return content_bytes.decode("utf-8", errors="ignore")
    except OSError as e:
        print(f"Error reading project doc {doc_path}: {e}")
        return ""
    except Exception as e:  # Catch potential decoding errors too
        print(f"Error processing project doc {doc_path}: {e}")
        return ""


# --- Main Configuration Loading ---


def load_config(
    config_path: Path | None = None,
    instructions_path: Path | None = None,
    cwd: Path | None = None,
    disable_project_doc: bool = False,
    project_doc_path: Path | None = None,
    is_full_context: bool = False,
    flex_mode: bool = False,
    full_stdout: bool = DEFAULT_FULL_STDOUT,  # Use default
) -> AppConfig:
    """Loads the application configuration from file and environment."""
    # Determine current working directory if not provided
    current_cwd = (cwd or Path.cwd()).resolve()

    actual_config_path: Path = CONFIG_JSON_FILEPATH
    if config_path is None:
        if CONFIG_YAML_FILEPATH.exists():
            config_path = CONFIG_YAML_FILEPATH
        elif CONFIG_YML_FILEPATH.exists():
            config_path = CONFIG_YML_FILEPATH
        else:
            config_path = CONFIG_JSON_FILEPATH  # Default to JSON
    else:
        actual_config_path = config_path.resolve()  # Ensure absolute path

    # Determine instructions path if not provided
    actual_instructions_path = (instructions_path or INSTRUCTIONS_FILEPATH).resolve()

    # --- Basic Config Loading ---
    stored_config: StoredConfig = {}
    if actual_config_path.exists():
        try:
            with open(actual_config_path, encoding="utf-8") as f:
                if actual_config_path.suffix.lower() in [".yaml", ".yml"]:
                    loaded_data = yaml.safe_load(f)
                    if isinstance(loaded_data, dict):
                        stored_config = loaded_data  # type: ignore
                    else:
                        print(f"Warning: Config file {actual_config_path} is not a valid dictionary. Ignoring.")
                else:  # Assume JSON
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, dict):
                        stored_config = loaded_data  # type: ignore
                    else:
                        print(f"Warning: Config file {actual_config_path} is not a valid dictionary. Ignoring.")
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as e:
            print(f"Error loading config file {actual_config_path}: {e}")
            # Keep stored_config empty
        except Exception as e:
            print(f"Unexpected error loading config file {actual_config_path}: {e}")

    # --- Instructions Loading ---
    user_instructions = ""
    if actual_instructions_path.exists():
        try:
            user_instructions = actual_instructions_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Error loading instructions file {actual_instructions_path}: {e}")

    # --- Project Doc Loading ---
    project_doc = ""
    actual_project_doc_path: Path | None = None
    should_load_project_doc = not disable_project_doc and os.environ.get("CODEXY_DISABLE_PROJECT_DOC") != "1"

    if should_load_project_doc:
        if project_doc_path:  # Explicit path provided
            explicit_path_resolved = (current_cwd / project_doc_path).resolve()
            if explicit_path_resolved.is_file():
                actual_project_doc_path = explicit_path_resolved
            else:
                print(f"Warning: Explicit project doc not found at {explicit_path_resolved}")
        else:  # Discover path
            actual_project_doc_path = _discover_project_doc_path(current_cwd)

        if actual_project_doc_path:
            print(f"Loading project doc from: {actual_project_doc_path}")  # Debugging
            project_doc = _load_project_doc(actual_project_doc_path)
        else:
            print(f"No project doc found starting from: {current_cwd}")  # Debugging

    # --- Combine Instructions ---
    combined_instructions_parts = []
    if user_instructions and user_instructions.strip():
        combined_instructions_parts.append(user_instructions.strip())
    if project_doc and project_doc.strip():
        combined_instructions_parts.append("--- project-doc ---\n\n" + project_doc.strip())

    combined_instructions = "\n\n".join(combined_instructions_parts) or DEFAULT_INSTRUCTIONS

    # --- Merging Config ---
    stored_model = stored_config.get("model")
    model = (
        stored_model.strip()
        if stored_model and stored_model.strip()
        else (DEFAULT_FULL_CONTEXT_MODEL if is_full_context else DEFAULT_AGENTIC_MODEL)
    )

    loaded_history_config = stored_config.get("history") or {}
    runtime_history: HistoryConfig = {
        "max_size": loaded_history_config.get("max_size", DEFAULT_HISTORY_MAX_SIZE),
        "save_history": loaded_history_config.get("save_history", DEFAULT_HISTORY_SAVE),
    }

    # Validate and set user's preferred approval mode, defaulting to SUGGEST
    approval_mode_str = stored_config.get("approval_mode", DEFAULT_APPROVAL_MODE) or DEFAULT_APPROVAL_MODE
    try:
        _ = ApprovalMode(approval_mode_str)
        user_preferred_approval_mode = approval_mode_str
    except ValueError:
        print(f"Warning: Invalid approval_mode '{approval_mode_str}' in config. Using default '{DEFAULT_APPROVAL_MODE}'.")
        user_preferred_approval_mode = DEFAULT_APPROVAL_MODE

    # Load safe commands, defaulting to empty list
    safe_commands = stored_config.get("safe_commands", [])
    if not isinstance(safe_commands, list) or not all(isinstance(s, str) for s in safe_commands):
        print("Warning: Invalid 'safe_commands' format in config. Expected list of strings. Ignoring.")
        safe_commands = list(DEFAULT_SAFE_COMMANDS)  # Use default

    # Load full_auto_error_mode, validate and provide default
    full_auto_error_mode = stored_config.get("full_auto_error_mode")
    if full_auto_error_mode not in ["ask-user", "ignore-and-continue"]:
        if full_auto_error_mode is not None:  # Warn only if an invalid value was provided
            print(
                f"Warning: Invalid full_auto_error_mode '{full_auto_error_mode}' in config. Using default '{DEFAULT_FULL_AUTO_ERROR_MODE}'."
            )
        full_auto_error_mode = DEFAULT_FULL_AUTO_ERROR_MODE

    # --- Final AppConfig Assembly ---
    app_config: AppConfig = {
        "api_key": OPENAI_API_KEY or None,
        "model": model,
        "instructions": combined_instructions,
        "full_auto_error_mode": full_auto_error_mode,
        "memory": stored_config.get("memory"),
        "notify": stored_config.get("notify", DEFAULT_NOTIFY) or False,
        "history": runtime_history,
        "safe_commands": safe_commands,
        "effective_approval_mode": user_preferred_approval_mode,
        # Runtime flags from function args
        "flex_mode": flex_mode,
        "full_stdout": full_stdout,
        "writable_roots": [],  # Initial empty, filled later by CLI
        "base_url": OPENAI_BASE_URL or None,
        "timeout": OPENAI_TIMEOUT_MS / 1000.0 if OPENAI_TIMEOUT_MS else None,
    }

    # --- First Run Bootstrap ---
    config_dir = actual_config_path.parent
    if not config_dir.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create config directory {config_dir}: {e}")

    # Create default config file if it doesn't exist
    if config_dir.is_dir() and not actual_config_path.exists():
        try:
            # Bootstrap with EMPTY_STORED_CONFIG which includes defaults
            with open(actual_config_path, "w", encoding="utf-8") as f:
                if actual_config_path.suffix.lower() in [".yaml", ".yml"]:
                    yaml.dump(dict(EMPTY_STORED_CONFIG), f, default_flow_style=False)
                else:
                    json.dump(EMPTY_STORED_CONFIG, f, indent=2)
            print(f"Created default config file: {actual_config_path}")
        except OSError as e:
            print(f"Warning: Could not create default config file {actual_config_path}: {e}")

    # Create default instructions file if it doesn't exist
    if config_dir.is_dir() and not actual_instructions_path.exists():
        try:
            actual_instructions_path.write_text(DEFAULT_INSTRUCTIONS, encoding="utf-8")
            print(f"Created default instructions file: {actual_instructions_path}")
            if not app_config["instructions"]:
                app_config["instructions"] = DEFAULT_INSTRUCTIONS
        except OSError as e:
            print(f"Warning: Could not create default instructions file {actual_instructions_path}: {e}")

    return app_config


def save_config(
    config: AppConfig,
    config_path: Path | None = None,
    instructions_path: Path | None = None,
):
    """Saves the persistent parts of the application configuration."""
    actual_config_path: Path
    if config_path is None:
        if CONFIG_YAML_FILEPATH.exists():
            actual_config_path = CONFIG_YAML_FILEPATH
        elif CONFIG_YML_FILEPATH.exists():
            actual_config_path = CONFIG_YML_FILEPATH
        else:
            actual_config_path = CONFIG_JSON_FILEPATH
    else:
        actual_config_path = config_path.resolve()

    actual_instructions_path = (instructions_path or INSTRUCTIONS_FILEPATH).resolve()

    # --- Prepare Data to Save (StoredConfig format) ---
    config_to_save: StoredConfig = {}

    # Only save values if they differ from typical defaults
    # Save the 'effective_approval_mode' as 'approval_mode' in the file
    if config.get("model") and config["model"] != DEFAULT_AGENTIC_MODEL and config["model"] != DEFAULT_FULL_CONTEXT_MODEL:
        config_to_save["model"] = config["model"]
    if config.get("effective_approval_mode") and config["effective_approval_mode"] != DEFAULT_APPROVAL_MODE:
        config_to_save["approval_mode"] = config["effective_approval_mode"]
    if config.get("full_auto_error_mode") and config["full_auto_error_mode"] != DEFAULT_FULL_AUTO_ERROR_MODE:
        config_to_save["full_auto_error_mode"] = config["full_auto_error_mode"]
    if config.get("memory") is not None:
        config_to_save["memory"] = config["memory"]
    if config.get("notify") != DEFAULT_NOTIFY:
        config_to_save["notify"] = config["notify"]

    # Save history config only if different from default
    history_to_save = config.get("history")
    if history_to_save:
        history_defaults = {"max_size": DEFAULT_HISTORY_MAX_SIZE, "save_history": DEFAULT_HISTORY_SAVE}
        # Only include history section if any value differs from default
        if any(history_to_save.get(k) != history_defaults.get(k) for k in history_defaults):  # type: ignore
            config_to_save["history"] = history_to_save

    # Save safe_commands only if the list is not empty (or differs from default if default isn't empty)
    if config.get("safe_commands") and config["safe_commands"] != DEFAULT_SAFE_COMMANDS:
        config_to_save["safe_commands"] = config["safe_commands"]

    # --- Ensure Directory Exists ---
    config_dir = actual_config_path.parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory for config {actual_config_path}: {e}")
        print("Failed to save configuration file due to directory error.")

    # --- Save Main Config File ---
    if config_to_save:  # Only write file if there's something non-default to save
        try:
            with open(actual_config_path, "w", encoding="utf-8") as f:
                if actual_config_path.suffix.lower() in [".yaml", ".yml"]:
                    yaml.dump(dict(config_to_save), f, default_flow_style=False, sort_keys=False)
                else:
                    json.dump(config_to_save, f, indent=2)
            # print(f"Configuration saved to {actual_config_path}") # Optional log
        except (OSError, yaml.YAMLError) as e:
            print(f"Error saving config file {actual_config_path}: {e}")
            # Don't abort if config save fails, instructions might still work
        except Exception as e:
            print(f"Unexpected error saving config file {actual_config_path}: {e}")

    # --- Save Instructions File ---
    # Extract ONLY the user instructions part for saving.
    instructions_content = config.get("instructions", "")
    project_doc_marker = "\n\n--- project-doc ---\n\n"
    user_instructions_to_save = instructions_content
    if project_doc_marker in instructions_content:
        # Save only the part *before* the project doc marker
        user_instructions_to_save = instructions_content.split(project_doc_marker, 1)[0]

    # Only save if different from default empty string
    if user_instructions_to_save.strip() != DEFAULT_INSTRUCTIONS:
        try:
            actual_instructions_path.parent.mkdir(parents=True, exist_ok=True)
            actual_instructions_path.write_text(user_instructions_to_save, encoding="utf-8")
        except OSError as e:
            print(f"Error saving instructions file {actual_instructions_path}: {e}")
        except Exception as e:
            print(f"Unexpected error saving instructions file {actual_instructions_path}: {e}")
