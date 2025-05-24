"""Allows running the CLI via 'python -m codexy'."""

# Ensure that the main CLI function is called when running as a module.
# Import from the 'cli' module located at the root level relative to the package directory.
# This assumes the parent directory containing 'cli.py' is accessible when running the module.
from .cli.main import codexy

if __name__ == "__main__":
    # Pass an empty object for context, similar to the original entry point check
    codexy(obj={})
