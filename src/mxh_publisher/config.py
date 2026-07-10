from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


APP_NAME = "MXHPublisher"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = root / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Development containers may expose a read-only home directory.  The
        # Windows production path above remains unchanged.
        path = Path(tempfile.gettempdir()) / APP_NAME
        path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True, slots=True)
class AppConfig:
    root_dir: Path
    database_path: Path
    media_dir: Path
    logs_dir: Path
    screenshots_dir: Path
    browser_profile_dir: Path
    timezone_name: str = "Asia/Ho_Chi_Minh"
    minimum_schedule_lead_minutes: int = 30
    caption_soft_limit: int = 2200
    graph_version: str = "v25.0"
    facebook_page_id: str = ""
    tiktok_upload_url: str = "https://www.tiktok.com/tiktokstudio/upload"
    tiktok_content_url: str = "https://www.tiktok.com/tiktokstudio/content"
    browser_channel: str = "msedge"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def ensure_directories(self) -> None:
        for directory in (
            self.root_dir,
            self.media_dir,
            self.logs_dir,
            self.screenshots_dir,
            self.browser_profile_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def load_config(path: Path | None = None) -> AppConfig:
    root = app_data_dir()
    path = path or root / "config.toml"
    raw: dict = {}
    if path.exists():
        with path.open("rb") as handle:
            raw = tomllib.load(handle)

    app = raw.get("app", {})
    facebook = raw.get("facebook", {})
    tiktok = raw.get("tiktok", {})
    config = AppConfig(
        root_dir=root,
        database_path=root / "publisher.sqlite3",
        media_dir=root / "media",
        logs_dir=root / "logs",
        screenshots_dir=root / "screenshots",
        browser_profile_dir=root / "browser_profile",
        timezone_name=str(app.get("timezone", "Asia/Ho_Chi_Minh")),
        minimum_schedule_lead_minutes=int(app.get("minimum_schedule_lead_minutes", 30)),
        caption_soft_limit=int(app.get("caption_soft_limit", 2200)),
        graph_version=str(facebook.get("graph_version", "v25.0")),
        facebook_page_id=str(facebook.get("page_id", "")),
        tiktok_upload_url=str(
            tiktok.get(
                "studio_upload_url", "https://www.tiktok.com/tiktokstudio/upload"
            )
        ),
        tiktok_content_url=str(
            tiktok.get(
                "studio_content_url", "https://www.tiktok.com/tiktokstudio/content"
            )
        ),
        browser_channel=str(tiktok.get("browser_channel", "msedge")),
    )
    config.ensure_directories()
    return config


def write_basic_config(config: AppConfig, *, page_id: str | None = None) -> Path:
    """Write only non-secret settings. Tokens are never accepted here."""
    target = config.root_dir / "config.toml"
    safe_page_id = (page_id if page_id is not None else config.facebook_page_id).strip()
    text = (
        "[app]\n"
        f'timezone = "{config.timezone_name}"\n'
        f"minimum_schedule_lead_minutes = {config.minimum_schedule_lead_minutes}\n"
        f"caption_soft_limit = {config.caption_soft_limit}\n\n"
        "[facebook]\n"
        f'graph_version = "{config.graph_version}"\n'
        f'page_id = "{safe_page_id}"\n\n'
        "[tiktok]\n"
        f'studio_upload_url = "{config.tiktok_upload_url}"\n'
        f'studio_content_url = "{config.tiktok_content_url}"\n'
        f'browser_channel = "{config.browser_channel}"\n'
    )
    target.write_text(text, encoding="utf-8")
    return target
