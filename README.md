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
procman start "python worker.py" --name worker --autostart --autostart-mode on_failure
procman start "python worker.py" --name worker --autostart --require-network
```

### List all processes

```bash
procman list
procman ls
```

### Show one process

```bash
procman show myapp
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

Autostart/restart logs are written into the same per-process log file:

```bash
~/.procman/logs/<process-name>.log
```

`autostart-watch` lines include timestamps, for example:

```text
[2026-03-17 08:58:38] autostart-watch: 'ipynb-ecnu8th-proxy' is running (pid=92207)
```

## Autostart

Enable autostart only for selected processes:

```bash
procman autostart enable myapp
procman autostart disable myapp
procman autostart enable myapp --require-network --network-stable-seconds 20
procman autostart enable myapp --mode on_wake
```

Autostart mode values:
- `always`: restart on both failure and wake
- `on_failure`: restart only after failure
- `on_wake`: restart only on wake events
- `never`: never auto-restart

Manual stop behavior:
- `procman stop <name>` marks the process as manually stopped.
- Manually stopped processes are not auto-restarted, including after sleep/wake.
- Use `procman start <... --name ...>` or `procman restart <name>` to clear manual stop.

Or configure it when starting the process:

```bash
procman start "python worker.py" --name worker --autostart
```

Current platform support:
- macOS: supported via per-user `launchd` agents
- Ubuntu 20.04: planned

For network-dependent tasks, autostart can wait until outbound connectivity has
been stable before restoring the process.

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
