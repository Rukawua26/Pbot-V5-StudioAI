# Contributing to Pbot V5ARCH DEV

Thanks for contributing.

## Workflow

1. Fork or branch from `main`.
2. Create a focused branch:
   - `feat/<topic>`
   - `fix/<topic>`
   - `docs/<topic>`
3. Run local checks before opening a PR.
4. Open a PR with a clear summary and risk notes.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Validation Checklist

- Bot starts without exceptions.
- `python -m py_compile` passes on changed files.
- No secrets committed (`.env`, DB, logs, model binaries).
- README/docs updated when behavior changes.

## Commit Style

Use concise prefixes:

- `feat:` new capability
- `fix:` bug fix
- `refactor:` internal restructure
- `docs:` documentation updates
- `chore:` maintenance

Examples:

- `fix: stabilize latency quarantine thresholds`
- `docs: add troubleshooting section for SIZE_ERROR`

## Pull Request Expectations

Include:

- What changed
- Why it changed
- Risk and rollback plan
- Validation evidence (logs/screenshots/commands)

## Security Rules

Never commit:

- `.env` or credentials
- API keys or tokens
- local DB/log files
- model binaries unless explicitly required and approved
