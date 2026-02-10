"""Configuration constants for procman."""

import os
from pathlib import Path

# Data directory in user's home
DATA_DIR = Path.home() / ".procman"
DATABASE_PATH = DATA_DIR / "procman.db"
LOGS_DIR = DATA_DIR / "logs"
PIDS_DIR = DATA_DIR / "pids"

# Log rotation settings
MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

# Database schema
SQLITE_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    command TEXT NOT NULL,
    working_dir TEXT,
    pid INTEGER,
    status TEXT NOT NULL CHECK(status IN ('running', 'stopped', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Ensure directories exist
def ensure_directories() -> None:
    """Create data directories if they don't exist."""
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    PIDS_DIR.mkdir(exist_ok=True)
