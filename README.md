# procman

A simple process manager for shell scripts and executables - like pm2 but without requiring sudo permissions.

## Features

- **User-space process management** - No sudo required
- **Persistent tracking** - SQLite database stores process state
- **Log rotation** - 10MB per file, keeps 5 backups
- **Beautiful CLI** - Rich terminal output with colors and tables
- **Process verification** - Detects and cleans up zombie processes
- **Supports any executable** - Bash, Shell, Python, Node.js, or anything else

## Installation

```bash
# From local directory
pip install -e .

# Or from PyPI (when published)
pip install procman
```

## Usage

### Start a process

```bash
procman start "python myscript.py" --name myapp
procman start "./myscript.sh" --name myscript --cwd /path/to/dir
procman start "uv run main.py" --name webapp
procman start "python worker.py" --name worker --autostart
```

### List all processes

```bash
procman list
```

### View logs

```bash
# View all logs
procman logs myapp

# View last 20 lines
procman logs myapp --tail

# Follow logs in real-time
procman logs myapp --follow
```

## Autostart

Enable autostart only for selected processes:

```bash
procman autostart enable myapp
procman autostart disable myapp
```

Or configure it when starting the process:

```bash
procman start "python worker.py" --name worker --autostart
```

Current platform support:
- macOS: supported via per-user `launchd` agents
- Ubuntu 20.04: planned

### Stop a process

```bash
procman stop myapp
```

### Restart a process

```bash
procman restart myapp
```

### Delete a process

```bash
procman delete myapp
```

## Data Location

All data is stored in `~/.procman/`:
- `procman.db` - SQLite database
- `logs/` - Process log files
- `pids/` - PID files for tracking

## Requirements

- Python 3.10+
- No sudo permissions needed

## License

MIT
