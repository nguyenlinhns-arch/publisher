from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import app_data_dir

CACHE_SCHEMA = "linh-edit.cache.v1"


@dataclass(frozen=True, slots=True)
class SourceSignature:
    path: str
    size: int
    mtime_ns: int
    key: str


def source_signature(path: Path) -> SourceSignature:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"Không tìm thấy source: {path}")
    stat = path.stat()
    material = f"{path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    key = hashlib.sha256(material).hexdigest()[:24]
    return SourceSignature(
        path=str(path),
        size=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
        key=key,
    )


def cache_root() -> Path:
    target = app_data_dir() / "cache-v1"
    target.mkdir(parents=True, exist_ok=True)
    return target


def source_cache_dir(path: Path) -> Path:
    signature = source_signature(path)
    target = cache_root() / signature.key
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: Path) -> dict[str, Any] | None:
    path = path.expanduser().resolve()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".partial")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)
    return path


def cache_matches(payload: dict[str, Any] | None, source: Path) -> bool:
    if not payload:
        return False
    try:
        signature = source_signature(source)
    except Exception:
        return False
    cached = payload.get("source_signature") or {}
    return (
        cached.get("key") == signature.key
        and int(cached.get("size", -1)) == signature.size
        and int(cached.get("mtime_ns", -1)) == signature.mtime_ns
    )


def cache_summary() -> dict[str, int]:
    root = cache_root()
    entries = 0
    files = 0
    bytes_total = 0
    for item in root.iterdir():
        if not item.is_dir():
            continue
        entries += 1
        for child in item.rglob("*"):
            if child.is_file():
                files += 1
                try:
                    bytes_total += child.stat().st_size
                except OSError:
                    pass
    return {
        "entries": entries,
        "files": files,
        "bytes": bytes_total,
    }
