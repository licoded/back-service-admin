"""Configuration constants for procman."""

import os
from pathlib import Path

# Persistent user data directory
DATA_DIR = Path.home() / ".procman"
DATABASE_PATH = DATA_DIR / "procman.db"
LOGS_DIR = DATA_DIR / "logs"
PIDS_DIR = DATA_DIR / "pids"

# Legacy location used by previous versions.
LEGACY_DATABASE_PATH = (
    Path("/tmp") / ".procman" / os.environ.get("USER", "unknown") / "procman.db"
)

# Log rotation settings
MAX_LOG_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# Database schema
SQLITE_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    command TEXT NOT NULL,
    working_dir TEXT,
    pid INTEGER,
    autostart INTEGER NOT NULL DEFAULT 0,
    autostart_mode TEXT NOT NULL DEFAULT 'always'
        CHECK(autostart_mode IN ('always', 'on_failure', 'on_wake', 'never')),
    require_network INTEGER NOT NULL DEFAULT 0,
    network_stable_seconds INTEGER NOT NULL DEFAULT 15,
    manual_stop INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('running', 'stopped', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PIDS_DIR.mkdir(parents=True, exist_ok=True)
