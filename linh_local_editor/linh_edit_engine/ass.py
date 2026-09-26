from __future__ import annotations

from pathlib import Path

from .models import EditPlan, TextSpec


def _time(value: float) -> str:
    cs = max(0, round(value * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _ass_color(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "&H00E9F1F4"
    r = value[0:2]
    g = value[2:4]
    b = value[4:6]
    return f"&H00{b}{g}{r}"


def _escape(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _alignment(text: TextSpec) -> int:
    if text.align == "left":
        return 1
    if text.align == "right":
        return 3
    return 2


def write_ass(plan: EditPlan, target: Path) -> None:
    w, h = plan.export.width, plan.export.height
    events: list[str] = []
    for item in plan.texts:
        x = round(item.x * w)
        y = round(item.y * h)
        color = _ass_color(item.color)
        bold = -1 if item.weight >= 700 else 0
        font_size = max(16, round(item.size * w / 1080))
        align = _alignment(item)
        body = _escape(item.text)
        tag = (
            rf"{{\an{align}\pos({x},{y})\fs{font_size}\b{bold}"
            rf"\c{color}\bord1.2\shad0\fad(140,120)}}"
        )
        events.append(
            f"Dialogue: 0,{_time(item.start)},{_time(item.end)},Default,,0,0,0,,{tag}{body}"
        )

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {w}",
            f"PlayResY: {h}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Roboto Condensed,72,&H00F4F1E9,&H00F4F1E9,"
            "&H60000000,&H00000000,-1,0,0,0,100,100,0,0,1,1.2,0,2,80,80,80,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
        ]
    )
    target.write_text(content, encoding="utf-8-sig")
