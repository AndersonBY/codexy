# -*- coding: utf-8 -*-

"""Model information utilities for codexy."""

import sys

# Default from oai/models.go (but this might change)
# Using a common default for unknown models.
DEFAULT_MAX_TOKENS = 4096
# o4-mini seems to be an alias for gpt-4-turbo-preview which is 128k context, but its output is 4k.
# Let's be conservative for o4-mini for now, or use a value that reflects typical usage patterns if known.
# If 'o4-mini' is used with codexy, it might be a specific internal configuration.
# For now, let's assume it aligns with a common smaller context unless specified otherwise.
# Update: From the config, o4-mini is the default agentic model.
# It's likely an alias for a model with a context length like gpt-4-turbo-preview (128k input, 4k output)
# or gpt-3.5-turbo (4k/16k).
# The old placeholder in agent.py used 128000 for o4-mini. Let's use that.

MODEL_MAX_TOKENS = {
    "gpt-4-turbo": 128000,      # Covers gpt-4-turbo-preview, gpt-4-0125-preview, gpt-4-1106-preview etc.
    "gpt-4-32k": 32768,
    "gpt-4.1-32k": 32768,     # Assuming gpt-4.1 is an alias that can also have 32k
    "gpt-4": 8192,
    "gpt-4.1": 8192,          # Assuming gpt-4.1 is an alias for gpt-4 8k
    "gpt-3.5-turbo-16k": 16384,
    "gpt-3.5-turbo": 4096,
    "o4-mini": 128000,        # Based on previous placeholder in agent.py
    # Add other models as needed
}

def get_model_max_tokens(model_name: str) -> int:
    """
    Returns the maximum context tokens for a given model name.
    Uses a dictionary for known models and a prefix-matching approach.
    """
    # Check for exact matches first
    if model_name in MODEL_MAX_TOKENS:
        return MODEL_MAX_TOKENS[model_name]
    
    # Check for well-known prefixes in a specific order to avoid issues
    # e.g., "gpt-4-turbo" should be checked before "gpt-4"
    # More specific names should come first.
    # This is a bit naive; a more robust solution might use regex or a more structured model DB.
    # For now, this handles the known cases.
    if "gpt-4-turbo" in model_name: # Catches variants like gpt-4-turbo-preview, gpt-4-0125-preview etc.
        return MODEL_MAX_TOKENS["gpt-4-turbo"]
    if "gpt-4-32k" in model_name:
        return MODEL_MAX_TOKENS["gpt-4-32k"]
    if "gpt-4" in model_name: # Catches base gpt-4 and other non-turbo/32k variants
        return MODEL_MAX_TOKENS["gpt-4"]
    if "gpt-3.5-turbo-16k" in model_name:
        return MODEL_MAX_TOKENS["gpt-3.5-turbo-16k"]
    if "gpt-3.5-turbo" in model_name:
        return MODEL_MAX_TOKENS["gpt-3.5-turbo"]
    if "o4-mini" in model_name: # If it's part of a longer name
        return MODEL_MAX_TOKENS["o4-mini"]

    print(f"Warning: Unknown model name '{model_name}'. Using default max tokens: {DEFAULT_MAX_TOKENS}", file=sys.stderr)
    return DEFAULT_MAX_TOKENS
