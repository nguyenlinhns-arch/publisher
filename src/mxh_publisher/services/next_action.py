from __future__ import annotations

from dataclasses import dataclass

from ..models import DeliveryStatus, Platform, PostStatus
from ..repository import Repository


@dataclass(frozen=True, slots=True)
class NextAction:
    key: str
    label: str
    explanation: str
    enabled: bool = True


def next_action(repository: Repository, post_id: str | None) -> NextAction:
    if not post_id:
        return NextAction("save", "Lưu và kiểm tra video", "Tạo bài mới từ nội dung hiện tại.")
    post, deliveries = repository.get_post_with_deliveries(post_id)
    by_platform = {item.platform: item for item in deliveries}
    if post.status in {PostStatus.DRAFT, PostStatus.APPROVED}:
        return NextAction("approve", "Kiểm tra & khóa lịch", "Lưu, duyệt nội dung và khóa tài khoản đích.")
    facebook = by_platform.get(Platform.FACEBOOK)
    tiktok = by_platform.get(Platform.TIKTOK)
    if not facebook or not tiktok:
        return NextAction("approve", "Kiểm tra & khóa lịch", "Bài chưa khóa đủ hai nền tảng.")
    if tiktok.status in {DeliveryStatus.PENDING, DeliveryStatus.RETRY_WAIT}:
        return NextAction("prepare_tiktok", "Chuẩn bị TikTok", "Dry-run tự chạy trước khi mở TikTok Studio.")
    if tiktok.status is DeliveryStatus.AWAITING_CONFIRMATION:
        return NextAction("verify_tiktok", "Xác minh TikTok & hẹn Facebook", "Đọc danh sách TikTok, sau đó mới hẹn Facebook.")
    if tiktok.status in {DeliveryStatus.UNKNOWN, DeliveryStatus.NEEDS_ACTION, DeliveryStatus.FAILED}:
        return NextAction("recover", "Mở phục hồi an toàn", "Cần đối soát trước khi thử lại.")
    if facebook.status in {DeliveryStatus.UNKNOWN, DeliveryStatus.NEEDS_ACTION, DeliveryStatus.FAILED}:
        return NextAction("recover", "Mở phục hồi an toàn", "Facebook cần đối soát trước khi thử lại.")
    if facebook.status is DeliveryStatus.PUBLISHED and tiktok.status is DeliveryStatus.PUBLISHED:
        return NextAction("done", "Đã hoàn tất", "Cả hai nền tảng đã được đối soát.", False)
    return NextAction("reconcile", "Đối soát kết quả", "Kiểm tra link và trạng thái từng nền tảng.")
