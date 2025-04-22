_COMPLETION_SCRIPTS = {
    "bash": """
_codexy_completion() {
    local cur prev words cword
    _get_comp_words_by_ref -n : cur prev words cword

    # Basic file/directory completion for options that take paths
    if [[ "$prev" == "--image" || "$prev" == "-i" || "$prev" == "--view" || "$prev" == "-v" || "$prev" == "--writable-root" || "$prev" == "-w" || "$prev" == "--project-doc" ]]; then
        _filedir
        return 0
    fi

    # Completion for the approval-mode option
    if [[ "$prev" == "--approval-mode" || "$prev" == "-a" ]]; then
        COMPREPLY=( $(compgen -W "suggest auto-edit full-auto dangerous-auto" -- "$cur") )
        return 0
    fi

     # Completion for the model option (can add common models here if desired)
    if [[ "$prev" == "--model" || "$prev" == "-m" ]]; then
        COMPREPLY=( $(compgen -W "o4-mini o3 gpt-4.1 gpt-4o" -- "$cur") )
        return 0
    fi

    # General argument completion (e.g., main prompt) or option names
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "-h --help --version --model -m --image -i --view -v --quiet -q --config -c --writable-root -w --approval-mode -a --auto-edit --full-auto --no-project-doc --project-doc --full-stdout --notify --dangerously-auto-approve-everything --full-context -f" -- "$cur") )
    else
         # Default to file/directory completion for arguments if not an option
        _filedir
    fi

    return 0
}
complete -F _codexy_completion codexy
""",
    "zsh": """
#compdef codexy

_codexy() {
    local -a options
    options=(
        '(-h --help)'{-h,--help}'[Show help message]'
        '--version[Show version information]'
        '(-m --model)'{-m,--model=}'[Model to use]: :(o4-mini o3 gpt-4.1 gpt-4o)'
        '(-i --image)'{-i,--image=}'[Path to image file]:_files'
        '(-v --view)'{-v,--view=}'[Path to rollout file]:_files'
        '(-q --quiet)'{-q,--quiet}'[Non-interactive mode]'
        '(-c --config)'{-c,--config}'[Open instructions file]'
        '(-w --writable-root)'{-w,--writable-root=}'[Writable root for full-auto]:_files -/'
        '(-a --approval-mode)'{-a,--approval-mode=}'[Approval policy]: :(suggest auto-edit full-auto dangerous-auto)'
        '--auto-edit[Auto-approve file edits]'
        '--full-auto[Auto-approve edits and sandboxed commands]'
        '--no-project-doc[Do not include codex.md]'
        '--project-doc=[Path to project doc]:_files'
        '--full-stdout[Do not truncate stdout/stderr]'
        '--notify[Enable desktop notifications]'
        '--dangerously-auto-approve-everything[Auto-approve everything unsandboxed (DANGEROUS)]'
        '(-f --full-context)'{-f,--full-context}'[Full-context mode]'
        '*:prompt:_files'
    )
    _arguments $options
}
_codexy
""",
    "fish": """
# fish completion for codexy
complete -c codexy -f -a "completion" -d "Generate shell completion script"

# Options for main command
complete -c codexy -s h -l help -d 'Show help message'
complete -c codexy -l version -d 'Show version information'
complete -c codexy -s m -l model -d 'Model to use' -xa "o4-mini o3 gpt-4.1 gpt-4o"
complete -c codexy -s i -l image -d 'Path to image file' -r -F
complete -c codexy -s v -l view -d 'Path to rollout file' -r -F
complete -c codexy -s q -l quiet -d 'Non-interactive mode'
complete -c codexy -s c -l config -d 'Open instructions file'
complete -c codexy -s w -l writable-root -d 'Writable root for full-auto' -r -F
complete -c codexy -s a -l approval-mode -d 'Approval policy' -xa "suggest auto-edit full-auto dangerous-auto"
complete -c codexy -l auto-edit -d 'Auto-approve file edits'
complete -c codexy -l full-auto -d 'Auto-approve edits and sandboxed commands'
complete -c codexy -l no-project-doc -d 'Do not include codex.md'
complete -c codexy -l project-doc -d 'Path to project doc' -r -F
complete -c codexy -l full-stdout -d 'Do not truncate stdout/stderr'
complete -c codexy -l notify -d 'Enable desktop notifications'
complete -c codexy -l dangerously-auto-approve-everything -d 'Auto-approve everything unsandboxed (DANGEROUS)'
complete -c codexy -l full-context -d 'Full-context mode'

# Options for 'completion' command
complete -c codexy -n "__fish_seen_subcommand_from completion" -f -a "bash zsh fish" -d "Shell type"

# Default argument completion (likely file paths or prompt text)
complete -c codexy -f -a "(__fish_complete_path)"
""",
}
