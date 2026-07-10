"""SQLite connection handling and forward-only schema migrations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Iterator, Sequence
from uuid import uuid4


SCHEMA_VERSION = 2


class DatabaseError(RuntimeError):
    pass


class DatabaseTooNewError(DatabaseError):
    pass


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _migration_001_core(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL DEFAULT '',
            video_path      TEXT NOT NULL,
            video_sha256    TEXT,
            caption         TEXT NOT NULL DEFAULT '',
            hashtags_json   TEXT NOT NULL DEFAULT '[]',
            content_hash    TEXT NOT NULL,
            approval_hash   TEXT,
            approved_at     TEXT,
            scheduled_at    TEXT,
            timezone        TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
            status          TEXT NOT NULL DEFAULT 'draft',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            CHECK (length(trim(id)) > 0),
            CHECK (length(trim(video_path)) > 0),
            CHECK (status IN (
                'draft', 'approved', 'ready', 'scheduled', 'publishing',
                'published', 'completed', 'partial', 'needs_action', 'failed',
                'cancelled'
            )),
            CHECK (
                (approval_hash IS NULL AND approved_at IS NULL) OR
                (approval_hash IS NOT NULL AND approved_at IS NOT NULL)
            )
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            id                  TEXT PRIMARY KEY,
            post_id             TEXT NOT NULL,
            platform            TEXT NOT NULL,
            account_id          TEXT,
            status              TEXT NOT NULL DEFAULT 'pending',
            remote_upload_id    TEXT,
            remote_post_id      TEXT,
            remote_url          TEXT,
            attempt_count       INTEGER NOT NULL DEFAULT 0,
            next_attempt_at     TEXT,
            last_error_code     TEXT,
            last_error_message  TEXT,
            published_at        TEXT,
            lease_owner         TEXT,
            lease_token         TEXT,
            lease_expires_at    TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            UNIQUE (post_id, platform),
            CHECK (platform IN ('facebook', 'tiktok')),
            CHECK (status IN (
                'pending', 'preparing', 'uploading', 'processing',
                'awaiting_confirmation', 'scheduled', 'retry_wait',
                'published', 'unknown', 'needs_action', 'failed', 'cancelled'
            )),
            CHECK (attempt_count >= 0),
            CHECK (
                (lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR
                (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
            )
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attempts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id     TEXT NOT NULL,
            attempt_no      INTEGER NOT NULL,
            phase           TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'started',
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            retryable       INTEGER,
            error_code      TEXT,
            error_message   TEXT,
            request_id      TEXT,
            details_json    TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
            UNIQUE (delivery_id, attempt_no),
            CHECK (attempt_no > 0),
            CHECK (status IN ('started', 'succeeded', 'failed', 'unknown')),
            CHECK (retryable IS NULL OR retryable IN (0, 1))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value_json  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            CHECK (length(trim(key)) > 0)
        )
        """
    )


def _migration_002_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_posts_status_schedule "
        "ON posts(status, scheduled_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_deliveries_due "
        "ON deliveries(status, next_attempt_at, lease_expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_deliveries_post "
        "ON deliveries(post_id, platform)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attempts_delivery_started "
        "ON attempts(delivery_id, started_at DESC)"
    )


MIGRATIONS: Sequence[Migration] = (
    Migration(1, "core_tables", _migration_001_core),
    Migration(2, "query_indexes", _migration_002_indexes),
)


class Database:
    """Small connection factory suitable for a GUI and one scheduled worker.

    Each operation receives its own connection.  WAL plus a busy timeout lets
    the GUI read while the worker writes.  ``BEGIN IMMEDIATE`` is available for
    claim/state-transition operations that must be atomic across processes.
    """

    def __init__(self, path: str | Path, *, timeout_seconds: float = 10.0) -> None:
        self.path = str(path)
        self.timeout_seconds = timeout_seconds
        self._uri = False
        self._keeper: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self.path = f"file:mxh-publisher-{uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
            self._keeper = self._open_connection()
        else:
            Path(self.path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.timeout_seconds,
            isolation_level=None,
            check_same_thread=False,
            uri=self._uri,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA synchronous = NORMAL")
        if not self._uri:
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._open_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Open a transaction and always commit or roll it back explicitly."""

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            else:
                conn.commit()

    def initialize(self) -> None:
        """Apply every missing migration exactly once.

        Migration DDL and its version marker share one exclusive transaction,
        so a process crash cannot leave a migration falsely marked as applied.
        All DDL is also ``IF NOT EXISTS`` to make recovery and repeated startup
        safe.
        """

        with self.connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version     INTEGER PRIMARY KEY,
                        name        TEXT NOT NULL,
                        applied_at  TEXT NOT NULL
                    )
                    """
                )
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
                ).fetchone()
                current = int(row["version"])
                if current > SCHEMA_VERSION:
                    raise DatabaseTooNewError(
                        f"Database schema {current} is newer than supported "
                        f"schema {SCHEMA_VERSION}."
                    )
                applied = {
                    int(item["version"])
                    for item in conn.execute(
                        "SELECT version FROM schema_migrations"
                    ).fetchall()
                }
                for migration in MIGRATIONS:
                    if migration.version in applied:
                        continue
                    migration.apply(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) "
                        "VALUES (?, ?, ?)",
                        (migration.version, migration.name, utc_now_text()),
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def schema_version(self) -> int:
        with self.connection() as conn:
            try:
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
                ).fetchone()
            except sqlite3.OperationalError:
                return 0
            return int(row["version"])

    def close(self) -> None:
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None

    def __enter__(self) -> "Database":
        self.initialize()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def initialize_database(path: str | Path) -> Database:
    database = Database(path)
    database.initialize()
    return database
