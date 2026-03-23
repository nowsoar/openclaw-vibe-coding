"""HarnessKit CLI entry point."""

import typer
from rich.console import Console

from harness_kit.config import (
    SUBDIRS,
    harness_dir,
    init_harness,
    is_initialized,
    read_config,
)

app = typer.Typer(
    name="harnesskit",
    help="Local AI Harness engineering toolkit.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _main() -> None:
    """HarnessKit — manage AI Agent runtimes like code."""


@app.command()
def init() -> None:
    """Initialize a HarnessKit project in the current directory."""
    if is_initialized():
        console.print(
            f"[yellow]⚠ Already initialized[/yellow] — "
            f"[dim]{harness_dir()} already exists.[/dim]"
        )
        raise typer.Exit(0)

    init_harness()

    console.print("[green bold]✓ Initialized HarnessKit project[/green bold]\n")
    console.print("[bold]Created:[/bold]")
    console.print(f"  [cyan].harness/config.yaml[/cyan]")
    for sub in SUBDIRS:
        console.print(f"  [cyan].harness/{sub}/[/cyan]")

    cfg = read_config()
    console.print("\n[bold]Default config:[/bold]")
    for k, v in cfg.items():
        console.print(f"  [dim]{k}[/dim]: {v}")

    console.print(
        "\n[dim]Run [bold]harnesskit --help[/bold] to see available commands.[/dim]"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
