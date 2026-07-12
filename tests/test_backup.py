from pathlib import Path
import sqlite3

from mxh_publisher.services.backup import backup_database


def test_backup_is_consistent_and_rotates(tmp_path: Path) -> None:
    source = tmp_path / "publisher.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('ok')")
    backup_dir = tmp_path / "backups"
    result = backup_database(source, backup_dir, keep=2)
    assert result is not None
    with sqlite3.connect(result) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("ok",)
    backup_database(source, backup_dir, keep=2)
    backup_database(source, backup_dir, keep=2)
    assert len(list(backup_dir.glob("*.sqlite3"))) == 2


def test_backup_missing_database_is_noop(tmp_path: Path) -> None:
    assert backup_database(tmp_path / "missing.sqlite3", tmp_path / "backups") is None
