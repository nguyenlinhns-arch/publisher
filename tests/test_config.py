from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mxh_publisher.config import AppConfig, write_basic_config


class ConfigTests(unittest.TestCase):
    def test_written_config_never_contains_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(
                root_dir=root,
                database_path=root / "db.sqlite3",
                media_dir=root / "media",
                logs_dir=root / "logs",
                screenshots_dir=root / "screenshots",
                browser_profile_dir=root / "browser",
            )
            path = write_basic_config(config, page_id="123456")
            text = path.read_text(encoding="utf-8")
        self.assertIn('page_id = "123456"', text)
        self.assertNotIn("token", text.lower())


if __name__ == "__main__":
    unittest.main()
