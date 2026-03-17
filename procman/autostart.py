"""Platform-specific autostart integration."""

import os
import platform
import re
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess

import psutil

from procman.config import LOGS_DIR


@dataclass
class AutostartProcess:
    """Process metadata needed to configure autostart."""

    name: str
    working_dir: str | None
    require_network: bool
    network_stable_seconds: int


class AutostartBackend:
    """Base autostart integration."""

    def enable(self, process: AutostartProcess) -> None:
        raise NotImplementedError

    def disable(self, name: str) -> None:
        raise NotImplementedError

    def ensure_loaded(self, process: AutostartProcess) -> None:
        """Ensure autostart integration is loaded for a process."""
        return None


class LaunchdAutostartBackend(AutostartBackend):
    """Manage per-user autostart on macOS using launchd agents."""

    def __init__(self) -> None:
        self._agents_dir = Path.home() / "Library" / "LaunchAgents"

    def enable(self, process: AutostartProcess) -> None:
        self._agents_dir.mkdir(parents=True, exist_ok=True)

        plist_path = self._plist_path(process.name)
        plist_path.write_bytes(self._plist_contents(process))

        self._run_launchctl("bootout", self._service_target(process.name), check=False)
        self._run_launchctl("bootstrap", self._domain_target(), str(plist_path), check=True)
        self._run_launchctl("enable", self._service_target(process.name), check=True)
        self._run_launchctl("kickstart", "-k", self._service_target(process.name), check=True)

    def disable(self, name: str) -> None:
        plist_path = self._plist_path(name)
        self._run_launchctl("bootout", self._service_target(name), check=False)
        self._run_launchctl("disable", self._service_target(name), check=False)
        if plist_path.exists():
            plist_path.unlink()

    def ensure_loaded(self, process: AutostartProcess) -> None:
        """Re-bootstrap a missing launchd service if plist exists."""
        if self._is_loaded(process.name):
            return

        plist_path = self._plist_path(process.name)
        if not plist_path.exists():
            return

        self._run_launchctl("bootstrap", self._domain_target(), str(plist_path), check=True)
        self._run_launchctl("enable", self._service_target(process.name), check=True)
        self._run_launchctl("kickstart", "-k", self._service_target(process.name), check=True)

    def _plist_contents(self, process: AutostartProcess) -> bytes:
        plist = ET.Element("plist", version="1.0")
        root_dict = ET.SubElement(plist, "dict")

        self._append_key_value(root_dict, "Label", self._label(process.name))
        self._append_key_array(
            root_dict,
            "ProgramArguments",
            [sys.executable, "-m", "procman", "autostart-watch", process.name],
        )
        self._append_key_value(root_dict, "RunAtLoad", True)
        self._append_key_value(root_dict, "KeepAlive", True)
        self._append_key_value(
            root_dict,
            "WorkingDirectory",
            process.working_dir or str(Path.home()),
        )
        self._append_environment_variables(root_dict)
        self._append_key_value(root_dict, "StandardOutPath", str(self._log_path(process.name)))
        self._append_key_value(root_dict, "StandardErrorPath", str(self._log_path(process.name)))

        contents = ET.tostring(plist, encoding="utf-8", xml_declaration=False)
        header = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        )
        return header + contents + b"\n"

    def _append_key_value(self, root: ET.Element, key: str, value: str | bool) -> None:
        ET.SubElement(root, "key").text = key
        if isinstance(value, bool):
            ET.SubElement(root, "true" if value else "false")
        else:
            ET.SubElement(root, "string").text = value

    def _append_key_array(self, root: ET.Element, key: str, values: list[str]) -> None:
        ET.SubElement(root, "key").text = key
        array = ET.SubElement(root, "array")
        for value in values:
            ET.SubElement(array, "string").text = value

    def _append_environment_variables(self, root: ET.Element) -> None:
        env_vars = {
            "PATH": os.environ.get("PATH", ""),
        }
        ET.SubElement(root, "key").text = "EnvironmentVariables"
        env_dict = ET.SubElement(root, "dict")
        for key, value in env_vars.items():
            ET.SubElement(env_dict, "key").text = key
            ET.SubElement(env_dict, "string").text = value

    def _plist_path(self, name: str) -> Path:
        return self._agents_dir / f"{self._label(name)}.plist"

    def _label(self, name: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "-", name)
        return f"com.procman.{safe_name}"

    def _log_path(self, name: str) -> Path:
        return LOGS_DIR / f"{name}.log"

    def _domain_target(self) -> str:
        return f"gui/{os.getuid()}"

    def _service_target(self, name: str) -> str:
        return f"{self._domain_target()}/{self._label(name)}"

    def _is_loaded(self, name: str) -> bool:
        completed = self._run_launchctl("print", self._service_target(name), check=False)
        return completed.returncode == 0

    def _run_launchctl(self, *args: str, check: bool) -> CompletedProcess[str]:
        completed = subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "launchctl failed"
            raise RuntimeError(message)
        return completed


class UnsupportedAutostartBackend(AutostartBackend):
    """Fallback backend for unsupported platforms."""

    def enable(self, process: AutostartProcess) -> None:
        raise RuntimeError(
            f"Autostart is not supported on {platform.system()} yet. "
            "macOS is implemented; Ubuntu 20.04 support is planned."
        )

    def disable(self, name: str) -> None:
        return None


def get_autostart_backend() -> AutostartBackend:
    """Return the platform-specific autostart backend."""
    system = platform.system()
    if system == "Darwin":
        return LaunchdAutostartBackend()
    return UnsupportedAutostartBackend()


def wait_for_network_stability(
    stable_seconds: int,
    timeout_seconds: int = 2,
    check_interval_seconds: int = 5,
) -> None:
    """Block until outbound network has remained reachable long enough."""
    stable_deadline = time.monotonic() + max(stable_seconds, 0)

    while True:
        if _has_network(timeout_seconds):
            if time.monotonic() >= stable_deadline:
                return
        else:
            stable_deadline = time.monotonic() + max(stable_seconds, 0)

        time.sleep(check_interval_seconds)


def _has_network(timeout_seconds: int) -> bool:
    """Check whether basic outbound network connectivity is available."""
    for host, port in [("1.1.1.1", 53), ("8.8.8.8", 53)]:
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                return True
        except OSError:
            continue
    return _has_active_non_loopback_interface()


def _has_active_non_loopback_interface() -> bool:
    """Fallback check for environments that block public DNS probes."""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for interface, interface_stats in stats.items():
        if not interface_stats.isup:
            continue
        addresses = addrs.get(interface, [])
        for address in addresses:
            if address.family not in (socket.AF_INET, socket.AF_INET6):
                continue
            if address.address.startswith("127.") or address.address == "::1":
                continue
            if address.address.startswith("fe80:"):
                continue
            return True
    return False
