from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..tools import resolve_asset, resolve_tool

from .ass import write_ass
from .models import EditPlan
from .qa import verify_output


class RenderError(RuntimeError):
    pass


def _tool(name: str) -> str:
    try:
        return resolve_tool(name)
    except RuntimeError as exc:
        raise RenderError(str(exc)) from exc


def _ffmpeg_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def _probe_has_audio(path: Path) -> bool:
    completed = subprocess.run(
        [
            _tool("ffprobe"),
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def render_plan(plan: EditPlan, output: Path) -> Path:
    plan.validate()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    for clip in plan.clips:
        if not clip.source.expanduser().resolve().is_file():
            raise RenderError(f"missing source: {clip.source}")
    if plan.audio.voiceover and not plan.audio.voiceover.expanduser().resolve().is_file():
        raise RenderError(f"missing voiceover: {plan.audio.voiceover}")
    if plan.audio.music and not plan.audio.music.expanduser().resolve().is_file():
        raise RenderError(f"missing music: {plan.audio.music}")
    for sfx in plan.audio.sfx:
        if not sfx.path.expanduser().resolve().is_file():
            raise RenderError(f"missing sfx: {sfx.path}")

    with tempfile.TemporaryDirectory(prefix="linh-edit-") as td:
        work = Path(td)
        ass = work / "text.ass"
        write_ass(plan, ass)
        temp_output = work / "render.partial.mp4"

        command: list[str] = [_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
        input_index: dict[str, int] = {}
        for index, clip in enumerate(plan.clips):
            command.extend(["-i", str(clip.source.expanduser().resolve())])
            input_index[f"clip_{index}"] = index

        next_input = len(plan.clips)
        voice_index: int | None = None
        music_index: int | None = None
        sfx_inputs: list[tuple[int, object]] = []
        if plan.audio.voiceover:
            voice_index = next_input
            command.extend(["-i", str(plan.audio.voiceover.expanduser().resolve())])
            next_input += 1
        if plan.audio.music:
            music_index = next_input
            command.extend(["-stream_loop", "-1", "-i", str(plan.audio.music.expanduser().resolve())])
            next_input += 1
        for sfx in plan.audio.sfx:
            sfx_inputs.append((next_input, sfx))
            command.extend(["-i", str(sfx.path.expanduser().resolve())])
            next_input += 1

        filters: list[str] = []
        video_labels: list[str] = []
        audio_labels: list[str] = []
        w, h, fps = plan.export.width, plan.export.height, plan.export.fps

        for index, clip in enumerate(plan.clips):
            end = clip.start + clip.duration
            vin = f"[{input_index[f'clip_{index}']}:v:0]"
            vout = f"[v{index}]"
            scale = max(1.0, clip.scale)
            filters.append(
                vin
                + f"trim=start={clip.start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
                + f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                + f"scale=iw*{scale:.6f}:ih*{scale:.6f},"
                + f"crop={w}:{h}:"
                + f"x='max(0,min(iw-{w},(iw-{w})*{clip.x:.6f}))':"
                + f"y='max(0,min(ih-{h},(ih-{h})*{clip.y:.6f}))',"
                + f"fps={fps},setsar=1,format=yuv420p"
                + vout
            )
            video_labels.append(vout)

            source = clip.source.expanduser().resolve()
            if not clip.mute_source_audio and _probe_has_audio(source):
                aout = f"[a{index}]"
                filters.append(
                    f"[{index}:a:0]atrim=start={clip.start:.3f}:end={end:.3f},"
                    f"asetpts=PTS-STARTPTS,aresample=48000,"
                    f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"volume={clip.source_gain:.6f}{aout}"
                )
            else:
                aout = f"[a{index}]"
                filters.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                    f"atrim=duration={clip.duration:.3f},asetpts=PTS-STARTPTS{aout}"
                )
            audio_labels.append(aout)

        concat_inputs = "".join(
            label
            for pair in zip(video_labels, audio_labels)
            for label in pair
        )
        filters.append(
            concat_inputs
            + f"concat=n={len(plan.clips)}:v=1:a=1[basev][basea]"
        )

        ass_path = _ffmpeg_path(ass)
        fonts_path = _ffmpeg_path(resolve_asset("assets/fonts"))
        filters.append(
            f"[basev]ass=filename='{ass_path}':fontsdir='{fonts_path}',"
            "format=yuv420p[outv]"
        )

        duration = plan.duration
        mix_labels = ["[basea]"]
        if voice_index is not None:
            filters.append(
                f"[{voice_index}:a:0]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"apad,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[voice]"
            )
            mix_labels.append("[voice]")
        if music_index is not None:
            fade_out_start = max(0.0, duration - 1.5)
            filters.append(
                f"[{music_index}:a:0]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume={plan.audio.music_gain:.6f},"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.3f}:d=1.5,"
                f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[music]"
            )
            mix_labels.append("[music]")

        for sfx_number, (sfx_index, sfx) in enumerate(sfx_inputs):
            delay_ms = max(0, round(sfx.start * 1000))
            label = f"[sfx{sfx_number}]"
            filters.append(
                f"[{sfx_index}:a:0]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume={sfx.gain:.6f},"
                f"adelay={delay_ms}|{delay_ms},apad,"
                f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS{label}"
            )
            mix_labels.append(label)

        if len(mix_labels) == 1:
            filters.append("[basea]anull[outa]")
        else:
            filters.append(
                "".join(mix_labels)
                + f"amix=inputs={len(mix_labels)}:duration=longest:normalize=0,"
                + "alimiter=limit=0.95[outa]"
            )

        command.extend(
            [
                "-filter_complex", ";".join(filters),
                "-map", "[outv]",
                "-map", "[outa]",
                "-t", f"{duration:.3f}",
                "-c:v", "libx264",
                "-preset", plan.export.preset,
                "-crf", str(plan.export.crf),
                "-profile:v", "high",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", plan.export.audio_bitrate,
                "-ar", "48000",
                "-movflags", "+faststart",
                str(temp_output),
            ]
        )

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            check=False,
        )
        if completed.returncode != 0:
            raise RenderError((completed.stderr or "ffmpeg render failed")[-4000:])

        qa = verify_output(
            temp_output,
            width=plan.export.width,
            height=plan.export.height,
            fps=plan.export.fps,
        )
        if not qa.passed:
            raise RenderError("QA failed: " + "; ".join(qa.errors))

        final_tmp = output.with_suffix(output.suffix + ".partial")
        shutil.copy2(temp_output, final_tmp)
        final_tmp.replace(output)
        report = output.with_suffix(".qa.json")
        report.write_text(
            json.dumps(
                {
                    "technical_pass": qa.passed,
                    "visual_review": "PENDING",
                    "audio_review": "PENDING",
                    "style_review": "PENDING",
                    "duration": qa.duration,
                    "width": qa.width,
                    "height": qa.height,
                    "fps": qa.fps,
                    "video_codec": qa.video_codec,
                    "audio_codec": qa.audio_codec,
                    "decoded_ok": qa.decoded_ok,
                    "errors": list(qa.errors),
                    "profile": plan.profile,
                    "planned_duration": duration,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return output
