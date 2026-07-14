from __future__ import annotations

import os
import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from mxh_publisher.services.media import default_frame_path

from .config import EditorConfig
from .editor import (
    BatchRenderOutcome,
    BatchVideoItem,
    TRIM_END_SECONDS,
    TRIM_START_SECONDS,
    build_batch_items,
    delete_rendered_video,
    list_rendered_videos,
    open_in_system,
    render_video_batch,
)


@dataclass(slots=True)
class QueuedVideo:
    source: Path
    title: str
    status: str = "Chờ xử lý"


class VideoEditorWindow:
    def __init__(self, root: tk.Tk, config: EditorConfig) -> None:
        self.root = root
        self.config = config
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="video-editor",
        )
        self.title_var = tk.StringVar()
        self.frame_var = tk.StringVar(value=str(default_frame_path()))
        self.status_var = tk.StringVar(value="Chọn một hoặc nhiều video để bắt đầu.")
        self.queue_count_var = tk.StringVar(value="0 video")
        self.jobs: dict[str, QueuedVideo] = {}
        self._job_by_source: dict[str, str] = {}
        self._selected_job_id: str | None = None
        self._loading_title = False
        self._busy = False
        self._batch_events: queue.SimpleQueue[
            tuple[int, int, BatchRenderOutcome]
        ] = queue.SimpleQueue()
        self._active_items: tuple[BatchVideoItem, ...] = ()
        self.title_var.trace_add("write", self._on_title_changed)

        root.title("MXH Video Editor v1.2.1")
        root.geometry("1080x820")
        root.minsize(900, 700)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self.refresh_outputs()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text="SỬA VIDEO DỌC 9:16",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "Chọn nhiều video và sửa tuần tự; cắt cố định 6,2 giây đầu "
                "và 4 giây cuối."
            ),
        ).pack(anchor=tk.W, pady=(2, 12))

        batch = ttk.LabelFrame(outer, text="Danh sách video cần sửa", padding=10)
        batch.pack(fill=tk.BOTH, expand=True)
        batch.rowconfigure(0, weight=1)
        batch.columnconfigure(0, weight=1)

        self.queue_tree = ttk.Treeview(
            batch,
            columns=("title", "status"),
            show="tree headings",
            selectmode="extended",
            height=8,
        )
        self.queue_tree.heading("#0", text="Tên file")
        self.queue_tree.heading("title", text="Tiêu đề trên video")
        self.queue_tree.heading("status", text="Trạng thái")
        self.queue_tree.column("#0", width=280, anchor=tk.W)
        self.queue_tree.column("title", width=520, anchor=tk.W)
        self.queue_tree.column("status", width=150, anchor=tk.CENTER)
        self.queue_tree.grid(row=0, column=0, columnspan=4, sticky=tk.NSEW)
        queue_scrollbar = ttk.Scrollbar(
            batch,
            orient=tk.VERTICAL,
            command=self.queue_tree.yview,
        )
        queue_scrollbar.grid(row=0, column=4, sticky=tk.NS)
        self.queue_tree.configure(yscrollcommand=queue_scrollbar.set)
        self.queue_tree.bind("<<TreeviewSelect>>", self._on_queue_selection)

        self.choose_button = ttk.Button(
            batch,
            text="Chọn nhiều video",
            command=self.choose_videos,
        )
        self.choose_button.grid(row=1, column=0, sticky=tk.EW, padx=(0, 5), pady=8)
        self.remove_button = ttk.Button(
            batch,
            text="Bỏ video đã chọn",
            command=self.remove_selected_jobs,
        )
        self.remove_button.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=8)
        self.clear_button = ttk.Button(
            batch,
            text="Xóa danh sách",
            command=self.clear_jobs,
        )
        self.clear_button.grid(row=1, column=2, sticky=tk.EW, padx=5, pady=8)
        ttk.Label(batch, textvariable=self.queue_count_var, anchor=tk.E).grid(
            row=1,
            column=3,
            sticky=tk.EW,
            padx=(5, 0),
            pady=8,
        )

        ttk.Label(batch, text="Tiêu đề video đang chọn").grid(
            row=2,
            column=0,
            sticky=tk.W,
            pady=4,
        )
        self.title_entry = ttk.Entry(
            batch,
            textvariable=self.title_var,
            state=tk.DISABLED,
        )
        self.title_entry.grid(
            row=2,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            padx=(10, 0),
            pady=4,
        )

        ttk.Label(batch, text="Nền tin tức mặc định").grid(
            row=3,
            column=0,
            sticky=tk.W,
            pady=4,
        )
        ttk.Entry(batch, textvariable=self.frame_var, state="readonly").grid(
            row=3,
            column=1,
            columnspan=2,
            sticky=tk.EW,
            padx=(10, 5),
            pady=4,
        )
        self.frame_button = ttk.Button(
            batch,
            text="Chọn nền khác",
            command=self.choose_frame,
        )
        self.frame_button.grid(row=3, column=3, sticky=tk.EW, padx=(5, 0), pady=4)

        ttk.Label(batch, text="Cắt video").grid(
            row=4,
            column=0,
            sticky=tk.W,
            pady=4,
        )
        ttk.Label(
            batch,
            text=(
                f"Đầu: {TRIM_START_SECONDS:.1f} giây     "
                f"Cuối: {TRIM_END_SECONDS:.1f} giây"
            ),
        ).grid(row=4, column=1, columnspan=3, sticky=tk.W, padx=(10, 0), pady=4)

        self.render_button = ttk.Button(
            batch,
            text="SỬA TẤT CẢ VIDEO",
            command=self.start_batch_render,
        )
        self.render_button.grid(
            row=5,
            column=0,
            columnspan=4,
            sticky=tk.EW,
            pady=(10, 5),
            ipady=6,
        )
        self.progress = ttk.Progressbar(batch, mode="determinate")
        self.progress.grid(
            row=6,
            column=0,
            columnspan=4,
            sticky=tk.EW,
            pady=(3, 0),
        )

        result = ttk.LabelFrame(outer, text="Video thành phẩm đã lưu", padding=10)
        result.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        result.rowconfigure(0, weight=1)
        for column in range(4):
            result.columnconfigure(column, weight=1)

        self.output_tree = ttk.Treeview(
            result,
            columns=("size", "created"),
            show="tree headings",
            selectmode="browse",
            height=6,
        )
        self.output_tree.heading("#0", text="Tên video")
        self.output_tree.heading("size", text="Dung lượng")
        self.output_tree.heading("created", text="Ngày tạo")
        self.output_tree.column("#0", width=560, anchor=tk.W)
        self.output_tree.column("size", width=100, anchor=tk.CENTER)
        self.output_tree.column("created", width=150, anchor=tk.CENTER)
        self.output_tree.grid(row=0, column=0, columnspan=4, sticky=tk.NSEW)
        output_scrollbar = ttk.Scrollbar(
            result,
            orient=tk.VERTICAL,
            command=self.output_tree.yview,
        )
        output_scrollbar.grid(row=0, column=4, sticky=tk.NS)
        self.output_tree.configure(yscrollcommand=output_scrollbar.set)
        self.output_tree.bind("<Double-1>", lambda _event: self.open_selected())

        ttk.Button(result, text="Mở video", command=self.open_selected).grid(
            row=1,
            column=0,
            sticky=tk.EW,
            padx=(0, 5),
            pady=(10, 0),
        )
        ttk.Button(
            result,
            text="Mở thư mục",
            command=self.open_output_folder,
        ).grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(10, 0))
        ttk.Button(
            result,
            text="Làm mới danh sách",
            command=self.refresh_outputs,
        ).grid(row=1, column=2, sticky=tk.EW, padx=5, pady=(10, 0))
        ttk.Button(
            result,
            text="Xóa video thành phẩm",
            command=self.delete_selected,
        ).grid(row=1, column=3, sticky=tk.EW, padx=(5, 0), pady=(10, 0))

        ttk.Label(
            outer,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(10, 0))

    @staticmethod
    def _source_key(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    def choose_videos(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Chọn các video gốc",
            filetypes=[("Video MP4", "*.mp4"), ("Tất cả tệp", "*.*")],
        )
        if not selected:
            return
        added: list[str] = []
        for item in build_batch_items(Path(value) for value in selected):
            key = self._source_key(item.source)
            if key in self._job_by_source:
                continue
            job = QueuedVideo(source=item.source, title=item.title)
            item_id = self.queue_tree.insert(
                "",
                tk.END,
                text=item.source.name,
                values=(job.title, job.status),
            )
            self.jobs[item_id] = job
            self._job_by_source[key] = item_id
            added.append(item_id)
        self._update_queue_count()
        if added:
            self.queue_tree.selection_set(added[0])
            self.queue_tree.focus(added[0])
            self.queue_tree.see(added[0])
        skipped = len(selected) - len(added)
        suffix = f"; bỏ qua {skipped} video trùng" if skipped else ""
        self.status_var.set(f"Đã thêm {len(added)} video{suffix}.")

    def _on_queue_selection(self, _event: object | None = None) -> None:
        selection = self.queue_tree.selection()
        item_id = selection[0] if selection else None
        self._selected_job_id = item_id
        self._loading_title = True
        try:
            self.title_var.set(self.jobs[item_id].title if item_id else "")
        finally:
            self._loading_title = False
        state = tk.NORMAL if item_id and not self._busy else tk.DISABLED
        self.title_entry.configure(state=state)

    def _on_title_changed(self, *_args: object) -> None:
        if self._loading_title or self._selected_job_id is None:
            return
        job = self.jobs.get(self._selected_job_id)
        if job is None:
            return
        job.title = self.title_var.get()
        self.queue_tree.set(self._selected_job_id, "title", job.title)

    def remove_selected_jobs(self) -> None:
        if self._busy:
            return
        for item_id in self.queue_tree.selection():
            job = self.jobs.pop(item_id, None)
            if job is not None:
                self._job_by_source.pop(self._source_key(job.source), None)
            self.queue_tree.delete(item_id)
        self._selected_job_id = None
        self._loading_title = True
        self.title_var.set("")
        self._loading_title = False
        self.title_entry.configure(state=tk.DISABLED)
        self._update_queue_count()

    def clear_jobs(self) -> None:
        if self._busy or not self.jobs:
            return
        if not messagebox.askyesno(
            "Xóa danh sách",
            "Xóa toàn bộ video khỏi danh sách chờ?\n\nVideo gốc không bị xóa.",
        ):
            return
        for item_id in self.queue_tree.get_children():
            self.queue_tree.delete(item_id)
        self.jobs.clear()
        self._job_by_source.clear()
        self._selected_job_id = None
        self._loading_title = True
        self.title_var.set("")
        self._loading_title = False
        self.title_entry.configure(state=tk.DISABLED)
        self._update_queue_count()
        self.status_var.set("Đã xóa danh sách chờ; video gốc không bị thay đổi.")

    def _update_queue_count(self) -> None:
        self.queue_count_var.set(f"{len(self.jobs)} video")

    def choose_frame(self) -> None:
        selected = filedialog.askopenfilename(
            title="Chọn nền PNG 1080×1920",
            filetypes=[("Ảnh PNG", "*.png")],
        )
        if selected:
            self.frame_var.set(selected)

    def start_batch_render(self) -> None:
        if self._busy:
            return
        item_ids = self.queue_tree.get_children()
        if not item_ids:
            messagebox.showerror(
                "Chưa có video",
                "Hãy chọn một hoặc nhiều video trước.",
            )
            return
        frame = Path(self.frame_var.get().strip())
        if not frame.is_file():
            messagebox.showerror("Thiếu nền", "Không tìm thấy tệp nền đã chọn.")
            return

        items: list[BatchVideoItem] = []
        for item_id in item_ids:
            job = self.jobs[item_id]
            title = job.title.strip() or job.source.stem
            job.title = title
            job.status = "Chờ xử lý"
            self.queue_tree.item(
                item_id,
                values=(job.title, job.status),
            )
            items.append(BatchVideoItem(source=job.source, title=title))

        self._active_items = tuple(items)
        self._batch_events = queue.SimpleQueue()
        self.progress.configure(maximum=len(items), value=0)
        self._set_busy(True)
        self.status_var.set(
            f"Đang xử lý 1/{len(items)}: {items[0].source.name}"
        )
        future = self.executor.submit(
            render_video_batch,
            self.config,
            self._active_items,
            frame_path=frame,
            on_progress=self._enqueue_progress,
        )
        self.root.after(100, self._poll_batch, future)

    def _enqueue_progress(
        self,
        index: int,
        total: int,
        outcome: BatchRenderOutcome,
    ) -> None:
        self._batch_events.put((index, total, outcome))

    def _poll_batch(
        self,
        future: Future[tuple[BatchRenderOutcome, ...]],
    ) -> None:
        self._drain_batch_events()
        if not future.done():
            self.root.after(100, self._poll_batch, future)
            return
        self._drain_batch_events()
        self._set_busy(False)
        try:
            outcomes = future.result()
        except Exception as exc:
            self.status_var.set("Không thể hoàn thành hàng đợi video.")
            messagebox.showerror("Lỗi hàng đợi", str(exc))
            return

        succeeded = [item for item in outcomes if item.rendered is not None]
        failed = [item for item in outcomes if not item.succeeded]
        last_rendered = succeeded[-1].rendered if succeeded else None
        last_path = last_rendered.path if last_rendered else None
        self.refresh_outputs(select_path=last_path)
        self.status_var.set(
            f"Hoàn tất: {len(succeeded)} thành công, {len(failed)} lỗi."
        )
        if failed:
            details = "\n".join(
                f"• {item.item.source.name}: {item.error}"
                for item in failed[:8]
            )
            if len(failed) > 8:
                details += f"\n• … và {len(failed) - 8} lỗi khác"
            messagebox.showwarning(
                "Đã hoàn thành hàng đợi",
                f"Thành công: {len(succeeded)}\nLỗi: {len(failed)}\n\n{details}",
            )
        else:
            messagebox.showinfo(
                "Hoàn tất",
                f"Đã sửa và lưu thành công {len(succeeded)} video.",
            )

    def _drain_batch_events(self) -> None:
        while True:
            try:
                index, total, outcome = self._batch_events.get_nowait()
            except queue.Empty:
                return
            key = self._source_key(outcome.item.source)
            item_id = self._job_by_source.get(key)
            if item_id and item_id in self.jobs:
                job = self.jobs[item_id]
                job.status = "Hoàn tất" if outcome.succeeded else "Lỗi"
                self.queue_tree.item(
                    item_id,
                    values=(job.title, job.status),
                )
                self.queue_tree.see(item_id)
            self.progress.configure(value=index)
            if index < total:
                next_item = self._active_items[index]
                self.status_var.set(
                    f"Đang xử lý {index + 1}/{total}: {next_item.source.name}"
                )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for button in (
            self.choose_button,
            self.remove_button,
            self.clear_button,
            self.frame_button,
            self.render_button,
        ):
            button.configure(state=state)
        title_state = (
            tk.NORMAL
            if not busy and self._selected_job_id is not None
            else tk.DISABLED
        )
        self.title_entry.configure(state=title_state)

    def refresh_outputs(self, *, select_path: Path | None = None) -> None:
        for item in self.output_tree.get_children():
            self.output_tree.delete(item)
        target = str(select_path.resolve()) if select_path else None
        selected_item: str | None = None
        for path in list_rendered_videos(self.config):
            stat = path.stat()
            size = f"{stat.st_size / (1024 * 1024):.1f} MB"
            created = datetime.fromtimestamp(stat.st_mtime).strftime(
                "%d/%m/%Y %H:%M"
            )
            item = self.output_tree.insert(
                "",
                tk.END,
                text=path.name,
                values=(size, created),
                tags=(str(path),),
            )
            if target == str(path.resolve()):
                selected_item = item
        if selected_item:
            self.output_tree.selection_set(selected_item)
            self.output_tree.focus(selected_item)
            self.output_tree.see(selected_item)

    def _selected_output_path(self) -> Path | None:
        selection = self.output_tree.selection()
        if not selection:
            return None
        tags = self.output_tree.item(selection[0], "tags")
        return Path(tags[0]) if tags else None

    def open_selected(self) -> None:
        path = self._selected_output_path()
        if path is None:
            messagebox.showinfo(
                "Chưa chọn video",
                "Hãy chọn một video thành phẩm trong danh sách.",
            )
            return
        try:
            open_in_system(path)
        except Exception as exc:
            messagebox.showerror("Không mở được video", str(exc))

    def open_output_folder(self) -> None:
        try:
            open_in_system(self.config.output_dir)
        except Exception as exc:
            messagebox.showerror("Không mở được thư mục", str(exc))

    def delete_selected(self) -> None:
        path = self._selected_output_path()
        if path is None:
            messagebox.showinfo(
                "Chưa chọn video",
                "Hãy chọn video thành phẩm cần xóa.",
            )
            return
        if not messagebox.askyesno(
            "Xóa video thành phẩm",
            f"Xóa vĩnh viễn tệp này?\n\n{path.name}",
        ):
            return
        try:
            delete_rendered_video(self.config, path)
        except Exception as exc:
            messagebox.showerror("Không xóa được video", str(exc))
            return
        self.refresh_outputs()
        self.status_var.set(f"Đã xóa: {path.name}")

    def close(self) -> None:
        if self._busy:
            messagebox.showinfo(
                "Đang sửa video",
                "Hãy đợi ứng dụng xử lý xong hàng đợi rồi mới đóng.",
            )
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def run_gui(config: EditorConfig) -> None:
    root = tk.Tk()
    VideoEditorWindow(root, config)
    root.mainloop()
