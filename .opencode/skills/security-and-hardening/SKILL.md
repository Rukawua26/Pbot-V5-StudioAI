---
name: security-and-hardening
description: Use ONLY for secrets, .env, API keys, authentication, permissions, shell scripts, external data, network access, dependencies, MCP, plugins, generated artifacts, logs, local databases, or hardening changes.
---

# Security And Hardening

Apply least privilege and avoid expanding the attack surface.

Required checks:

- Never print, commit, or persist secrets from `.env`, API keys, exchange credentials, or tokens.
- Do not commit local `.db` files, logs, generated reports, or environment-specific artifacts.
- Treat shell scripts and external data as high-risk inputs.
- Avoid broad filesystem, network, MCP, or plugin permissions without a concrete need.
- Prefer explicit denial or confirmation for destructive commands.
- Keep remote services and MCP for a later phase unless the task explicitly requires them.

If a change touches trading runtime and security, also apply `runtime-ops-and-trading-safety`.
