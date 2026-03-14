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
            self.conn.execute(
                "ALTER TABLE processes ADD COLUMN autostart INTEGER NOT NULL DEFAULT 0"
            )

    def create_process(
        self,
        name: str,
        command: str,
        working_dir: Optional[str] = None,
        pid: Optional[int] = None,
        autostart: bool = False,
        status: str = "running",
    ) -> Process:
        """Create a new process record."""
        cursor = self.conn.execute(
            """
            INSERT INTO processes (name, command, working_dir, pid, autostart, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, command, working_dir, pid, int(autostart), status),
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
    ) -> Optional[Process]:
        """Update process status and optionally PID."""
        if pid is not None:
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
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
                """,
                (status, name),
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
        return Process(**data)
