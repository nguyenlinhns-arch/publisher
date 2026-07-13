from __future__ import annotations

import math
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from mxh_publisher.services.media import default_frame_path, inspect_video

from .config import EditorConfig
from .editor import (
    RenderedVideo,
    TRIM_END_SECONDS,
    TRIM_START_SECONDS,
    delete_rendered_video,
    list_rendered_videos,
    open_in_system,
    render_video,
)


class VideoEditorWindow:
    def __init__(self, root: tk.Tk, config: EditorConfig) -> None:
        self.root = root
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-editor")
        self.source_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.frame_var = tk.StringVar(value=str(default_frame_path()))
        self.status_var = tk.StringVar(value="Chọn video để bắt đầu.")
        self._busy = False

        root.title("MXH Video Editor v1.1.0")
        root.geometry("980x680")
        root.minsize(820, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self.refresh_outputs()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="SỬA VIDEO DỌC 9:16", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Cắt cố định 6,2 giây đầu và 4 giây cuối; giữ nguyên toàn bộ phần còn lại.",
        ).pack(anchor=tk.W, pady=(2, 14))

        form = ttk.LabelFrame(outer, text="Video cần sửa", padding=12)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Video gốc").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        ttk.Entry(form, textvariable=self.source_var, state="readonly").grid(row=0, column=1, sticky=tk.EW, pady=5)
        self.choose_button = ttk.Button(form, text="Chọn video", command=self.choose_video)
        self.choose_button.grid(row=0, column=2, padx=(10, 0), pady=5)

        ttk.Label(form, text="Tiêu đề trên video").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        ttk.Entry(form, textvariable=self.title_var).grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=5)

        ttk.Label(form, text="Nền xanh mặc định").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        ttk.Entry(form, textvariable=self.frame_var, state="readonly").grid(row=2, column=1, sticky=tk.EW, pady=5)
        self.frame_button = ttk.Button(form, text="Chọn nền khác", command=self.choose_frame)
        self.frame_button.grid(row=2, column=2, padx=(10, 0), pady=5)

        ttk.Label(form, text="Cắt video").grid(row=3, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        ttk.Label(
            form,
            text=f"Đầu: {TRIM_START_SECONDS:.1f} giây     Cuối: {TRIM_END_SECONDS:.1f} giây",
        ).grid(row=3, column=1, columnspan=2, sticky=tk.W, pady=5)

        self.render_button = ttk.Button(form, text="SỬA VÀ LƯU VIDEO", command=self.start_render)
        self.render_button.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(12, 5), ipady=6)
        self.progress = ttk.Progressbar(form, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(4, 2))

        result = ttk.LabelFrame(outer, text="Video thành phẩm đã lưu", padding=10)
        result.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        result.rowconfigure(0, weight=1)
        result.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(result, columns=("size", "created"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Tên video")
        self.tree.heading("size", text="Dung lượng")
        self.tree.heading("created", text="Ngày tạo")
        self.tree.column("#0", width=560, anchor=tk.W)
        self.tree.column("size", width=100, anchor=tk.CENTER)
        self.tree.column("created", width=150, anchor=tk.CENTER)
        self.tree.grid(row=0, column=0, columnspan=4, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(result, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=4, sticky=tk.NS)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())

        ttk.Button(result, text="Mở video", command=self.open_selected).grid(row=1, column=0, sticky=tk.EW, padx=(0, 5), pady=(10, 0))
        ttk.Button(result, text="Mở thư mục", command=self.open_output_folder).grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(10, 0))
        ttk.Button(result, text="Làm mới danh sách", command=self.refresh_outputs).grid(row=1, column=2, sticky=tk.EW, padx=5, pady=(10, 0))
        ttk.Button(result, text="Xóa video thành phẩm", command=self.delete_selected).grid(row=1, column=3, sticky=tk.EW, padx=(5, 0), pady=(10, 0))

        ttk.Label(outer, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, pady=(12, 0))

    def choose_video(self) -> None:
        selected = filedialog.askopenfilename(title="Chọn video gốc", filetypes=[("Video MP4", "*.mp4"), ("Tất cả tệp", "*.*")])
        if not selected:
            return
        path = Path(selected)
        self.source_var.set(str(path))
        if not self.title_var.get().strip():
            self.title_var.set(path.stem)
        self.status_var.set(f"Đã chọn: {path.name}")

    def choose_frame(self) -> None:
        selected = filedialog.askopenfilename(title="Chọn nền PNG 1080×1920", filetypes=[("Ảnh PNG", "*.png")])
        if selected:
            self.frame_var.set(selected)

    def start_render(self) -> None:
        if self._busy:
            return
        source = Path(self.source_var.get().strip())
        if not source.is_file():
            messagebox.showerror("Thiếu video", "Hãy chọn video gốc trước.")
            return
        title = self.title_var.get().strip() or source.stem
        frame = Path(self.frame_var.get().strip())
        try:
            info = inspect_video(source)
        except Exception as exc:
            messagebox.showerror("Không đọc được video", str(exc))
            return
        remaining = info.duration_seconds - TRIM_START_SECONDS - TRIM_END_SECONDS
        if not math.isfinite(remaining) or remaining <= 0:
            messagebox.showerror("Video quá ngắn", "Video phải dài hơn 10,2 giây để cắt 6,2 giây đầu và 4 giây cuối.")
            return

        self._set_busy(True)
        self.status_var.set(f"Đang sửa video… Thời lượng sau cắt khoảng {remaining:.1f} giây.")
        future = self.executor.submit(
            render_video, self.config, source, title, frame_path=frame
        )
        self.root.after(100, self._poll_render, future)

    def _poll_render(self, future: Future[RenderedVideo]) -> None:
        if not future.done():
            self.root.after(100, self._poll_render, future)
            return
        self._set_busy(False)
        try:
            result = future.result()
        except Exception as exc:
            self.status_var.set("Sửa video thất bại.")
            messagebox.showerror("Không sửa được video", str(exc))
            return
        self.refresh_outputs(select_path=result.path)
        self.status_var.set(f"Đã lưu video: {result.path}")
        messagebox.showinfo("Hoàn tất", f"Đã sửa và lưu video:\n{result.path}")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.choose_button.configure(state=state)
        self.frame_button.configure(state=state)
        self.render_button.configure(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def refresh_outputs(self, *, select_path: Path | None = None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        target = str(select_path.resolve()) if select_path else None
        selected_item: str | None = None
        for path in list_rendered_videos(self.config):
            stat = path.stat()
            size = f"{stat.st_size / (1024 * 1024):.1f} MB"
            created = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
            item = self.tree.insert("", tk.END, text=path.name, values=(size, created), tags=(str(path),))
            if target == str(path.resolve()):
                selected_item = item
        if selected_item:
            self.tree.selection_set(selected_item)
            self.tree.focus(selected_item)
            self.tree.see(selected_item)

    def _selected_path(self) -> Path | None:
        selection = self.tree.selection()
        if not selection:
            return None
        tags = self.tree.item(selection[0], "tags")
        return Path(tags[0]) if tags else None

    def open_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            messagebox.showinfo("Chưa chọn video", "Hãy chọn một video thành phẩm trong danh sách.")
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
        path = self._selected_path()
        if path is None:
            messagebox.showinfo("Chưa chọn video", "Hãy chọn video thành phẩm cần xóa.")
            return
        if not messagebox.askyesno("Xóa video thành phẩm", f"Xóa vĩnh viễn tệp này?\n\n{path.name}"):
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
                "Hãy đợi ứng dụng lưu xong video rồi mới đóng để tránh tệp bị lỗi.",
            )
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def run_gui(config: EditorConfig) -> None:
    root = tk.Tk()
    VideoEditorWindow(root, config)
    root.mainloop()
