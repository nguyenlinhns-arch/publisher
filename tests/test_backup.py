from pathlib import Path
import sqlite3

from mxh_publisher.services.backup import backup_database


def test_backup_is_consistent_and_rotates(tmp_path: Path) -> None:
    source = tmp_path / "publisher.sqlite3"
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('ok')")
        connection.commit()
    finally:
        connection.close()
    backup_dir = tmp_path / "backups"
    result = backup_database(source, backup_dir, keep=2)
    assert result is not None
    connection = sqlite3.connect(result)
    try:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("ok",)
    finally:
        connection.close()
    backup_database(source, backup_dir, keep=2)
    backup_database(source, backup_dir, keep=2)
    assert len(list(backup_dir.glob("*.sqlite3"))) == 2


def test_backup_missing_database_is_noop(tmp_path: Path) -> None:
    assert backup_database(tmp_path / "missing.sqlite3", tmp_path / "backups") is None
