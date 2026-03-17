import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from procman.database import Database, Process
from procman.manager import ProcessManager, normalize_autostart_mode


def _process(mode: str, autostart: bool = True, manual_stop: bool = False) -> Process:
    return Process(
        id=1,
        name="demo",
        command="sleep 10",
        working_dir=None,
        pid=1234,
        autostart=autostart,
        autostart_mode=mode,
        require_network=False,
        network_stable_seconds=0,
        manual_stop=manual_stop,
        status="stopped",
        created_at="2026-03-17 00:00:00",
        updated_at="2026-03-17 00:00:00",
    )


@pytest.mark.parametrize(
    ("mode", "expect_failure", "expect_wake"),
    [
        ("always", True, True),
        ("on_failure", True, False),
        ("on_wake", False, True),
        ("never", False, False),
    ],
)
def test_should_restart_matrix(mode: str, expect_failure: bool, expect_wake: bool) -> None:
    manager = object.__new__(ProcessManager)
    process = _process(mode=mode)
    assert manager.should_restart_process(process, wake_event=False) is expect_failure
    assert manager.should_restart_process(process, wake_event=True) is expect_wake


def test_manual_stop_overrides_mode() -> None:
    manager = object.__new__(ProcessManager)
    process = _process(mode="always", manual_stop=True)
    assert manager.should_restart_process(process, wake_event=False) is False
    assert manager.should_restart_process(process, wake_event=True) is False


def test_autostart_disabled_never_restarts() -> None:
    manager = object.__new__(ProcessManager)
    process = _process(mode="always", autostart=False)
    assert manager.should_restart_process(process, wake_event=False) is False
    assert manager.should_restart_process(process, wake_event=True) is False


def test_normalize_autostart_mode_accepts_hyphen() -> None:
    assert normalize_autostart_mode("on-failure") == "on_failure"


def test_database_status_update_clears_pid_on_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "procman.db"

    monkeypatch.setattr("procman.database.DATABASE_PATH", db_path)
    monkeypatch.setattr(
        "procman.database.ensure_directories",
        lambda: db_path.parent.mkdir(parents=True, exist_ok=True),
    )

    db = Database()
    try:
        created = db.create_process(
            name="pid-clear-test",
            command="sleep 10",
            pid=9876,
            autostart=True,
            autostart_mode="always",
            status="running",
        )
        assert created.pid == 9876

        stopped = db.update_process_status("pid-clear-test", "stopped", manual_stop=True)
        assert stopped is not None
        assert stopped.status == "stopped"
        assert stopped.pid is None
        assert stopped.manual_stop is True

        running = db.update_process_status("pid-clear-test", "running", pid=2222, manual_stop=False)
        assert running is not None
        assert running.status == "running"
        assert running.pid == 2222
        assert running.manual_stop is False
    finally:
        db.close()


def test_stop_marks_manual_stop_before_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = object.__new__(ProcessManager)
    calls: list[str] = []

    process = _process(mode="always", manual_stop=False)

    class FakeDb:
        def get_process_by_name(self, name: str) -> Process:
            assert name == "demo"
            return process

        def update_process_manual_stop(self, name: str, manual_stop: bool) -> Process:
            assert name == "demo"
            assert manual_stop is True
            calls.append("manual")
            return replace(process, manual_stop=True)

        def update_process_status(
            self,
            name: str,
            status: str,
            pid: int | None = None,
            manual_stop: bool | None = None,
        ) -> Process:
            assert name == "demo"
            assert status == "stopped"
            assert manual_stop is True
            calls.append("status")
            return replace(process, status="stopped", pid=None, manual_stop=True)

    manager.db = FakeDb()
    monkeypatch.setattr(manager, "_is_process_running", lambda pid: True)

    def _kill_process(pid: int) -> None:
        assert pid == process.pid
        calls.append("kill")

    monkeypatch.setattr(manager, "_kill_process", _kill_process)
    monkeypatch.setattr("procman.manager.remove_pid_file", lambda name: calls.append("pidfile"))

    manager.stop("demo")

    assert calls[:2] == ["manual", "kill"]


def test_enable_autostart_does_not_reset_manual_stop() -> None:
    manager = object.__new__(ProcessManager)
    process = _process(mode="on_failure", autostart=False, manual_stop=True)
    captured: dict[str, object] = {}

    class FakeDb:
        def get_process_by_name(self, name: str) -> Process:
            assert name == "demo"
            return process

        def update_process_autostart_settings(
            self,
            name: str,
            enabled: bool,
            autostart_mode: str,
            require_network: bool,
            network_stable_seconds: int,
            manual_stop: bool | None = None,
        ) -> Process:
            captured["name"] = name
            captured["enabled"] = enabled
            captured["mode"] = autostart_mode
            captured["manual_stop"] = manual_stop
            return replace(
                process,
                autostart=enabled,
                autostart_mode=autostart_mode,
                require_network=require_network,
                network_stable_seconds=network_stable_seconds,
            )

    class FakeBackend:
        def enable(self, _process: object) -> None:
            return None

    manager.db = FakeDb()
    manager.autostart_backend = FakeBackend()

    updated = manager.enable_autostart("demo")
    assert updated.autostart is True
    assert updated.manual_stop is True
    assert captured["manual_stop"] is None


def test_database_restores_from_legacy_when_primary_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary_db = tmp_path / "home" / "procman.db"
    legacy_db = tmp_path / "tmp" / "procman.db"
    primary_db.parent.mkdir(parents=True, exist_ok=True)
    legacy_db.parent.mkdir(parents=True, exist_ok=True)

    for path in (primary_db, legacy_db):
        db = sqlite3.connect(path)
        db.execute(
            """
            CREATE TABLE processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                command TEXT NOT NULL,
                working_dir TEXT,
                pid INTEGER,
                autostart INTEGER NOT NULL DEFAULT 0,
                autostart_mode TEXT NOT NULL DEFAULT 'always',
                require_network INTEGER NOT NULL DEFAULT 0,
                network_stable_seconds INTEGER NOT NULL DEFAULT 15,
                manual_stop INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()
        db.close()

    legacy_conn = sqlite3.connect(legacy_db)
    legacy_conn.execute(
        """
        INSERT INTO processes
        (name, command, autostart, autostart_mode, status)
        VALUES ('legacy-task', 'sleep 1', 1, 'always', 'stopped')
        """
    )
    legacy_conn.commit()
    legacy_conn.close()

    monkeypatch.setattr("procman.database.DATABASE_PATH", primary_db)
    monkeypatch.setattr("procman.database.LEGACY_DATABASE_PATH", legacy_db)
    monkeypatch.setattr(
        "procman.database.ensure_directories",
        lambda: primary_db.parent.mkdir(parents=True, exist_ok=True),
    )

    db = Database()
    try:
        restored = db.get_process_by_name("legacy-task")
        assert restored is not None
        assert restored.command == "sleep 1"
    finally:
        db.close()
