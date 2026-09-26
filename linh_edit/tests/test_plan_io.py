import json

from linh_edit.engine.plan_io import load_plan


def test_plan_load_accepts_windows_utf8_bom(tmp_path):
    payload = {
        "profile": "TALKING_HEAD_EXPERT",
        "title": "Smoke",
        "clips": [
            {
                "source": "clip.mp4",
                "kind": "video",
                "start": 0.0,
                "duration": 2.0,
                "role": "human",
                "x": 0.5,
                "y": 0.5,
                "scale": 1.0,
                "motion": "none",
                "mute_source_audio": False,
                "source_gain": 1.0,
            }
        ],
        "texts": [],
        "audio": {},
        "export": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "crf": 18,
            "preset": "medium",
            "audio_bitrate": "192k",
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig")

    plan = load_plan(path)

    assert plan.profile == "TALKING_HEAD_EXPERT"
    assert plan.duration == 2.0
    assert plan.clips[0].source == (tmp_path / "clip.mp4").resolve()
