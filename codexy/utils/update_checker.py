# -*- coding: utf-8 -*-

"""Utility for checking for new versions of the codexy package on PyPI."""

import sys
import json
import httpx
import asyncio
from datetime import datetime, timezone
from importlib import metadata
from typing import Optional, TypedDict, cast

from packaging.version import parse as parse_version

from ..config import CONFIG_DIR
from .. import PACKAGE_NAME

# Constants
PYPI_URL_TEMPLATE = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
UPDATE_CHECK_FREQUENCY_SECONDS = 60 * 60 * 24  # Check once per day
STATE_FILE = CONFIG_DIR / "update_check.json"


class UpdateCheckState(TypedDict, total=False):
    """Structure for storing the last update check timestamp."""

    last_check_ts: float  # Store timestamp as float (seconds since epoch)


class UpdateInfo(TypedDict):
    """Structure for returning update information."""

    current_version: str
    latest_version: str


# --- State Management ---


def _read_state() -> Optional[UpdateCheckState]:
    """Reads the last check state from the JSON file."""
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "last_check_ts" in data:
                return cast(UpdateCheckState, data)  # Use cast after validation
            else:
                print(f"Warning: Invalid format in {STATE_FILE}. Ignoring.", file=sys.stderr)
                return None
    except (IOError, json.JSONDecodeError) as e:
        print(f"Warning: Could not read update check state from {STATE_FILE}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Unexpected error reading update state {STATE_FILE}: {e}", file=sys.stderr)
        return None


def _write_state(state: UpdateCheckState):
    """Writes the current check state to the JSON file."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        print(f"Error: Could not write update check state to {STATE_FILE}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error: Unexpected error writing update state {STATE_FILE}: {e}", file=sys.stderr)


# --- Version Information ---


async def _get_current_version() -> Optional[str]:
    """Gets the currently installed version of the package."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        print(f"Warning: Package '{PACKAGE_NAME}' not found. Cannot determine current version.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Error getting current version for '{PACKAGE_NAME}': {e}", file=sys.stderr)
        return None


async def _fetch_latest_version() -> Optional[str]:
    """Fetches the latest version string from PyPI."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:  # Add a timeout
            response = await client.get(PYPI_URL_TEMPLATE)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            data = response.json()
            return data.get("info", {}).get("version")
    except httpx.RequestError as e:
        # Network-related errors
        print(f"Warning: Network error checking for updates: {e}", file=sys.stderr)
        return None
    except httpx.HTTPStatusError as e:
        # Errors for 4xx/5xx responses
        print(
            f"Warning: HTTP error checking for updates: {e.response.status_code} - {e.response.text[:100]}...",
            file=sys.stderr,
        )
        return None
    except json.JSONDecodeError:
        print(f"Warning: Could not decode JSON response from PyPI for {PACKAGE_NAME}.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Unexpected error fetching latest version: {e}", file=sys.stderr)
        return None


# --- Main Check Function ---


async def check_for_updates() -> Optional[UpdateInfo]:
    """
    Checks PyPI for a newer version of the package if enough time has passed.

    Returns:
        An UpdateInfo dictionary if a newer version is found, otherwise None.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    state = _read_state()
    last_check_ts = state.get("last_check_ts", 0.0) if state else 0.0

    # Check if enough time has passed since the last check
    if (now_ts - last_check_ts) < UPDATE_CHECK_FREQUENCY_SECONDS:
        # print("Debug: Update check skipped, frequency not met.", file=sys.stderr)
        return None

    print("Checking for codexy updates...", file=sys.stderr)  # Indicate check is running

    # Get current and latest versions concurrently
    current_version_str, latest_version_str = await asyncio.gather(
        _get_current_version(),  # Run sync metadata call in thread
        _fetch_latest_version(),
    )

    # Update state regardless of whether the check succeeded, to avoid constant checks on failure
    _write_state({"last_check_ts": now_ts})

    if not current_version_str or not latest_version_str:
        print("Debug: Could not determine current or latest version.", file=sys.stderr)
        return None  # Cannot compare if either version is missing

    try:
        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)

        if latest_version > current_version:
            print(f"Update found: {current_version_str} -> {latest_version_str}", file=sys.stderr)
            return {
                "current_version": current_version_str,
                "latest_version": latest_version_str,
            }
        else:
            # print(f"Debug: Already on the latest version ({current_version_str}).", file=sys.stderr)
            return None
    except Exception as e:  # Catch errors during version parsing/comparison
        print(
            f"Warning: Error comparing versions ('{current_version_str}', '{latest_version_str}'): {e}",
            file=sys.stderr,
        )
        return None
