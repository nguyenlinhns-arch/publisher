from pathlib import Path

import linh_edit.normalization as normalization
from linh_edit.media import MediaInfo


def test_normalization_plan_flags_vfr_rotation_hdr_and_proxy(tmp_path, monkeypatch):
    source = tmp_path / "phone.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr(
        normalization,
        "probe",
        lambda _path: MediaInfo(
            path=source,
            duration=20.0,
            width=2160,
            height=3840,
            fps=29.7,
            has_audio=True,
            video_codec="hevc",
            audio_codec="aac",
            r_fps=30.0,
            is_vfr=True,
            rotation=90,
            pixel_format="yuv420p10le",
            color_transfer="smpte2084",
            color_space="bt2020nc",
            color_primaries="bt2020",
        ),
    )

    plan = normalization.build_normalization_plan(source)

    assert plan.proxy_recommended
    assert plan.cfr_recommended_for_analysis
    assert plan.rotation_normalization_recommended
    assert plan.hdr_proxy_tonemap_recommended
    assert plan.final_source_policy == "KEEP_ORIGINAL_FOR_FINAL_RENDER"
