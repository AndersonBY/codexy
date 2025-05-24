import os
import subprocess
import sys
import traceback
from pathlib import Path

import click
from rich.console import Console

from ..approvals import ApprovalMode
from ..config import DEFAULT_FULL_STDOUT, INSTRUCTIONS_FILEPATH, AppConfig, load_config
from ..tui import CodexTuiApp
from .completion_scripts import _COMPLETION_SCRIPTS

stderr_console = Console(stderr=True)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="codexy")
@click.option("--model", "-m", help="Model to use for completions (e.g., o4-mini).")
@click.option(
    "--image",
    "-i",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path(s) to image files to include as input.",
)
@click.option(
    "--view",
    "-v",
    type=click.Path(exists=True, dir_okay=False),
    help="Inspect a previously saved rollout instead of starting a session.",
)
@click.option("--quiet", "-q", is_flag=True, help="Non-interactive mode that only prints the assistant's final output.")
@click.option("--config", "-c", is_flag=True, help="Open the instructions file in your editor.")
@click.option(
    "--writable-root",
    "-w",
    multiple=True,
    type=click.Path(file_okay=False),
    help="Writable folder for sandbox in full-auto mode (can be specified multiple times).",
)
@click.option(
    "--approval-mode",
    "-a",
    type=click.Choice([mode.value for mode in ApprovalMode]),  # Use enum values for choices
    default=None,
    help="Override the approval policy.",
)
@click.option("--auto-edit", is_flag=True, help="Automatically approve file edits; still prompt for commands.")
@click.option("--full-auto", is_flag=True, help="Automatically approve edits and commands when executed in the sandbox.")
@click.option("--no-project-doc", is_flag=True, help="Do not automatically include the repository's 'codex.md'.")
@click.option(
    "--project-doc",
    type=click.Path(exists=True, dir_okay=False),
    help="Include an additional markdown file as context.",
)
@click.option(
    "--full-stdout",
    is_flag=True,
    default=DEFAULT_FULL_STDOUT,
    help="Do not truncate stdout/stderr from command outputs.",  # Updated help text
)
@click.option(
    "--notify",
    is_flag=True,
    default=None,  # Default to None to distinguish between not set and set to False
    help="Enable desktop notifications for responses.",
)
@click.option(
    "--flex-mode",
    is_flag=True,
    help='Enable "flex-mode" service tier (only supported by o3, o4-mini).',
)
@click.option(
    "--dangerously-auto-approve-everything",
    is_flag=True,
    help="Skip all confirmation prompts and execute commands without sandboxing (DANGEROUS).",
)
@click.option("--full-context", "-f", is_flag=True, help='Launch in "full-context" mode.')
@click.argument("prompt", required=False)
def codexy(
    prompt: str | None,
    model: str | None,
    image: tuple[str, ...],
    view: str | None,
    quiet: bool,
    config: bool,
    writable_root: tuple[str, ...],
    approval_mode: str | None,
    auto_edit: bool,
    full_auto: bool,
    no_project_doc: bool,
    project_doc: str | None,
    full_stdout: bool,
    notify: bool | None,
    flex_mode: bool,
    dangerously_auto_approve_everything: bool,
    full_context: bool,
):
    """Interactive REPL for Codex agent.

    codexy         Interactive REPL
    codexy "..."   Initial prompt for interactive REPL
    """
    # --- Completion script generation ---
    if len(sys.argv) > 1 and sys.argv[1] == "completion":
        if len(sys.argv) > 2:
            shell = sys.argv[2]
            generate_completion(shell)
        else:
            generate_completion(None)  # Ask user or default
        return

    # --- Execute main application logic ---
    run_repl(
        prompt=prompt,
        model=model,
        image=image,  # Pass tuple directly
        view=view,
        quiet=quiet,
        handle_config_flag=config,  # Renamed to avoid conflict with config dict
        writable_root=writable_root,  # Pass tuple directly
        cli_approval_mode=approval_mode,  # Renamed to avoid conflict
        auto_edit=auto_edit,
        full_auto=full_auto,
        no_project_doc=no_project_doc,
        project_doc=project_doc,
        full_stdout=full_stdout,  # Pass the flag value
        notify=notify,
        flex_mode=flex_mode,  # Pass the flag value
        dangerously_auto_approve_everything=dangerously_auto_approve_everything,
        full_context=full_context,
    )


def generate_completion(shell: str | None):  # Added type hint
    """Generate shell completion script."""
    if shell is None:
        # Simple prompt if shell not provided
        shell = click.prompt("Which shell? (bash, zsh, fish)", type=str)

    assert isinstance(shell, str)

    script = _COMPLETION_SCRIPTS.get(shell)
    if script:
        click.echo(script)
        click.echo(f"\n# To enable completion, add the above to your shell's config file (e.g., ~/.{shell}rc)")
        click.echo("# Or follow instructions specific to your shell completion setup.")
    else:
        click.echo(f"Error: Unsupported shell '{shell}'. Choose from bash, zsh, fish.")


# Renamed kwargs keys to avoid conflicts and be more explicit
def run_repl(
    prompt: str | None,
    model: str | None,
    image: tuple[str, ...],
    view: str | None,
    quiet: bool,
    handle_config_flag: bool,  # Renamed from config
    writable_root: tuple[str, ...],
    cli_approval_mode: str | None,  # Renamed from approval_mode
    auto_edit: bool,
    full_auto: bool,
    no_project_doc: bool,
    project_doc: str | None,
    full_stdout: bool,  # Added parameter
    notify: bool | None,
    flex_mode: bool,  # Added parameter
    dangerously_auto_approve_everything: bool,
    full_context: bool,
):
    """Run the interactive REPL."""

    # --- Handle Action Flags (like --config) FIRST ---
    if handle_config_flag:
        editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "vim")
        try:
            if not INSTRUCTIONS_FILEPATH.exists():
                INSTRUCTIONS_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
                INSTRUCTIONS_FILEPATH.touch()
                stderr_console.print(f"Created instructions file: {INSTRUCTIONS_FILEPATH}")
            else:
                stderr_console.print(f"Opening instructions file: {INSTRUCTIONS_FILEPATH}")
            # Use subprocess.call for potentially better editor handling
            return_code = subprocess.call([editor, str(INSTRUCTIONS_FILEPATH)])
            if return_code != 0:
                stderr_console.print(f"[yellow]Editor exited with code {return_code}.[/yellow]")
        except FileNotFoundError:
            stderr_console.print(f"[bold red]Error: Editor '{editor}' not found. Set the EDITOR environment variable.[/bold red]")
        except Exception as e:
            stderr_console.print(f"[bold red]Error opening file '{INSTRUCTIONS_FILEPATH}': {e}[/bold red]")
        sys.exit(0)  # Exit after handling config flag

    # --- Configuration Loading ---
    config_options = {
        "disable_project_doc": no_project_doc,
        "project_doc_path": Path(project_doc) if project_doc else None,
        "is_full_context": full_context,
        "flex_mode": flex_mode,  # Pass to load_config
        "full_stdout": full_stdout,  # Pass to load_config
    }
    try:
        # Pass runtime flags to load_config
        app_config: AppConfig = load_config(cwd=Path.cwd(), **config_options)

        # Override loaded config with CLI flags if provided
        if model:
            app_config["model"] = model
        if notify is not None:  # Check for None explicitly
            app_config["notify"] = notify

        app_config["full_stdout"] = full_stdout

        # Determine the final approval mode based on CLI flags and config
        effective_mode = ApprovalMode(app_config["effective_approval_mode"])

        # CLI flags override config
        if cli_approval_mode:
            effective_mode = ApprovalMode(cli_approval_mode)
        if auto_edit and effective_mode == ApprovalMode.SUGGEST:
            effective_mode = ApprovalMode.AUTO_EDIT
        if full_auto and effective_mode in [ApprovalMode.SUGGEST, ApprovalMode.AUTO_EDIT]:
            effective_mode = ApprovalMode.FULL_AUTO
        if dangerously_auto_approve_everything:  # Highest priority override
            effective_mode = ApprovalMode.DANGEROUS_AUTO

        # Update the effective mode in the config dict
        app_config["effective_approval_mode"] = effective_mode.value

        # Resolve writable roots here instead of in AppConfig
        resolved_writable_roots = [str(Path(p).resolve()) for p in writable_root]
        app_config["writable_roots"] = resolved_writable_roots

    except Exception as e:
        stderr_console.print(f"[bold red]Error loading configuration:[/bold red] {e}")
        traceback.print_exc(file=sys.stderr)  # Print traceback for debugging
        sys.exit(1)

    # --- Handle Other Flags/Modes (like --view, --quiet) ---
    if view:
        # TODO: Implement viewing rollout file
        stderr_console.print(f"Viewing rollout file '{view}' is not implemented yet.")
        sys.exit(0)

    if quiet:
        # TODO: Implement quiet mode (non-TUI)
        stderr_console.print("Quiet mode is not implemented yet.")
        sys.exit(1)

    if full_context:
        # TODO: Implement full context mode (non-TUI)
        stderr_console.print("Full context mode is not implemented yet.")
        sys.exit(1)

    # --- API Key Check ---
    # Check API key *after* loading config, as it might be set there
    # (although current load_config doesn't load it from file, only env)
    if not app_config.get("api_key"):
        stderr_console.print(
            "\n[bold red]Missing OpenAI API key.[/bold red]\n\n"
            "Set the environment variable [bold]OPENAI_API_KEY[/bold] or place it in a [bold].env[/bold] file.\n"
            "Create a key at: [link=https://platform.openai.com/account/api-keys]https://platform.openai.com/account/api-keys[/link]\n"
        )
        sys.exit(1)

    # --- Start Textual TUI ---
    try:
        # Pass resolved_writable_roots directly to TuiApp if needed, or Agent
        tui_app = CodexTuiApp(
            config=app_config,
            initial_prompt=prompt,
            initial_images=list(image),
        )
        tui_app.run()
        # Exit with TUI's return code if available, otherwise 0
        sys.exit(tui_app.return_code or 0)
    except Exception as e:
        # Catch potential errors during TUI setup or run
        stderr_console.print(f"[bold red]Error running Textual TUI:[/bold red] {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def main():
    """Entry point for the package."""
    # Custom help text including completion subcommand
    ctx = click.Context(codexy, info_name="codexy")
    help_text = ctx.get_help()
    # Check if help flag is present *before* parsing arguments
    if "--help" in sys.argv or "-h" in sys.argv:
        click.echo(help_text)
        click.echo("\nCommands:\n  completion  Generate shell completion script.")
        sys.exit(0)

    # Let click handle the actual command execution and argument parsing
    codexy()  # No obj={} needed here, click handles context


if __name__ == "__main__":
    main()
