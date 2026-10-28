"""Chinese desktop interface for the MoonAlign registration engine.

Only the Tk main thread reads or changes widgets. Background work communicates
through a queue, including folder inspection and all engine progress callbacks.
"""
from __future__ import annotations

from datetime import datetime
import ctypes
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__


STAGE_NAMES = {
    "inspect": "检查文件",
    "pilot": "小批验证",
    "all": "全量对齐",
    "audit": "最终检查",
}


def _error_log(details: str) -> Path | None:
    """Keep crash information out of potentially read-only app directories."""
    try:
        folder = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "MoonAlign" / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "error.log"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n{'=' * 68}\n{datetime.now().isoformat(timespec='seconds')}\n")
            stream.write(details.rstrip() + "\n")
        return path
    except OSError:
        return None


def _size_text(value: int | float) -> str:
    return f"{value / 1_000_000_000:.1f} GB" if value >= 1_000_000_000 else f"{value / 1_000_000:.1f} MB"


def _elapsed_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours} 小时 {minutes} 分" if hours else f"{minutes} 分 {seconds} 秒"


class MoonAlignApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MoonAlign {__version__} · 月面旋转对齐")
        width = min(1060, max(780, self.winfo_screenwidth() - 80))
        height = min(760, max(580, self.winfo_screenheight() - 100))
        left = max(0, (self.winfo_screenwidth() - width) // 2)
        top = max(0, (self.winfo_screenheight() - height) // 2 - 15)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(min(880, width), min(620, height))
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.events: queue.Queue = queue.Queue()
        self._files: list[Path] = []
        self._checked: set[int] = set()
        self._invalid: dict[int, str] = {}
        self._visible_indices: list[int] = []
        self._reference_index: int | None = None
        self._reference_user_chosen = False
        self._source: Path | None = None
        self._output_is_auto = True
        self._scan_generation = 0
        self._render_generation = 0
        self._inspection_ready = False
        self._running = False
        self._closed = False
        self._close_requested = False
        self._cancel_event = threading.Event()
        self._file_results: dict[str, str] = {}
        self._search_after: str | None = None
        self._result_frames: Path | None = None
        self._result_reports: Path | None = None

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.reference_var = tk.StringVar(value="参考片：读取文件后自动选择")
        self.selection_var = tk.StringVar(value="尚未选择文件")
        self.inspect_var = tk.StringVar(value="选择 PIPP 输出的 TIFF 文件夹开始。")
        self.stage_var = tk.StringVar(value="就绪")
        self.progress_var = tk.StringVar(value="0 / 0")
        self.counts_var = tk.StringVar(value="成功 0    失败 0")
        self.workers_var = tk.StringVar(value="3")
        self._configure_style()
        self._build()
        self.search_var.trace_add("write", self._search_changed)
        self.after(100, self._drain_events)

    def _configure_style(self):
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Muted.TLabel", foreground="#5b6470")
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10))

    def _build(self):
        main = ttk.Frame(self, padding=12)
        main.grid(sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=5)
        main.grid_rowconfigure(5, weight=2)

        heading = ttk.Frame(main)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        heading.grid_columnconfigure(0, weight=1)
        ttk.Label(heading, text="月面旋转对齐", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(heading, text="使用说明", command=self._show_help).grid(row=0, column=1, sticky="e")
        ttk.Label(heading, text="PIPP → MoonAlign → AutoStakkert!    ·    自动验证后对齐，最后由你在 AS 中叠加",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        paths = ttk.Frame(main)
        paths.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        paths.grid_columnconfigure(1, weight=1)
        ttk.Label(paths, text="输入文件夹").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(paths, textvariable=self.source_var, state="readonly").grid(row=0, column=1, sticky="ew", pady=3)
        self.source_button = ttk.Button(paths, text="选择…", command=self._choose_source)
        self.source_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(paths, text="输出文件夹").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.output_entry = ttk.Entry(paths, textvariable=self.output_var)
        self.output_entry.grid(row=1, column=1, sticky="ew", pady=3)
        self.output_entry.bind("<KeyRelease>", lambda _event: self._custom_output())
        self.output_button = ttk.Button(paths, text="选择…", command=self._choose_output)
        self.output_button.grid(row=1, column=2, padx=(8, 0))
        ttk.Label(paths, text="输入照片保持不变；新目录保存 16 位彩色 TIFF，保留原文件名。也可选择本程序原输出目录续跑。",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        listing = ttk.LabelFrame(main, text="选择照片", padding=(8, 5))
        listing.grid(row=2, column=0, sticky="nsew")
        listing.grid_columnconfigure(0, weight=1)
        listing.grid_rowconfigure(1, weight=1)
        toolbar = ttk.Frame(listing)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.all_button = ttk.Button(toolbar, text="全选", width=7, command=self._select_all)
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(toolbar, text="取消全选", width=9, command=self._select_none)
        self.none_button.pack(side="left", padx=(5, 10))
        ttk.Label(toolbar, textvariable=self.selection_var).pack(side="left")
        ttk.Label(toolbar, text="搜索文件名").pack(side="left", padx=(18, 6))
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=22)
        self.search_entry.pack(side="left", fill="x", expand=True)

        self.tree = ttk.Treeview(listing, columns=("check", "name", "state"), show="headings", selectmode="extended", height=8)
        self.tree.heading("check", text="勾选")
        self.tree.heading("name", text="文件名")
        self.tree.heading("state", text="状态")
        self.tree.column("check", width=48, minwidth=48, stretch=False, anchor="center")
        self.tree.column("name", width=530, minwidth=180, stretch=True)
        self.tree.column("state", width=185, minwidth=125, stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("invalid", foreground="#a23b36")
        self.tree.tag_configure("reference", foreground="#175c9b")
        self.tree.bind("<Button-1>", self._click_check)
        self.tree.bind("<space>", self._space_check)
        self.tree.bind("<Button-3>", self._context_menu)

        reference_row = ttk.Frame(listing)
        reference_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        reference_row.grid_columnconfigure(0, weight=1)
        ttk.Label(reference_row, textvariable=self.reference_var).grid(row=0, column=0, sticky="w")
        self.reference_button = ttk.Button(reference_row, text="将选中行设为参考片", command=self._set_reference_from_selection)
        self.reference_button.grid(row=0, column=1, sticky="e")

        options = ttk.Frame(main)
        options.grid(row=3, column=0, sticky="ew", pady=6)
        options.grid_columnconfigure(0, weight=1)
        ttk.Label(options, textvariable=self.inspect_var, style="Muted.TLabel", wraplength=650).grid(row=0, column=0, sticky="w")
        ttk.Label(options, text="同时处理").grid(row=0, column=1, padx=(8, 4))
        self.workers_spin = ttk.Spinbox(options, from_=1, to=6, width=3, textvariable=self.workers_var, state="readonly")
        self.workers_spin.grid(row=0, column=2)
        ttk.Label(options, text="张").grid(row=0, column=3, padx=(3, 10))
        self.start_button = ttk.Button(options, text="开始对齐", command=self._start, state="disabled")
        self.start_button.grid(row=0, column=4, padx=(0, 6))
        self.cancel_button = ttk.Button(options, text="取消", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=5)

        progress = ttk.Frame(main)
        progress.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        progress.grid_columnconfigure(0, weight=1)
        ttk.Label(progress, textvariable=self.stage_var).grid(row=0, column=0, sticky="w")
        ttk.Label(progress, textvariable=self.counts_var).grid(row=0, column=1, sticky="e")
        self.progress = ttk.Progressbar(progress, mode="determinate", maximum=1)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Label(progress, textvariable=self.progress_var, width=15, anchor="e").grid(row=1, column=1, padx=(8, 0), sticky="e")

        log_frame = ttk.LabelFrame(main, text="处理日志", padding=5)
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self.log = ScrolledText(log_frame, height=5, wrap="word", state="disabled", font=("Microsoft YaHei UI", 9))
        self.log.grid(sticky="nsew")
        self.log.tag_configure("error", foreground="#a23b36")
        self.log.tag_configure("success", foreground="#216b36")
        footer = ttk.Frame(main)
        footer.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        footer.grid_columnconfigure(0, weight=1)
        ttk.Label(footer, text="适用：同一批完整月盘。校正旋转和平移；模糊、缺失的月面细节仍需在 AS 中筛选。",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.frames_button = ttk.Button(footer, text="打开对齐照片", command=lambda: self._open_result("frames"), state="disabled")
        self.frames_button.grid(row=0, column=1, padx=(8, 5))
        self.reports_button = ttk.Button(footer, text="打开报告", command=lambda: self._open_result("reports"), state="disabled")
        self.reports_button.grid(row=0, column=2)

    def _custom_output(self):
        self._output_is_auto = False

    def _choose_source(self):
        if self._running:
            return
        initial = str(self._source or Path.home())
        selected = filedialog.askdirectory(parent=self, title="选择 PIPP 输出的 TIFF 文件夹", initialdir=initial)
        if not selected:
            return
        self._source = Path(selected).resolve()
        self.source_var.set(str(self._source))
        if self._output_is_auto or not self.output_var.get().strip():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_var.set(str(self._source.parent / f"MoonAlign_{stamp}"))
            self._output_is_auto = True
        self._scan_generation += 1
        generation = self._scan_generation
        self._files = []
        self._checked.clear()
        self._invalid.clear()
        self._reference_index = None
        self._reference_user_chosen = False
        self._inspection_ready = False
        self.search_var.set("")
        self.reference_var.set("参考片：正在读取文件…")
        self.inspect_var.set("正在检查 TIFF 文件，请稍候…")
        self.stage_var.set("读取文件夹")
        self.start_button.configure(state="disabled")
        self._render_files()
        self._append_log(f"读取文件夹：{self._source}")
        threading.Thread(target=self._scan_worker, args=(self._source, generation), daemon=True).start()

    def _scan_worker(self, source: Path, generation: int):
        try:
            with os.scandir(source) as entries:
                files = sorted((Path(entry.path) for entry in entries
                                if entry.is_file() and Path(entry.name).suffix.lower() in {".tif", ".tiff"}),
                               key=lambda path: path.name.casefold())
            self.events.put(("files_loaded", generation, files))
            if not files:
                self.events.put(("inspection", generation, {"count": 0, "valid_count": 0,
                    "invalid_files": [], "message": "文件夹中没有 .tif 或 .tiff 照片。"}))
                return
            from .engine import inspect_files
            inspection = inspect_files(files)
            self.events.put(("inspection", generation, inspection))
        except Exception as error:
            details = traceback.format_exc()
            log_path = _error_log(details)
            self.events.put(("scan_error", generation, str(error), str(log_path) if log_path else ""))

    def _choose_output(self):
        if self._running:
            return
        initial = self._source.parent if self._source else Path.home()
        current = self.output_var.get().strip()
        if current:
            proposed = Path(current)
            if proposed.is_dir():
                initial = proposed
            elif proposed.parent.is_dir():
                initial = proposed.parent
        selected = filedialog.askdirectory(parent=self,
            title="选择空输出目录，或本程序原输出目录以续跑（也可直接在框内填写新目录）", initialdir=str(initial))
        if selected:
            self.output_var.set(str(Path(selected).resolve()))
            self._output_is_auto = False

    def _search_changed(self, *_args):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(160, self._render_files)

    def _render_files(self):
        self._search_after = None
        self._render_generation += 1
        generation = self._render_generation
        text = self.search_var.get().strip().casefold()
        self._visible_indices = [index for index, path in enumerate(self._files) if text in path.name.casefold()]
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        visible = list(self._visible_indices)
        self._update_selection_label()

        def insert_batch(start: int):
            if self._closed or generation != self._render_generation:
                return
            for index in visible[start:start + 250]:
                tags = ("invalid",) if index in self._invalid else (("reference",) if index == self._reference_index else ())
                self.tree.insert("", "end", iid=str(index), values=self._row_values(index), tags=tags)
            if start + 250 < len(visible):
                self.after(1, insert_batch, start + 250)

        insert_batch(0)

    def _row_values(self, index: int):
        if index in self._invalid:
            status = "不支持：" + self._invalid[index]
        elif index == self._reference_index:
            status = "参考片"
        else:
            status = "可处理" if self._inspection_ready else "待检查"
        return ("☑" if index in self._checked else "☐", self._files[index].name, status)

    def _refresh_rows(self, indices):
        for index in indices:
            iid = str(index)
            if self.tree.exists(iid):
                tags = ("invalid",) if index in self._invalid else (("reference",) if index == self._reference_index else ())
                self.tree.item(iid, values=self._row_values(index), tags=tags)

    def _update_selection_label(self):
        self.selection_var.set(f"已勾选 {len(self._checked)} / {len(self._files)} 张 · 显示 {len(self._visible_indices)} 张")
        enabled = bool(self._checked) and self._inspection_ready and not self._running
        self.start_button.configure(state="normal" if enabled else "disabled")

    def _ensure_reference(self):
        old = self._reference_index
        if old not in self._checked:
            selected = sorted(self._checked)
            self._reference_index = selected[len(selected) // 2] if selected else None
            self._reference_user_chosen = False
        if self._reference_index is None:
            self.reference_var.set("参考片：请先勾选照片")
        else:
            self.reference_var.set(f"参考片：{self._files[self._reference_index].name}")
        self._refresh_rows(index for index in [old, self._reference_index] if index is not None)

    def _change_checks(self, indices, checked: bool | None = None):
        if self._running:
            return
        changed = []
        for index in indices:
            if index in self._invalid:
                continue
            value = index not in self._checked if checked is None else checked
            if value:
                self._checked.add(index)
            else:
                self._checked.discard(index)
            changed.append(index)
        self._ensure_reference()
        self._refresh_rows(changed)
        self._update_selection_label()

    def _select_all(self):
        self._change_checks(range(len(self._files)), True)

    def _select_none(self):
        self._change_checks(range(len(self._files)), False)

    def _click_check(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                self._change_checks([int(iid)])
                return "break"
        return None

    def _space_check(self, _event):
        indices = [int(iid) for iid in self.tree.selection()]
        if indices:
            self._change_checks(indices, not all(index in self._checked for index in indices))
        return "break"

    def _context_menu(self, event):
        if self._running:
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=False)
        indices = [int(value) for value in self.tree.selection()]
        menu.add_command(label="勾选选中行", command=lambda: self._change_checks(indices, True))
        menu.add_command(label="取消勾选选中行", command=lambda: self._change_checks(indices, False))
        menu.add_separator()
        menu.add_command(label="设为参考片", command=self._set_reference_from_selection,
                         state="normal" if len(indices) == 1 else "disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _set_reference_from_selection(self):
        if self._running:
            return
        selection = self.tree.selection()
        if len(selection) != 1:
            messagebox.showinfo("选择参考片", "先在列表中单击一张清晰、完整的月亮照片，再设为参考片。", parent=self)
            return
        index = int(selection[0])
        if index in self._invalid:
            messagebox.showerror("无法选择", "这张照片未通过文件检查，请选择另一张。", parent=self)
            return
        old = self._reference_index
        self._checked.add(index)
        self._reference_index = index
        self._reference_user_chosen = True
        self.reference_var.set(f"参考片：{self._files[index].name}")
        self._refresh_rows(value for value in [old, index] if value is not None)
        self._update_selection_label()

    def _apply_inspection(self, result: dict):
        errors = {}
        for item in result.get("invalid_files", []):
            file = str(item.get("file", ""))
            errors[file.casefold()] = str(item.get("error", "文件不支持"))
            errors[Path(file).name.casefold()] = str(item.get("error", "文件不支持"))
        self._invalid = {index: errors[path.name.casefold()] for index, path in enumerate(self._files)
                         if path.name.casefold() in errors}
        self._checked.difference_update(self._invalid)
        self._inspection_ready = True
        recommended = result.get("recommended_reference")
        if recommended and not self._reference_user_chosen:
            name = Path(str(recommended)).name.casefold()
            self._reference_index = next((index for index in sorted(self._checked)
                                          if self._files[index].name.casefold() == name), None)
        self._ensure_reference()
        message = str(result.get("message") or "文件检查完成。")
        count = int(result.get("valid_count", len(self._files) - len(self._invalid)))
        dimensions = result.get("dimensions")
        details = f"可用 {count} 张"
        if dimensions:
            details += f" · {dimensions[0]} × {dimensions[1]}"
        if result.get("total_bytes"):
            details += f" · {_size_text(result['total_bytes'])}"
        self.inspect_var.set(details + (f"；不支持 {len(self._invalid)} 张" if self._invalid else ""))
        self.stage_var.set("就绪" if self._checked else "请选择可处理的照片")
        self._append_log(message)
        for index in list(self._invalid)[:5]:
            self._append_log(f"未勾选 {self._files[index].name}：{self._invalid[index]}", "error")
        self._render_files()

    def _set_busy(self, busy: bool):
        self._running = busy
        state = "disabled" if busy else "normal"
        for widget in [self.source_button, self.output_entry, self.output_button, self.all_button,
                       self.none_button, self.reference_button, self.search_entry]:
            widget.configure(state=state)
        self.workers_spin.configure(state="disabled" if busy else "readonly")
        self.cancel_button.configure(state="normal" if busy else "disabled", text="取消")
        self._update_selection_label()

    def _start(self):
        if self._running or not self._inspection_ready:
            return
        self._ensure_reference()
        if self._source is None or not self._checked or self._reference_index is None:
            messagebox.showerror("尚未选择照片", "请选择输入文件夹并勾选照片。", parent=self)
            return
        try:
            text = self.output_var.get().strip().strip('"')
            if not text:
                raise ValueError("请填写一个新的输出文件夹。")
            output = Path(os.path.expandvars(os.path.expanduser(text))).resolve()
            if output == self._source or output.is_relative_to(self._source) or self._source.is_relative_to(output):
                raise ValueError("输出目录必须与输入目录分开，不能是输入目录本身、其内部目录或上级目录。")
            if not output.parent.is_dir():
                raise ValueError("输出目录的上级文件夹不存在，请先选择已有的位置。")
            workers = int(self.workers_var.get())
            if workers < 1 or workers > 6:
                raise ValueError("同时处理的数量应为 1～6。")
        except (OSError, ValueError) as error:
            messagebox.showerror("请检查输出位置", str(error), parent=self)
            return
        files = [self._files[index] for index in sorted(self._checked)]
        reference = self._files[self._reference_index]
        self.output_var.set(str(output))
        self._cancel_event = threading.Event()
        self._file_results.clear()
        self._result_frames = None
        self._result_reports = None
        self.frames_button.configure(state="disabled")
        self.reports_button.configure(state="disabled")
        self.progress.configure(maximum=max(1, len(files)), value=0)
        self.progress_var.set(f"0 / {len(files)}")
        self.counts_var.set("成功 0    失败 0")
        self.stage_var.set("准备小批验证")
        self._append_log(f"开始：{len(files)} 张；参考片 {reference.name}；输出 {output}")
        self._set_busy(True)
        threading.Thread(target=self._run_worker,
            args=(files, reference, output, workers, self._cancel_event), daemon=True).start()

    def _run_worker(self, files, reference, output, workers, cancel_event):
        try:
            from .engine import run_alignment
            summary = run_alignment(files=files, reference=reference, output=output, workers=workers,
                progress=lambda event: self.events.put(("engine", event)), cancel_event=cancel_event)
            self.events.put(("worker_finished", summary))
        except Exception as error:
            log_path = _error_log(traceback.format_exc())
            self.events.put(("worker_error", str(error), str(log_path) if log_path else ""))

    def _engine_event(self, event: dict):
        kind = event.get("event")
        stage = STAGE_NAMES.get(str(event.get("stage", "")), "正在处理")
        total = int(event.get("total") or self.progress["maximum"] or 1)
        done = int(event.get("done") or 0)
        if kind in {"start", "frame"}:
            self.progress.configure(maximum=max(1, total), value=min(done, total))
            self.progress_var.set(f"{done} / {total}")
        if not self._cancel_event.is_set():
            self.stage_var.set(stage)
        if kind == "frame":
            name = str(event.get("filename", ""))
            status = str(event.get("status", ""))
            self._file_results[name] = status
            success = sum(value == "success" for value in self._file_results.values())
            failed = sum(value == "failed" for value in self._file_results.values())
            self.counts_var.set(f"成功 {success}    失败 {failed}")
            if status == "failed":
                self._append_log(f"未输出 {name}：{event.get('message') or '未通过对齐检查'}", "error")
            elif done == 1 or done % 25 == 0 or done == total:
                self._append_log(f"{stage} {done}/{total} · {name}")
        elif kind == "message" and event.get("message"):
            self._append_log(str(event["message"]))

    def _cancel(self):
        if not self._running or self._cancel_event.is_set():
            return
        self._cancel_event.set()
        self.cancel_button.configure(state="disabled", text="正在停止…")
        self.stage_var.set("正在安全停止，等待当前照片写入完成…")
        self._append_log("已请求停止；正在处理的照片会安全完成，已完成结果可继续使用或续跑。")

    def _finish(self, summary: dict):
        success, failed = int(summary.get("success", 0)), int(summary.get("failed", 0))
        total = int(summary.get("total", success + failed))
        self.progress.configure(maximum=max(total, 1), value=min(success + failed, total))
        self.progress_var.set(f"{success + failed} / {total}")
        self.counts_var.set(f"成功 {success}    失败 {failed}")
        self._result_frames = Path(summary["output_directory"]) if summary.get("output_directory") else None
        self._result_reports = Path(summary["report_directory"]) if summary.get("report_directory") else None
        self._set_busy(False)
        self.frames_button.configure(state="normal" if self._result_frames and self._result_frames.is_dir() else "disabled")
        self.reports_button.configure(state="normal" if self._result_reports and self._result_reports.is_dir() else "disabled")
        cancelled = bool(summary.get("cancelled")) or summary.get("status") == "cancelled"
        pilot_failed = summary.get("status") == "pilot_failed"
        audit_evidence = any(summary.get(key) for key in (
            "audit_problem_files", "source_files_changed_by_size_or_mtime", "source_files_changed"))
        audit_failed = (not cancelled and not pilot_failed and
                        (summary.get("passed") is not True or summary.get("audit_passed") is False or audit_evidence))
        if cancelled:
            label = "已停止，可选择同一输出目录续跑"
        elif pilot_failed:
            label = "小批验证未通过，尚未开始全量"
        elif audit_failed:
            label = "最终检查未通过，请查看报告，暂勿导入 AS"
        elif failed:
            label = "处理完成，请查看失败清单"
        else:
            label = "对齐完成，可将 frames 中的 TIFF 导入 AutoStakkert!"
        self.stage_var.set(label)
        elapsed = _elapsed_text(float(summary.get("elapsed_seconds") or 0))
        self._append_log(f"{label}。成功 {success} 张，失败 {failed} 张，用时 {elapsed}。",
                         "error" if failed or pilot_failed or audit_failed else "" if cancelled else "success")
        if summary.get("message"):
            self._append_log(str(summary["message"]))
        for key, description in [
            ("audit_problem_files", "输出检查未通过"),
            ("source_files_changed_by_size_or_mtime", "输入文件发生变化"),
            ("source_files_changed", "输入文件发生变化"),
        ]:
            problems = summary.get(key)
            if problems:
                if not isinstance(problems, (list, tuple)):
                    problems = [problems]
                names = []
                for item in problems[:8]:
                    if isinstance(item, dict):
                        name = str(item.get("file") or item.get("name") or item)
                        if item.get("error"):
                            name += ": " + str(item["error"])
                    else:
                        name = str(item)
                    names.append(name)
                tail = f"；另有 {len(problems) - 8} 项，详见报告" if len(problems) > 8 else ""
                self._append_log(f"{description}：" + "；".join(names) + tail, "error")
        if self._close_requested:
            self._destroy()

    def _append_log(self, message: str, tag: str = ""):
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now().strftime('%H:%M:%S')}  {message}\n", tag)
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 800:
            self.log.delete("1.0", f"{lines - 650}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_events(self):
        if self._closed:
            return
        try:
            for _ in range(150):
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                kind = event[0]
                if kind == "files_loaded" and event[1] == self._scan_generation:
                    self._files = event[2]
                    self._checked = set(range(len(self._files)))
                    self._ensure_reference()
                    self._render_files()
                elif kind == "inspection" and event[1] == self._scan_generation:
                    self._apply_inspection(event[2])
                elif kind == "scan_error" and event[1] == self._scan_generation:
                    self._inspection_ready = False
                    self.inspect_var.set("文件检查失败，请查看日志或重新选择文件夹。")
                    self.stage_var.set("检查失败")
                    self._append_log(event[2], "error")
                    suffix = f"\n\n错误详情：{event[3]}" if event[3] else ""
                    messagebox.showerror("无法读取文件夹", event[2] + suffix, parent=self)
                elif kind == "engine":
                    self._engine_event(event[1])
                elif kind == "worker_finished":
                    self._finish(event[1])
                elif kind == "worker_error":
                    self._set_busy(False)
                    self.stage_var.set("处理未完成，请检查错误信息")
                    self._append_log(event[1], "error")
                    suffix = f"\n\n错误详情：{event[2]}" if event[2] else ""
                    if self._close_requested:
                        self._destroy()
                    else:
                        messagebox.showerror("处理未完成", event[1] + suffix, parent=self)
        finally:
            if not self._closed:
                self.after(100, self._drain_events)

    def _open_result(self, kind: str):
        path = self._result_frames if kind == "frames" else self._result_reports
        if not path or not path.is_dir():
            messagebox.showinfo("尚无结果", "结果文件夹尚未生成。", parent=self)
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                import subprocess
                subprocess.Popen(["open" if os.sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as error:
            messagebox.showerror("无法打开文件夹", f"{path}\n\n{error}", parent=self)

    def _show_help(self):
        if os.name == "nt":
            root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
            candidates = [root / "快速入门.txt"]
            if getattr(sys, "_MEIPASS", None):
                candidates.append(Path(sys._MEIPASS) / "快速入门.txt")
            guide = next((path for path in candidates if path.is_file()), None)
            if guide:
                try:
                    os.startfile(str(guide))
                    return
                except OSError as error:
                    self._append_log(f"无法打开说明文件：{error}", "error")
        messagebox.showinfo("MoonAlign 使用说明",
            "1. 在 PIPP 中保留彩色和原始像素，输出 16 位 RGB TIFF。\n"
            "2. 选择文件夹，勾选全部或部分照片。可在列表多选后按空格切换勾选，或使用右键菜单。\n"
            "3. 选择清晰、完整的参考片；默认从照片列表中选择。\n"
            "4. 填写新的输出目录，点击开始。程序先小批验证，通过后自动处理全部勾选照片。\n"
            "5. 完成后将 frames 内的 TIFF 导入 AutoStakkert! 筛片和叠加；它们已经是彩色照片，无需 Debayer。\n\n"
            "适用于同一批、相同尺寸的近满月完整月盘。画面每边 800～6000 像素，月盘等效直径至少 800 像素，建议 1000 像素以上。\n"
            "同一批的焦距、增距镜和导出缩放比例应一致；更换焦距或缩放比例的照片应分开处理。\n"
            "校正旋转和平移，不会补回失焦、运动模糊或被切掉的月面。\n"
            "输入文件保持不变。取消会等待在途照片完成；选择同一批文件、参考片和原输出目录可续跑。",
            parent=self)

    def _close(self):
        if self._running:
            if self._close_requested:
                return
            stop = messagebox.askyesno("任务仍在运行",
                "是否停止处理并退出？\n\n程序会等待当前照片安全写入后关闭，已完成结果可以续跑。", parent=self)
            if stop:
                self._close_requested = True
                self._cancel()
            return
        self._destroy()

    def _destroy(self):
        self._closed = True
        self.destroy()

    def report_callback_exception(self, exc_type, value, tb):
        details = "".join(traceback.format_exception(exc_type, value, tb))
        path = _error_log(details)
        if not self._closed:
            suffix = f"\n\n错误详情：{path}" if path else ""
            messagebox.showerror("界面发生错误", str(value) + suffix, parent=self)


def main():
    try:
        if os.name == "nt":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        app = MoonAlignApp()
        app.mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        path = _error_log(details)
        message = "MoonAlign 无法启动。"
        if path:
            message += f"\n\n错误详情已保存到：\n{path}"
        try:
            if os.name == "nt":
                ctypes.windll.user32.MessageBoxW(None, message, "MoonAlign", 0x10)
            else:
                messagebox.showerror("MoonAlign", message)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
