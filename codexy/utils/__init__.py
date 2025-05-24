# Expose necessary functions from submodules

from .filesystem import check_in_git, short_cwd, shorten_path
from .model_info import get_max_tokens_for_model, get_model_max_tokens
from .model_utils import (
    format_model_for_display,
    get_available_models,
    is_model_supported,
    preload_models,
    sort_models_for_display,
)
from .storage import (
    DEFAULT_HISTORY_CONFIG,
    HistoryConfig,
    HistoryEntry,
    add_to_history,
    clear_command_history,
    load_command_history,
    save_command_history,
)
from .token_utils import approximate_tokens_used
from .update_checker import UpdateInfo, check_for_updates

__all__ = [
    "check_in_git",
    "shorten_path",
    "short_cwd",
    "load_command_history",
    "save_command_history",
    "add_to_history",
    "clear_command_history",
    "HistoryEntry",
    "DEFAULT_HISTORY_CONFIG",
    "HistoryConfig",
    "check_for_updates",
    "UpdateInfo",
    "get_available_models",
    "is_model_supported",
    "preload_models",
    "sort_models_for_display",
    "format_model_for_display",
    "get_max_tokens_for_model",
    "get_model_max_tokens",
    "approximate_tokens_used",
]
