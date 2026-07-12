from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3


def backup_database(database_path: Path, backup_dir: Path, *, keep: int = 12) -> Path | None:
    """Create a consistent SQLite backup and rotate old copies.

    Missing databases (notably during first-run setup) are intentionally a no-op.
    SQLite's backup API also includes committed WAL pages.
    """
    if not database_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"publisher-{stamp}.sqlite3"
    with sqlite3.connect(database_path) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
        row = dest.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError("Bản sao lưu SQLite không vượt qua kiểm tra toàn vẹn.")
    copies = sorted(backup_dir.glob("publisher-*.sqlite3"), reverse=True)
    for old in copies[max(1, keep) :]:
        old.unlink(missing_ok=True)
    return target
