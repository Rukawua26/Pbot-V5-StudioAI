#!/usr/bin/env python3
"""Prune backup folders to keep project lightweight."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def parse_backup_ts(name: str) -> datetime | None:
    prefix = "backup_"
    if not name.startswith(prefix):
        return None
    stamp = name[len(prefix) :]
    for fmt in ("%Y%m%d_%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(stamp, fmt)
        except ValueError:
            continue
    return None


def folder_size_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune old backup directories")
    parser.add_argument("--backups-dir", default="backups")
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--min-keep", type=int, default=10)
    parser.add_argument("--apply", action="store_true", help="Delete selected backups")
    args = parser.parse_args()

    backups_dir = Path(args.backups_dir).resolve()
    if not backups_dir.exists():
        print(f"Backups dir not found: {backups_dir}")
        return 1

    now = datetime.now()
    cutoff = now - timedelta(days=args.keep_days)

    items: list[tuple[Path, datetime, int]] = []
    for entry in backups_dir.iterdir():
        if not entry.is_dir():
            continue
        ts = parse_backup_ts(entry.name)
        if ts is None:
            continue
        size = folder_size_bytes(entry)
        items.append((entry, ts, size))

    items.sort(key=lambda x: x[1], reverse=True)

    keep_names = {x[0].name for x in items[: max(args.min_keep, 0)]}
    to_delete: list[tuple[Path, datetime, int]] = []
    for entry, ts, size in items:
        if entry.name in keep_names:
            continue
        if ts < cutoff:
            to_delete.append((entry, ts, size))

    bytes_total = sum(x[2] for x in to_delete)
    print(f"Backups found: {len(items)}")
    print(f"Candidates: {len(to_delete)}")
    print(f"Space recoverable: {bytes_total / (1024**3):.2f} GB")

    for entry, ts, size in to_delete[:20]:
        print(f"  - {entry.name} | {ts.isoformat()} | {size / (1024**2):.1f} MB")
    if len(to_delete) > 20:
        print(f"  ... +{len(to_delete) - 20} more")

    if not args.apply:
        print("Dry run only. Re-run with --apply to delete.")
        return 0

    deleted = 0
    for entry, _, _ in to_delete:
        shutil.rmtree(entry, ignore_errors=True)
        deleted += 1

    print(f"Deleted: {deleted} backup dirs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
