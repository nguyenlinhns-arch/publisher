from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .checkpoint import create_checkpoint
from .media import probe_duration
from .project import ProjectState, TextItem

STOPWORDS = {
    "và", "là", "có", "của", "một", "những", "các", "thì", "mà", "đã",
    "đang", "sẽ", "với", "cho", "ở", "tại", "trong", "khi", "này", "đó",
    "được", "cũng", "như", "vì", "nên", "tôi", "mình", "chúng", "ta", "rất",
}

ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("road_reset", ("đường", "đèo", "xe", "di chuyển", "hành trình", "chặng")),
    ("place", ("núi", "cao nguyên", "thác", "sông", "cầu", "địa danh", "toàn cảnh")),
    ("work", ("họp", "làm việc", "công việc", "trao đổi", "hồ sơ", "cơ quan")),
    ("human", ("người", "gặp", "anh", "chị", "bà con", "người dân", "đồng nghiệp")),
    ("life", ("làng", "buôn", "nhà dân", "đời sống", "sinh hoạt", "chợ")),
    ("detail", ("bếp", "món", "cà phê", "chi tiết", "bữa", "đồ ăn")),
    ("emotion", ("nhớ", "thương", "ấn tượng", "cảm giác", "yên", "bình dị")),
)


@dataclass(frozen=True, slots=True)
class CaptionBlock:
    start: float
    end: float
    text: str
    importance: float
    desired_role: str = ""
    keywords: tuple[str, ...] = ()

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _words(value: str) -> list[str]:
    return [item for item in re.split(r"\s+", _clean(value)) if item]


def _split_sentences(text: str) -> list[str]:
    normalized = _clean(text.replace("\n", " "))
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?…])\s+|\s*[;:]\s+", normalized)
    return [part.strip(" \t-–—") for part in parts if part.strip(" \t-–—")]


def _chunk_sentence(sentence: str, *, maximum_words: int = 12) -> list[str]:
    words = _words(sentence)
    if not words:
        return []
    if len(words) <= maximum_words:
        return [" ".join(words)]
    result: list[str] = []
    cursor = 0
    while cursor < len(words):
        remaining = len(words) - cursor
        take = min(maximum_words, remaining)
        if remaining > maximum_words and remaining - take < 4:
            take = max(6, remaining // 2)
        result.append(" ".join(words[cursor : cursor + take]))
        cursor += take
    return result


def _desired_role(text: str) -> tuple[str, tuple[str, ...]]:
    folded = text.casefold()
    hits: list[str] = []
    for role, keywords in ROLE_RULES:
        role_hits = [keyword for keyword in keywords if keyword in folded]
        if role_hits:
            return role, tuple(role_hits[:4])
    return "", ()


def _importance(text: str, desired_role: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    content = [
        word
        for word in words
        if re.sub(r"[^\wÀ-ỹđĐ]", "", word, flags=re.UNICODE).casefold()
        not in STOPWORDS
    ]
    content_ratio = len(content) / max(1, len(words))
    number_bonus = 0.18 if re.search(r"\d", text) else 0.0
    visual_bonus = 0.14 if desired_role else 0.0
    length_score = min(1.0, len(words) / 8.0)
    return round(
        min(
            1.0,
            0.48 * content_ratio
            + 0.24 * length_score
            + number_bonus
            + visual_bonus,
        ),
        4,
    )


def plan_selective_captions(
    transcript: str,
    total_seconds: float,
    *,
    hook_end: float = 3.0,
    coverage_target: float = 0.65,
    maximum_words: int = 12,
) -> tuple[CaptionBlock, ...]:
    sentences = _split_sentences(transcript)
    chunks: list[str] = []
    for sentence in sentences:
        chunks.extend(_chunk_sentence(sentence, maximum_words=maximum_words))
    if not chunks:
        return ()

    total_seconds = max(0.5, float(total_seconds))
    weights = [max(2, len(_words(chunk))) for chunk in chunks]
    total_weight = sum(weights) or len(weights)

    raw: list[CaptionBlock] = []
    cursor = 0.0
    for chunk, weight in zip(chunks, weights):
        duration = total_seconds * weight / total_weight
        start = cursor
        end = min(total_seconds, cursor + duration)
        role, keywords = _desired_role(chunk)
        raw.append(
            CaptionBlock(
                start=round(start, 3),
                end=round(end, 3),
                text=chunk,
                importance=_importance(chunk, role),
                desired_role=role,
                keywords=keywords,
            )
        )
        cursor = end

    # Hook text already owns the first seconds. Preserve timing but do not
    # duplicate narration captions under it.
    eligible: list[CaptionBlock] = []
    for block in raw:
        start = max(block.start, hook_end)
        if block.end - start < 0.45:
            continue
        eligible.append(
            CaptionBlock(
                start=round(start, 3),
                end=block.end,
                text=block.text,
                importance=block.importance,
                desired_role=block.desired_role,
                keywords=block.keywords,
            )
        )
    if not eligible:
        return ()

    available = max(0.0, total_seconds - hook_end)
    target = max(0.0, min(1.0, coverage_target)) * available
    ranked = sorted(
        enumerate(eligible),
        key=lambda pair: (
            pair[1].importance,
            bool(pair[1].desired_role),
            pair[1].duration,
        ),
        reverse=True,
    )
    chosen: set[int] = set()
    covered = 0.0
    for index, block in ranked:
        if covered >= target and chosen:
            break
        chosen.add(index)
        covered += block.duration

    return tuple(
        block
        for index, block in enumerate(eligible)
        if index in chosen
    )


def project_caption_plan(
    project: ProjectState,
    *,
    coverage_target: float = 0.65,
) -> tuple[CaptionBlock, ...]:
    transcript = project.transcript.strip()
    if not transcript:
        raise ValueError("Project chưa có transcript để tạo selective caption.")

    timeline_duration = sum(item.duration for item in project.timeline)
    spoken_duration = timeline_duration or project.target_seconds
    if project.voiceover:
        voice = Path(project.voiceover).expanduser().resolve()
        if voice.is_file():
            spoken_duration = probe_duration(voice)
    return plan_selective_captions(
        transcript,
        spoken_duration,
        coverage_target=coverage_target,
    )


def apply_selective_captions(
    project: ProjectState,
    *,
    coverage_target: float = 0.65,
    replace_existing: bool = True,
) -> dict[str, Any]:
    blocks = project_caption_plan(
        project,
        coverage_target=coverage_target,
    )
    if not blocks:
        raise ValueError("Không tạo được selective caption từ transcript.")

    if replace_existing:
        project.texts = [
            item for item in project.texts
            if item.role != "caption"
        ]
    for block in blocks:
        project.texts.append(
            TextItem(
                start=block.start,
                end=block.end,
                text=block.text,
                role="caption",
                x=0.5,
                y=0.78,
                size=72,
                weight=700,
                color="#F4F1E9",
                align="center",
            )
        )
    project.dirty = True
    display = round(sum(block.duration for block in blocks), 3)
    speech_end = round(max(block.end for block in blocks), 3)
    return {
        "status": "DONE",
        "caption_blocks": len(blocks),
        "display_seconds": display,
        "last_caption_end": speech_end,
        "coverage_target": float(coverage_target),
        "blocks": [block.to_dict() for block in blocks],
    }


def apply_selective_captions_to_file(
    project_path: Path,
    *,
    coverage_target: float = 0.65,
) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-selective-captions",
    )
    result = apply_selective_captions(
        project,
        coverage_target=coverage_target,
    )
    project.save(project_path)
    result["project"] = str(project_path)
    result["checkpoint"] = str(checkpoint)
    return result
