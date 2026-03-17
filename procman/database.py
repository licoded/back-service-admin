"""Database operations for procman using SQLite."""

import sqlite3
from dataclasses import dataclass
from typing import Optional

from procman.config import DATABASE_PATH, SQLITE_CREATE_TABLE, ensure_directories


@dataclass
class Process:
    """Data class representing a process record."""

    id: int
    name: str
    command: str
    working_dir: Optional[str]
    pid: Optional[int]
    autostart: bool
    autostart_mode: str
    require_network: bool
    network_stable_seconds: int
    manual_stop: bool
    status: str
    created_at: str
    updated_at: str


class Database:
    """SQLite database wrapper for process management."""

    def __init__(self) -> None:
        """Initialize database and create table if needed."""
        ensure_directories()
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy connection initialization."""
        if self._conn is None:
            self._conn = sqlite3.connect(DATABASE_PATH)
            self._conn.row_factory = sqlite3.Row
            self._create_table()
        return self._conn

    def _create_table(self) -> None:
        """Create the processes table if it doesn't exist."""
        self.conn.execute(SQLITE_CREATE_TABLE)
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        """Apply lightweight forward-compatible schema migrations."""
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(processes)").fetchall()
        }
        if "autostart" not in columns:
            self._add_column_if_missing(
                "ALTER TABLE processes ADD COLUMN autostart INTEGER NOT NULL DEFAULT 0"
            )
        added_autostart_mode = False
        if "autostart_mode" not in columns:
            added_autostart_mode = True
            self._add_column_if_missing(
                "ALTER TABLE processes "
                "ADD COLUMN autostart_mode TEXT NOT NULL DEFAULT 'always'"
            )
        if "require_network" not in columns:
            self._add_column_if_missing(
                "ALTER TABLE processes ADD COLUMN require_network INTEGER NOT NULL DEFAULT 0"
            )
        if "network_stable_seconds" not in columns:
            self._add_column_if_missing(
                "ALTER TABLE processes "
                "ADD COLUMN network_stable_seconds INTEGER NOT NULL DEFAULT 15"
            )
        if "manual_stop" not in columns:
            self._add_column_if_missing(
                "ALTER TABLE processes ADD COLUMN manual_stop INTEGER NOT NULL DEFAULT 0"
            )
        if added_autostart_mode:
            # Map legacy records: autostart-enabled jobs keep old behavior (`always`).
            self.conn.execute(
                """
                UPDATE processes
                SET autostart_mode = CASE
                    WHEN autostart = 1 THEN 'always'
                    ELSE 'never'
                END
                """
            )

    def create_process(
        self,
        name: str,
        command: str,
        working_dir: Optional[str] = None,
        pid: Optional[int] = None,
        autostart: bool = False,
        autostart_mode: str = "always",
        require_network: bool = False,
        network_stable_seconds: int = 15,
        manual_stop: bool = False,
        status: str = "running",
    ) -> Process:
        """Create a new process record."""
        cursor = self.conn.execute(
            """
            INSERT INTO processes (
                name,
                command,
                working_dir,
                pid,
                autostart,
                autostart_mode,
                require_network,
                network_stable_seconds,
                manual_stop,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                command,
                working_dir,
                pid,
                int(autostart),
                autostart_mode,
                int(require_network),
                network_stable_seconds,
                int(manual_stop),
                status,
            ),
        )
        self.conn.commit()
        return self.get_process_by_id(cursor.lastrowid)

    def get_process_by_name(self, name: str) -> Optional[Process]:
        """Get a process by its unique name."""
        cursor = self.conn.execute(
            "SELECT * FROM processes WHERE name = ?",
            (name,),
        )
        row = cursor.fetchone()
        return self._row_to_process(row) if row else None

    def get_process_by_id(self, process_id: int) -> Optional[Process]:
        """Get a process by its ID."""
        cursor = self.conn.execute(
            "SELECT * FROM processes WHERE id = ?",
            (process_id,),
        )
        row = cursor.fetchone()
        return self._row_to_process(row) if row else None

    def get_all_processes(self) -> list[Process]:
        """Get all process records."""
        cursor = self.conn.execute("SELECT * FROM processes ORDER BY created_at DESC")
        return [self._row_to_process(row) for row in cursor.fetchall()]

    def get_processes_by_status(self, status: str) -> list[Process]:
        """Get all processes with a specific status."""
        cursor = self.conn.execute(
            "SELECT * FROM processes WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [self._row_to_process(row) for row in cursor.fetchall()]

    def update_process_status(
        self,
        name: str,
        status: str,
        pid: Optional[int] = None,
        manual_stop: Optional[bool] = None,
    ) -> Optional[Process]:
        """Update process status and optionally PID."""
        if pid is not None:
            if manual_stop is None:
                cursor = self.conn.execute(
                    """
                    UPDATE processes
                    SET status = ?, pid = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ?
                    """,
                    (status, pid, name),
                )
            else:
                cursor = self.conn.execute(
                    """
                    UPDATE processes
                    SET status = ?, pid = ?, manual_stop = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ?
                    """,
                    (status, pid, int(manual_stop), name),
                )
        else:
            clear_pid = status in {"stopped", "failed"}
            if manual_stop is None:
                if clear_pid:
                    cursor = self.conn.execute(
                        """
                        UPDATE processes
                        SET status = ?, pid = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE name = ?
                        """,
                        (status, name),
                    )
                else:
                    cursor = self.conn.execute(
                        """
                        UPDATE processes
                        SET status = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE name = ?
                        """,
                        (status, name),
                    )
            else:
                if clear_pid:
                    cursor = self.conn.execute(
                        """
                        UPDATE processes
                        SET status = ?, pid = NULL, manual_stop = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE name = ?
                        """,
                        (status, int(manual_stop), name),
                    )
                else:
                    cursor = self.conn.execute(
                        """
                        UPDATE processes
                        SET status = ?, manual_stop = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE name = ?
                        """,
                        (status, int(manual_stop), name),
                    )
        self.conn.commit()
        return self.get_process_by_name(name) if cursor.rowcount > 0 else None

    def update_process_pid(self, name: str, pid: int) -> Optional[Process]:
        """Update process PID."""
        cursor = self.conn.execute(
            """
            UPDATE processes
            SET pid = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
            """,
            (pid, name),
        )
        self.conn.commit()
        return self.get_process_by_name(name) if cursor.rowcount > 0 else None

    def update_process_autostart(self, name: str, enabled: bool) -> Optional[Process]:
        """Update autostart configuration."""
        cursor = self.conn.execute(
            """
            UPDATE processes
            SET autostart = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
            """,
            (int(enabled), name),
        )
        self.conn.commit()
        return self.get_process_by_name(name) if cursor.rowcount > 0 else None

    def update_process_autostart_settings(
        self,
        name: str,
        enabled: bool,
        autostart_mode: str,
        require_network: bool,
        network_stable_seconds: int,
        manual_stop: Optional[bool] = None,
    ) -> Optional[Process]:
        """Update autostart-related configuration."""
        if manual_stop is None:
            cursor = self.conn.execute(
                """
                UPDATE processes
                SET autostart = ?, autostart_mode = ?, require_network = ?,
                    network_stable_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
                """,
                (int(enabled), autostart_mode, int(require_network), network_stable_seconds, name),
            )
        else:
            cursor = self.conn.execute(
                """
                UPDATE processes
                SET autostart = ?, autostart_mode = ?, require_network = ?,
                    network_stable_seconds = ?, manual_stop = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
                """,
                (
                    int(enabled),
                    autostart_mode,
                    int(require_network),
                    network_stable_seconds,
                    int(manual_stop),
                    name,
                ),
            )
        self.conn.commit()
        return self.get_process_by_name(name) if cursor.rowcount > 0 else None

    def update_process_manual_stop(self, name: str, manual_stop: bool) -> Optional[Process]:
        """Update manual stop flag."""
        cursor = self.conn.execute(
            """
            UPDATE processes
            SET manual_stop = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
            """,
            (int(manual_stop), name),
        )
        self.conn.commit()
        return self.get_process_by_name(name) if cursor.rowcount > 0 else None

    def delete_process(self, name: str) -> bool:
        """Delete a process by name."""
        cursor = self.conn.execute("DELETE FROM processes WHERE name = ?", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _row_to_process(self, row: sqlite3.Row) -> Process:
        """Convert a SQLite row to a Process object."""
        data = dict(row)
        data["autostart"] = bool(data.get("autostart", 0))
        data["autostart_mode"] = str(data.get("autostart_mode", "always"))
        data["require_network"] = bool(data.get("require_network", 0))
        data["network_stable_seconds"] = int(data.get("network_stable_seconds", 15))
        data["manual_stop"] = bool(data.get("manual_stop", 0))
        return Process(**data)

    def _add_column_if_missing(self, sql: str) -> None:
        """Best-effort column migration that tolerates concurrent initializers."""
        try:
            self.conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
