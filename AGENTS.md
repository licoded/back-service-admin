# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

## Procman Incident Note (2026-03-17)

Root cause:
- `procman` metadata DB was stored under `/tmp/.procman/.../procman.db` (ephemeral path).
- After system cleanup/restart, DB entries disappeared, so `procman list` showed empty.
- Launchd watchdogs kept running but failed with repeated `Process '<name>' not found`.

Prevention:
- Keep process metadata DB on persistent path (`~/.procman/procman.db`), not `/tmp`.
- Keep `/tmp` only for backward-compatible migration/read fallback.
- After changing autostart/watchdog logic, always verify:
  - `procman list` contains expected tasks
  - `procman show <name>` has full command + autostart mode
  - `~/.procman/logs/<name>.log` has no repeated `not found` loops
