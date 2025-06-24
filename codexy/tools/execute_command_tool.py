import os
import shlex
import subprocess
from pathlib import Path

from openai.types.chat import ChatCompletionToolParam

PROJECT_ROOT = Path.cwd()
DEFAULT_MAX_OUTPUT_LINES = 20


def execute_command_tool(
    command: str,
    cwd: str | None = None,
    is_sandboxed: bool = False,
    allowed_write_paths: list[Path] | None = None,
    full_stdout: bool = False,
) -> str:
    """
    Executes a shell command and returns its output (stdout and stderr).
    If is_sandboxed is True, attempts to run the command with shell=False within
    one of the allowed_write_paths.
    """
    if not command:
        return "Error: Empty command received."

    effective_cwd_path = Path(cwd) if cwd else PROJECT_ROOT
    try:
        # Resolve CWD to an absolute path to prevent relative path issues
        effective_cwd = effective_cwd_path.resolve(strict=True)
    except FileNotFoundError:
        return f"Error: Working directory '{effective_cwd_path}' not found."
    except Exception as e:
        return f"Error resolving working directory '{effective_cwd_path}': {e}"

    if not effective_cwd.is_dir():
        return f"Error: Working directory '{effective_cwd}' is not a directory."

    # --- Sandboxing Logic ---
    if is_sandboxed:
        print(f"Attempting sandboxed execution for: '{command}'")
        if not allowed_write_paths:
            print(f"[Sandbox] No allowed_write_paths provided, using project root: {PROJECT_ROOT}")
            allowed_write_paths = [PROJECT_ROOT]

        # Ensure allowed paths are resolved absolute paths
        resolved_allowed_paths = []
        for p in allowed_write_paths:
            try:
                resolved_allowed_paths.append(Path(p).resolve(strict=True))
            except Exception as e:
                return f"Error resolving allowed writable path '{p}': {e}"

        # Check if the effective CWD is within one of the allowed paths
        is_cwd_allowed = False
        for allowed_path in resolved_allowed_paths:
            if effective_cwd == allowed_path or str(effective_cwd).startswith(str(allowed_path) + os.sep):
                is_cwd_allowed = True
                break
        if not is_cwd_allowed:
            allowed_paths_str = ", ".join([str(p) for p in resolved_allowed_paths])
            return f"Error: Sandboxed command CWD '{effective_cwd}' is not within allowed paths: [{allowed_paths_str}]"

        # Use shell=False for safety - requires splitting the command string
        try:
            cmd_list = shlex.split(command)
            if not cmd_list:  # Handle empty command after split
                return "Error: Empty command after parsing for sandbox execution."
            print(f"Executing sandboxed (shell=False): {cmd_list} in '{effective_cwd}'")
            result = subprocess.run(
                cmd_list,  # Pass list of args
                shell=False,  # <<< IMPORTANT: No shell for sandboxed commands
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except Exception as e:
            # Catch errors during shlex.split or subprocess.run with shell=False
            return f"Error executing sandboxed command '{command}': {e}"

    # --- Default (Non-Sandboxed) Execution ---
    else:
        # Keep shell=True for now for non-sandboxed, but acknowledge the risk.
        # Consider switching to shell=False + shlex.split here too eventually.
        print(f"Executing command (shell=True): '{command}' in '{effective_cwd}'")
        try:
            result = subprocess.run(
                command,
                shell=True,  # <<< Risk acknowledged
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except Exception as e:
            return f"Error executing command '{command}': {e}"

    # --- Process result (common for both sandboxed and non-sandboxed) ---
    try:
        output = f"Exit Code: {result.returncode}\n"
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if not full_stdout:
            stdout_lines = stdout.splitlines()
            stderr_lines = stderr.splitlines()
            if len(stdout_lines) > DEFAULT_MAX_OUTPUT_LINES:
                stdout = (
                    "\n".join(stdout_lines[:DEFAULT_MAX_OUTPUT_LINES])
                    + f"\n... ({len(stdout_lines) - DEFAULT_MAX_OUTPUT_LINES} more lines truncated)"
                )
            if len(stderr_lines) > DEFAULT_MAX_OUTPUT_LINES:
                stderr = (
                    "\n".join(stderr_lines[:DEFAULT_MAX_OUTPUT_LINES])
                    + f"\n... ({len(stderr_lines) - DEFAULT_MAX_OUTPUT_LINES} more lines truncated)"
                )

        if stdout:
            output += f"--- stdout ---\n{stdout}\n"
        if stderr:
            output += f"--- stderr ---\n{stderr}\n"

        return output.strip()

    except subprocess.TimeoutExpired:
        return f"Error: Command '{command}' timed out after 60 seconds."
    except FileNotFoundError:
        return f"Error: Command not found or shell execution failed for '{command}'."
    except Exception as e:
        return f"Error processing result for command '{command}': {e}"


EXECUTE_COMMAND_TOOL_DEF: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "execute_command",
        "description": "Execute a CLI command on the user's system. Use this for system operations, running scripts, file manipulations (like mkdir, rm, mv), etc. Always prefer using dedicated file operation tools if available.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The CLI command to execute (e.g., 'ls -la', 'python script.py', 'mkdir new_dir').",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory to execute the command in. Defaults to the project root.",
                },
                # <<< It might be better *not* to expose sandbox/write paths/full_stdout to the LLM directly.
                # The agent should decide these based on context and policy.
                # Keeping them internal to the Python implementation.
            },
            "required": ["command"],
        },
    },
}
