from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from mxh_publisher.services.dry_run import run_dry_run
from mxh_publisher.services.media import VideoInfo, inspect_video, sha256_file


class MediaTests(unittest.TestCase):
    def test_sha256_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mp4"
            path.write_bytes(b"video")
            self.assertEqual(
                sha256_file(path),
                "0cab1c9617404faf2b24e221e189ca5945813e14d3f766345b09ca13bbe28ffc",
            )

    @patch("mxh_publisher.services.media.find_ffprobe", return_value="ffprobe")
    @patch("mxh_publisher.services.media.subprocess.run")
    def test_inspect_valid_video(self, run, _find) -> None:
        payload = {
            "format": {"duration": "30.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "avg_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps(payload)
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mp4"
            path.write_bytes(b"video")
            info = inspect_video(path)
        self.assertTrue(info.is_valid)
        self.assertEqual(info.width, 1080)
        self.assertEqual(info.audio_codec, "aac")

    def test_dry_run_blocks_changed_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mp4"
            path.write_bytes(b"actual")
            report = run_dry_run(
                video_path=path,
                expected_sha256="different",
                caption="Nội dung",
                hashtags="#TKV",
                scheduled_at_utc=datetime.now(UTC) + timedelta(hours=2),
                approved=True,
            )
        self.assertFalse(report.ready)
        self.assertIn(
            "VIDEO_HASH", {check.code for check in report.checks if not check.passed}
        )

    @patch("mxh_publisher.services.dry_run.sha256_file", return_value="abc")
    @patch("mxh_publisher.services.dry_run.inspect_video")
    def test_dry_run_ready(self, inspect, _hash) -> None:
        inspect.return_value = VideoInfo(
            path=Path("sample.mp4"),
            sha256="abc",
            size_bytes=10,
            duration_seconds=30,
            width=1080,
            height=1920,
            fps=30,
            video_codec="h264",
            audio_codec="aac",
            has_audio=True,
            issues=(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mp4"
            path.write_bytes(b"actual")
            report = run_dry_run(
                video_path=path,
                expected_sha256="abc",
                caption="Nội dung",
                hashtags="#TKV",
                scheduled_at_utc=datetime.now(UTC) + timedelta(hours=2),
                approved=True,
            )
        self.assertTrue(report.ready, report.as_text())


if __name__ == "__main__":
    unittest.main()
