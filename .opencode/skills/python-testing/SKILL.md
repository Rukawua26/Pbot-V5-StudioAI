---
name: python-testing
description: Use ONLY when creating, changing, or reviewing Python tests, unittest coverage, fixtures, mocks, runtime contract tests, temporal invariance tests, or test commands in this repository.
---

# Python Testing

Follow existing repository patterns and keep tests deterministic.

Guidelines:

- Prefer existing `unittest` style unless a nearby test uses another pattern.
- Do not require real network, real Binance credentials, or live exchange state.
- Use `SNIPER_DISABLE_FILE_TELEMETRY=1` for unittest commands.
- Cover mode-specific behavior when a change can affect `PAPER`, `SHADOW`, or `REAL`.
- For runtime-critical behavior, test failure/ambiguous-state paths, not just happy paths.
- Keep tests focused; avoid broad rewrites of unrelated test files.

If tests touch runtime safety, also apply `runtime-ops-and-trading-safety`.
