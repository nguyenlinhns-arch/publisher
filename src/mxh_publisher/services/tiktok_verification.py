from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


@dataclass(frozen=True, slots=True)
class TikTokVerification:
    matched: bool
    confidence: str
    message: str


def verify_content_text(
    visible_text: str, *, title: str, scheduled_local: datetime
) -> TikTokVerification:
    """Conservatively match a scheduled item from read-only Studio text.

    This never treats a partial match as permission to schedule Facebook.
    The browser adapter can feed the visible Content page text into this pure
    function without clicking Post, Schedule, Delete, or Edit.
    """
    compact = re.sub(r"\s+", " ", visible_text).casefold()
    title_tokens = [token for token in re.findall(r"\w+", title.casefold()) if len(token) >= 3]
    title_ok = bool(title_tokens) and all(token in compact for token in title_tokens[:5])
    candidates = {
        scheduled_local.strftime("%Y-%m-%d %H:%M").casefold(),
        scheduled_local.strftime("%d/%m/%Y %H:%M").casefold(),
        scheduled_local.strftime("%d-%m-%Y %H:%M").casefold(),
    }
    time_ok = any(value in compact for value in candidates)
    if title_ok and time_ok:
        return TikTokVerification(True, "high", "Đã thấy đúng tiêu đề và giờ hẹn trong TikTok Studio.")
    missing = []
    if not title_ok:
        missing.append("tiêu đề")
    if not time_ok:
        missing.append("giờ hẹn")
    return TikTokVerification(False, "insufficient", "Chưa xác minh chắc chắn: thiếu " + " và ".join(missing) + ".")
