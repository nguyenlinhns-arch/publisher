from __future__ import annotations

import shutil
import sys
from pathlib import Path


def runtime_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            roots.append(Path(bundle).resolve())
    roots.append(Path(__file__).resolve().parent)
    roots.append(Path(__file__).resolve().parents[1])
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def resolve_tool(name: str) -> str:
    exe = name + ".exe" if sys.platform == "win32" and not name.lower().endswith(".exe") else name
    for root in runtime_roots():
        for candidate in (root / "bin" / exe, root / exe):
            if candidate.is_file():
                return str(candidate)
    resolved = shutil.which(name) or shutil.which(exe)
    if resolved:
        return resolved
    raise RuntimeError(f"Không tìm thấy {name}. Linh Edit cần FFmpeg/FFprobe đã đóng gói hoặc có trong PATH.")


def resolve_asset(relative: str) -> Path:
    for root in runtime_roots():
        candidate = root / relative
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Thiếu tài nguyên Linh Edit: {relative}")
