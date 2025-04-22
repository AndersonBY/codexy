# -*- coding: utf-8 -*-

"""Approval logic for executing commands and file operations."""

import shlex
from enum import Enum
from pathlib import Path
from typing import List, TypedDict, Optional, Set, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig

# --- Enums and Types ---


class ApprovalMode(Enum):
    """Defines the different levels of automatic approval."""

    SUGGEST = "suggest"  # Ask for everything except known safe read-only commands
    AUTO_EDIT = "auto-edit"  # Auto-approve safe reads and file edits, ask for commands
    FULL_AUTO = "full-auto"  # Auto-approve safe reads, edits, sandboxed commands
    DANGEROUS_AUTO = "dangerous-auto"  # Auto-approve everything without sandbox (use with extreme caution)


class SafetyAssessmentResult(TypedDict):
    """Result structure for safety assessment."""

    type: str  # 'auto-approve', 'ask-user', 'reject'
    reason: Optional[str]  # Explanation for auto-approve/reject
    group: Optional[str]  # Category for safe commands
    run_in_sandbox: bool  # Whether execution requires sandboxing


# --- Session State ---

# Commands approved with "Always" for the current session
# Stores derived keys (e.g., "exec:ls", "apply_diff")
_session_always_approved: Set[str] = set()


def clear_session_approvals():
    """Clears the set of commands marked as 'always approved' for the session."""
    _session_always_approved.clear()
    print("[Approval] Cleared session 'always approve' list.")


# --- Known Safe Commands (Read-only focus) ---

# List of commands considered safe for auto-approval in 'suggest' mode and above.
# Focuses on read-only operations and basic navigation/status checks.
# This list should be conservative.
KNOWN_SAFE_COMMANDS = {
    "ls",
    "dir",  # List directory contents
    "cat",
    "type",  # Display file contents
    "head",
    "tail",  # Display parts of files
    "pwd",
    "cd ..",  # Print/change directory (cd without args is often safe, cd .. too)
    "git status",  # Check git status
    "git diff",
    "git show",  # Show git changes/objects
    "git log",  # Show git history
    "git branch",  # List git branches
    "grep",
    "findstr",
    "rg",  # Search for text in files
    "find",  # Find files (read-only usage assumed)
    "wc",  # Word count
    "which",
    "where",  # Locate command
    "true",  # No-op
    "echo",  # Print arguments (generally safe)
    # Add more safe read-only commands here if needed
}

# --- Helper Functions ---


def _command_to_string(command_list: List[str]) -> str:
    """Converts a command list back into a string for matching."""
    # Use shlex.join to handle parameters with spaces or special characters more safely
    # Note: shlex.join is available in Python 3.8+
    try:
        return shlex.join(command_list)
    except AttributeError:  # shlex.join may not exist in older versions
        # Provide a basic fallback
        return " ".join(shlex.quote(arg) for arg in command_list)


def _is_command_prefix_safe(command_list: List[str], safe_prefixes: Set[str]) -> bool:
    """Checks if the command starts with a known safe prefix."""
    if not command_list:
        return False
    command_str = _command_to_string(command_list)
    for prefix in safe_prefixes:
        # Ensure prefix matching considers spaces correctly
        if command_str == prefix or command_str.startswith(prefix + " "):
            return True
    return False


def _derive_command_key(tool_name: str, tool_args: Dict) -> str:
    """
    Generates a stable key for a tool call to use in the 'always approve' cache.
    For exec commands, uses 'exec:<base_command>'. For others, uses tool name.
    """
    if tool_name == "execute_command":
        # 'command' parameter may not exist or be of the wrong type
        cmd_input = tool_args.get("command")
        if not cmd_input or not isinstance(cmd_input, str):
            return "exec:invalid_input"  # Provide a more specific key

        try:
            # Use shlex.split to parse the command string into a list
            cmd_list = shlex.split(cmd_input)
            if not cmd_list:
                return "exec:empty_command"  # Empty command
            # Use only the base command (first element) as the key
            base_cmd = cmd_list[0]
            # Basic key cleanup (e.g., remove path components)
            # Use os.path.basename to ensure cross-platform compatibility
            base_cmd = Path(base_cmd).name
            # Further cleanup, remove potential extensions, etc., adjust as needed
            # base_cmd = base_cmd.split('.')[0]
            return f"exec:{base_cmd}"
        except ValueError:
            # If shlex.split fails (e.g., mismatched quotes)
            return "exec:parse_error"
        except Exception:
            # Catch other potential parsing errors
            return "exec:unknown_parse_error"

    # For file editing or other tools, usually don't want to base 'always' on content.
    # Now just use the tool name as a simple key, but 'always' might be less useful here.
    elif tool_name in ["write_to_file", "apply_diff", "apply_patch"]:
        return tool_name  # Simple key, but 'always' might be less useful here.
    else:
        # For unknown or other tools, use the name directly.
        return tool_name


def add_to_always_approved(tool_name: str, tool_args: Dict):
    """Adds a command key to the session's always-approved set."""
    call_key = _derive_command_key(tool_name, tool_args)
    if call_key:
        print(f"[Approval] Adding '{call_key}' to session's always-approved list.")
        _session_always_approved.add(call_key)


# --- Core Approval Logic ---


def is_safe_readonly_command(command_list: List[str], config: "AppConfig") -> Optional[Dict[str, str]]:
    """
    Checks if a command is likely safe and read-only.
    Returns a dict with 'reason' and 'group' if safe, otherwise None.
    """
    if not command_list:
        return None

    # 1. Check user-configured safe commands first
    # Ensure safe_commands is treated as a list, default to empty if missing/invalid
    user_safe_commands_list = config.get("safe_commands", [])
    if not isinstance(user_safe_commands_list, list):
        user_safe_commands_list = []  # Handle configuration format errors
    user_safe_commands = set(user_safe_commands_list)

    if _is_command_prefix_safe(command_list, user_safe_commands):
        return {"reason": "User-defined safe command", "group": "User Config"}

    # 2. Check built-in known safe commands (exact match or prefix)
    if _is_command_prefix_safe(command_list, KNOWN_SAFE_COMMANDS):
        # Provide more specific reasons based on the command if possible
        cmd_base = command_list[0]
        reason = f"Safe read-only command ({cmd_base})"
        group = "Read/Info"
        if cmd_base in ["ls", "dir", "find", "grep", "findstr", "rg"]:
            group = "Searching"
        elif cmd_base in ["cat", "type", "head", "tail", "wc"]:
            group = "Reading Files"
        elif cmd_base == "pwd":
            group = "Navigating"
        elif cmd_base == "cd" and command_list == ["cd", ".."]:  # Be specific about safe 'cd' usage
            group = "Navigating"
            reason = "Change to parent directory"
        elif cmd_base == "git":
            # Only allow specific safe git subcommands
            safe_git_subcommands = {"status", "diff", "show", "log", "branch"}
            if len(command_list) > 1 and command_list[1] in safe_git_subcommands:
                # Check for potential unsafe flags (this is a basic example that can be expanded)
                unsafe_flags = {"--hard", "--force", "-f", "-D"}
                if any(flag in command_list[2:] for flag in unsafe_flags):
                    return None  # If it contains unsafe flags, consider it unsafe
                group = "Versioning"
                reason = f"Safe Git read command ({' '.join(command_list[:2])})"
            else:
                return None  # Other git commands require approval
        elif cmd_base in ["which", "where"]:
            group = "Utility"
        elif cmd_base == "echo":
            # Note that echo can be used to write to files (e.g. echo "..." > file)
            # Note that echo can be used to write to files (e.g. echo "..." > file)
            command_str = _command_to_string(command_list)
            if ">" in command_str or ">>" in command_str:  # Simple redirection check
                return None  # echo with redirection is unsafe
            group = "Printing"
            reason = "Echo command (no redirection)"
        elif cmd_base == "true":
            group = "Utility"
            reason = "No-op (true)"

        return {"reason": reason, "group": group}

    # TODO: Add more sophisticated checks if needed (e.g., analyzing flags)

    return None


def can_auto_approve(
    tool_name: str, tool_args: Dict, policy: ApprovalMode, config: "AppConfig"
) -> SafetyAssessmentResult:
    """
    Determines if a tool call can be automatically approved based on the policy.
    Now includes session 'always approve' check.
    """
    # 0. Check session 'always approve' cache FIRST
    call_key = _derive_command_key(tool_name, tool_args)
    if call_key and call_key in _session_always_approved:
        print(f"[Approval] Auto-approving '{call_key}' due to previous 'Always' selection.")
        # Usually, always approving means no sandbox
        return SafetyAssessmentResult(
            type="auto-approve",
            reason="Previously approved always",
            group="Session",
            run_in_sandbox=False,  # User explicitly approved always, usually means trust the operation
        )

    # 1. Handle specific tool types
    if tool_name == "execute_command":
        # Get command list from tool_args (assume it's already parsed as a list, or we need to parse it)
        # Note: _derive_command_key already handles parsing, but here we may need to parse again for safety checks
        cmd_input = tool_args.get("command")
        cmd_list: List[str] = []
        if isinstance(cmd_input, str):
            try:
                cmd_list = shlex.split(cmd_input)
            except ValueError:
                return SafetyAssessmentResult(
                    type="reject", reason="Cannot parse command", group=None, run_in_sandbox=False
                )
        elif isinstance(cmd_input, list) and all(isinstance(item, str) for item in cmd_input):
            cmd_list = cmd_input  # If already a list, use it directly
        else:
            return SafetyAssessmentResult(
                type="reject", reason="Invalid command structure in args", group=None, run_in_sandbox=False
            )

        if not cmd_list:
            return SafetyAssessmentResult(type="reject", reason="Empty command", group=None, run_in_sandbox=False)

        # Check if it's a known safe read-only command
        safe_info = is_safe_readonly_command(cmd_list, config)
        if safe_info:
            # Safe read-only commands are approved in all modes (no sandbox)
            return SafetyAssessmentResult(
                type="auto-approve",
                reason=safe_info["reason"],
                group=safe_info["group"],
                run_in_sandbox=False,
            )

        # If not inherently safe, decision depends on policy
        if policy == ApprovalMode.SUGGEST or policy == ApprovalMode.AUTO_EDIT:
            return SafetyAssessmentResult(type="ask-user", reason=None, group=None, run_in_sandbox=False)
        elif policy == ApprovalMode.FULL_AUTO:
            print("[Approval] Auto-approving command for sandboxed execution (full-auto mode).")
            # In full-auto mode, non-explicitly safe commands need to be run in a sandbox
            return SafetyAssessmentResult(
                type="auto-approve",
                reason="Full-auto mode policy",
                group="Commands",
                run_in_sandbox=True,  # Need sandbox
            )
        elif policy == ApprovalMode.DANGEROUS_AUTO:
            print("[Approval] Auto-approving command UNSANDBOXED (dangerous-auto mode).")
            return SafetyAssessmentResult(
                type="auto-approve",
                reason="Dangerous-auto mode policy",
                group="Commands",
                run_in_sandbox=False,  # Dangerous mode: no sandbox
            )
        else:  # Should not happen
            return SafetyAssessmentResult(
                type="reject", reason="Unknown approval policy", group=None, run_in_sandbox=False
            )

    elif tool_name in ["write_to_file", "apply_diff", "apply_patch"]:  # File modification tools
        if policy == ApprovalMode.SUGGEST:
            return SafetyAssessmentResult(type="ask-user", reason=None, group=None, run_in_sandbox=False)
        elif policy in [ApprovalMode.AUTO_EDIT, ApprovalMode.FULL_AUTO, ApprovalMode.DANGEROUS_AUTO]:
            # Auto-Edit, Full-Auto, Dangerous-Auto approve file modifications (unsandboxed)
            print(f"[Approval] Auto-approving file modification '{tool_name}' ({policy.value} mode).")
            # TODO: Add path validation here? Ensure it's within the project boundaries?
            # Can check if 'path' in tool_args is within allowed ranges here
            # file_path_str = tool_args.get("path")
            # if file_path_str and not is_path_allowed(file_path_str, config):
            #     return SafetyAssessmentResult(type="reject", reason="File path not allowed", ...)
            return SafetyAssessmentResult(
                type="auto-approve",
                reason=f"{policy.value} policy",
                group="File Edit",
                run_in_sandbox=False,  # File modifications usually not run in a sandbox
            )
        else:  # Should not happen
            return SafetyAssessmentResult(
                type="reject", reason="Unknown approval policy", group=None, run_in_sandbox=False
            )

    elif tool_name in ["read_file", "list_files"]:  # Read-only file tools
        # These are generally safe and can be auto-approved in all modes (unsandboxed)
        print(f"[Approval] Auto-approving read-only file operation '{tool_name}'.")
        return SafetyAssessmentResult(
            type="auto-approve",
            reason="Read-only file tool",
            group="File Read",
            run_in_sandbox=False,
        )

    else:  # Unknown tool
        # Always ask the user for unknown tools, regardless of policy (safer default)
        print(f"[Approval] Unknown tool '{tool_name}', asking user.")
        return SafetyAssessmentResult(type="ask-user", reason="Unknown tool", group=None, run_in_sandbox=False)
