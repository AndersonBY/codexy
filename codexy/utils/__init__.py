# -*- coding: utf-8 -*-

# Expose necessary functions from submodules

from .filesystem import check_in_git, shorten_path, short_cwd
from .storage import (
    load_command_history,
    save_command_history,
    add_to_history,
    clear_command_history,
    HistoryEntry,
    DEFAULT_HISTORY_CONFIG,
    HistoryConfig,
)
from .update_checker import check_for_updates, UpdateInfo
from .model_utils import (
    get_available_models,
    is_model_supported,
    preload_models,
    sort_models_for_display,
    format_model_for_display,
)

from .model_info import get_max_tokens_for_model
from .token_utils import approximate_tokens_used

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
    "approximate_tokens_used",
]
