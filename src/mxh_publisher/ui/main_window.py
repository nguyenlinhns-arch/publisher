from __future__ import annotations

import tkinter as tk
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from ..config import AppConfig, load_config, write_basic_config
from ..models import Platform, Post
from ..repository import Repository
from ..secrets import FACEBOOK_TOKEN_NAME, SecretStore
from ..services.doctor import format_doctor, run_doctor
from ..services.media import ingest_video, inspect_video
from ..services.backup import backup_database
from ..services.next_action import next_action
from ..services.orchestrator import ActionResult, PublishingOrchestrator


DATE_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_HASHTAGS = "#ThầyLinhTuyểnThợMỏ #NghềMỏ #TKV #ViệcLàm"

STATUS_VI = {
    "draft": "Nháp",
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

        self.title("MXH Publisher v0.3.2 — Facebook & TikTok")
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
            connections, text="Kết nối Facebook", command=self.connect_facebook
        )
        facebook_connect.grid(row=0, column=2, padx=3)
        facebook_check = ttk.Button(
            connections, text="Kiểm tra", command=self.check_facebook_connection
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
            [facebook_connect, facebook_check, tiktok_connect, tiktok_check]
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
        form.rowconfigure(2, weight=1)

        ttk.Label(form, text="Tiêu đề quản lý").grid(
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

        ttk.Label(form, text="Caption chung").grid(row=2, column=0, sticky="nw", pady=4)
        self.caption_text = tk.Text(form, height=9, wrap="word", undo=True)
        self.caption_text.grid(row=2, column=1, columnspan=2, sticky="nsew", pady=4)

        ttk.Label(form, text="Hashtag").grid(row=3, column=0, sticky="nw", pady=4)
        ttk.Entry(form, textvariable=self.hashtags_var).grid(
            row=3, column=1, columnspan=2, sticky="new", pady=4
        )

        ttk.Label(form, text="Giờ đăng (VN)").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.schedule_var).grid(
            row=4, column=1, sticky="ew", pady=4
        )
        ttk.Label(form, text="YYYY-MM-DD HH:MM").grid(
            row=4, column=2, sticky="w", padx=(6, 0)
        )

        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for index in range(4):
            actions.columnconfigure(index, weight=1)

        self.primary_button = ttk.Button(actions, text="Tiếp tục", command=self.run_primary_action)
        self.primary_button.grid(row=0, column=0, columnspan=4, sticky="ew", padx=3, pady=(3, 8))
        self._busy_widgets.append(self.primary_button)
        buttons = [
            ("Bài mới", self.clear_form),
            ("Dry-run chi tiết", self.dry_run),
            ("Ghi nhận link đã đăng", self.record_published),
            ("Thử lại sau kiểm tra", self.requeue_after_check),
            ("Thiết lập/kiểm tra", self.open_settings),
        ]
        for index, (label, command) in enumerate(buttons):
            button = ttk.Button(actions, text=label, command=command)
            button.grid(row=1 + index // 4, column=index % 4, sticky="ew", padx=3, pady=3)
            self._busy_widgets.append(button)

        ttk.Separator(form).grid(row=6, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(
            form,
            text=(
                "TikTok: ứng dụng chỉ upload và điền caption, sau đó Thầy tự bấm Lên lịch. "
                "Facebook chỉ được lên lịch sau bước xác nhận TikTok."
            ),
            wraplength=650,
            foreground="#444444",
        ).grid(row=7, column=0, columnspan=3, sticky="w")

        status = ttk.Label(
            self, textvariable=self.status_var, relief="sunken", anchor="w"
        )
        status.grid(row=1, column=0, sticky="ew")

    def _refresh_connection_summary(self) -> None:
        page_id = self.config_data.facebook_page_id.strip()
        try:
            has_token = bool(self.secret_store.get(FACEBOOK_TOKEN_NAME))
        except Exception:
            has_token = False
        if page_id.isdigit() and has_token:
            self.facebook_connection_var.set(f"Đã cấu hình Page ID {page_id}")
        elif page_id.isdigit():
            self.facebook_connection_var.set("Thiếu Page access token")
        else:
            self.facebook_connection_var.set("Chưa kết nối")
        account = self.config_data.tiktok_account_id.strip()
        self.tiktok_connection_var.set(
            f"Đã cấu hình {account}" if account else "Chưa kết nối"
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

    def connect_facebook(self) -> None:
        opened = webbrowser.open(
            "https://developers.facebook.com/tools/explorer/", new=2
        )
        if not opened:
            messagebox.showwarning(
                "Không mở được trình duyệt",
                "Hãy mở https://developers.facebook.com/tools/explorer/ rồi đăng nhập.",
                parent=self,
            )
        self.open_settings()

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

    def run_primary_action(self) -> None:
        action = next_action(self.repository, self.selected_post_id)
        commands = {
            "save": self.save_draft,
            "approve": self.approve_and_schedule,
            "prepare_tiktok": self.prepare_tiktok,
            "verify_tiktok": self.confirm_and_schedule_facebook,
            "recover": self.requeue_after_check,
            "reconcile": self.record_published,
        }
        command = commands.get(action.key)
        if command:
            command()

    def _refresh_primary_action(self) -> None:
        action = next_action(self.repository, self.selected_post_id)
        self.primary_button.configure(text=action.label)
        self.primary_button.state(["!disabled"] if action.enabled else ["disabled"])

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

    def clear_form(self) -> None:
        self.selected_post_id = None
        self.title_var.set("")
        self.video_source.set("")
        self.caption_text.delete("1.0", "end")
        self.hashtags_var.set(DEFAULT_HASHTAGS)
        self.schedule_var.set(
            (datetime.now(self.config_data.timezone) + timedelta(hours=2)).strftime(
                DATE_FORMAT
            )
        )
        self.tree.selection_remove(self.tree.selection())
        self.status_var.set("Đang tạo bài mới.")
        self._refresh_primary_action()

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
            expected_updated_at=current.updated_at if current else None,
        )

    def _save_draft_task(self, draft: DraftInput) -> Post:
        info = inspect_video(draft.source)
        if not info.is_valid:
            errors = "\n".join(
                "- " + issue.message
                for issue in info.issues
                if issue.severity == "error"
            )
            raise ValueError("Video chưa đạt chuẩn:\n" + errors)
        managed = ingest_video(draft.source, self.config_data.media_dir, info.sha256)
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
        draft = self._capture_draft_input()

        def success(post: Post) -> None:
            self.selected_post_id = post.id
            self.status_var.set("Đã lưu nháp và sao chép video vào thư mục an toàn.")

        self._run_background(
            lambda: self._save_draft_task(draft),
            working_message="Đang kiểm tra và sao chép video…",
            success=success,
        )

    def _require_selected(self) -> str | None:
        if not self.selected_post_id:
            messagebox.showwarning(
                "Chưa chọn bài", "Hãy lưu hoặc chọn một bài.", parent=self
            )
            return None
        return self.selected_post_id

    def approve_and_schedule(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        page_id = self.config_data.facebook_page_id.strip()
        tiktok_account_id = self.config_data.tiktok_account_id.strip()
        setup_errors = []
        if not page_id.isdigit():
            setup_errors.append("Facebook Page ID phải là số.")
        if not tiktok_account_id:
            setup_errors.append("Chưa cấu hình TikTok @username/account.")
        if setup_errors:
            messagebox.showerror(
                "Thiết lập chưa đầy đủ",
                "\n".join(setup_errors)
                + "\n\nHãy mở Thiết lập/kiểm tra, lưu thông tin rồi khởi động lại ứng dụng.",
                parent=self,
            )
            return
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
            return self.repository.schedule_post(
                saved.id,
                scheduled,
                destinations={
                    Platform.FACEBOOK: page_id,
                    Platform.TIKTOK: tiktok_account_id,
                },
            )

        self._run_background(
            task,
            working_message="Đang khóa nội dung và đặt lịch…",
            success=lambda saved_post: self._approved_success(saved_post),
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
        details = self._tiktok_schedule_details(post_id)
        if details is None:
            return
        account_id, scheduled_text = details

        def success(result: ActionResult) -> None:
            self.status_var.set(
                f"TikTok {account_id}: chờ xác nhận lịch {scheduled_text} (giờ Việt Nam)."
            )
            messagebox.showinfo(
                "TikTok Studio",
                f"Tài khoản TikTok: {account_id}\n"
                f"Giờ cần chọn: {scheduled_text} (giờ Việt Nam)\n\n"
                f"{result.message}",
                parent=self,
            )

        self._run_background(
            lambda: self.orchestrator.prepare_tiktok(post_id),
            working_message="Đang mở TikTok Studio và upload video…",
            success=success,
        )

    def confirm_and_schedule_facebook(self) -> None:
        post_id = self._require_selected()
        if not post_id:
            return
        details = self._tiktok_schedule_details(post_id)
        if details is None:
            return
        account_id, scheduled_text = details
        confirmation = simpledialog.askstring(
            "Xác nhận TikTok",
            f"Tài khoản TikTok: {account_id}\n"
            f"Giờ phải xuất hiện trong danh sách hẹn giờ: {scheduled_text} "
            "(giờ Việt Nam)\n\n"
            "Sau khi đã kiểm tra video và tự bấm Lên lịch trong TikTok Studio, "
            f"hãy nhập lại chính xác chuỗi sau để xác nhận:\n\n{scheduled_text}",
            parent=self,
        )
        if confirmation is None:
            return
        if confirmation.strip() != scheduled_text:
            messagebox.showerror(
                "Giờ xác nhận không khớp",
                f"Cần nhập chính xác: {scheduled_text}\n\n"
                f"Hãy kiểm tra lại lịch của tài khoản TikTok {account_id}.",
                parent=self,
            )
            return

        def success(result: ActionResult) -> None:
            self.status_var.set("Đã ghi nhận TikTok và xử lý lịch Facebook.")
            messagebox.showinfo("Kết quả", result.message, parent=self)

        self._run_background(
            lambda: self.orchestrator.confirm_tiktok_and_schedule_facebook(post_id),
            working_message="Đang upload và lên lịch Facebook qua API…",
            success=success,
        )

    def _tiktok_schedule_details(self, post_id: str) -> tuple[str, str] | None:
        post = self.repository.get_post(post_id)
        if post.scheduled_at is None:
            messagebox.showerror(
                "Bài chưa khóa lịch",
                "Hãy duyệt nội dung và khóa lịch trước khi chuẩn bị TikTok.",
                parent=self,
            )
            return None
        delivery = self.repository.get_delivery_for_platform(post_id, Platform.TIKTOK)
        account_id = (
            delivery.account_id or self.config_data.tiktok_account_id
        ).strip()
        if not account_id:
            messagebox.showerror(
                "Chưa cấu hình TikTok",
                "Hãy nhập TikTok @username/account trong Thiết lập/kiểm tra, "
                "sau đó khởi động lại ứng dụng.",
                parent=self,
            )
            return None
        scheduled_text = post.scheduled_at.astimezone(
            self.config_data.timezone
        ).strftime(DATE_FORMAT)
        return account_id, scheduled_text

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

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Thiết lập và kiểm tra")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        page_id = tk.StringVar(value=self.config_data.facebook_page_id)
        tiktok_account = tk.StringVar(value=self.config_data.tiktok_account_id)
        token = tk.StringVar()
        ttk.Label(dialog, text="Facebook Page ID").grid(
            row=0, column=0, padx=10, pady=8, sticky="w"
        )
        ttk.Entry(dialog, textvariable=page_id, width=45).grid(
            row=0, column=1, padx=10, pady=8, sticky="ew"
        )
        ttk.Label(dialog, text="TikTok @username/account").grid(
            row=1, column=0, padx=10, pady=8, sticky="w"
        )
        ttk.Entry(dialog, textvariable=tiktok_account, width=45).grid(
            row=1, column=1, padx=10, pady=8, sticky="ew"
        )
        ttk.Label(dialog, text="Page access token").grid(
            row=2, column=0, padx=10, pady=8, sticky="w"
        )
        ttk.Entry(dialog, textvariable=token, show="•", width=45).grid(
            row=2, column=1, padx=10, pady=8, sticky="ew"
        )
        result_box = tk.Text(dialog, width=76, height=14, wrap="word")
        result_box.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

        def save() -> None:
            value = page_id.get().strip()
            if not value.isdigit():
                messagebox.showerror("Page ID", "Page ID phải là số.", parent=dialog)
                return
            tiktok_value = tiktok_account.get().strip()
            if not tiktok_value:
                messagebox.showerror(
                    "TikTok account",
                    "TikTok @username/account không được để trống.",
                    parent=dialog,
                )
                return
            try:
                write_basic_config(
                    self.config_data,
                    page_id=value,
                    tiktok_account_id=tiktok_value,
                )
                if token.get().strip():
                    self.secret_store.set(FACEBOOK_TOKEN_NAME, token.get())
            except Exception as exc:
                messagebox.showerror("Không lưu được", str(exc), parent=dialog)
                return
            messagebox.showinfo(
                "Đã lưu",
                "Đã lưu cấu hình. Thiết lập mới có hiệu lực ngay trong cửa sổ này.",
                parent=dialog,
            )
            self.config_data = load_config()
            self.orchestrator = PublishingOrchestrator(
                self.repository, self.config_data, secret_store=self.secret_store
            )
            self._refresh_connection_summary()

        def doctor() -> None:
            result_box.delete("1.0", "end")
            result_box.insert("1.0", format_doctor(run_doctor(self.config_data)))

        buttons = ttk.Frame(dialog)
        buttons.grid(row=3, column=0, columnspan=2, pady=4)
        ttk.Button(buttons, text="Lưu thiết lập", command=save).pack(
            side="left", padx=5
        )
        ttk.Button(buttons, text="Chạy kiểm tra", command=doctor).pack(
            side="left", padx=5
        )
        ttk.Button(buttons, text="Đóng", command=dialog.destroy).pack(
            side="left", padx=5
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
        self._refresh_primary_action()

    def _on_select_post(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        post_id = selection[0]
        post = self.repository.get_post(post_id)
        self.selected_post_id = post_id
        self.title_var.set(post.title)
        self.video_source.set(post.video_path)
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
