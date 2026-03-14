"""Platform-specific autostart integration."""

import os
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutostartProcess:
    """Process metadata needed to configure autostart."""

    name: str
    working_dir: str | None


class AutostartBackend:
    """Base autostart integration."""

    def enable(self, process: AutostartProcess) -> None:
        raise NotImplementedError

    def disable(self, name: str) -> None:
        raise NotImplementedError


class LaunchdAutostartBackend(AutostartBackend):
    """Manage per-user autostart on macOS using launchd agents."""

    def __init__(self) -> None:
        self._agents_dir = Path.home() / "Library" / "LaunchAgents"

    def enable(self, process: AutostartProcess) -> None:
        self._agents_dir.mkdir(parents=True, exist_ok=True)

        plist_path = self._plist_path(process.name)
        plist_path.write_bytes(self._plist_contents(process))

        self._run_launchctl("bootout", self._service_target(process.name), check=False)
        self._run_launchctl("bootstrap", self._domain_target(), str(plist_path), check=False)
        self._run_launchctl("enable", self._service_target(process.name), check=False)

    def disable(self, name: str) -> None:
        plist_path = self._plist_path(name)
        self._run_launchctl("bootout", self._service_target(name), check=False)
        self._run_launchctl("disable", self._service_target(name), check=False)
        if plist_path.exists():
            plist_path.unlink()

    def _plist_contents(self, process: AutostartProcess) -> bytes:
        plist = ET.Element("plist", version="1.0")
        root_dict = ET.SubElement(plist, "dict")

        self._append_key_value(root_dict, "Label", self._label(process.name))
        self._append_key_array(
            root_dict,
            "ProgramArguments",
            [sys.executable, "-m", "procman", "autostart-run", process.name],
        )
        self._append_key_value(root_dict, "RunAtLoad", True)
        self._append_key_value(root_dict, "KeepAlive", True)
        self._append_key_value(
            root_dict,
            "WorkingDirectory",
            process.working_dir or str(Path.home()),
        )

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

    def _plist_path(self, name: str) -> Path:
        return self._agents_dir / f"{self._label(name)}.plist"

    def _label(self, name: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "-", name)
        return f"com.procman.{safe_name}"

    def _domain_target(self) -> str:
        return f"gui/{os.getuid()}"

    def _service_target(self, name: str) -> str:
        return f"{self._domain_target()}/{self._label(name)}"

    def _run_launchctl(self, *args: str, check: bool) -> None:
        completed = subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "launchctl failed"
            raise RuntimeError(message)


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
