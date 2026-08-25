---
name: runtime-ops-and-trading-safety
description: Hardens runtime operations for the trading bot. Use when changing exchange connectivity, execution flows, persistent runtime state, reconciliation, emergency exits, watchdogs, or operational observability.
---

# Runtime Ops and Trading Safety

## Overview

The bot is not a generic app. It is a long-running trading system with live capital risk, partial failures, asynchronous exchange state, and operational recovery requirements. This skill exists to protect runtime correctness first, then code quality.

## When to Use

- Changing startup, bootstrap, or exchange connectivity
- Modifying order lifecycle, execution, reconciliation, or wallet sync
- Touching runtime persistence or recovery logic
- Adjusting guardian, watchdog, emergency close, or stop-loss behavior
- Adding telemetry, audit events, or operational alerts
- Investigating incidents where bot state and exchange state may diverge

## Core Rules

### 1. Protect capital before convenience

- Prefer a safe halt over ambiguous continued execution
- Never leave a real position without protective reasoning
- Treat missing stop-loss attachment as a critical event
- If state is uncertain, reconcile before acting

### 2. Exchange state is source-of-truth for live exposure

- Local DB is intent and recovery support, not final truth
- Before mutating live trade state, verify whether exchange positions/orders disagree
- Distinguish clearly between:
  - intended order
  - acknowledged order
  - filled entry
  - active position
  - closing initiated

### 3. Every failure path needs an explicit operational outcome

Never leave `except` paths vague. Each failure must end in one of these:

- retry with bounded policy
- degrade to safe shadow/paper behavior
- quarantine symbol / subsystem
- reconcile and recover
- emergency close
- halt with alert

### 4. Persist transitions, not just final results

- Persist lifecycle changes before and after risky exchange actions when possible
- Make restart recovery deterministic
- Prefer additive telemetry over inferred postmortems

## Required Review Checklist

For any runtime-sensitive change, review these questions before merging:

1. Can this create a naked live position?
2. Can this duplicate an order after restart or retry?
3. Can DB state say `OPEN` while exchange is flat, or vice versa?
4. Can timeout/retry logic create repeated side effects?
5. Can a partial fill leave the system in an unmanaged state?
6. Is there enough telemetry to audit the incident later?
7. Is the change safe in both `PAPER_MODE` and real mode?

## Safe Change Pattern

1. Read the full lifecycle path involved
2. Identify existing invariants and persisted states
3. Add or update regression test first when feasible
4. Make the smallest behavior change possible
5. Verify startup, runtime, and restart semantics
6. Check logs/telemetry text remains actionable

## Operational Invariants

- Real-mode auth failures must fail clearly
- Paper/shadow mode should prefer degraded continuity over fatal boot when safe
- Emergency actions must be idempotent or bounded
- Recovery routines must not invent exposure that cannot be observed
- Watchdog and heartbeat paths must stay lightweight and deterministic

## Verification

After changes in this area, verify with some combination of:

- targeted unit tests around the affected flow
- runtime state persistence tests
- reconciliation / recovery regression tests
- modular import smoke checks
- manual inspection of resulting log messages and audit events

## Red Flags

- silent exception swallowing in runtime code
- non-idempotent retries around order placement/cancelation
- state changes that are only in memory
- ambiguous status strings with overlapping meanings
- paper-mode assumptions leaking into real-mode code
- operational logs that do not identify symbol, side, state, or reason
