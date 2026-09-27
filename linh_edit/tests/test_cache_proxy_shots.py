from pathlib import Path

import linh_edit.cache as cache
import linh_edit.proxy as proxy
import linh_edit.shot_detection as shots
from linh_edit.media import MediaInfo


def test_source_signature_changes_when_size_changes(tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"a")
    first = cache.source_signature(path)
    path.write_bytes(b"abcd")
    second = cache.source_signature(path)

    assert first.key != second.key


def test_spans_from_boundaries_builds_stable_shots():
    result = shots.spans_from_boundaries(
        [0.1, 2.0, 2.2, 5.0, 9.0],
        10.0,
        min_shot_seconds=0.5,
    )

    assert result[0].start == 0.0
    assert result[-1].end == 10.0
    assert all(item.duration >= 0.5 for item in result)


def test_proxy_reuses_cached_result(tmp_path: Path, monkeypatch):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    root = tmp_path / "cache"
    monkeypatch.setattr(cache, "cache_root", lambda: root)
    monkeypatch.setattr(proxy, "source_cache_dir", cache.source_cache_dir)
    monkeypatch.setattr(
        proxy,
        "probe",
        lambda _path: MediaInfo(
            path=source.resolve(),
            duration=8.0,
            width=2160,
            height=3840,
            fps=30.0,
            has_audio=True,
            video_codec="hevc",
            audio_codec="aac",
        ),
    )

    calls = {"count": 0}

    class Completed:
        returncode = 0
        stderr = ""

    def fake_run(args, **_kwargs):
        calls["count"] += 1
        Path(args[-1]).write_bytes(b"proxy")
        return Completed()

    monkeypatch.setattr(proxy.subprocess, "run", fake_run)
    monkeypatch.setattr(proxy, "resolve_tool", lambda _name: "ffmpeg")

    first = proxy.ensure_proxy(source)
    second = proxy.ensure_proxy(source)

    assert not first.reused
    assert second.reused
    assert calls["count"] == 1
    assert Path(second.proxy).is_file()
