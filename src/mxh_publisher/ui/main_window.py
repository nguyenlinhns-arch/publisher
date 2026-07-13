from __future__ import annotations

import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from ..config import AppConfig
from ..models import DeliveryStatus, Platform, Post, PostStatus
from ..repository import Repository
from ..secrets import SecretStore
from ..services.media import (
    VideoEditSpec,
    default_frame_path,
    inspect_video,
    render_social_video,
)
from ..services.backup import backup_database
from ..services.orchestrator import ActionResult, PublishingOrchestrator


DATE_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_HASHTAGS = "#ThầyLinhTuyểnThợMỏ #NghềMỏ #TKV #ViệcLàm"

STATUS_VI = {
    "draft": "Video đã sửa",
    "approved": "Đã duyệt",
    "ready": "Sẵn sàng",
    "scheduled": "Đã đặt lịch",
    "publishing": "Đang xử lý",
    "published": "Đã đăng",
    "completed": "Hoàn tất",
    "partial": "Đăng một phần",
    "needs_action": "Cần xử lý",
    "failed": "Lỗi",
    "cancelled": "Đã hủy",
    "pending": "Chờ",
    "preparing": "Đang chuẩn bị",
    "uploading": "Đang tải",
    "processing": "Đang xử lý",
    "awaiting_confirmation": "Chờ xác nhận",
    "retry_wait": "Chờ thử lại",
    "unknown": "Chưa rõ kết quả",
}


@dataclass(frozen=True, slots=True)
class DraftInput:
    post_id: str | None
    source: Path
    title: str
    caption: str
    hashtags: str
    frame: Path | None
    trim_start_seconds: float
    trim_end_seconds: float
    expected_updated_at: datetime | None


class MainWindow(tk.Tk):
    def __init__(self, config: AppConfig, repository: Repository) -> None:
        super().__init__()
        self.config_data = config
        self.repository = repository
        recovery_error: str | None = None
        try:
            recovered_tasks = repository.recover_expired_leases()
            startup_status = f"Đã kiểm tra và phục hồi {recovered_tasks} tác vụ bị gián đoạn."
        except Exception as exc:
            recovered_tasks = 0
            recovery_error = str(exc)
            startup_status = "Không kiểm tra được tác vụ bị gián đoạn; dữ liệu chưa bị thay đổi."
        self.secret_store = SecretStore()
        self.orchestrator = PublishingOrchestrator(
            repository, config, secret_store=self.secret_store
        )
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="publisher"
        )
        self.selected_post_id: str | None = None
        self.video_source = tk.StringVar()
        self.frame_source = tk.StringVar(value=str(default_frame_path()))
        self.trim_start_var = tk.StringVar(value="6.2")
        self.trim_end_var = tk.StringVar(value="4.0")
        self.title_var = tk.StringVar()
        self.hashtags_var = tk.StringVar(value=DEFAULT_HASHTAGS)
        self.schedule_var = tk.StringVar(
            value=(datetime.now(config.timezone) + timedelta(hours=2)).strftime(
                DATE_FORMAT
            )
        )
        self.status_var = tk.StringVar(value=startup_status)
        self.facebook_connection_var = tk.StringVar()
        self.tiktok_connection_var = tk.StringVar()
        self._busy_widgets: list[ttk.Button] = []
        self._busy = False

        self.title("MXH Publisher v0.5.2 — Biên tập, Facebook & TikTok")
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.refresh_posts()
        if recovered_tasks:
            self.after_idle(
                lambda: messagebox.showinfo(
                    "Phục hồi tác vụ",
                    f"Đã phục hồi {recovered_tasks} tác vụ bị gián đoạn từ lần chạy trước.",
                    parent=self,
                )
            )
        elif recovery_error is not None:
            self.after_idle(
                lambda: messagebox.showwarning(
                    "Chưa kiểm tra được tác vụ",
                    "Ứng dụng vẫn được mở nhưng chưa thể kiểm tra các tác vụ bị gián đoạn.\n\n"
                    f"Chi tiết: {recovery_error}",
                    parent=self,
                )
            )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer = ttk.Frame(self, padding=12)
        outer.grid(sticky="nsew")
        outer.columnconfigure(0, weight=2)
        outer.columnconfigure(1, weight=3)
        outer.rowconfigure(1, weight=1)

        connections = ttk.LabelFrame(outer, text="Kết nối nền tảng", padding=8)
        connections.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        connections.columnconfigure(1, weight=1)
        connections.columnconfigure(5, weight=1)

        ttk.Label(connections, text="Facebook", width=10).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(connections, textvariable=self.facebook_connection_var).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        facebook_connect = ttk.Button(
            connections,
            text="Kết nối Facebook",
            command=self.check_facebook_browser_connection,
        )
        facebook_connect.grid(row=0, column=2, padx=3)
        facebook_check = ttk.Button(
            connections,
            text="Kiểm tra lại",
            command=self.check_facebook_browser_connection,
        )
        facebook_check.grid(row=0, column=3, padx=(3, 14))

        ttk.Label(connections, text="TikTok", width=8).grid(
            row=0, column=4, sticky="w"
        )
        ttk.Label(connections, textvariable=self.tiktok_connection_var).grid(
            row=0, column=5, sticky="w", padx=(0, 8)
        )
        tiktok_connect = ttk.Button(
            connections, text="Mở kết nối", command=self.check_tiktok_connection
        )
        tiktok_connect.grid(row=0, column=6, padx=3)
        tiktok_check = ttk.Button(
            connections, text="Kiểm tra lại", command=self.check_tiktok_connection
        )
        tiktok_check.grid(row=0, column=7, padx=3)
        self._busy_widgets.extend(
            [
                facebook_connect,
                facebook_check,
                tiktok_connect,
                tiktok_check,
            ]
        )
        self._refresh_connection_summary()

        list_frame = ttk.LabelFrame(outer, text="Danh sách bài", padding=8)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("time", "status", "facebook", "tiktok"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Bài/video")
        self.tree.heading("time", text="Giờ đăng")
        self.tree.heading("status", text="Trạng thái")
        self.tree.heading("facebook", text="Facebook")
        self.tree.heading("tiktok", text="TikTok")
        self.tree.column("#0", width=180)
        self.tree.column("time", width=125)
        self.tree.column("status", width=95)
        self.tree.column("facebook", width=95)
        self.tree.column("tiktok", width=95)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_post)
        ttk.Button(list_frame, text="Làm mới", command=self.refresh_posts).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        form = ttk.LabelFrame(outer, text="Nội dung và lịch đăng", padding=12)
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(5, weight=1)

        ttk.Label(form, text="Tiêu đề trên video").grid(
            row=0, column=0, sticky="w", pady=4
        )
        ttk.Entry(form, textvariable=self.title_var).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=4
        )

        ttk.Label(form, text="Video MP4").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.video_source, state="readonly").grid(
            row=1, column=1, sticky="ew", pady=4
        )
        ttk.Button(form, text="Chọn video", command=self.choose_video).grid(
            row=1, column=2, padx=(6, 0), pady=4
        )

        ttk.Label(form, text="Khung nền mặc định").grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Entry(form, textvariable=self.frame_source, state="readonly").grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Button(form, text="Chọn khung", command=self.choose_frame).grid(
            row=2, column=2, padx=(6, 0), pady=4
        )

        trim_frame = ttk.Frame(form)
        trim_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Label(form, text="Cắt video").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(trim_frame, text="Đầu (giây)").pack(side="left")
        ttk.Entry(trim_frame, textvariable=self.trim_start_var, width=8).pack(
            side="left", padx=(5, 16)
        )
        ttk.Label(trim_frame, text="Cuối (giây)").pack(side="left")
        ttk.Entry(trim_frame, textvariable=self.trim_end_var, width=8).pack(
            side="left", padx=5
        )

        ttk.Label(
            form,
            text=(
                "Mặc định: khung xanh mẫu, video ngang ở giữa, tiêu đề trắng viền đen."
            ),
            foreground="#555555",
        ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 4))

        ttk.Label(form, text="Caption chung").grid(row=5, column=0, sticky="nw", pady=4)
        self.caption_text = tk.Text(form, height=9, wrap="word", undo=True)
        self.caption_text.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=4)

        ttk.Label(form, text="Hashtag").grid(row=6, column=0, sticky="nw", pady=4)
        ttk.Entry(form, textvariable=self.hashtags_var).grid(
            row=6, column=1, columnspan=2, sticky="new", pady=4
        )

        ttk.Label(form, text="Giờ đăng (VN)").grid(row=7, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.schedule_var).grid(
            row=7, column=1, sticky="ew", pady=4
        )
        ttk.Label(form, text="YYYY-MM-DD HH:MM").grid(
            row=7, column=2, sticky="w", padx=(6, 0)
        )

        actions = ttk.Frame(form)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for index in range(4):
            actions.columnconfigure(index, weight=1)

        buttons = [
            ("Sửa video", self.save_draft),
            ("Đăng FB", self.publish_facebook),
            ("Đăng TikTok", self.publish_tiktok),
            ("Xóa bài/video", self.delete_published_video),
        ]
        for index, (label, command) in enumerate(buttons):
            button = ttk.Button(actions, text=label, command=command)
            button.grid(row=0, column=index, sticky="ew", padx=3, pady=3)
            self._busy_widgets.append(button)

        ttk.Separator(form).grid(row=9, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(
            form,
            text=(
                "TikTok: ứng dụng tự tải, điền caption và đăng/lên lịch khi xác định "
                "chắc chắn các điều khiển. Facebook đăng Fanpage độc lập bằng Meta API."
            ),
            wraplength=650,
            foreground="#444444",
        ).grid(row=10, column=0, columnspan=3, sticky="w")

        status = ttk.Label(
            self, textvariable=self.status_var, relief="sunken", anchor="w"
        )
        status.grid(row=1, column=0, sticky="ew")

    def _refresh_connection_summary(self) -> None:
        facebook_profile = self.config_data.browser_profile_dir / "chrome"
        self.facebook_connection_var.set(
            "Có phiên đã lưu — bấm Kiểm tra"
            if facebook_profile.exists()
            else "Chưa kết nối"
        )
        self.tiktok_connection_var.set(
            "Có phiên đã lưu — bấm Kiểm tra"
            if facebook_profile.exists()
            else "Chưa kết nối"
        )

    def check_facebook_connection(self) -> None:
        self._run_background(
            self.orchestrator.verify_facebook_connection,
            working_message="Đang kiểm tra kết nối Facebook…",
            success=self._facebook_connection_success,
        )

    def _facebook_connection_success(self, page_name: str) -> None:
        message = f"Đã kết nối Facebook Page: {page_name}."
        self.facebook_connection_var.set(f"Đã kết nối: {page_name}")
        self.status_var.set(message)
        messagebox.showinfo("Đã kết nối", message, parent=self)

    def check_facebook_browser_connection(self) -> None:
        self._run_background(
            self.orchestrator.verify_facebook_browser_connection,
            working_message="Đang mở Facebook bằng hồ sơ Chrome của ứng dụng…",
            success=self._facebook_browser_connection_success,
        )

    def _facebook_browser_connection_success(self, result) -> None:
        self.facebook_connection_var.set(
            "Đã kết nối" if result.connected else "Chờ đăng nhập"
        )
        self.status_var.set(result.message)
        title = "Đã kết nối" if result.connected else "Đăng nhập Facebook"
        messagebox.showinfo(title, result.message, parent=self)

    def check_tiktok_connection(self) -> None:
        self._run_background(
            self.orchestrator.verify_tiktok_connection,
            working_message="Đang mở và kiểm tra TikTok Studio…",
            success=self._tiktok_connection_success,
        )

    def _tiktok_connection_success(self, result) -> None:
        account = self.config_data.tiktok_account_id.strip() or "TikTok"
        self.tiktok_connection_var.set(
            f"Đã kết nối: {account}" if result.connected else "Chờ đăng nhập/xác minh"
        )
        self.status_var.set(result.message)
        title = "Đã kết nối" if result.connected else "Cần đăng nhập/xác minh"
        messagebox.showinfo(title, result.message, parent=self)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        for widget in self._busy_widgets:
            widget.state(["disabled"] if busy else ["!disabled"])
        if message:
            self.status_var.set(message)

    def _run_background(
        self,
        function: Callable[[], Any],
        *,
        working_message: str,
        success: Callable[[Any], None] | None = None,
    ) -> None:
        self._set_busy(True, working_message)
        future = self.executor.submit(function)

        def done(completed: Future) -> None:
            self.after(0, lambda: self._complete_future(completed, success))

        future.add_done_callback(done)

    def _complete_future(
        self, future: Future, success: Callable[[Any], None] | None
    ) -> None:
        self._set_busy(False)
        try:
            result = future.result()
        except Exception as exc:
            self.status_var.set("Lỗi: " + str(exc))
            messagebox.showerror("Không thực hiện được", str(exc), parent=self)
            self.refresh_posts()
            return
        if success:
            success(result)
        self.refresh_posts()

    def choose_video(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Chọn video MP4",
            filetypes=[("Video MP4", "*.mp4"), ("Tất cả tệp", "*.*")],
        )
        if filename:
            self.video_source.set(filename)
            if not self.title_var.get().strip():
                self.title_var.set(Path(filename).stem)

    def choose_frame(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Chọn khung dọc 9:16",
            filetypes=[
                ("Khung PNG", "*.png"),
                ("Ảnh JPG", "*.jpg *.jpeg"),
                ("Tất cả tệp", "*.*"),
            ],
        )
        if filename:
            self.frame_source.set(filename)

    def clear_form(self) -> None:
        self.selected_post_id = None
        self.title_var.set("")
        self.video_source.set("")
        self.frame_source.set(str(default_frame_path()))
        self.trim_start_var.set("6.2")
        self.trim_end_var.set("4.0")
        self.caption_text.delete("1.0", "end")
        self.hashtags_var.set(DEFAULT_HASHTAGS)
        self.schedule_var.set(
            (datetime.now(self.config_data.timezone) + timedelta(hours=2)).strftime(
                DATE_FORMAT
            )
        )
        self.tree.selection_remove(self.tree.selection())
        self.status_var.set("Đang tạo bài mới.")

    def _local_schedule_utc(self) -> datetime:
        value = datetime.strptime(self.schedule_var.get().strip(), DATE_FORMAT)
        aware = value.replace(tzinfo=self.config_data.timezone)
        scheduled = aware.astimezone(UTC)
        if scheduled < datetime.now(UTC) + timedelta(
            minutes=self.config_data.minimum_schedule_lead_minutes
        ):
            raise ValueError(
                f"Giờ đăng phải cách hiện tại ít nhất "
                f"{self.config_data.minimum_schedule_lead_minutes} phút."
            )
        return scheduled

    def _capture_draft_input(self) -> DraftInput:
        source = Path(self.video_source.get().strip())
        try:
            trim_start = float(self.trim_start_var.get().strip().replace(",", "."))
            trim_end = float(self.trim_end_var.get().strip().replace(",", "."))
        except ValueError as exc:
            raise ValueError("Thời gian cắt đầu/cuối phải là số.") from exc
        if not math.isfinite(trim_start) or not math.isfinite(trim_end):
            raise ValueError("Thời gian cắt đầu/cuối phải là số hữu hạn.")
        if trim_start < 0 or trim_end < 0:
            raise ValueError("Thời gian cắt đầu/cuối không được âm.")
        frame_text = self.frame_source.get().strip()
        current = (
            self.repository.get_post(self.selected_post_id)
            if self.selected_post_id
            else None
        )
        return DraftInput(
            post_id=self.selected_post_id,
            source=source,
            title=self.title_var.get().strip() or source.stem,
            caption=self.caption_text.get("1.0", "end-1c").strip(),
            hashtags=self.hashtags_var.get().strip(),
            frame=Path(frame_text) if frame_text else None,
            trim_start_seconds=trim_start,
            trim_end_seconds=trim_end,
            expected_updated_at=current.updated_at if current else None,
        )

    def _save_draft_task(self, draft: DraftInput) -> Post:
        current = self.repository.get_post(draft.post_id) if draft.post_id else None
        same_rendered_video = False
        if current is not None:
            try:
                same_rendered_video = (
                    draft.source.expanduser().resolve()
                    == Path(current.video_path).expanduser().resolve()
                )
            except OSError:
                same_rendered_video = False
        if same_rendered_video:
            info = inspect_video(draft.source)
        else:
            info = render_social_video(
                draft.source,
                self.config_data.media_dir / "edited",
                VideoEditSpec(
                    trim_start_seconds=draft.trim_start_seconds,
                    trim_end_seconds=draft.trim_end_seconds,
                    frame_path=draft.frame,
                    title=draft.title,
                ),
            )
        if not info.is_valid:
            errors = "\n".join(
                "- " + issue.message
                for issue in info.issues
                if issue.severity == "error"
            )
            raise ValueError("Video chưa đạt chuẩn:\n" + errors)
        managed = info.path
        if draft.post_id:
            return self.repository.update_post(
                draft.post_id,
                title=draft.title,
                video_path=str(managed),
                video_sha256=info.sha256,
                caption=draft.caption,
                hashtags=draft.hashtags,
                timezone_name=self.config_data.timezone_name,
                expected_updated_at=draft.expected_updated_at,
            )
        return self.repository.create_post(
            title=draft.title,
            video_path=str(managed),
            video_sha256=info.sha256,
            caption=draft.caption,
            hashtags=draft.hashtags,
            timezone_name=self.config_data.timezone_name,
        )

    def save_draft(self) -> None:
        if not self.video_source.get().strip():
            messagebox.showwarning(
                "Thiếu video", "Hãy chọn video MP4 trước.", parent=self
            )
            return
        try:
            draft = self._capture_draft_input()
        except ValueError as exc:
            messagebox.showerror("Thiết lập biên tập chưa hợp lệ", str(exc), parent=self)
            return

        def success(post: Post) -> None:
            self.selected_post_id = post.id
            self.video_source.set(post.video_path)
            message = f"Đã sửa và lưu file video tại:\n{post.video_path}"
            self.status_var.set(message.replace("\n", " "))
            messagebox.showinfo("Đã lưu video đã sửa", message, parent=self)

        self._run_background(
            lambda: self._save_draft_task(draft),
            working_message="Đang cắt video, ghép khung và xuất 1080×1920…",
            success=success,
        )

    def _require_selected(self) -> str | None:
        if not self.selected_post_id:
            messagebox.showwarning(
                "Chưa chọn bài", "Hãy lưu hoặc chọn một bài.", parent=self
            )
            return None
        return self.selected_post_id

    def approve_and_schedule(
        self,
        *,
        continue_to_tiktok: bool = False,
        continue_to_facebook: bool = False,
    ) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        page_id = self.config_data.facebook_page_id.strip()
        tiktok_account_id = (
            self.config_data.tiktok_account_id.strip() or "chrome-profile"
        )
        try:
            scheduled = self._local_schedule_utc()
            draft = self._capture_draft_input()
        except ValueError as exc:
            messagebox.showerror("Giờ đăng không hợp lệ", str(exc), parent=self)
            return

        def task() -> Post:
            backup_database(
                self.config_data.database_path, self.config_data.root_dir / "backups"
            )
            saved = self._save_draft_task(draft)
            self.repository.approve_post(saved.id)
            destinations = {Platform.TIKTOK: tiktok_account_id}
            if page_id.isdigit():
                destinations[Platform.FACEBOOK] = page_id
            return self.repository.schedule_post(
                saved.id, scheduled, destinations=destinations
            )

        def success(saved_post: Post) -> None:
            self._approved_success(saved_post)
            if continue_to_tiktok:
                self.after_idle(self.prepare_tiktok)
            elif continue_to_facebook:
                self.after_idle(self.schedule_facebook)

        self._run_background(
            task,
            working_message="Đang khóa nội dung và đặt lịch…",
            success=success,
        )

    def _approved_success(self, post: Post) -> None:
        self.selected_post_id = post.id
        self.status_var.set(
            "Đã lưu nội dung hiện tại, duyệt và đặt lịch trong ứng dụng."
        )

    def dry_run(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return

        def success(report) -> None:
            self.status_var.set("Dry-run hoàn tất.")
            messagebox.showinfo("Kết quả dry-run", report.as_text(), parent=self)

        self._run_background(
            lambda: self.orchestrator.dry_run(post_id),
            working_message="Đang kiểm tra dry-run…",
            success=success,
        )

    def prepare_tiktok(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return

        def success(result: ActionResult) -> None:
            state = result.platform_result.state if result.platform_result else ""
            self.status_var.set(result.message)
            messagebox.showinfo(
                "TikTok đã xử lý" if state in {"scheduled", "published"} else "TikTok Studio",
                result.message,
                parent=self,
            )

        self._run_background(
            lambda: self.orchestrator.prepare_tiktok(post_id),
            working_message="Đang mở TikTok Studio và upload video…",
            success=success,
        )

    def publish_tiktok(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        post = self.repository.get_post(post_id)
        if post.status in {PostStatus.DRAFT, PostStatus.APPROVED}:
            self.approve_and_schedule(continue_to_tiktok=True)
            return
        try:
            delivery = self.repository.get_delivery_for_platform(
                post_id, Platform.TIKTOK
            )
        except Exception:
            messagebox.showerror(
                "TikTok chưa có lịch",
                "Bài chưa có tác vụ TikTok. Hãy sửa video rồi thử lại.",
                parent=self,
            )
            return
        if delivery.status in {DeliveryStatus.PENDING, DeliveryStatus.RETRY_WAIT}:
            self.prepare_tiktok()
            return
        if delivery.status is DeliveryStatus.AWAITING_CONFIRMATION:
            messagebox.showinfo(
                "TikTok đang chờ xác nhận",
                "Video đã được đưa vào TikTok Studio. Hãy kiểm tra và tự bấm "
                "Lên lịch, sau đó dùng nút Đăng FB.",
                parent=self,
            )
            return
        if delivery.status in {DeliveryStatus.SCHEDULED, DeliveryStatus.PUBLISHED}:
            messagebox.showinfo(
                "TikTok đã xử lý",
                "TikTok đã được đăng/lên lịch. Ứng dụng không gửi lại để tránh trùng.",
                parent=self,
            )
            return
        messagebox.showinfo(
            "Không tải lại TikTok",
            f"TikTok đang ở trạng thái {STATUS_VI.get(delivery.status.value, delivery.status.value)}. "
            "Ứng dụng không tải lại để tránh đăng trùng.",
            parent=self,
        )

    def publish_facebook(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        post = self.repository.get_post(post_id)
        if post.status in {PostStatus.DRAFT, PostStatus.APPROVED}:
            self.approve_and_schedule(continue_to_facebook=True)
            return
        self.schedule_facebook()

    def delete_published_video(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        post, deliveries = self.repository.get_post_with_deliveries(post_id)
        video = Path(post.video_path).expanduser().resolve()
        media_root = self.config_data.media_dir.expanduser().resolve()
        if post.status is PostStatus.DRAFT and not deliveries:
            if not messagebox.askyesno(
                "Xóa video đã sửa",
                "Xóa mục Video đã sửa khỏi danh sách và xóa bản video trong thư "
                "mục ứng dụng? Video gốc không bị xóa.",
                parent=self,
            ):
                return

            def delete_draft_task() -> Path:
                self.repository.delete_post(post_id)
                if media_root in video.parents:
                    video.unlink(missing_ok=True)
                return video

            def delete_draft_success(_deleted: Path) -> None:
                self.clear_form()
                self.status_var.set("Đã xóa mục và bản video đã sửa.")
                messagebox.showinfo(
                    "Đã xóa",
                    "Đã xóa mục và bản video đã sửa. Video gốc vẫn được giữ.",
                    parent=self,
                )

            self._run_background(
                delete_draft_task,
                working_message="Đang xóa mục và bản video đã sửa…",
                success=delete_draft_success,
            )
            return
        unsafe_statuses = {
            DeliveryStatus.PENDING,
            DeliveryStatus.PREPARING,
            DeliveryStatus.UPLOADING,
            DeliveryStatus.PROCESSING,
            DeliveryStatus.AWAITING_CONFIRMATION,
            DeliveryStatus.SCHEDULED,
            DeliveryStatus.RETRY_WAIT,
            DeliveryStatus.UNKNOWN,
        }
        if any(delivery.status in unsafe_statuses for delivery in deliveries):
            messagebox.showwarning(
                "Chưa được xóa video",
                "File video đang còn tác vụ chờ hoặc chưa rõ kết quả. Hãy hoàn tất "
                "việc đăng/đối soát trước khi xóa.",
                parent=self,
            )
            return
        if media_root not in video.parents:
            messagebox.showerror(
                "Không xóa file gốc",
                "Video này không nằm trong thư mục xuất của ứng dụng nên sẽ không "
                "bị xóa. Ứng dụng không bao giờ xóa video gốc của Thầy.",
                parent=self,
            )
            return
        if not video.exists():
            messagebox.showinfo(
                "Video đã được xóa",
                "File video xuất không còn trên máy; lịch sử đăng vẫn được giữ lại.",
                parent=self,
            )
            return
        confirmed = messagebox.askyesno(
            "Xóa video đã đăng",
            "Chỉ xóa bản video xuất trên máy. Bài trên Facebook/TikTok và lịch sử "
            "đối soát vẫn được giữ nguyên.\n\nBạn có chắc muốn xóa không?",
            parent=self,
        )
        if not confirmed:
            return

        def task() -> Path:
            video.unlink()
            return video

        def success(deleted: Path) -> None:
            self.status_var.set(f"Đã xóa file video đã đăng: {deleted.name}")
            self.video_source.set("")
            messagebox.showinfo(
                "Đã xóa video",
                "Đã xóa bản video xuất trên máy. Bài Facebook/TikTok không bị xóa.",
                parent=self,
            )

        self._run_background(
            task,
            working_message="Đang xóa bản video đã đăng trên máy…",
            success=success,
        )

    def schedule_facebook(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return

        def success(result: ActionResult) -> None:
            self.status_var.set("Đã xử lý lịch Facebook.")
            messagebox.showinfo("Kết quả", result.message, parent=self)

        self._run_background(
            lambda: self.orchestrator.schedule_facebook(post_id),
            working_message="Đang upload và lên lịch Facebook qua API…",
            success=success,
        )

    def record_published(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        platform_text = simpledialog.askstring(
            "Nền tảng", "Nhập facebook hoặc tiktok:", parent=self
        )
        if not platform_text:
            return
        try:
            platform = Platform(platform_text.strip().lower())
        except ValueError:
            messagebox.showerror(
                "Sai nền tảng", "Chỉ nhập facebook hoặc tiktok.", parent=self
            )
            return
        remote_id = simpledialog.askstring(
            "ID bài đăng", "Nhập ID bài đăng trên nền tảng:", parent=self
        )
        if not remote_id:
            return
        url = simpledialog.askstring(
            "Đường dẫn", "Dán đường dẫn bài đăng (có thể để trống):", parent=self
        )
        confirmed = messagebox.askyesno(
            "Xác nhận bằng chứng",
            "Thầy đã trực tiếp mở nền tảng và xác nhận đúng ID/link này là bài đã "
            "đăng của video đang chọn chưa?",
            parent=self,
        )
        if not confirmed:
            return
        self._run_background(
            lambda: self.orchestrator.record_manual_published(
                post_id,
                platform,
                remote_post_id=remote_id,
                permalink_url=url,
            ),
            working_message="Đang lưu kết quả đối soát…",
            success=lambda result: self.status_var.set(result.message),
        )

    def requeue_after_check(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        platform_text = simpledialog.askstring(
            "Nền tảng", "Nhập facebook hoặc tiktok:", parent=self
        )
        if not platform_text:
            return
        try:
            platform = Platform(platform_text.strip().lower())
        except ValueError:
            messagebox.showerror(
                "Sai nền tảng", "Chỉ nhập facebook hoặc tiktok.", parent=self
            )
            return
        confirmed = messagebox.askyesno(
            "Xác nhận không có bài trùng",
            "Thầy đã kiểm tra trên nền tảng và chắc chắn tác vụ trước chưa tạo bài "
            "đăng hoặc lịch đăng nào chưa?\n\nChỉ tiếp tục khi câu trả lời là Có.",
            parent=self,
        )
        if not confirmed:
            return
        self._run_background(
            lambda: self.orchestrator.requeue_after_manual_check(post_id, platform),
            working_message="Đang đưa tác vụ về hàng chờ…",
            success=lambda result: self.status_var.set(result.message),
        )

    def refresh_posts(self) -> None:
        selected = self.selected_post_id
        for item in self.tree.get_children():
            self.tree.delete(item)
        for post in self.repository.list_posts(limit=500):
            deliveries = {
                delivery.platform: delivery
                for delivery in self.repository.list_deliveries(post_id=post.id)
            }
            local_time = (
                post.scheduled_at.astimezone(self.config_data.timezone).strftime(
                    DATE_FORMAT
                )
                if post.scheduled_at
                else "—"
            )
            facebook = deliveries.get(Platform.FACEBOOK)
            tiktok = deliveries.get(Platform.TIKTOK)
            self.tree.insert(
                "",
                "end",
                iid=post.id,
                text=post.title or Path(post.video_path).name,
                values=(
                    local_time,
                    STATUS_VI.get(post.status.value, post.status.value),
                    STATUS_VI.get(facebook.status.value, facebook.status.value)
                    if facebook
                    else "—",
                    STATUS_VI.get(tiktok.status.value, tiktok.status.value)
                    if tiktok
                    else "—",
                ),
            )
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)

    def _on_select_post(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        post_id = selection[0]
        post = self.repository.get_post(post_id)
        self.selected_post_id = post_id
        self.title_var.set(post.title)
        self.video_source.set(post.video_path)
        self.frame_source.set(str(default_frame_path()))
        self.trim_start_var.set("6.2")
        self.trim_end_var.set("4.0")
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", post.caption)
        self.hashtags_var.set(" ".join(post.hashtags))
        if post.scheduled_at:
            self.schedule_var.set(
                post.scheduled_at.astimezone(self.config_data.timezone).strftime(
                    DATE_FORMAT
                )
            )
        self.status_var.set(
            f"Đã chọn bài {post.id[:8]} — {STATUS_VI.get(post.status.value, post.status.value)}"
        )

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showwarning(
                "Tác vụ đang chạy",
                "Không thể đóng ứng dụng khi đang upload/đối soát. Hãy chờ tác vụ "
                "hoàn tất để trạng thái được lưu an toàn.",
                parent=self,
            )
            return
        self._set_busy(True, "Đang đóng trình duyệt và ứng dụng…")
        future = self.executor.submit(self.orchestrator.close)
        try:
            future.result(timeout=15)
        except Exception as exc:
            self._set_busy(False, "Chưa đóng được trình duyệt an toàn.")
            messagebox.showwarning(
                "Chưa thể đóng",
                "Ứng dụng chưa đóng được phiên trình duyệt an toàn. Hãy chờ rồi thử "
                f"lại.\n\nChi tiết: {exc}",
                parent=self,
            )
            return
        self.executor.shutdown(wait=True, cancel_futures=False)
        self.destroy()


def run_gui(config: AppConfig, repository: Repository) -> None:
    window = MainWindow(config, repository)
    window.mainloop()
