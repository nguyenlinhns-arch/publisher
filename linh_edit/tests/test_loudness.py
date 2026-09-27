from pathlib import Path

import linh_edit.loudness as loudness
from linh_edit.project import ProjectState


def test_parse_loudnorm_json():
    stderr = """
    [Parsed_loudnorm_0 @ 000] {
        "input_i" : "-18.50",
        "input_tp" : "-2.10",
        "input_lra" : "4.30",
        "input_thresh" : "-28.90",
        "output_i" : "-15.90"
    }
    """
    measured = loudness.parse_loudnorm_json(stderr, Path("voice.wav"))

    assert measured.integrated_lufs == -18.5
    assert measured.true_peak_dbfs == -2.1
    assert measured.lra == 4.3


def test_gain_for_target_matches_db_math():
    value = loudness.gain_for_target(-20.0, -16.0, minimum=0.1, maximum=4.0)

    assert 1.57 < value < 1.60


def test_auto_balance_project_updates_voice_and_music(monkeypatch, tmp_path):
    voice = tmp_path / "voice.wav"
    music = tmp_path / "music.wav"
    voice.write_bytes(b"x")
    music.write_bytes(b"x")
    project = ProjectState(voiceover=str(voice), music=str(music))

    def fake_measure(path):
        if path.name == "voice.wav":
            return loudness.LoudnessMeasurement(str(path), -20.0, -2.0, 4.0, -30.0)
        return loudness.LoudnessMeasurement(str(path), -14.0, -1.0, 8.0, -24.0)

    monkeypatch.setattr(loudness, "measure_loudness", fake_measure)
    result = loudness.auto_balance_project(project)

    assert result["voice"]["recommended_gain"] > 1.0
    assert 0.1 < result["music"]["recommended_gain"] < 0.2
    assert project.auto_master_audio is True
