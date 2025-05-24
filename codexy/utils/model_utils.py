import asyncio
import sys

from openai import APIError, AsyncOpenAI

# --- Constants ---
# Define recommended models (adjust as needed)
RECOMMENDED_MODELS: list[str] = ["o4-mini", "o3", "gpt-4o", "gpt-4.1"]
MODEL_LIST_TIMEOUT_SECONDS = 5.0  # Timeout for fetching model list

# --- Caching ---
# Simple in-memory cache for the model list
_cached_models: list[str] | None = None
_cache_lock = asyncio.Lock()
_is_fetching = False

# --- Functions ---


async def _fetch_models_from_api(client: AsyncOpenAI) -> list[str]:
    """Fetches the list of models from the OpenAI API."""
    global _is_fetching
    if _is_fetching:
        # Avoid concurrent fetches if one is already in progress
        print("Model fetch already in progress, waiting...", file=sys.stderr)
        while _is_fetching:
            await asyncio.sleep(0.1)
        return _cached_models or []  # Return potentially updated cache

    _is_fetching = True
    try:
        print("Fetching available models from OpenAI API...", file=sys.stderr)
        models_response = await client.models.list()
        # Extract model IDs, filter out older models if desired, and sort
        # Example filtering: models starting with 'gpt-', 'ft:', 'o3', 'o4'
        models = sorted(
            m.id
            for m in models_response.data
            if m.id and (m.id.startswith("gpt-") or m.id.startswith("ft:") or m.id.startswith("o3") or m.id.startswith("o4"))
        )
        print(f"Fetched {len(models)} models.", file=sys.stderr)
        return models
    except APIError as e:
        print(f"Warning: API Error fetching models: {e.code} - {e.message}", file=sys.stderr)
        return []  # Return empty on API error
    except Exception as e:
        print(f"Warning: Unexpected error fetching models: {e}", file=sys.stderr)
        return []  # Return empty on other errors
    finally:
        _is_fetching = False


async def get_available_models(client: AsyncOpenAI, force_refresh: bool = False) -> list[str]:
    """
    Gets the list of available models, using cache if available and not forced.
    Adds recommended models even if the API call fails.
    """
    global _cached_models
    async with _cache_lock:
        if _cached_models is None or force_refresh:
            fetched_models = await _fetch_models_from_api(client)
            # Combine fetched models with recommended models, ensuring uniqueness and sorting
            combined_models = set(fetched_models) | set(RECOMMENDED_MODELS)
            _cached_models = sorted(combined_models)
            if not fetched_models:
                print("Warning: Using only recommended models due to fetch failure.", file=sys.stderr)

        return _cached_models if _cached_models is not None else list(RECOMMENDED_MODELS)  # Fallback


async def preload_models(client: AsyncOpenAI):
    """Initiates the model fetching process in the background."""
    async with _cache_lock:
        if _cached_models is None and not _is_fetching:
            asyncio.create_task(_fetch_models_from_api(client))


async def is_model_supported(model_id: str, client: AsyncOpenAI) -> bool:
    """Checks if a given model ID is likely supported."""
    if not model_id:
        return False
    # Assume recommended models are always supported initially
    if model_id in RECOMMENDED_MODELS:
        return True
    try:
        available = await get_available_models(client)
        return model_id in available
    except Exception:
        # If check fails, conservatively assume it might be supported
        return True


def sort_models_for_display(models: list[str], current_model: str) -> list[str]:
    """Sorts models, putting recommended and current at the top."""
    recommended_set = set(RECOMMENDED_MODELS)
    current_list = [m for m in models if m == current_model]
    recommended_list = sorted([m for m in models if m in recommended_set and m != current_model])
    other_list = sorted([m for m in models if m not in recommended_set and m != current_model])
    return current_list + recommended_list + other_list


def format_model_for_display(model_id: str, current_model: str) -> str:
    """Formats the model ID for display, adding markers."""
    prefix = ""
    if model_id == current_model:
        prefix += "✓ "  # Checkmark for current
    if model_id in RECOMMENDED_MODELS:
        prefix += "⭐ "  # Star for recommended
    return f"{prefix}{model_id}"
