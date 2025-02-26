import click
import importlib
from pathlib import Path
import logging
import os
import sys

"""
Top level CLI that registers commands with this logic:

- Find all subdirectories WITH __init__.py
- Fetch a 'cli' click.group() from __init__.py if it exists, or create one
- For all python files in the subdirectory:
    - If the file defines a 'cli' click.group(), add it to the subdirectory's group
    - If the file defines a 'main' click.command(), add it to the subdirectory's group
- If any commands are added to the subdirectory's group, add the group to the main CLI
"""

def register_commands(cli: click.Group) -> None:
    """Find all command groups in the scripts directory."""
    scripts_dir = Path(__file__).parent
    
    # for each subdirectory, try to import subdir.__init__
    for subdir in scripts_dir.glob('**'):
        if not subdir.is_dir():
            continue

        # get group from __init__.py or create a new one
        subdir_import = f"scripts.{subdir.name}"
        try:
            init_module = importlib.import_module(subdir_import+'.__init__')
        except ImportError:
            continue
        if hasattr(init_module, 'cli'):
            group = init_module.cli
        else:
            @click.group()
            def group():
                pass

        # add commands from the subdirectory
        for item in subdir.glob('*.py'):
            if item.name == '__init__.py':
                continue
            file_import = f"{subdir_import}.{item.stem}"
            module = importlib.import_module(file_import)
            if type(getattr(module, 'cli', None)) == click.Group:
                group.add_command(module.cli, name=item.stem)
            elif type(getattr(module, 'main', None)) == click.Command:
                group.add_command(module.main, name=item.stem)

        # add the group to the main cli
        if group.commands:
            cli.add_command(group, name=subdir.name)

@click.group()
@click.option('--log-level', '-l',
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
              default='WARNING',
              help='Logging level.')
def cli(log_level):
    """Main CLI entry point for the vault tool."""
    logging.basicConfig(level=log_level)

@cli.command()
@click.option('--shell', '-s', type=click.Choice(['bash', 'zsh', 'fish']), 
              help='Shell to generate completion script for. Defaults to auto-detect.')
def completion(shell):
    """Install tab completion for the CLI.
    
    Examples:
        # Auto-detect shell and print instructions
        $ vault completion
        
        # Generate completion script for bash
        $ vault completion --shell=bash > ~/.vault-complete.bash
        
        # Generate completion script for zsh
        $ vault completion --shell=zsh > ~/.vault-complete.zsh
        
        # Generate completion script for fish
        $ vault completion --shell=fish > ~/.config/fish/completions/vault.fish
    """
    # Auto-detect shell if not specified
    if not shell:
        shell = os.environ.get('SHELL', '')
        if 'bash' in shell:
            shell = 'bash'
        elif 'zsh' in shell:
            shell = 'zsh'
        elif 'fish' in shell:
            shell = 'fish'
        else:
            click.echo("Could not auto-detect shell. Please specify with --shell option.")
            return

    # Get the script name (executable name)
    script_name = os.path.basename(sys.argv[0])
    env_var = f"_{script_name.replace('-', '_').upper()}_COMPLETE"
    
    if shell == 'bash':
        click.echo(f"# Save the completion script:")
        click.echo(f"{env_var}=bash_source {script_name} > ~/.{script_name}-complete.bash")
        click.echo("\n# Then add this line to your ~/.bashrc:")
        click.echo(f". ~/.{script_name}-complete.bash")
    elif shell == 'zsh':
        click.echo(f"# Save the completion script:")
        click.echo(f"{env_var}=zsh_source {script_name} > ~/.{script_name}-complete.zsh")
        click.echo("\n# Then add this line to your ~/.zshrc:")
        click.echo(f". ~/.{script_name}-complete.zsh")
    elif shell == 'fish':
        click.echo(f"# Save the completion script to the fish completions directory:")
        click.echo(f"{env_var}=fish_source {script_name} > ~/.config/fish/completions/{script_name}.fish")

register_commands(cli)

if __name__ == "__main__":
    cli()