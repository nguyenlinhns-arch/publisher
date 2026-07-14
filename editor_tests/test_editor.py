from __future__ import annotations

from pathlib import Path

import pytest

from mxh_publisher.services.media import (
    WINDOWS_CREATE_NO_WINDOW,
    _title_font_size,
    _wrapped_video_title,
    default_fonts_dir,
    default_intro_sound_path,
    probe_media_duration,
    subprocess_creation_flags,
)
from mxh_video_editor.config import EditorConfig
from mxh_video_editor.editor import (
    BatchVideoItem,
    TRIM_END_SECONDS,
    TRIM_START_SECONDS,
    build_batch_items,
    delete_rendered_video,
    list_rendered_videos,
    render_video_batch,
    safe_filename,
)


def make_config(tmp_path: Path) -> EditorConfig:
    config = EditorConfig(tmp_path, tmp_path / "outputs", tmp_path / "cache")
    config.ensure_directories()
    return config


def test_fixed_trim_values() -> None:
    assert TRIM_START_SECONDS == 6.2
    assert TRIM_END_SECONDS == 4.0


def test_ffmpeg_child_processes_are_hidden_on_windows() -> None:
    assert subprocess_creation_flags("win32") == WINDOWS_CREATE_NO_WINDOW
    assert subprocess_creation_flags("linux") == 0


def test_hyphen_creates_manual_title_line_break() -> None:
    assert _wrapped_video_title("NGHỀ MỎ KHÔNG-PHẢI NGHỀ NHÀN") == (
        r"NGHỀ MỎ KHÔNG\NPHẢI NGHỀ NHÀN"
    )


def test_bundled_vietnamese_fonts_exist() -> None:
    fonts = default_fonts_dir()
    assert (fonts / "Anton-Regular.ttf").is_file()
    assert (fonts / "BeVietnamPro-SemiBold.ttf").is_file()


def test_news_title_font_size_adapts_to_line_length() -> None:
    assert _title_font_size(r"TIN MỚI\NHÔM NAY") == 116
    assert _title_font_size("A" * 22) == 104
    assert _title_font_size("A" * 28) == 92
    assert _title_font_size("A" * 34) == 80


def test_default_intro_sound_is_valid() -> None:
    sound = default_intro_sound_path()
    assert sound.stat().st_size > 0
    assert probe_media_duration(sound) == pytest.approx(0.36, abs=0.02)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Tiêu đề   video  ", "Tiêu đề video"),
        ('Tên: có / ký * tự?', "Tên- có - ký - tự"),
        ("...", "video_da_sua"),
    ],
)
def test_safe_filename(value: str, expected: str) -> None:
    assert safe_filename(value) == expected


def test_build_batch_items_deduplicates_and_uses_stems(tmp_path: Path) -> None:
    first = tmp_path / "Tin ngành than.mp4"
    second = tmp_path / "Tuyển thợ mỏ.mp4"
    items = build_batch_items((first, first, second))
    assert [item.source for item in items] == [first.resolve(), second.resolve()]
    assert [item.title for item in items] == ["Tin ngành than", "Tuyển thợ mỏ"]


def test_batch_continues_after_one_video_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    items = (
        BatchVideoItem(tmp_path / "ok-1.mp4", "OK 1"),
        BatchVideoItem(tmp_path / "bad.mp4", "BAD"),
        BatchVideoItem(tmp_path / "ok-2.mp4", "OK 2"),
    )
    calls: list[str] = []
    progress: list[tuple[int, int, str, bool]] = []

    def fake_render(*_args: object, **_kwargs: object) -> object:
        source = _args[1]
        assert isinstance(source, Path)
        calls.append(source.name)
        if source.name == "bad.mp4":
            raise RuntimeError("video lỗi")
        return object()

    monkeypatch.setattr("mxh_video_editor.editor.render_video", fake_render)
    outcomes = render_video_batch(
        config,
        items,
        on_progress=lambda index, total, outcome: progress.append(
            (index, total, outcome.item.source.name, outcome.succeeded)
        ),
    )

    assert calls == ["ok-1.mp4", "bad.mp4", "ok-2.mp4"]
    assert [outcome.succeeded for outcome in outcomes] == [True, False, True]
    assert outcomes[1].error == "video lỗi"
    assert progress == [
        (1, 3, "ok-1.mp4", True),
        (2, 3, "bad.mp4", False),
        (3, 3, "ok-2.mp4", True),
    ]


def test_list_outputs_newest_first(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    older = config.output_dir / "older.mp4"
    newer = config.output_dir / "newer.mp4"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    older.touch()
    newer.touch()
    older_mtime = newer.stat().st_mtime - 10
    older.touch()
    import os

    os.utime(older, (older_mtime, older_mtime))
    assert list_rendered_videos(config) == [newer, older]


def test_delete_only_output_mp4(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    target = config.output_dir / "done.mp4"
    target.write_bytes(b"video")
    delete_rendered_video(config, target)
    assert not target.exists()


def test_delete_refuses_file_outside_output(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    outside = tmp_path / "original.mp4"
    outside.write_bytes(b"do not delete")
    with pytest.raises(ValueError, match="Chỉ được xóa"):
        delete_rendered_video(config, outside)
    assert outside.exists()
