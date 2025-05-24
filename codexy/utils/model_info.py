"""Stores information about supported models, like context length."""

from typing import TypedDict


# Define the structure for model information
class ModelInfo(TypedDict):
    label: str
    max_context_length: int  # Using tokens as the unit


# Dictionary mapping model IDs to their information
# Based on codex-cli/src/utils/model-info.ts, but simplified for common models
# We estimate context length in tokens.
MODEL_INFO_REGISTRY: dict[str, ModelInfo] = {
    "o1-pro-2025-03-19": {"label": "o1 Pro (2025-03-19)", "max_context_length": 200000},
    "o3": {"label": "o3", "max_context_length": 200000},
    "o3-2025-04-16": {"label": "o3 (2025-04-16)", "max_context_length": 200000},
    "o4-mini": {"label": "o4 Mini", "max_context_length": 200000},
    "gpt-4.1-nano": {"label": "GPT-4.1 Nano", "max_context_length": 1000000},
    "gpt-4.1-nano-2025-04-14": {"label": "GPT-4.1 Nano (2025-04-14)", "max_context_length": 1000000},
    "o4-mini-2025-04-16": {"label": "o4 Mini (2025-04-16)", "max_context_length": 200000},
    "gpt-4": {"label": "GPT-4", "max_context_length": 8192},
    "o1-preview-2024-09-12": {"label": "o1 Preview (2024-09-12)", "max_context_length": 128000},
    "gpt-4.1-mini": {"label": "GPT-4.1 Mini", "max_context_length": 1000000},
    "gpt-3.5-turbo-instruct-0914": {"label": "GPT-3.5 Turbo Instruct (0914)", "max_context_length": 4096},
    "gpt-4o-mini-search-preview": {"label": "GPT-4o Mini Search Preview", "max_context_length": 128000},
    "gpt-4.1-mini-2025-04-14": {"label": "GPT-4.1 Mini (2025-04-14)", "max_context_length": 1000000},
    "chatgpt-4o-latest": {"label": "ChatGPT-4o Latest", "max_context_length": 128000},
    "gpt-3.5-turbo-1106": {"label": "GPT-3.5 Turbo (1106)", "max_context_length": 16385},
    "gpt-4o-search-preview": {"label": "GPT-4o Search Preview", "max_context_length": 128000},
    "gpt-4-turbo": {"label": "GPT-4 Turbo", "max_context_length": 128000},
    "gpt-4o-realtime-preview-2024-12-17": {
        "label": "GPT-4o Realtime Preview (2024-12-17)",
        "max_context_length": 128000,
    },
    "gpt-3.5-turbo-instruct": {"label": "GPT-3.5 Turbo Instruct", "max_context_length": 4096},
    "gpt-3.5-turbo": {"label": "GPT-3.5 Turbo", "max_context_length": 16385},
    "gpt-4-turbo-preview": {"label": "GPT-4 Turbo Preview", "max_context_length": 128000},
    "gpt-4o-mini-search-preview-2025-03-11": {
        "label": "GPT-4o Mini Search Preview (2025-03-11)",
        "max_context_length": 128000,
    },
    "gpt-4-0125-preview": {"label": "GPT-4 (0125) Preview", "max_context_length": 128000},
    "gpt-4o-2024-11-20": {"label": "GPT-4o (2024-11-20)", "max_context_length": 128000},
    "o3-mini": {"label": "o3 Mini", "max_context_length": 200000},
    "gpt-4o-2024-05-13": {"label": "GPT-4o (2024-05-13)", "max_context_length": 128000},
    "gpt-4-turbo-2024-04-09": {"label": "GPT-4 Turbo (2024-04-09)", "max_context_length": 128000},
    "gpt-3.5-turbo-16k": {"label": "GPT-3.5 Turbo 16k", "max_context_length": 16385},
    "o3-mini-2025-01-31": {"label": "o3 Mini (2025-01-31)", "max_context_length": 200000},
    "o1-preview": {"label": "o1 Preview", "max_context_length": 128000},
    "o1-2024-12-17": {"label": "o1 (2024-12-17)", "max_context_length": 128000},
    "gpt-4-0613": {"label": "GPT-4 (0613)", "max_context_length": 8192},
    "o1": {"label": "o1", "max_context_length": 128000},
    "o1-pro": {"label": "o1 Pro", "max_context_length": 200000},
    "gpt-4.5-preview": {"label": "GPT-4.5 Preview", "max_context_length": 128000},
    "gpt-4.5-preview-2025-02-27": {"label": "GPT-4.5 Preview (2025-02-27)", "max_context_length": 128000},
    "gpt-4o-search-preview-2025-03-11": {"label": "GPT-4o Search Preview (2025-03-11)", "max_context_length": 128000},
    "gpt-4o": {"label": "GPT-4o", "max_context_length": 128000},
    "gpt-4o-mini": {"label": "GPT-4o Mini", "max_context_length": 128000},
    "gpt-4o-2024-08-06": {"label": "GPT-4o (2024-08-06)", "max_context_length": 128000},
    "gpt-4.1": {"label": "GPT-4.1", "max_context_length": 1000000},
    "gpt-4.1-2025-04-14": {"label": "GPT-4.1 (2025-04-14)", "max_context_length": 1000000},
    "gpt-4o-mini-2024-07-18": {"label": "GPT-4o Mini (2024-07-18)", "max_context_length": 128000},
    "o1-mini": {"label": "o1 Mini", "max_context_length": 128000},
    "gpt-3.5-turbo-0125": {"label": "GPT-3.5 Turbo (0125)", "max_context_length": 16385},
    "o1-mini-2024-09-12": {"label": "o1 Mini (2024-09-12)", "max_context_length": 128000},
    "gpt-4-1106-preview": {"label": "GPT-4 (1106) Preview", "max_context_length": 128000},
    "deepseek-chat": {"label": "DeepSeek Chat", "max_context_length": 64000},
    "deepseek-reasoner": {"label": "DeepSeek Reasoner", "max_context_length": 64000},
}

# Default fallback context length if model is unknown
DEFAULT_CONTEXT_LENGTH = 128000  # Align with JS version's default


def get_max_tokens_for_model(model_id: str) -> int:
    """Returns the maximum context token length for a given model ID."""
    if not model_id:  # Handle empty model_id case
        return DEFAULT_CONTEXT_LENGTH

    info = MODEL_INFO_REGISTRY.get(model_id)
    if info:
        return info["max_context_length"]

    # Fallback heuristics similar to JS version
    lower_id = model_id.lower()
    if "32k" in lower_id:
        return 32000
    if "16k" in lower_id:
        return 16000
    if "8k" in lower_id:
        return 8000
    if "4k" in lower_id:
        return 4000

    # Default if no specific info or heuristic match
    return DEFAULT_CONTEXT_LENGTH
