"""Daemonization utilities for running processes in the background."""

import os
import subprocess
from pathlib import Path
from typing import Optional

from procman.config import PIDS_DIR

DEFAULT_PATH_SEGMENTS = [
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
]


def daemonize_process(
    name: str,
    command: str,
    working_dir: Optional[str] = None,
    log_path: Optional[Path] = None,
) -> int:
    """Run a command as a daemon process.

    Args:
        name: Process name (used for PID file)
        command: Command to execute
        working_dir: Working directory for the process
        log_path: Path to log file for stdout/stderr

    Returns:
        PID of the daemonized process

    Raises:
        RuntimeError: If process fails to start
    """
    pid_file = PIDS_DIR / f"{name}.pid"

    # Set up working directory
    cwd = working_dir if working_dir else os.getcwd()

    # Set up log file
    log_file = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a")

    env = os.environ.copy()
    env["PATH"] = _build_path_env(env.get("PATH", ""))

    try:
        # Start the process as a new session leader (daemonizes it)
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            stdout=log_file if log_file else subprocess.DEVNULL,
            stderr=log_file if log_file else subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # This creates a new session, detaching from terminal
        )

        # Write PID to file immediately
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))

        return proc.pid

    except Exception as e:
        if log_file:
            log_file.close()
        raise RuntimeError(f"Failed to start process: {e}")


def _build_path_env(current_path: str) -> str:
    """Build a PATH that preserves the current environment and common binary paths."""
    segments = [segment for segment in current_path.split(":") if segment]
    for segment in DEFAULT_PATH_SEGMENTS:
        if segment not in segments:
            segments.append(segment)
    return ":".join(segments)


def read_pid_file(name: str) -> Optional[int]:
    """Read PID from file for a named process.

    Args:
        name: Process name

    Returns:
        PID if file exists and contains valid PID, None otherwise
    """
    pid_file = PIDS_DIR / f"{name}.pid"
    if not pid_file.exists():
        return None

    try:
        with open(pid_file, "r") as f:
            pid_str = f.read().strip()
            return int(pid_str) if pid_str else None
    except (ValueError, IOError):
        return None


def remove_pid_file(name: str) -> None:
    """Remove PID file for a named process.

    Args:
        name: Process name
    """
    pid_file = PIDS_DIR / f"{name}.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except OSError:
            pass
