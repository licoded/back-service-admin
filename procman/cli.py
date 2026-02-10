"""CLI interface for procman using Typer."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from procman.manager import ProcessManager

app = typer.Typer(
    name="procman",
    help="Simple process manager for shell scripts and executables (no sudo required)",
    add_completion=False,
)

console = Console()


@app.command()
def start(
    script: str = typer.Argument(..., help="Command or script to execute"),
    name: str = typer.Option(..., "--name", "-n", help="Unique name for the process"),
    cwd: Optional[str] = typer.Option(None, "--cwd", "-c", help="Working directory"),
) -> None:
    """Start a new process and run it in the background."""
    manager = ProcessManager()

    try:
        process = manager.start(name, script, cwd)
        console.print(
            f"[green]✓[/green] Process '{process.name}' started successfully (PID: {process.pid})"
        )
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command()
def stop(
    name: str = typer.Argument(..., help="Name of the process to stop"),
) -> None:
    """Stop a running process."""
    manager = ProcessManager()

    try:
        process = manager.stop(name)
        console.print(f"[green]✓[/green] Process '{process.name}' stopped")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command()
def restart(
    name: str = typer.Argument(..., help="Name of the process to restart"),
) -> None:
    """Restart a process."""
    manager = ProcessManager()

    try:
        process = manager.restart(name)
        console.print(
            f"[green]✓[/green] Process '{process.name}' restarted (PID: {process.pid})"
        )
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command("list")
def list_processes() -> None:
    """List all managed processes."""
    manager = ProcessManager()

    try:
        processes = manager.list_all()

        if not processes:
            console.print("[yellow]No processes managed[/yellow]")
            return

        # Create table
        table = Table(title="Managed Processes")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("PID", style="green")
        table.add_column("Command", style="white")
        table.add_column("Created", style="dim")

        for proc in processes:
            # Color code status
            status_color = {
                "running": "green",
                "stopped": "yellow",
                "failed": "red",
            }.get(proc.status, "white")

            table.add_row(
                proc.name,
                f"[{status_color}]{proc.status}[/{status_color}]",
                str(proc.pid) if proc.pid else "-",
                proc.command[:50] + "..." if len(proc.command) > 50 else proc.command,
                proc.created_at[:19],  # Truncate microseconds
            )

        console.print(table)

    finally:
        manager.close()


@app.command()
def logs(
    name: str = typer.Argument(..., help="Name of the process"),
    tail: bool = typer.Option(False, "--tail", "-t", help="Show last 20 lines"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
) -> None:
    """View logs for a process."""
    manager = ProcessManager()

    try:
        log_path = manager.get_log_path(name)

        if not log_path.exists():
            console.print(f"[yellow]No logs found for process '{name}'[/yellow]")
            raise typer.Exit(0)

        if tail:
            # Show last 20 lines
            with open(log_path, "r") as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    console.print(line.rstrip())
        elif follow:
            # Follow mode
            import time

            console.print(f"[dim]Following logs for '{name}' (Ctrl+C to exit)[/dim]\n")

            # Seek to end
            with open(log_path, "r") as f:
                f.seek(0, 2)  # Go to end

                try:
                    while True:
                        line = f.readline()
                        if line:
                            console.print(line.rstrip())
                        else:
                            time.sleep(0.1)
                except KeyboardInterrupt:
                    console.print("\n[dim]Stopped following logs[/dim]")
        else:
            # Show all logs
            with open(log_path, "r") as f:
                for line in f:
                    console.print(line.rstrip())

    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command()
def delete(
    name: str = typer.Argument(..., help="Name of the process to delete"),
) -> None:
    """Delete a process from management (must be stopped first)."""
    manager = ProcessManager()

    try:
        if manager.delete(name):
            console.print(f"[green]✓[/green] Process '{name}' deleted")
        else:
            console.print(f"[yellow]Process '{name}' not found[/yellow]")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
