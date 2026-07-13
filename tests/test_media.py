from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from mxh_publisher.services.dry_run import run_dry_run
from mxh_publisher.services.media import (
    VideoEditSpec,
    VideoInfo,
    _wrapped_video_title,
    inspect_video,
    render_social_video,
    sha256_file,
)


class MediaTests(unittest.TestCase):
    @staticmethod
    def _video_info(path: Path, *, duration: float, valid: bool) -> VideoInfo:
        return VideoInfo(
            path=path,
            sha256="a" * 64,
            size_bytes=100,
            duration_seconds=duration,
            width=1080 if valid else 1920,
            height=1920 if valid else 1080,
            fps=30,
            video_codec="h264",
            audio_codec="aac",
            has_audio=True,
            issues=(),
        )

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

    @patch("mxh_publisher.services.media.find_ffmpeg", return_value="ffmpeg")
    @patch("mxh_publisher.services.media.inspect_video")
    @patch("mxh_publisher.services.media.subprocess.run")
    def test_render_trims_and_overlays_frame(self, run, inspect, _find) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            frame = root / "frame.png"
            source.write_bytes(b"source")
            frame.write_bytes(b"frame")

            def execute(command, **_kwargs):
                Path(command[-1]).write_bytes(b"rendered")
                result = unittest.mock.Mock()
                result.returncode = 0
                result.stderr = ""
                return result

            run.side_effect = execute
            inspect.side_effect = [
                self._video_info(source, duration=30, valid=False),
                self._video_info(root / "temporary.mp4", duration=17.6, valid=True),
                self._video_info(root / "result.mp4", duration=17.6, valid=True),
            ]
            result = render_social_video(
                source,
                root / "output",
                VideoEditSpec(6.2, 6.2, frame),
            )

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-ss") + 1], "6.200")
        self.assertEqual(command[command.index("-t") + 1], "17.600")
        video_filter = command[command.index("-filter_complex") + 1]
        self.assertIn("overlay=0:360", video_filter)
        self.assertIn("ass=filename=", video_filter)
        self.assertEqual((result.width, result.height, result.fps), (1080, 1920, 30))

    def test_default_edit_removes_6_2_seconds_start_and_4_seconds_end(self) -> None:
        spec = VideoEditSpec()

        self.assertEqual(spec.trim_start_seconds, 6.2)
        self.assertEqual(spec.trim_end_seconds, 4.0)

    def test_project_title_is_split_like_the_reference_layout(self) -> None:
        title = _wrapped_video_title(
            "Than Vàng Danh gặp mặt, biểu dương 130 gia đình công nhân tiêu biểu"
        )

        self.assertEqual(
            title,
            "THAN VÀNG DANH\\NGẶP MẶT, BIỂU DƯƠNG\\N"
            "130 GIA ĐÌNH CÔNG NHÂN TIÊU BIỂU",
        )

    @patch("mxh_publisher.services.media.inspect_video")
    def test_render_blocks_output_longer_than_90_seconds(self, inspect) -> None:
        from mxh_publisher.services.media import VideoEditError

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            source.write_bytes(b"source")
            inspect.return_value = self._video_info(
                source, duration=120, valid=False
            )
            with self.assertRaisesRegex(VideoEditError, "tối đa 90 giây"):
                render_social_video(
                    source,
                    Path(directory) / "output",
                    VideoEditSpec(6.2, 6.2),
                )


if __name__ == "__main__":
    unittest.main()
