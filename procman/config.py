"""Configuration constants for procman."""

import os
from pathlib import Path

# Use local filesystem for SQLite database to avoid NFS locking issues
LOCAL_DATA_DIR = Path("/tmp") / ".procman" / os.environ.get("USER", "unknown")

# Fallback to home for logs/pids
DATA_DIR = Path.home() / ".procman"
DATABASE_PATH = LOCAL_DATA_DIR / "procman.db"
LOGS_DIR = DATA_DIR / "logs"
PIDS_DIR = DATA_DIR / "pids"

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
    require_network INTEGER NOT NULL DEFAULT 0,
    network_stable_seconds INTEGER NOT NULL DEFAULT 15,
    status TEXT NOT NULL CHECK(status IN ('running', 'stopped', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def ensure_directories() -> None:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    PIDS_DIR.mkdir(exist_ok=True)
