from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from mxh_publisher.config import AppConfig, load_config, write_basic_config


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
            path = write_basic_config(
                config,
                page_id="123456",
                tiktok_account_id="@example_account",
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn('page_id = "123456"', text)
        self.assertIn('account_id = "@example_account"', text)
        self.assertNotIn("token", text.lower())

    def test_loads_tiktok_account_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "custom.toml"
            path.write_text(
                "[facebook]\npage_id = \"123456\"\n\n"
                "[tiktok]\naccount_id = \"@loaded_account\"\n",
                encoding="utf-8",
            )
            with patch("mxh_publisher.config.app_data_dir", return_value=root):
                config = load_config(path)

        self.assertEqual(config.tiktok_account_id, "@loaded_account")

    def test_tiktok_account_defaults_to_empty_and_writes_valid_toml(self) -> None:
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
            path = write_basic_config(config)
            raw = tomllib.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(config.tiktok_account_id, "")
        self.assertEqual(raw["tiktok"]["account_id"], "")

    def test_tiktok_account_cannot_inject_toml(self) -> None:
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
            injected = '@safe"\n[attacker]\nenabled = true'
            path = write_basic_config(config, tiktok_account_id=injected)
            raw = tomllib.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(raw["tiktok"]["account_id"], injected)
        self.assertNotIn("attacker", raw)

    def test_old_edge_setting_is_migrated_to_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "old.toml"
            path.write_text(
                '[tiktok]\nbrowser_channel = "msedge"\n', encoding="utf-8"
            )
            with patch("mxh_publisher.config.app_data_dir", return_value=root):
                config = load_config(path)

        self.assertEqual(config.browser_channel, "chrome")


if __name__ == "__main__":
    unittest.main()
