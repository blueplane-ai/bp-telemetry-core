# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Shell completion support for the CLI.
"""

import os
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


def get_completion_script(shell: str, prog_name: str = "blueplane") -> str:
    """
    Generate shell completion script.

    Args:
        shell: Shell type (bash, zsh, fish)
        prog_name: Program name

    Returns:
        Completion script as string
    """
    if shell == "bash":
        return f"""
# Bash completion for {prog_name}
_blueplane_completion() {{
    local IFS=$'\\n'
    local response

    response=$(env COMP_WORDS="${{COMP_WORDS[*]}}" COMP_CWORD=$COMP_CWORD _{prog_name.upper()}_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read type value <<< "$completion"

        if [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        elif [[ $type == 'dir' ]]; then
            COMPREPLY+=("${{value}}/")
        elif [[ $type == 'file' ]]; then
            COMPREPLY+=($value)
        fi
    done

    return 0
}}

complete -o nospace -F _blueplane_completion {prog_name}
"""
    elif shell == "zsh":
        return f"""
# Zsh completion for {prog_name}
#compdef {prog_name}

_{prog_name}_completion() {{
    local -a completions
    local -a completions_with_descriptions
    local -a response
    (( ! $+commands[{prog_name}] )) && return 1

    response=("${{(@f)$(env COMP_WORDS="${{words[*]}}" COMP_CWORD=${{#words[@]}} _{prog_name.upper()}_COMPLETE=zsh_complete {prog_name})}}")

    for type key descr in "${{response[@]}}"; do
        if [[ "${{type}}" == "plain" ]]; then
            if [[ "${{descr}}" == "_" ]]; then
                completions+=("${{key}}")
            else
                completions_with_descriptions+=("${{key}}:${{descr}}")
            fi
        elif [[ "${{type}}" == "dir" ]]; then
            _path_files -/
        elif [[ "${{type}}" == "file" ]]; then
            _path_files -f
        fi
    done

    if [ -n "${{completions_with_descriptions[1]}}" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ -n "${{completions[1]}}" ]; then
        compadd -U -V unsorted -a completions
    fi
}}

if [[ $ZSH_VERSION ]]; then
    autoload -U compinit && compinit
    compdef _{prog_name}_completion {prog_name}
fi
"""
    elif shell == "fish":
        return f"""
# Fish completion for {prog_name}
function __{prog_name}_completion
    set -l response (env COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) _{prog_name.upper()}_COMPLETE=fish_complete {prog_name})

    for completion in $response
        set -l metadata (string split "," $completion)

        if test $metadata[1] = "plain"
            echo $metadata[2]
        end
    end
end

complete -c {prog_name} -f -a "(__{prog_name}_completion)"
"""
    else:
        raise ValueError(f"Unsupported shell: {shell}")


def install_completion(shell: str, prog_name: str = "blueplane") -> bool:
    """
    Install shell completion for the specified shell.

    Args:
        shell: Shell type (bash, zsh, fish)
        prog_name: Program name

    Returns:
        True if successful, False otherwise
    """
    try:
        script = get_completion_script(shell, prog_name)

        if shell == "bash":
            # Try different locations for bash completion
            completion_dirs = [
                Path.home() / ".bash_completion.d",
                Path("/etc/bash_completion.d"),
                Path("/usr/local/etc/bash_completion.d"),
            ]

            for completion_dir in completion_dirs:
                if completion_dir.exists() or completion_dir.parent.exists():
                    completion_dir.mkdir(parents=True, exist_ok=True)
                    completion_file = completion_dir / prog_name
                    completion_file.write_text(script)

                    console.print(f"[green]Bash completion installed to {completion_file}[/green]")
                    console.print("[yellow]Reload your shell or run: source ~/.bashrc[/yellow]")
                    return True

            # Fallback: append to .bashrc
            bashrc = Path.home() / ".bashrc"
            with open(bashrc, "a") as f:
                f.write(f"\n# {prog_name} completion\n")
                f.write(script)

            console.print(f"[green]Bash completion added to {bashrc}[/green]")
            console.print("[yellow]Reload your shell or run: source ~/.bashrc[/yellow]")

        elif shell == "zsh":
            # Zsh completion directory
            completion_dir = Path.home() / ".zsh" / "completions"
            completion_dir.mkdir(parents=True, exist_ok=True)

            completion_file = completion_dir / f"_{prog_name}"
            completion_file.write_text(script)

            # Ensure the directory is in fpath
            zshrc = Path.home() / ".zshrc"
            fpath_line = f"fpath=({completion_dir} $fpath)"

            if zshrc.exists():
                content = zshrc.read_text()
                if fpath_line not in content:
                    with open(zshrc, "a") as f:
                        f.write(f"\n# Add {prog_name} completions to fpath\n")
                        f.write(f"{fpath_line}\n")
                        f.write("autoload -U compinit && compinit\n")

            console.print(f"[green]Zsh completion installed to {completion_file}[/green]")
            console.print("[yellow]Reload your shell or run: source ~/.zshrc[/yellow]")

        elif shell == "fish":
            # Fish completion directory
            completion_dir = Path.home() / ".config" / "fish" / "completions"
            completion_dir.mkdir(parents=True, exist_ok=True)

            completion_file = completion_dir / f"{prog_name}.fish"
            completion_file.write_text(script)

            console.print(f"[green]Fish completion installed to {completion_file}[/green]")
            console.print("[yellow]Reload your shell or run: source ~/.config/fish/config.fish[/yellow]")

        return True

    except Exception as e:
        console.print(f"[red]Failed to install completion: {e}[/red]")
        return False


def show_completion_script(shell: str, prog_name: str = "blueplane"):
    """
    Display the completion script for manual installation.

    Args:
        shell: Shell type (bash, zsh, fish)
        prog_name: Program name
    """
    try:
        script = get_completion_script(shell, prog_name)

        console.print(f"[cyan]# {shell.title()} completion script for {prog_name}[/cyan]")
        console.print(script)
        console.print()
        console.print("[yellow]To install manually, add this script to your shell configuration.[/yellow]")

        if shell == "bash":
            console.print("[dim]Add to ~/.bashrc or ~/.bash_completion[/dim]")
        elif shell == "zsh":
            console.print("[dim]Save as ~/.zsh/completions/_blueplane and add to fpath[/dim]")
        elif shell == "fish":
            console.print("[dim]Save as ~/.config/fish/completions/blueplane.fish[/dim]")

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")