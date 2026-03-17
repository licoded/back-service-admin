"""CLI interface for procman using Typer."""

from datetime import datetime, timezone
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
autostart_app = typer.Typer(help="Manage autostart configuration for a process")
app.add_typer(autostart_app, name="autostart")

console = Console()


def _format_local_timestamp(value: str) -> str:
    """Convert a SQLite UTC timestamp to local time for display."""
    try:
        utc_dt = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return utc_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value[:19]


def _watch_log(message: str) -> None:
    """Write a timestamped autostart-watch log line."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _render_process_list() -> None:
    """Render the managed process list."""
    manager = ProcessManager()

    try:
        processes = manager.list_all()

        if not processes:
            console.print("[yellow]No processes managed[/yellow]")
            return

        table = Table(title="Managed Processes")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("PID", style="green")
        table.add_column("Auto", style="magenta")
        table.add_column("Command", style="white")
        table.add_column("Created", style="dim")

        for proc in processes:
            status_color = {
                "running": "green",
                "stopped": "yellow",
                "failed": "red",
            }.get(proc.status, "white")

            table.add_row(
                proc.name,
                f"[{status_color}]{proc.status}[/{status_color}]",
                str(proc.pid) if proc.pid else "-",
                "yes" if proc.autostart else "no",
                proc.command[:50] + "..." if len(proc.command) > 50 else proc.command,
                _format_local_timestamp(proc.created_at),
            )

        console.print(table)
    finally:
        manager.close()


@app.command()
def start(
    script: str = typer.Argument(..., help="Command or script to execute"),
    name: str = typer.Option(..., "--name", "-n", help="Unique name for the process"),
    cwd: Optional[str] = typer.Option(None, "--cwd", "-c", help="Working directory"),
    autostart: bool = typer.Option(
        False,
        "--autostart/--no-autostart",
        help="Automatically restore this process on supported platforms",
    ),
    require_network: bool = typer.Option(
        False,
        "--require-network/--no-require-network",
        help="Wait for outbound network before autostart restores this process",
    ),
    network_stable_seconds: int = typer.Option(
        15,
        "--network-stable-seconds",
        min=0,
        help="Seconds that network must remain reachable before autostart restores",
    ),
) -> None:
    """Start a new process and run it in the background."""
    manager = ProcessManager()

    try:
        process = manager.start(
            name,
            script,
            cwd,
            autostart,
            require_network,
            network_stable_seconds,
        )
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
    _render_process_list()


@app.command("ls")
def list_processes_alias() -> None:
    """Alias for list."""
    _render_process_list()


@app.command()
def show(name: str = typer.Argument(..., help="Name of the process")) -> None:
    """Show full details for a process, including the complete command."""
    manager = ProcessManager()

    try:
        process = manager.get_status(name)
        table = Table(show_header=False, box=None)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Name", process.name)
        table.add_row("Status", process.status)
        table.add_row("PID", str(process.pid) if process.pid else "-")
        table.add_row("Autostart", "yes" if process.autostart else "no")
        table.add_row("Require Network", "yes" if process.require_network else "no")
        table.add_row("Network Stable", str(process.network_stable_seconds))
        table.add_row("Working Dir", process.working_dir or "-")
        table.add_row("Created", _format_local_timestamp(process.created_at))
        table.add_row("Updated", _format_local_timestamp(process.updated_at))
        table.add_row("Command", process.command)
        console.print(table)
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
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


@autostart_app.command("enable")
def enable_autostart(
    name: str = typer.Argument(..., help="Name of the process"),
    require_network: Optional[bool] = typer.Option(
        None,
        "--require-network/--no-require-network",
        help="Override whether autostart must wait for outbound network",
    ),
    network_stable_seconds: Optional[int] = typer.Option(
        None,
        "--network-stable-seconds",
        min=0,
        help="Override the autostart network stability wait in seconds",
    ),
) -> None:
    """Enable autostart for a process."""
    manager = ProcessManager()

    try:
        process = manager.enable_autostart(
            name,
            require_network=require_network,
            network_stable_seconds=network_stable_seconds,
        )
        console.print(f"[green]✓[/green] Enabled autostart for '{process.name}'")
    except (RuntimeError, ValueError) as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@autostart_app.command("disable")
def disable_autostart(name: str = typer.Argument(..., help="Name of the process")) -> None:
    """Disable autostart for a process."""
    manager = ProcessManager()

    try:
        process = manager.disable_autostart(name)
        console.print(f"[green]✓[/green] Disabled autostart for '{process.name}'")
    except (RuntimeError, ValueError) as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command("autostart-run", hidden=True)
def autostart_run(name: str = typer.Argument(..., help="Name of the process")) -> None:
    """Internal command used by platform autostart integrations."""
    manager = ProcessManager()

    try:
        manager.ensure_running(name)
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


@app.command("autostart-watch", hidden=True)
def autostart_watch(name: str = typer.Argument(..., help="Name of the process")) -> None:
    """Internal watchdog used by platform autostart integrations."""
    manager = ProcessManager()

    try:
        import time

        last_running_pid: Optional[int] = None
        waiting_for_network = False

        while True:
            process = manager.get_status(name)
            if process.status != "running" and process.require_network:
                if not waiting_for_network:
                    _watch_log(
                        f"autostart-watch: waiting for network stability "
                        f"({process.network_stable_seconds}s) for '{name}'"
                    )
                    waiting_for_network = True
            else:
                waiting_for_network = False

            try:
                manager.wait_for_start_conditions(name)
                process = manager.ensure_running(name)
            except RuntimeError as e:
                _watch_log(f"autostart-watch: restart failed for '{name}': {e}")
                last_running_pid = None
                time.sleep(5)
                continue

            if process.status == "running" and process.pid != last_running_pid:
                _watch_log(
                    f"autostart-watch: '{name}' is running (pid={process.pid})"
                )
                last_running_pid = process.pid
            time.sleep(5)
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    finally:
        manager.close()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
