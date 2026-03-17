"""Core process management logic for procman."""

import time
from pathlib import Path
from typing import Optional

import psutil

from procman.autostart import (
    AutostartProcess,
    get_autostart_backend,
    wait_for_network_stability,
)
from procman.config import LOGS_DIR
from procman.daemonize import daemonize_process, remove_pid_file
from procman.database import Database, Process

AUTOSTART_MODES = {
    "always": (True, True),
    "on_failure": (True, False),
    "on_wake": (False, True),
    "never": (False, False),
}


def normalize_autostart_mode(mode: str) -> str:
    """Normalize and validate autostart mode."""
    normalized = mode.strip().lower().replace("-", "_")
    if normalized not in AUTOSTART_MODES:
        allowed = ", ".join(sorted(AUTOSTART_MODES))
        raise ValueError(f"Invalid autostart mode '{mode}'. Expected one of: {allowed}")
    return normalized


def autostart_mode_flags(mode: str) -> tuple[bool, bool]:
    """Return (restart_on_failure, restart_on_wake) flags for a mode."""
    return AUTOSTART_MODES[normalize_autostart_mode(mode)]


class ProcessManager:
    """Manages process lifecycle: start, stop, restart, status."""

    def __init__(self) -> None:
        """Initialize the process manager with database connection."""
        self.db = Database()
        self.autostart_backend = get_autostart_backend()

    def start(
        self,
        name: str,
        command: str,
        working_dir: Optional[str] = None,
        autostart: bool = False,
        autostart_mode: str = "always",
        require_network: bool = False,
        network_stable_seconds: int = 15,
    ) -> Process:
        """Start a new process.

        Args:
            name: Unique name for the process
            command: Command to execute
            working_dir: Working directory (defaults to current)

        Returns:
            Process record from database

        Raises:
            ValueError: If process name already exists
            RuntimeError: If process fails to start
        """
        # Check if process already exists
        existing = self.db.get_process_by_name(name)
        if existing:
            # Verify if actually running
            if self._is_process_running(existing.pid):
                raise ValueError(f"Process '{name}' already exists and is running")
            # Clean up stale record
            self.db.delete_process(name)

        resolved_mode = normalize_autostart_mode(autostart_mode)

        # Set up log file
        log_path = LOGS_DIR / f"{name}.log"

        # Start the daemonized process
        try:
            pid = daemonize_process(name, command, working_dir, log_path)
        except Exception as e:
            # Create failed record
            self.db.create_process(
                name,
                command,
                working_dir,
                None,
                autostart,
                resolved_mode,
                require_network,
                network_stable_seconds,
                False,
                "failed",
            )
            raise RuntimeError(f"Failed to start process: {e}")

        # Give process a moment to start
        time.sleep(0.1)

        # Verify process started
        if not self._is_process_running(pid):
            raise RuntimeError("Process failed to start or exited immediately")

        # Create database record
        process = self.db.create_process(
            name,
            command,
            working_dir,
            pid,
            autostart,
            resolved_mode,
            require_network,
            network_stable_seconds,
            False,
            "running",
        )

        if autostart:
            self.enable_autostart(
                name,
                autostart_mode=resolved_mode,
                require_network=require_network,
                network_stable_seconds=network_stable_seconds,
            )
            process = self.db.get_process_by_name(name)

        return process

    def stop(self, name: str) -> Process:
        """Stop a running process.

        Args:
            name: Process name

        Returns:
            Updated process record

        Raises:
            ValueError: If process not found or not running
        """
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        if not self._is_process_running(process.pid):
            # Process is not actually running, update status
            self.db.update_process_status(name, "stopped", manual_stop=True)
            raise ValueError(f"Process '{name}' is not running")

        # Mark manual stop intent before terminating the process to avoid
        # watchdog race windows that could otherwise restart it.
        self.db.update_process_manual_stop(name, True)

        # Kill the process
        self._kill_process(process.pid)

        # Clean up PID file
        remove_pid_file(name)

        # Update database
        return self.db.update_process_status(name, "stopped", manual_stop=True)

    def restart(self, name: str) -> Process:
        """Restart a process, or start a stopped process.

        If the process is running, it will be stopped and restarted.
        If the process is stopped, it will be started.

        Args:
            name: Process name

        Returns:
            Process record

        Raises:
            ValueError: If process not found
            RuntimeError: If process fails to start
        """
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        # Stop if running
        if process.status == "running" and self._is_process_running(process.pid):
            self._kill_process(process.pid)
            remove_pid_file(name)

        # Delete old record so start() can create a fresh one
        self.db.delete_process(name)

        # Start again
        return self.start(
            process.name,
            process.command,
            process.working_dir,
            process.autostart,
            process.autostart_mode,
            process.require_network,
            process.network_stable_seconds,
        )

    def delete(self, name: str) -> bool:
        """Delete a process from management.

        Args:
            name: Process name

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If process is still running
        """
        process = self.db.get_process_by_name(name)
        if not process:
            return False

        if process.status == "running" and self._is_process_running(process.pid):
            raise ValueError(f"Cannot delete running process '{name}'. Stop it first.")

        # Clean up PID file if exists
        remove_pid_file(name)

        # Delete from database
        return self.db.delete_process(name)

    def enable_autostart(
        self,
        name: str,
        autostart_mode: Optional[str] = None,
        require_network: Optional[bool] = None,
        network_stable_seconds: Optional[int] = None,
    ) -> Process:
        """Enable autostart for a process."""
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        resolved_require_network = (
            process.require_network if require_network is None else require_network
        )
        resolved_stable_seconds = (
            process.network_stable_seconds
            if network_stable_seconds is None
            else network_stable_seconds
        )
        resolved_mode = normalize_autostart_mode(
            process.autostart_mode if autostart_mode is None else autostart_mode
        )

        self.autostart_backend.enable(
            AutostartProcess(
                name=process.name,
                working_dir=process.working_dir,
                require_network=resolved_require_network,
                network_stable_seconds=resolved_stable_seconds,
            )
        )
        updated = self.db.update_process_autostart_settings(
            name,
            True,
            resolved_mode,
            resolved_require_network,
            resolved_stable_seconds,
        )
        if updated is None:
            raise RuntimeError(f"Failed to update autostart for '{name}'")
        return updated

    def disable_autostart(self, name: str) -> Process:
        """Disable autostart for a process."""
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        self.autostart_backend.disable(name)
        updated = self.db.update_process_autostart_settings(
            name,
            False,
            "never",
            process.require_network,
            process.network_stable_seconds,
        )
        if updated is None:
            raise RuntimeError(f"Failed to update autostart for '{name}'")
        return updated

    def ensure_running(self, name: str, respect_manual_stop: bool = True) -> Process:
        """Ensure a configured process is running."""
        process = self.get_status(name)
        if process.status == "running":
            return process
        if respect_manual_stop and process.manual_stop:
            return process
        return self.restart(name)

    def should_restart_process(self, process: Process, wake_event: bool) -> bool:
        """Decide whether a stopped process should be auto-restored now."""
        if not process.autostart:
            return False
        if process.manual_stop:
            return False

        restart_on_failure, restart_on_wake = autostart_mode_flags(process.autostart_mode)
        if wake_event and restart_on_wake:
            return True
        if not wake_event and restart_on_failure:
            return True
        return False

    def wait_for_start_conditions(self, name: str) -> Process:
        """Wait for any configured preconditions before restoring a process."""
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        if process.require_network:
            wait_for_network_stability(process.network_stable_seconds)

        return process

    def get_status(self, name: str) -> Process:
        """Get status of a process.

        Args:
            name: Process name

        Returns:
            Process record

        Raises:
            ValueError: If process not found
        """
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        # Verify actual status
        is_running = self._is_process_running(process.pid)
        if is_running and process.status != "running":
            # Process is running but DB says otherwise - update
            return self.db.update_process_status(
                name,
                "running",
                process.pid,
                manual_stop=False,
            )
        elif not is_running and process.status == "running":
            # Process died but DB doesn't know - update
            return self.db.update_process_status(name, "stopped")

        return process

    def list_all(self) -> list[Process]:
        """List all processes and verify their status.

        Returns:
            List of all process records
        """
        processes = self.db.get_all_processes()

        # Reconcile launchd services for autostart processes.
        for proc in processes:
            if proc.autostart:
                try:
                    self.autostart_backend.ensure_loaded(
                        AutostartProcess(
                            name=proc.name,
                            working_dir=proc.working_dir,
                            require_network=proc.require_network,
                            network_stable_seconds=proc.network_stable_seconds,
                        )
                    )
                except RuntimeError:
                    # Keep list command resilient; status check below still runs.
                    pass

        # Verify and update stale statuses
        for proc in processes:
            if proc.status == "running" and not self._is_process_running(proc.pid):
                self.db.update_process_status(proc.name, "stopped")
                # Refresh to get updated status
                proc = self.db.get_process_by_name(proc.name)

        return self.db.get_all_processes()

    def get_log_path(self, name: str) -> Path:
        """Get log file path for a process.

        Args:
            name: Process name

        Returns:
            Path to log file

        Raises:
            ValueError: If process not found
        """
        process = self.db.get_process_by_name(name)
        if not process:
            raise ValueError(f"Process '{name}' not found")

        return LOGS_DIR / f"{name}.log"

    def _is_process_running(self, pid: Optional[int]) -> bool:
        """Check if a process is actually running.

        Args:
            pid: Process ID to check

        Returns:
            True if running, False otherwise
        """
        if pid is None:
            return False

        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() not in (
                psutil.STATUS_ZOMBIE,
                psutil.STATUS_DEAD,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _kill_process(self, pid: int) -> None:
        """Kill a process gracefully.

        Args:
            pid: Process ID to kill

        Raises:
            RuntimeError: If process cannot be killed
        """
        try:
            proc = psutil.Process(pid)

            # Try graceful termination first
            proc.terminate()

            # Wait up to 5 seconds.
            if not self._wait_for_process_exit(pid, timeout=5):
                # Force kill if graceful termination did not work.
                proc.kill()
                if not self._wait_for_process_exit(pid, timeout=2):
                    raise RuntimeError(f"Failed to kill process {pid}: timed out")

        except psutil.NoSuchProcess:
            # Already dead
            pass
        except Exception as e:
            raise RuntimeError(f"Failed to kill process {pid}: {e}")

    def _wait_for_process_exit(self, pid: int, timeout: float) -> bool:
        """Wait until a PID is no longer running."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._is_process_running(pid):
                return True
            time.sleep(0.1)
        return not self._is_process_running(pid)

    def close(self) -> None:
        """Close database connection."""
        self.db.close()
