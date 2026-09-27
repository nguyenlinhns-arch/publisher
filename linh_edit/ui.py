from __future__ import annotations

import hashlib
import os
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .article_ingest import apply_article, fetch_article
from .contact_sheet import extract_contact_sheet
from .cover import extract_cover
from .engine_adapter import render_project
from .paths import output_dir
from .planner import build_rough_cut, import_media
from .legacy_import import import_legacy_script
from .media import probe_duration
from .news_ingest import apply_news_content, resync_story_to_duration
from .project import MediaItem, ProjectState, SfxItem, TextItem
from .storyboard import import_storyboard as load_storyboard

APP_VERSION = "1.1.0"

PROFILE_LABELS = {
    "Travel / Công tác": "TRAVEL_DOCUMENTARY",
    "Talk / Chuyên gia": "TALKING_HEAD_EXPERT",
    "Tin tức": "EXPLAINER_NEWS",
    "Tuyển dụng": "DIRECT_RECRUITMENT",
}
PROFILE_NAMES = {value: key for key, value in PROFILE_LABELS.items()}

ROLES = [
    "visual_hook",
    "human",
    "work",
    "road_reset",
    "place",
    "life",
    "detail",
    "emotion",
    "ending",
]


class LinhEditWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.project = ProjectState(output_dir=str(output_dir()))
        self.project_path: Path | None = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="linh-edit")
        self.busy = False
        self.last_contact_sheet: Path | None = None

        self.status_var = tk.StringVar(value="Sẵn sàng.")
        self.profile_var = tk.StringVar(value=PROFILE_NAMES[self.project.profile])
        self.target_var = tk.DoubleVar(value=self.project.target_seconds)
        self.title_var = tk.StringVar(value=self.project.title)
        self.voice_var = tk.StringVar(value=self.project.voiceover)
        self.music_var = tk.StringVar(value=self.project.music)
        self.role_var = tk.StringVar(value="detail")
        self.score_var = tk.DoubleVar(value=0.5)

        root.title(f"Linh Edit {APP_VERSION}")
        root.geometry("1280x850")
        root.minsize(1080, 720)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_menu()
        self._build()
        self._refresh_all()

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Dự án mới", command=self.new_project)
        file_menu.add_command(label="Mở dự án...", command=self.open_project)
        file_menu.add_command(label="Nhập storyboard JSON...", command=self.import_storyboard_json)
        file_menu.add_command(
            label="Nhập dự án app cũ (script.json)...",
            command=self.import_legacy_project,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Lưu", command=self.save_project)
        file_menu.add_command(label="Lưu thành...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Mở thư mục thành phẩm", command=self.open_output_folder)
        file_menu.add_command(label="Mở contact sheet gần nhất", command=self.open_contact_sheet)
        file_menu.add_command(
            label="Xuất visual master không tiếng...",
            command=self.export_visual_master,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Thoát", command=self.close)
        menu.add_cascade(label="Tệp", menu=file_menu)
        self.root.configure(menu=menu)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        head = ttk.Frame(outer)
        head.pack(fill=tk.X)
        ttk.Label(head, text="LINH EDIT", font=("Segoe UI", 20, "bold")).pack(side=tk.LEFT)
        ttk.Label(
            head,
            text="  Một app cho Travel • Talk • Tin tức • Tuyển dụng",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, pady=(7, 0))

        quick = ttk.LabelFrame(outer, text="Dựng nhanh", padding=10)
        quick.pack(fill=tk.X, pady=(10, 8))
        for col in range(8):
            quick.columnconfigure(col, weight=1)

        ttk.Label(quick, text="Loại video").grid(row=0, column=0, sticky=tk.W)
        profile = ttk.Combobox(
            quick,
            textvariable=self.profile_var,
            values=list(PROFILE_LABELS),
            state="readonly",
            width=18,
        )
        profile.grid(row=1, column=0, sticky=tk.EW, padx=(0, 6))
        profile.bind("<<ComboboxSelected>>", lambda _e: self._mark_dirty())

        ttk.Label(quick, text="Thời lượng mục tiêu").grid(row=0, column=1, sticky=tk.W)
        ttk.Spinbox(
            quick,
            from_=10,
            to=180,
            increment=5,
            textvariable=self.target_var,
            width=9,
        ).grid(row=1, column=1, sticky=tk.EW, padx=6)

        ttk.Button(quick, text="＋ THÊM MEDIA", command=self.add_videos).grid(
            row=1, column=2, sticky=tk.EW, padx=6
        )
        ttk.Button(quick, text="🎙 GIỌNG ĐỌC", command=self.choose_voice).grid(
            row=1, column=3, sticky=tk.EW, padx=6
        )
        ttk.Button(quick, text="♫ NHẠC", command=self.choose_music).grid(
            row=1, column=4, sticky=tk.EW, padx=6
        )

        self.auto_button = ttk.Button(quick, text="AUTO EDIT", command=self.auto_edit)
        self.auto_button.grid(row=1, column=5, sticky=tk.EW, padx=6)

        self.preview_button = ttk.Button(quick, text="XEM THỬ", command=self.render_preview)
        self.preview_button.grid(row=1, column=6, sticky=tk.EW, padx=6)

        self.export_button = ttk.Button(quick, text="XUẤT VIDEO", command=self.export_final)
        self.export_button.grid(row=1, column=7, sticky=tk.EW, padx=(6, 0))

        ttk.Label(quick, text="Nguồn nội dung").grid(
            row=2, column=0, sticky=tk.W, pady=(8, 0)
        )
        self.news_button = ttk.Button(
            quick, text="DÁN NEWS / JSON", command=self.paste_news_clipboard
        )
        self.news_button.grid(
            row=2, column=1, columnspan=2, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        self.article_button = ttk.Button(
            quick, text="VIDEO TỪ LINK BÀI VIẾT", command=self.article_from_url
        )
        self.article_button.grid(
            row=2, column=3, columnspan=2, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        self.transcript_button = ttk.Button(
            quick, text="MỞ TRANSCRIPT", command=self.open_transcript
        )
        self.transcript_button.grid(
            row=2, column=5, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        self.source_label = ttk.Label(quick, text="Nguồn: thủ công", anchor=tk.W)
        self.source_label.grid(
            row=2, column=6, columnspan=2, sticky=tk.EW, padx=(6, 0), pady=(8, 0)
        )

        titlebar = ttk.Frame(outer)
        titlebar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(titlebar, text="Tiêu đề / ý chính").pack(side=tk.LEFT)
        title_entry = ttk.Entry(titlebar, textvariable=self.title_var)
        title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        title_entry.bind("<KeyRelease>", lambda _e: self._mark_dirty())
        ttk.Button(titlebar, text="Hook 3 tầng", command=self.add_hook).pack(side=tk.RIGHT)
        ttk.Button(titlebar, text="＋ Text", command=self.add_text).pack(side=tk.RIGHT, padx=(0, 6))

        middle = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        middle.pack(fill=tk.BOTH, expand=True)

        media_frame = ttk.LabelFrame(middle, text="Media", padding=8)
        timeline_frame = ttk.LabelFrame(middle, text="Timeline", padding=8)
        middle.add(media_frame, weight=2)
        middle.add(timeline_frame, weight=3)

        media_frame.rowconfigure(0, weight=1)
        media_frame.columnconfigure(0, weight=1)
        self.media_tree = ttk.Treeview(
            media_frame,
            columns=("role", "duration", "score"),
            show="tree headings",
            selectmode="extended",
        )
        self.media_tree.heading("#0", text="File")
        self.media_tree.heading("role", text="Vai trò")
        self.media_tree.heading("duration", text="Đoạn dùng")
        self.media_tree.heading("score", text="Ưu tiên")
        self.media_tree.column("#0", width=260)
        self.media_tree.column("role", width=105, anchor=tk.CENTER)
        self.media_tree.column("duration", width=85, anchor=tk.CENTER)
        self.media_tree.column("score", width=70, anchor=tk.CENTER)
        self.media_tree.grid(row=0, column=0, columnspan=5, sticky=tk.NSEW)
        ms = ttk.Scrollbar(media_frame, command=self.media_tree.yview)
        ms.grid(row=0, column=5, sticky=tk.NS)
        self.media_tree.configure(yscrollcommand=ms.set)
        self.media_tree.bind("<<TreeviewSelect>>", self._media_selected)

        ttk.Combobox(
            media_frame,
            textvariable=self.role_var,
            values=ROLES,
            state="readonly",
            width=13,
        ).grid(row=1, column=0, sticky=tk.EW, pady=(8, 0))
        ttk.Spinbox(
            media_frame,
            from_=0,
            to=1,
            increment=0.1,
            textvariable=self.score_var,
            width=6,
        ).grid(row=1, column=1, sticky=tk.EW, padx=4, pady=(8, 0))
        ttk.Button(media_frame, text="Áp dụng", command=self.apply_media_meta).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        ttk.Button(media_frame, text="→ Timeline", command=self.add_selected_to_timeline).grid(
            row=1, column=3, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        ttk.Button(media_frame, text="Bỏ", command=self.remove_media).grid(
            row=1, column=4, sticky=tk.EW, pady=(8, 0)
        )
        ttk.Button(media_frame, text="↑ Ảnh", command=lambda: self.move_media(-1)).grid(
            row=2, column=0, sticky=tk.EW, pady=(6, 0)
        )
        ttk.Button(media_frame, text="↓ Ảnh", command=lambda: self.move_media(1)).grid(
            row=2, column=1, sticky=tk.EW, padx=4, pady=(6, 0)
        )
        ttk.Label(
            media_frame,
            text="Thứ tự Media cũng là thứ tự ảnh News/Editorial",
        ).grid(row=2, column=2, columnspan=3, sticky=tk.W, padx=4, pady=(6, 0))

        timeline_frame.rowconfigure(0, weight=1)
        timeline_frame.columnconfigure(0, weight=1)
        self.timeline_tree = ttk.Treeview(
            timeline_frame,
            columns=("role", "start", "duration", "audio"),
            show="tree headings",
            selectmode="browse",
        )
        self.timeline_tree.heading("#0", text="# / File")
        self.timeline_tree.heading("role", text="Vai trò")
        self.timeline_tree.heading("start", text="In")
        self.timeline_tree.heading("duration", text="Dài")
        self.timeline_tree.heading("audio", text="Tiếng")
        self.timeline_tree.column("#0", width=290)
        self.timeline_tree.column("role", width=105, anchor=tk.CENTER)
        self.timeline_tree.column("start", width=70, anchor=tk.CENTER)
        self.timeline_tree.column("duration", width=70, anchor=tk.CENTER)
        self.timeline_tree.column("audio", width=65, anchor=tk.CENTER)
        self.timeline_tree.grid(row=0, column=0, columnspan=6, sticky=tk.NSEW)
        ts = ttk.Scrollbar(timeline_frame, command=self.timeline_tree.yview)
        ts.grid(row=0, column=6, sticky=tk.NS)
        self.timeline_tree.configure(yscrollcommand=ts.set)
        self.timeline_tree.bind("<Double-1>", lambda _e: self.edit_timeline_item())

        ttk.Button(timeline_frame, text="↑", command=lambda: self.move_timeline(-1)).grid(
            row=1, column=0, sticky=tk.EW, pady=(8, 0)
        )
        ttk.Button(timeline_frame, text="↓", command=lambda: self.move_timeline(1)).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        ttk.Button(timeline_frame, text="Sửa đoạn", command=self.edit_timeline_item).grid(
            row=1, column=2, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        ttk.Button(timeline_frame, text="Tách bản sao", command=self.duplicate_timeline_item).grid(
            row=1, column=3, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        ttk.Button(timeline_frame, text="Bỏ khỏi timeline", command=self.remove_timeline).grid(
            row=1, column=4, sticky=tk.EW, padx=4, pady=(8, 0)
        )
        self.duration_label = ttk.Label(timeline_frame, text="0.0s", anchor=tk.E)
        self.duration_label.grid(row=1, column=5, sticky=tk.EW, pady=(8, 0))

        audio = ttk.LabelFrame(outer, text="Âm thanh & Text", padding=8)
        audio.pack(fill=tk.X, pady=(8, 0))
        audio.columnconfigure(1, weight=1)
        audio.columnconfigure(3, weight=1)

        ttk.Label(audio, text="Giọng đọc").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(audio, textvariable=self.voice_var, state="readonly").grid(
            row=0, column=1, sticky=tk.EW, padx=6
        )
        ttk.Label(audio, text="Nhạc").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(audio, textvariable=self.music_var, state="readonly").grid(
            row=0, column=3, sticky=tk.EW, padx=6
        )
        ttk.Button(audio, text="SFX…", command=self.manage_sfx).grid(
            row=0, column=4, sticky=tk.EW, padx=(4, 4)
        )
        self.sfx_count_label = ttk.Label(audio, text="0 SFX")
        self.sfx_count_label.grid(row=0, column=5, sticky=tk.E, padx=(0, 8))
        self.text_count_label = ttk.Label(audio, text="0 text")
        self.text_count_label.grid(row=0, column=6, sticky=tk.E)

        status = ttk.Label(outer, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(fill=tk.X, pady=(8, 0))

    def _sync_project(self) -> None:
        self.project.profile = PROFILE_LABELS.get(
            self.profile_var.get(), "TRAVEL_DOCUMENTARY"
        )
        self.project.target_seconds = float(self.target_var.get())
        self.project.title = self.title_var.get().strip()
        self.project.voiceover = self.voice_var.get().strip()
        self.project.music = self.music_var.get().strip()

    def _mark_dirty(self) -> None:
        self._sync_project()
        self.project.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = self.project_path.name if self.project_path else self.project.name
        star = " *" if self.project.dirty else ""
        self.root.title(f"Linh Edit {APP_VERSION} — {name}{star}")

    def _refresh_all(self) -> None:
        self._refresh_media()
        self._refresh_timeline()
        self.text_count_label.configure(text=f"{len(self.project.texts)} text")
        self.sfx_count_label.configure(text=f"{len(self.project.sfx)} SFX")
        self.duration_label.configure(
            text=f"{sum(x.duration for x in self.project.timeline):.1f}s"
        )
        if hasattr(self, "source_label"):
            source = self.project.source_mode or "thủ công"
            if self.project.source_url:
                source += " • URL"
            self.source_label.configure(text=f"Nguồn: {source}")
        self._update_title()

    def _refresh_media(self) -> None:
        for item in self.media_tree.get_children():
            self.media_tree.delete(item)
        for index, item in enumerate(self.project.media):
            self.media_tree.insert(
                "",
                tk.END,
                iid=str(index),
                text=Path(item.path).name,
                values=(item.role, f"{item.duration:.1f}s", f"{item.score:.1f}"),
            )

    def _refresh_timeline(self) -> None:
        for item in self.timeline_tree.get_children():
            self.timeline_tree.delete(item)
        for index, item in enumerate(self.project.timeline):
            self.timeline_tree.insert(
                "",
                tk.END,
                iid=str(index),
                text=f"{index+1:02d}  {Path(item.path).name}",
                values=(
                    item.role,
                    f"{item.start:.2f}",
                    f"{item.duration:.2f}",
                    "ON" if item.keep_audio else "OFF",
                ),
            )
        self.duration_label.configure(
            text=f"{sum(x.duration for x in self.project.timeline):.1f}s"
        )

    def add_videos(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Chọn video hoặc ảnh",
            filetypes=[
                ("Media", "*.mp4 *.mov *.m4v *.webm *.jpg *.jpeg *.png *.webp *.bmp"),
                ("Video", "*.mp4 *.mov *.m4v *.webm"),
                ("Ảnh", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("Tất cả tệp", "*.*"),
            ],
        )
        if not selected:
            return
        self.status_var.set("Đang đọc media...")
        self.root.update_idletasks()
        added = 0
        errors: list[str] = []
        for value in selected:
            try:
                items = import_media([Path(value)])
                self.project.media.extend(items)
                added += len(items)
            except Exception as exc:
                errors.append(f"{Path(value).name}: {exc}")
        self.project.dirty = True
        self._refresh_all()
        self.status_var.set(f"Đã thêm {added} media.")
        if errors:
            messagebox.showwarning("Một số file chưa đọc được", "\n".join(errors[:8]))

    def _select_news_images(self) -> list[str]:
        existing = [item.path for item in self.project.media if item.kind == "image"]
        if existing:
            return existing
        selected = filedialog.askopenfilenames(
            title="Chọn ảnh cho News / Editorial",
            filetypes=[
                ("Ảnh", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("Tất cả tệp", "*.*"),
            ],
        )
        return list(selected)

    def paste_news_clipboard(self) -> None:
        if self.busy:
            return
        try:
            content = self.root.clipboard_get().strip()
        except tk.TclError:
            content = ""
        if not content:
            messagebox.showinfo("Clipboard trống", "Hãy sao chép bài viết hoặc JSON rồi thử lại.")
            return
        images = self._select_news_images()
        if not images:
            messagebox.showinfo("Chưa có ảnh", "News/Editorial cần ít nhất một ảnh.")
            return

        try:
            # Content changed: never silently reuse a voice made for an older transcript.
            self.voice_var.set("")
            self.project.voiceover = ""
            apply_news_content(
                self.project,
                content,
                images=images,
                minimum_scenes=3,
            )
        except Exception as exc:
            messagebox.showerror("Không tạo được News", str(exc))
            return

        self.profile_var.set("Tin tức")
        self.target_var.set(self.project.target_seconds)
        self.title_var.set(self.project.title)
        self._refresh_all()
        self.status_var.set(
            f"Đã hợp nhất News: {len(self.project.timeline)} cảnh • "
            f"{self.project.target_seconds:.1f}s. Chọn giọng đọc để căn lại đúng VO."
        )

    def article_from_url(self) -> None:
        if self.busy:
            return
        value = simpledialog.askstring(
            "Video từ link bài viết",
            "Dán URL bài viết công khai:",
            parent=self.root,
        )
        if not value or not value.strip():
            return
        url = value.strip()
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        workspace = Path(self.project.output_dir or output_dir()) / "_article_sources" / digest
        workspace.mkdir(parents=True, exist_ok=True)
        self._set_busy(True, "Đang lấy bài viết và ảnh nguồn...")

        future = self.executor.submit(fetch_article, url, workspace)

        def poll() -> None:
            if not future.done():
                self.root.after(150, poll)
                return
            self._set_busy(False)
            try:
                article = future.result()
                if not article.local_images:
                    raise ValueError("Không tải được ảnh hợp lệ từ bài viết.")
                self.voice_var.set("")
                self.project.voiceover = ""
                apply_article(self.project, article)
            except Exception as exc:
                self.status_var.set("Không lấy được bài viết.")
                messagebox.showerror("Video từ link chưa thành công", str(exc))
                return

            self.profile_var.set("Tin tức")
            self.target_var.set(self.project.target_seconds)
            self.title_var.set(self.project.title)
            self._refresh_all()
            self.status_var.set(
                f"Đã biên tập URL → {len(self.project.timeline)} cảnh, "
                f"{len(article.local_images)} ảnh nguồn. Hãy chọn giọng đọc."
            )

        self.root.after(150, poll)

    def open_transcript(self) -> None:
        transcript = self.project.transcript.strip()
        if not transcript:
            messagebox.showinfo(
                "Chưa có transcript",
                "Hãy dùng DÁN NEWS / JSON hoặc VIDEO TỪ LINK BÀI VIẾT trước.",
            )
            return
        if self.project_path:
            target = self.project_path.with_name(self.project_path.stem + "_transcript.txt")
        else:
            folder = Path(self.project.output_dir or output_dir()) / "_sources"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "linh_edit_transcript.txt"
        target.write_text(transcript + "\n", encoding="utf-8")
        self._open_path(target)

    def choose_voice(self) -> None:
        value = filedialog.askopenfilename(
            title="Chọn giọng đọc",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả tệp", "*.*")],
        )
        if value:
            self.voice_var.set(value)
            self.project.voiceover = value
            try:
                voice_seconds = probe_duration(Path(value))
                profile = PROFILE_LABELS.get(self.profile_var.get(), "TRAVEL_DOCUMENTARY")
                if profile == "EXPLAINER_NEWS" and self.project.story_scenes:
                    resync_story_to_duration(self.project, voice_seconds)
                    suggested = self.project.target_seconds
                    self.target_var.set(round(suggested, 1))
                    self.status_var.set(
                        f"Đã căn {len(self.project.story_scenes)} cảnh theo VO {voice_seconds:.1f}s."
                    )
                    self._refresh_all()
                else:
                    if profile == "TRAVEL_DOCUMENTARY":
                        suggested = max(45.0, min(90.0, voice_seconds + 6.0))
                    elif profile == "TALKING_HEAD_EXPERT":
                        suggested = max(10.0, min(90.0, voice_seconds))
                    else:
                        suggested = max(20.0, min(90.0, voice_seconds + 1.0))
                    self.target_var.set(round(suggested, 1))
                    self.status_var.set(
                        f"Đã đọc VO {voice_seconds:.1f}s → gợi ý video {suggested:.1f}s."
                    )
            except Exception:
                pass
            self._mark_dirty()

    def choose_music(self) -> None:
        value = filedialog.askopenfilename(
            title="Chọn nhạc nền",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả tệp", "*.*")],
        )
        if value:
            self.music_var.set(value)
            self._mark_dirty()

    def _media_selected(self, _event=None) -> None:
        selected = self.media_tree.selection()
        if not selected:
            return
        item = self.project.media[int(selected[0])]
        self.role_var.set(item.role)
        self.score_var.set(item.score)

    def apply_media_meta(self) -> None:
        selected = self.media_tree.selection()
        if not selected:
            return
        for iid in selected:
            item = self.project.media[int(iid)]
            item.role = self.role_var.get()
            item.score = float(self.score_var.get())
        self.project.dirty = True
        self._refresh_all()

    def add_selected_to_timeline(self) -> None:
        for iid in self.media_tree.selection():
            self.project.timeline.append(deepcopy(self.project.media[int(iid)]))
        self.project.dirty = True
        self._refresh_all()

    def remove_media(self) -> None:
        indices = sorted((int(x) for x in self.media_tree.selection()), reverse=True)
        for index in indices:
            self.project.media.pop(index)
        self.project.dirty = True
        self._refresh_all()

    def move_media(self, offset: int) -> None:
        selection = self.media_tree.selection()
        if len(selection) != 1:
            return
        index = int(selection[0])
        dest = index + offset
        if not 0 <= dest < len(self.project.media):
            return
        self.project.media[index], self.project.media[dest] = (
            self.project.media[dest],
            self.project.media[index],
        )
        self.project.dirty = True
        self._refresh_media()
        self.media_tree.selection_set(str(dest))
        self.media_tree.focus(str(dest))

    def auto_edit(self) -> None:
        self._sync_project()
        if not self.project.media:
            messagebox.showinfo("Chưa có video", "Hãy thêm footage trước.")
            return
        try:
            timeline = build_rough_cut(self.project)
        except Exception as exc:
            messagebox.showerror("Không tạo được rough cut", str(exc))
            return
        if not timeline:
            messagebox.showwarning("Chưa đủ footage", "Không tạo được timeline phù hợp.")
            return
        self.project.timeline = timeline
        self.project.dirty = True
        self._refresh_all()
        self.status_var.set(
            f"Auto Edit xong rough cut {sum(x.duration for x in timeline):.1f}s. "
            "Có thể double-click từng đoạn để tinh chỉnh."
        )

    def _selected_timeline_index(self) -> int | None:
        selection = self.timeline_tree.selection()
        return int(selection[0]) if selection else None

    def move_timeline(self, offset: int) -> None:
        index = self._selected_timeline_index()
        if index is None:
            return
        dest = index + offset
        if not 0 <= dest < len(self.project.timeline):
            return
        self.project.timeline[index], self.project.timeline[dest] = (
            self.project.timeline[dest],
            self.project.timeline[index],
        )
        self.project.dirty = True
        self._refresh_timeline()
        self.timeline_tree.selection_set(str(dest))

    def remove_timeline(self) -> None:
        index = self._selected_timeline_index()
        if index is None:
            return
        self.project.timeline.pop(index)
        self.project.dirty = True
        self._refresh_all()

    def duplicate_timeline_item(self) -> None:
        index = self._selected_timeline_index()
        if index is None:
            return
        self.project.timeline.insert(index + 1, deepcopy(self.project.timeline[index]))
        self.project.dirty = True
        self._refresh_all()
        self.timeline_tree.selection_set(str(index + 1))

    def edit_timeline_item(self) -> None:
        index = self._selected_timeline_index()
        if index is None:
            return
        item = self.project.timeline[index]
        win = tk.Toplevel(self.root)
        win.title("Sửa đoạn")
        win.transient(self.root)
        win.grab_set()

        vars_ = {
            "role": tk.StringVar(value=item.role),
            "start": tk.DoubleVar(value=item.start),
            "duration": tk.DoubleVar(value=item.duration),
            "x": tk.DoubleVar(value=item.x),
            "y": tk.DoubleVar(value=item.y),
            "scale": tk.DoubleVar(value=item.scale),
            "motion": tk.StringVar(value=item.motion),
            "keep_audio": tk.BooleanVar(value=item.keep_audio),
            "source_gain": tk.DoubleVar(value=item.source_gain),
        }
        rows = [
            ("Vai trò", "role"),
            ("In (giây)", "start"),
            ("Thời lượng", "duration"),
            ("Reframe X 0–1", "x"),
            ("Reframe Y 0–1", "y"),
            ("Scale", "scale"),
            ("Motion", "motion"),
            ("Gain tiếng gốc", "source_gain"),
        ]
        for row, (label, key) in enumerate(rows):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            if key == "role":
                ttk.Combobox(win, textvariable=vars_[key], values=ROLES, state="readonly").grid(
                    row=row, column=1, sticky=tk.EW, padx=10, pady=5
                )
            elif key == "motion":
                ttk.Combobox(
                    win,
                    textvariable=vars_[key],
                    values=["none", "slow_zoom"],
                    state="readonly",
                ).grid(row=row, column=1, sticky=tk.EW, padx=10, pady=5)
            else:
                ttk.Entry(win, textvariable=vars_[key]).grid(
                    row=row, column=1, sticky=tk.EW, padx=10, pady=5
                )
        ttk.Checkbutton(win, text="Giữ tiếng gốc", variable=vars_["keep_audio"]).grid(
            row=len(rows), column=0, columnspan=2, sticky=tk.W, padx=10, pady=5
        )

        def save() -> None:
            try:
                item.role = vars_["role"].get()
                item.start = max(0.0, float(vars_["start"].get()))
                item.duration = max(0.2, float(vars_["duration"].get()))
                item.x = min(1.0, max(0.0, float(vars_["x"].get())))
                item.y = min(1.0, max(0.0, float(vars_["y"].get())))
                item.scale = max(1.0, float(vars_["scale"].get()))
                item.motion = vars_["motion"].get()
                item.keep_audio = bool(vars_["keep_audio"].get())
                item.source_gain = max(0.0, min(4.0, float(vars_["source_gain"].get())))
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Giá trị chưa hợp lệ", str(exc), parent=win)
                return
            self.project.dirty = True
            self._refresh_all()
            win.destroy()

        ttk.Button(win, text="Lưu", command=save).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=10
        )
        win.columnconfigure(1, weight=1)

    def add_hook(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Hook 3 tầng")
        win.transient(self.root)
        win.grab_set()

        context = tk.StringVar(value="GIA LAI" if self.project.profile == "TRAVEL_DOCUMENTARY" else "")
        main = tk.StringVar(value="KHÔNG CHỈ LÀ" if self.project.profile == "TRAVEL_DOCUMENTARY" else "")
        keyword = tk.StringVar(value=self.title_var.get().strip())
        for row, (label, var) in enumerate([
            ("Context", context),
            ("Main", main),
            ("Keyword", keyword),
        ]):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=6)
            ttk.Entry(win, textvariable=var, width=42).grid(
                row=row, column=1, sticky=tk.EW, padx=10, pady=6
            )

        def save() -> None:
            self.project.texts = [x for x in self.project.texts if x.role not in {"context", "main", "keyword"}]
            if context.get().strip():
                self.project.texts.append(
                    TextItem(0.0, 3.0, context.get().strip(), "context", 0.5, 0.20, 60, 600, "#F4F1E9")
                )
            if main.get().strip():
                self.project.texts.append(
                    TextItem(0.5, 3.0, main.get().strip(), "main", 0.5, 0.27, 102, 700, "#F4F1E9")
                )
            if keyword.get().strip():
                self.project.texts.append(
                    TextItem(1.0, 3.0, keyword.get().strip(), "keyword", 0.5, 0.36, 138, 800, "#FFC928")
                )
            self.project.dirty = True
            self._refresh_all()
            win.destroy()

        ttk.Button(win, text="Áp dụng Hook", command=save).grid(
            row=3, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=10
        )
        win.columnconfigure(1, weight=1)

    def add_text(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Thêm text")
        win.transient(self.root)
        win.grab_set()
        text = tk.StringVar()
        start = tk.DoubleVar(value=3.0)
        end = tk.DoubleVar(value=6.0)
        for row, (label, var) in enumerate([
            ("Nội dung", text),
            ("Bắt đầu", start),
            ("Kết thúc", end),
        ]):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=6)
            ttk.Entry(win, textvariable=var, width=42).grid(
                row=row, column=1, sticky=tk.EW, padx=10, pady=6
            )

        def save() -> None:
            try:
                s, e = float(start.get()), float(end.get())
                if e <= s or not text.get().strip():
                    raise ValueError("Text hoặc timecode chưa hợp lệ.")
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Chưa hợp lệ", str(exc), parent=win)
                return
            self.project.texts.append(
                TextItem(s, e, text.get().strip(), "caption", 0.5, 0.78, 72, 700, "#F4F1E9")
            )
            self.project.dirty = True
            self._refresh_all()
            win.destroy()

        ttk.Button(win, text="Thêm", command=save).grid(
            row=3, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=10
        )
        win.columnconfigure(1, weight=1)

    def manage_sfx(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("SFX")
        win.geometry("720x360")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(
            frame,
            columns=("start", "gain"),
            show="tree headings",
            selectmode="browse",
        )
        tree.heading("#0", text="File")
        tree.heading("start", text="Thời điểm")
        tree.heading("gain", text="Gain")
        tree.column("#0", width=450)
        tree.column("start", width=90, anchor=tk.CENTER)
        tree.column("gain", width=80, anchor=tk.CENTER)
        tree.grid(row=0, column=0, columnspan=3, sticky=tk.NSEW)

        def refresh() -> None:
            for iid in tree.get_children():
                tree.delete(iid)
            for index, item in enumerate(self.project.sfx):
                tree.insert(
                    "",
                    tk.END,
                    iid=str(index),
                    text=Path(item.path).name,
                    values=(f"{item.start:.2f}s", f"{item.gain:.2f}"),
                )

        def add() -> None:
            path = filedialog.askopenfilename(
                title="Chọn SFX",
                parent=win,
                filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả tệp", "*.*")],
            )
            if not path:
                return
            start = simpledialog.askfloat(
                "Thời điểm",
                "SFX bắt đầu tại giây:",
                initialvalue=1.0,
                minvalue=0.0,
                parent=win,
            )
            if start is None:
                return
            gain = simpledialog.askfloat(
                "Gain",
                "Mức âm SFX (0.10–1.00 thường đủ):",
                initialvalue=0.30,
                minvalue=0.0,
                maxvalue=4.0,
                parent=win,
            )
            if gain is None:
                return
            self.project.sfx.append(SfxItem(path=path, start=start, gain=gain))
            self.project.dirty = True
            refresh()
            self._refresh_all()

        def remove() -> None:
            selection = tree.selection()
            if not selection:
                return
            self.project.sfx.pop(int(selection[0]))
            self.project.dirty = True
            refresh()
            self._refresh_all()

        ttk.Button(frame, text="＋ Thêm SFX", command=add).grid(
            row=1, column=0, sticky=tk.EW, pady=(8, 0)
        )
        ttk.Button(frame, text="Bỏ SFX", command=remove).grid(
            row=1, column=1, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        ttk.Button(frame, text="Đóng", command=win.destroy).grid(
            row=1, column=2, sticky=tk.EW, pady=(8, 0)
        )
        refresh()

    def _ensure_timeline(self) -> bool:
        self._sync_project()
        if self.project.timeline:
            return True
        if not self.project.media:
            messagebox.showinfo("Chưa có video", "Hãy thêm footage trước.")
            return False
        self.auto_edit()
        return bool(self.project.timeline)

    def _set_busy(self, value: bool, message: str = "") -> None:
        self.busy = value
        state = tk.DISABLED if value else tk.NORMAL
        self.auto_button.configure(state=state)
        self.preview_button.configure(state=state)
        self.export_button.configure(state=state)
        if hasattr(self, "news_button"):
            self.news_button.configure(state=state)
            self.article_button.configure(state=state)
            self.transcript_button.configure(state=state)
        if message:
            self.status_var.set(message)

    def render_preview(self) -> None:
        if self.busy or not self._ensure_timeline():
            return
        preview_dir = Path(self.project.output_dir or output_dir()) / "_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        target = preview_dir / "linh_edit_preview.mp4"
        self._render_async(target, preview=True)

    def export_visual_master(self) -> None:
        if self.busy or not self._ensure_timeline():
            return
        default_dir = Path(self.project.output_dir or output_dir())
        default_dir.mkdir(parents=True, exist_ok=True)
        initial = (self.project.title.strip() or "linh_edit") + "_visual_master_no_audio"
        target = filedialog.asksaveasfilename(
            title="Xuất visual master không tiếng",
            initialdir=str(default_dir),
            initialfile=initial + ".mp4",
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4")],
        )
        if target:
            safe_target = self._versioned_output(Path(target))
            self._render_async(
                safe_target,
                preview=False,
                include_audio=False,
            )

    def export_final(self) -> None:
        if self.busy or not self._ensure_timeline():
            return
        default_dir = Path(self.project.output_dir or output_dir())
        default_dir.mkdir(parents=True, exist_ok=True)
        initial = self.project.title.strip() or "linh_edit_final"
        target = filedialog.asksaveasfilename(
            title="Xuất video",
            initialdir=str(default_dir),
            initialfile=initial + ".mp4",
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4")],
        )
        if target:
            safe_target = self._versioned_output(Path(target))
            if safe_target != Path(target):
                self.status_var.set(
                    f"File đã tồn tại → xuất bản mới: {safe_target.name}"
                )
            self._render_async(safe_target, preview=False, include_audio=True)

    @staticmethod
    def _versioned_output(path: Path) -> Path:
        if not path.exists():
            return path
        number = 2
        while True:
            candidate = path.with_name(f"{path.stem}_v{number}{path.suffix}")
            if not candidate.exists():
                return candidate
            number += 1

    def _render_async(
        self,
        target: Path,
        *,
        preview: bool,
        include_audio: bool = True,
    ) -> None:
        self._sync_project()
        snapshot = deepcopy(self.project)
        self._set_busy(True, "Đang render preview..." if preview else "Đang xuất video final...")

        def work():
            output = render_project(
                snapshot,
                target,
                preview=preview,
                include_audio=include_audio,
            )
            cover = None
            sheet = None
            if preview:
                try:
                    sheet = extract_contact_sheet(
                        output,
                        output.with_name(output.stem + "_contact_sheet.jpg"),
                    )
                except Exception:
                    sheet = None
            else:
                try:
                    cover = extract_cover(output, output.with_suffix(".jpg"), at_seconds=1.5)
                except Exception:
                    cover = None
            return output, cover, sheet

        future = self.executor.submit(work)

        def poll() -> None:
            if not future.done():
                self.root.after(150, poll)
                return
            self._set_busy(False)
            try:
                output, cover, sheet = future.result()
            except Exception as exc:
                self.status_var.set("Render lỗi.")
                messagebox.showerror("Render chưa thành công", str(exc))
                return
            if preview:
                self.last_contact_sheet = sheet
                note = f" • Contact sheet: {sheet.name}" if sheet else ""
                self.status_var.set(f"Hoàn tất preview: {output.name}{note}")
                self._open_path(output)
            else:
                self.status_var.set(f"Hoàn tất: {output}")
                self.project.output_dir = str(output.parent)
                detail = f"Video: {output.name}"
                if not include_audio:
                    detail += "\nÂm thanh: KHÔNG CÓ (visual master)"
                if cover:
                    detail += f"\nCover: {cover.name}"
                detail += f"\nQA: {output.with_suffix('.qa.json').name}"
                messagebox.showinfo("Xuất video thành công", detail)

        self.root.after(150, poll)

    def _open_path(self, path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Không mở được", str(exc))

    def open_output_folder(self) -> None:
        self._open_path(Path(self.project.output_dir or output_dir()))

    def open_contact_sheet(self) -> None:
        if self.last_contact_sheet and self.last_contact_sheet.is_file():
            self._open_path(self.last_contact_sheet)
            return
        preview_dir = Path(self.project.output_dir or output_dir()) / "_preview"
        candidate = preview_dir / "linh_edit_preview_contact_sheet.jpg"
        if candidate.is_file():
            self.last_contact_sheet = candidate
            self._open_path(candidate)
            return
        messagebox.showinfo(
            "Chưa có contact sheet",
            "Hãy tạo XEM THỬ trước. Linh Edit sẽ tự tạo ảnh duyệt các cảnh.",
        )

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = ProjectState(output_dir=str(output_dir()))
        self.project_path = None
        self.profile_var.set(PROFILE_NAMES[self.project.profile])
        self.target_var.set(self.project.target_seconds)
        self.title_var.set("")
        self.voice_var.set("")
        self.music_var.set("")
        self._refresh_all()
        self.status_var.set("Dự án mới.")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        value = filedialog.askopenfilename(
            title="Mở dự án Linh Edit",
            filetypes=[("Linh Edit Project", "*.linhedit.json"), ("JSON", "*.json")],
        )
        if not value:
            return
        try:
            self.project = ProjectState.load(Path(value))
        except Exception as exc:
            messagebox.showerror("Không mở được dự án", str(exc))
            return
        self.project_path = Path(value)
        self.profile_var.set(PROFILE_NAMES.get(self.project.profile, "Travel / Công tác"))
        self.target_var.set(self.project.target_seconds)
        self.title_var.set(self.project.title)
        self.voice_var.set(self.project.voiceover)
        self.music_var.set(self.project.music)
        self._refresh_all()
        self.status_var.set("Đã mở dự án.")

    def import_storyboard_json(self) -> None:
        if self.busy:
            return
        value = filedialog.askopenfilename(
            title="Nhập storyboard JSON",
            filetypes=[("JSON", "*.json"), ("Tất cả tệp", "*.*")],
        )
        if not value:
            return
        try:
            load_storyboard(Path(value), self.project)
        except Exception as exc:
            messagebox.showerror("Không nhập được storyboard", str(exc))
            return
        self.profile_var.set(PROFILE_NAMES.get(self.project.profile, "Tin tức"))
        self.target_var.set(self.project.target_seconds)
        self.title_var.set(self.project.title)
        self.voice_var.set(self.project.voiceover)
        self.music_var.set(self.project.music)
        self._refresh_all()
        self.status_var.set(
            f"Đã nhập storyboard: {len(self.project.timeline)} cảnh, "
            f"{len(self.project.media)} media."
        )

    def import_legacy_project(self) -> None:
        if self.busy:
            return
        value = filedialog.askopenfilename(
            title="Nhập script.json từ app News / Editorial cũ",
            filetypes=[("script.json / JSON", "*.json"), ("Tất cả tệp", "*.*")],
        )
        if not value:
            return
        try:
            import_legacy_script(Path(value), self.project)
        except Exception as exc:
            messagebox.showerror("Không nhập được dự án cũ", str(exc))
            return

        self.profile_var.set(PROFILE_NAMES.get(self.project.profile, "Tin tức"))
        self.target_var.set(self.project.target_seconds)
        self.title_var.set(self.project.title)
        self.voice_var.set(self.project.voiceover)
        self.music_var.set(self.project.music)
        self._refresh_all()
        voice_note = " • đã khớp voice cũ" if self.project.voiceover else ""
        self.status_var.set(
            f"Đã hợp nhất {self.project.source_mode}: "
            f"{len(self.project.timeline)} cảnh{voice_note}."
        )

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self._sync_project()
        try:
            self.project.save(self.project_path)
        except Exception as exc:
            messagebox.showerror("Không lưu được", str(exc))
            return
        self._update_title()
        self.status_var.set(f"Đã lưu: {self.project_path.name}")

    def save_project_as(self) -> None:
        self._sync_project()
        value = filedialog.asksaveasfilename(
            title="Lưu dự án Linh Edit",
            defaultextension=".linhedit.json",
            filetypes=[("Linh Edit Project", "*.linhedit.json")],
        )
        if not value:
            return
        self.project_path = Path(value)
        self.project.name = self.project_path.stem.replace(".linhedit", "")
        self.save_project()

    def _confirm_discard(self) -> bool:
        if not self.project.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Dự án chưa lưu",
            "Lưu thay đổi trước khi tiếp tục?",
        )
        if answer is None:
            return False
        if answer:
            self.save_project()
            return not self.project.dirty
        return True

    def close(self) -> None:
        if self.busy:
            messagebox.showinfo("Đang render", "Hãy chờ render hoàn tất rồi đóng app.")
            return
        if not self._confirm_discard():
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    LinhEditWindow(root)
    root.mainloop()
    return 0
