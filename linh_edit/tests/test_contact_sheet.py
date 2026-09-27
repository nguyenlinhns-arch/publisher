from pathlib import Path

import linh_edit.contact_sheet as contact_sheet


class _Completed:
    returncode = 0
    stderr = ""


def test_contact_sheet_uses_local_ffmpeg_and_writes_target(tmp_path, monkeypatch):
    video = tmp_path / "preview.mp4"
    video.write_bytes(b"video")
    target = tmp_path / "sheet.jpg"

    monkeypatch.setattr(contact_sheet, "probe_duration", lambda _path: 24.0)
    monkeypatch.setattr(contact_sheet, "resolve_tool", lambda _name: "ffmpeg")

    def fake_run(args, **_kwargs):
        Path(args[-1]).write_bytes(b"sheet")
        assert "tile=4x3" in args[args.index("-vf") + 1]
        return _Completed()

    monkeypatch.setattr(contact_sheet.subprocess, "run", fake_run)

    result = contact_sheet.extract_contact_sheet(video, target)

    assert result == target.resolve()
    assert target.is_file()
