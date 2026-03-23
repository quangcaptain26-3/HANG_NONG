"""
AGV Log & Image Dashboard
A lightweight desktop tool for inspecting AGV logs and image inspection results.
Dependencies: tkinter (stdlib), os (stdlib), Pillow, matplotlib
"""

import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.font import Font
import threading

# ── Third-party ──────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    messagebox.showerror("Missing library", "Install Pillow:  pip install Pillow")
    raise

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    messagebox.showerror("Missing library", "Install matplotlib:  pip install matplotlib")
    raise


# ── Constants ─────────────────────────────────────────────────────────────────
THUMB_SIZE     = (110, 110)
BORDER_PX      = 4
GRID_COLS      = 5
AUTO_REFRESH_S = 10          # seconds between auto-refreshes (0 = disabled)

# Keyword groups for log highlighting
DISCONNECT_KW = ("disconnect", "disconnected", "lost", "error", "fail", "timeout", "offline")
CONNECT_KW    = ("connect", "connected", "online", "success", "ok", "established")
LOG_CATEGORIES = ("DISCONNECT", "CONNECT", "REPORT", "TASK", "RESOURCE", "OTHER")

# Colour palette (dark-industrial theme)
C = {
    "bg":       "#1a1c20",
    "panel":    "#22252b",
    "border":   "#2e3138",
    "accent":   "#4f8ef7",
    "text":     "#d4d8e0",
    "muted":    "#6b7280",
    "pass":     "#22c55e",
    "fail":     "#ef4444",
    "warn":     "#f59e0b",
    "header":   "#0f1117",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def classify_image(filename: str) -> str:
    """Return 'FAIL' or 'PASS' based on filename."""
    name = filename.lower()
    if "fail" in name:
        return "FAIL"
    if "all_pass" in name or "all pass" in name or "pass" in name:
        return "PASS"
    return "PASS"          # default — uncategorised treated as PASS


def make_thumb(path: str, label: str) -> ImageTk.PhotoImage:
    """Open image, add coloured border, return PhotoImage thumbnail."""
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        img = Image.new("RGB", THUMB_SIZE, "#333")

    img.thumbnail(THUMB_SIZE, Image.LANCZOS)

    border_color = C["fail"] if label == "FAIL" else C["pass"]
    total = (img.width + BORDER_PX * 2, img.height + BORDER_PX * 2)
    bordered = Image.new("RGB", total, border_color)
    bordered.paste(img, (BORDER_PX, BORDER_PX))

    return ImageTk.PhotoImage(bordered)


def scan_images(folder: str):
    """Return list of (filepath, label) tuples for image files in folder."""
    results = []
    if not folder or not os.path.isdir(folder):
        return results
    for root, _dirs, files in os.walk(folder):
        for fname in sorted(files):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
                continue
            full = os.path.join(root, fname)
            parent_name = os.path.basename(root).lower()
            if parent_name == "fail":
                label = "FAIL"
            elif parent_name in ("all_pass", "all pass"):
                label = "PASS"
            else:
                label = classify_image(fname)
            results.append((full, label))
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────────────────────────────────────

class AGVDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AGV Dashboard")
        self.geometry("1280x820")
        self.minsize(900, 600)
        self.configure(bg=C["bg"])

        # State
        self.log_path    = tk.StringVar()
        self.img_folder  = tk.StringVar()
        self.log_filter_query = tk.StringVar()
        self._log_lines = []
        self._log_rows = []
        self._category_vars = {}
        self._category_checks = {}
        self._img_folders = []
        self._image_rows = []
        self._thumb_refs = []          # keep PhotoImage alive
        self._preview_win = None

        self._build_ui()
        self._sync_img_folder_label()
        self._update_source_label()
        self._schedule_refresh()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._style()
        self._header()
        self._global_toolbar()

        # ── Main pane: horizontal dashboard
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                               bg=C["border"], sashwidth=4, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 10))

        left = self._log_panel(paned)
        right = self._right_panel(paned)

        paned.add(left,  minsize=520, width=790)
        paned.add(right, minsize=360, width=470)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",       background=C["panel"])
        s.configure("TLabel",       background=C["panel"],  foreground=C["text"], font=("Courier New", 10))
        s.configure("Header.TLabel",background=C["panel"],  foreground=C["accent"], font=("Courier New", 11, "bold"))
        s.configure("Muted.TLabel", background=C["panel"],  foreground=C["muted"], font=("Courier New", 9))
        s.configure("TButton",      background=C["accent"],  foreground="#fff",
                    font=("Courier New", 9, "bold"), borderwidth=0, relief=tk.FLAT, padding=(8, 4))
        s.map("TButton", background=[("active", "#3a7bd5"), ("pressed", "#2563eb")])
        s.configure("TScrollbar",   background=C["border"],  troughcolor=C["bg"], borderwidth=0)
        s.configure(
            "Treeview",
            background=C["bg"],
            fieldbackground=C["bg"],
            foreground=C["text"],
            bordercolor=C["border"],
            rowheight=22,
            font=("Courier New", 9),
        )
        s.configure(
            "Treeview.Heading",
            background=C["panel"],
            foreground=C["accent"],
            font=("Courier New", 9, "bold"),
            relief=tk.FLAT,
        )
        s.map("Treeview", background=[("selected", C["accent"])], foreground=[("selected", "#ffffff")])

    def _header(self):
        hdr = tk.Frame(self, bg=C["header"], height=48)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="◈  AGV DASHBOARD", bg=C["header"],
                 fg=C["accent"], font=("Courier New", 14, "bold")).pack(side=tk.LEFT, padx=16)

        tk.Label(hdr, text="log + image inspection tool", bg=C["header"],
                 fg=C["muted"], font=("Courier New", 9)).pack(side=tk.LEFT)

        # Auto-refresh indicator
        self._refresh_lbl = tk.Label(hdr, text="", bg=C["header"],
                                     fg=C["muted"], font=("Courier New", 9))
        self._refresh_lbl.pack(side=tk.RIGHT, padx=14)

    def _global_toolbar(self):
        bar = tk.Frame(self, bg=C["panel"], height=42, highlightthickness=1, highlightbackground=C["border"])
        bar.pack(fill=tk.X, padx=10, pady=(8, 0))
        bar.pack_propagate(False)

        tk.Label(
            bar,
            text="Quick Actions",
            bg=C["panel"],
            fg=C["accent"],
            font=("Courier New", 10, "bold"),
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(bar, text="Open log…", command=self._pick_log).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Button(bar, text="Add folder…", command=self._pick_folder).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Clear folders", command=self._clear_image_folders).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Refresh", command=self._refresh).pack(side=tk.LEFT)

        self.source_lbl = tk.Label(
            bar,
            text="Sources: log=none | images=0 folders",
            bg=C["panel"],
            fg=C["muted"],
            font=("Courier New", 8),
        )
        self.source_lbl.pack(side=tk.RIGHT, padx=10)

    # ── Left panel: log viewer ────────────────────────────────────────────────

    def _log_panel(self, parent):
        frame = tk.Frame(parent, bg=C["panel"], highlightthickness=1, highlightbackground=C["border"])

        # Toolbar
        bar = tk.Frame(frame, bg=C["panel"], pady=6)
        bar.pack(fill=tk.X, padx=8)
        tk.Label(bar, text="AGV LOG", bg=C["panel"], fg=C["accent"],
                 font=("Courier New", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(bar, text="Realtime parsed log table", bg=C["panel"], fg=C["muted"],
                 font=("Courier New", 8)).pack(side=tk.RIGHT)

        # Path display
        tk.Label(frame, textvariable=self.log_path, bg=C["panel"], fg=C["muted"],
                 font=("Courier New", 8), wraplength=380, anchor="w").pack(fill=tk.X, padx=8)

        # Filter controls
        filter_bar = tk.Frame(frame, bg=C["panel"], pady=4)
        filter_bar.pack(fill=tk.X, padx=8)

        tk.Label(filter_bar, text="Search:", bg=C["panel"], fg=C["text"],
                 font=("Courier New", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        query_entry = tk.Entry(
            filter_bar,
            textvariable=self.log_filter_query,
            bg=C["bg"], fg=C["text"], insertbackground=C["text"],
            relief=tk.FLAT, font=("Courier New", 9), width=26
        )
        query_entry.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        query_entry.bind("<KeyRelease>", lambda _e: self._apply_log_filter())

        ttk.Button(filter_bar, text="Clear", command=self._clear_log_filter).pack(side=tk.RIGHT)

        # Category toggles (always visible)
        cate_bar = tk.Frame(frame, bg=C["panel"], pady=4)
        cate_bar.pack(fill=tk.X, padx=8)
        for name in LOG_CATEGORIES:
            var = tk.BooleanVar(value=True)
            self._category_vars[name] = var
            chk = tk.Checkbutton(
                cate_bar,
                text=f"{name} (0)",
                variable=var,
                command=self._apply_log_filter,
                bg=C["panel"],
                fg=C["text"],
                activebackground=C["panel"],
                activeforeground=C["text"],
                selectcolor=C["bg"],
                font=("Courier New", 8, "bold"),
                bd=0,
                highlightthickness=0,
                padx=4,
            )
            chk.pack(side=tk.LEFT, padx=(0, 4))
            self._category_checks[name] = chk

        self.log_count_lbl = tk.Label(
            frame, text="showing: 0 / 0", bg=C["panel"], fg=C["muted"], font=("Courier New", 8)
        )
        self.log_count_lbl.pack(fill=tk.X, padx=8)

        # Table + scrollbar
        table_frame = tk.Frame(frame, bg=C["bg"])
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        vbar = tk.Scrollbar(table_frame, bg=C["border"])
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar = tk.Scrollbar(table_frame, orient=tk.HORIZONTAL, bg=C["border"])
        hbar.pack(side=tk.BOTTOM, fill=tk.X)

        cols = ("time", "category", "agv", "task", "message")
        self.log_table = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            yscrollcommand=vbar.set,
            xscrollcommand=hbar.set,
        )
        self.log_table.heading("time", text="Time")
        self.log_table.heading("category", text="Category")
        self.log_table.heading("agv", text="AGV/IP")
        self.log_table.heading("task", text="Task ID")
        self.log_table.heading("message", text="Message")
        self.log_table.column("time", width=178, anchor=tk.W, stretch=False)
        self.log_table.column("category", width=92, anchor=tk.W, stretch=False)
        self.log_table.column("agv", width=90, anchor=tk.W, stretch=False)
        self.log_table.column("task", width=230, anchor=tk.W, stretch=False)
        self.log_table.column("message", width=700, anchor=tk.W, stretch=True)
        self.log_table.pack(fill=tk.BOTH, expand=True)

        vbar.config(command=self.log_table.yview)
        hbar.config(command=self.log_table.xview)
        self.log_table.tag_configure("DISCONNECT", foreground=C["fail"])
        self.log_table.tag_configure("CONNECT", foreground=C["pass"])
        self.log_table.tag_configure("REPORT", foreground=C["warn"])
        self.log_table.tag_configure("TASK", foreground=C["accent"])
        self.log_table.tag_configure("RESOURCE", foreground=C["text"])
        self.log_table.tag_configure("OTHER", foreground=C["muted"])

        # Legend
        leg = tk.Frame(frame, bg=C["panel"], pady=4)
        leg.pack(fill=tk.X, padx=8)
        tk.Label(leg, text="● DISCONNECT", bg=C["panel"], fg=C["fail"],
                 font=("Courier New", 8)).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(leg, text="● CONNECT", bg=C["panel"], fg=C["pass"],
                 font=("Courier New", 8)).pack(side=tk.LEFT)

        return frame

    # ── Right panel: images + chart ───────────────────────────────────────────

    def _right_panel(self, parent):
        frame = tk.Frame(parent, bg=C["panel"], highlightthickness=1, highlightbackground=C["border"])

        # ── Header row
        bar = tk.Frame(frame, bg=C["panel"], pady=6)
        bar.pack(fill=tk.X, padx=8)
        tk.Label(bar, text="IMAGE STATISTICS", bg=C["panel"], fg=C["accent"],
                 font=("Courier New", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(bar, text="Daily PASS/FAIL trend", bg=C["panel"], fg=C["muted"],
                 font=("Courier New", 8)).pack(side=tk.RIGHT)

        tk.Label(frame, textvariable=self.img_folder, bg=C["panel"], fg=C["muted"],
                 font=("Courier New", 8), wraplength=460, anchor="w", justify=tk.LEFT).pack(fill=tk.X, padx=8)

        # ── Summary bar
        summary = tk.Frame(frame, bg=C["panel"], pady=4)
        summary.pack(fill=tk.X, padx=8)

        self.lbl_pass = tk.Label(summary, text="PASS: 0", bg=C["panel"],
                                  fg=C["pass"], font=("Courier New", 10, "bold"))
        self.lbl_pass.pack(side=tk.LEFT, padx=(0, 16))

        self.lbl_fail = tk.Label(summary, text="FAIL: 0", bg=C["panel"],
                                  fg=C["fail"], font=("Courier New", 10, "bold"))
        self.lbl_fail.pack(side=tk.LEFT)

        self.lbl_total = tk.Label(summary, text="", bg=C["panel"],
                                   fg=C["muted"], font=("Courier New", 9))
        self.lbl_total.pack(side=tk.LEFT, padx=12)

        chart_note = tk.Label(
            frame,
            text="Chart mode: thống kê PASS/FAIL theo ngày từ nhiều folder ảnh",
            bg=C["panel"],
            fg=C["muted"],
            font=("Courier New", 8),
        )
        chart_note.pack(fill=tk.X, padx=8, pady=(0, 4))

        # Chart area only
        chart_frame = tk.Frame(frame, bg=C["panel"])
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self._build_chart(chart_frame)

        return frame

    def _build_chart(self, parent):
        self.fig = Figure(figsize=(6, 3.2), dpi=90, facecolor=C["panel"])
        self.ax  = self.fig.add_subplot(111)
        self._style_chart({})
        self.chart_canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _style_chart(self, day_stats):
        ax = self.ax
        ax.clear()
        ax.set_facecolor(C["panel"])
        self.fig.patch.set_facecolor(C["panel"])

        if not day_stats:
            ax.text(
                0.5, 0.5, "No image data",
                color=C["muted"], fontsize=11, ha="center", va="center", transform=ax.transAxes
            )
            ax.set_xticks([])
            ax.set_yticks([])
            self.fig.tight_layout(pad=0.6)
            if hasattr(self, "chart_canvas"):
                self.chart_canvas.draw()
            return

        days = sorted(day_stats.keys())
        pass_vals = [day_stats[d]["PASS"] for d in days]
        fail_vals = [day_stats[d]["FAIL"] for d in days]

        ax.bar(days, pass_vals, color=C["pass"], width=0.65, edgecolor="none", label="PASS")
        ax.bar(days, fail_vals, bottom=pass_vals, color=C["fail"], width=0.65, edgecolor="none", label="FAIL")

        totals = [p + f for p, f in zip(pass_vals, fail_vals)]
        for idx, total in enumerate(totals):
            ax.text(idx, total + 0.2, str(total), ha="center", va="bottom", color=C["text"], fontsize=8)

        ax.set_ylim(0, max(totals + [1]) * 1.25)
        ax.tick_params(colors=C["muted"], labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(C["border"])
        ax.set_ylabel("Images", color=C["muted"], fontsize=8)
        ax.tick_params(axis="x", colors=C["text"], rotation=20)
        ax.legend(loc="upper right", frameon=False, fontsize=8, labelcolor=C["text"])
        ax.grid(axis="y", color=C["border"], alpha=0.5, linestyle="--", linewidth=0.6)
        ax.tick_params(axis="x", colors=C["text"])
        self.fig.tight_layout(pad=0.6)
        if hasattr(self, "chart_canvas"):
            self.chart_canvas.draw()

    # ── File pickers ──────────────────────────────────────────────────────────

    def _pick_log(self):
        path = filedialog.askopenfilename(
            title="Select AGV log file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self.log_path.set(path)
            self._update_source_label()
            self._load_log(path)

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select image folder (YYYYMMDD)")
        if folder:
            if folder not in self._img_folders:
                self._img_folders.append(folder)
            self._sync_img_folder_label()
            self._load_images()

    def _sync_img_folder_label(self):
        if not self._img_folders:
            self.img_folder.set("No folder selected")
            self._update_source_label()
            return
        if len(self._img_folders) == 1:
            self.img_folder.set(self._img_folders[0])
            self._update_source_label()
            return
        preview = "; ".join(self._img_folders[:2])
        more = len(self._img_folders) - 2
        if more > 0:
            preview += f"; +{more} folders"
        self.img_folder.set(preview)
        self._update_source_label()

    def _update_source_label(self):
        log_name = os.path.basename(self.log_path.get()) if self.log_path.get() else "none"
        self.source_lbl.config(text=f"Sources: log={log_name} | images={len(self._img_folders)} folders")

    def _clear_image_folders(self):
        self._img_folders = []
        self._image_rows = []
        self._sync_img_folder_label()
        self.lbl_pass.config(text="PASS: 0")
        self.lbl_fail.config(text="FAIL: 0")
        self.lbl_total.config(text="total: 0 | folders: 0 | days: 0")
        self._style_chart({})

    # ── Log loading ───────────────────────────────────────────────────────────

    def _load_log(self, path: str):
        """Read log in background thread to avoid UI freeze."""
        def worker():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Log error", str(exc)))
                return
            self.after(0, lambda: self._set_log_lines(lines))

        threading.Thread(target=worker, daemon=True).start()

    def _set_log_lines(self, lines):
        self._log_lines = list(lines)
        self._log_rows = [self._parse_log_line(line) for line in self._log_lines]
        self._update_category_counts()
        self._apply_log_filter()

    def _classify_log_line(self, line: str):
        lo = line.lower()
        if "掉线" in line or any(k in lo for k in DISCONNECT_KW):
            return "DISCONNECT"
        if "连接" in line or any(k in lo for k in CONNECT_KW):
            return "CONNECT"
        if "上报" in line or "taskstart" in lo or "taskend" in lo or "无法连接到远程服务器" in line:
            return "REPORT"
        if "任务" in line or "下发路线" in line or "目标点" in line or "状态修改" in line:
            return "TASK"
        if "资源集" in line:
            return "RESOURCE"
        return "OTHER"

    def _parse_log_line(self, line: str):
        line = line.rstrip("\n")
        m = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)$", line)
        if m:
            timestamp, msg = m.group(1), m.group(2)
        else:
            timestamp, msg = "", line

        category = self._classify_log_line(msg)
        task_m = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', msg)
        agv_m = re.search(r'(\d{3,5})号AGV', msg) or re.search(r'"carId":\s*(\d+)', msg)
        ip_m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', msg)

        agv = ""
        if agv_m:
            agv = agv_m.group(1)
        elif ip_m:
            agv = ip_m.group(1)

        return {
            "time": timestamp,
            "category": category,
            "agv": agv,
            "task": task_m.group(1) if task_m else "",
            "message": msg,
            "raw": line,
        }

    def _line_match_filter(self, row):
        query = self.log_filter_query.get().strip().lower()
        if not self._category_vars.get(row["category"], tk.BooleanVar(value=False)).get():
            return False
        if query:
            hay = f'{row["time"]} {row["category"]} {row["agv"]} {row["task"]} {row["message"]}'.lower()
            if query not in hay:
                return False
        return True

    def _update_category_counts(self):
        counts = {name: 0 for name in LOG_CATEGORIES}
        for row in self._log_rows:
            counts[row["category"]] += 1
        for name, chk in self._category_checks.items():
            chk.config(text=f"{name} ({counts.get(name, 0)})")

    def _render_log_table(self, rows, total_rows=None):
        self.log_table.delete(*self.log_table.get_children())
        for row in rows:
            self.log_table.insert(
                "",
                tk.END,
                values=(row["time"], row["category"], row["agv"], row["task"], row["message"]),
                tags=(row["category"],),
            )
        total = len(rows) if total_rows is None else total_rows
        self.log_count_lbl.config(text=f"showing: {len(rows)} / {total}")
        if rows:
            first = self.log_table.get_children()
            if first:
                self.log_table.see(first[-1])

    def _apply_log_filter(self):
        rows = [row for row in self._log_rows if self._line_match_filter(row)]
        self._render_log_table(rows, total_rows=len(self._log_rows))

    def _clear_log_filter(self):
        self.log_filter_query.set("")
        for name in LOG_CATEGORIES:
            self._category_vars[name].set(True)
        self._apply_log_filter()

    def _render_log(self, lines, total_lines=None):
        # Backward compatibility wrapper for older call path.
        rows = [self._parse_log_line(line) for line in lines]
        self._render_log_table(rows, total_rows=total_lines)

    def _line_match_filter_legacy(self, line: str):
        # Deprecated, preserved to avoid breaking any external call.
        row = self._parse_log_line(line)
        if not self._category_vars.get(row["category"], tk.BooleanVar(value=False)).get():
            return False
        query = self.log_filter_query.get().strip().lower()
        if query:
            hay = row["raw"].lower()
            if query not in hay:
                return False
        return True

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_images(self):
        rows = []
        for folder in self._img_folders:
            for path, label in scan_images(folder):
                rows.append({"path": path, "label": label, "day": self._extract_day(path)})
        self._image_rows = rows
        self._render_images(rows)

    def _extract_day(self, path: str):
        # 1) Preferred: package folder created by thuthap.py
        #    format: thu_thap_YYYY-MM-DD (or old format with time suffix)
        normalized = path.replace("\\", "/")
        m = re.search(r"thu_thap_(\d{4}-\d{2}-\d{2})(?:_\d{2}-\d{2}-\d{2})?", normalized, re.IGNORECASE)
        if m:
            return m.group(1)

        # 2) Legacy format in folder name: YYYYMMDD
        folder_name = os.path.basename(os.path.dirname(path))
        m2 = re.search(r"(20\d{6})", folder_name)
        if m2:
            raw = m2.group(1)
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

        # 3) Fallback: file modified date
        try:
            ts = os.path.getmtime(path)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return "unknown"

    def _render_images(self, rows):
        pass_n = sum(1 for r in rows if r["label"] == "PASS")
        fail_n = sum(1 for r in rows if r["label"] == "FAIL")
        day_stats = {}
        for r in rows:
            d = r["day"]
            if d not in day_stats:
                day_stats[d] = {"PASS": 0, "FAIL": 0}
            day_stats[d][r["label"]] += 1

        self.lbl_pass.config(text=f"PASS: {pass_n}")
        self.lbl_fail.config(text=f"FAIL: {fail_n}")
        self.lbl_total.config(
            text=f"total: {len(rows)} | folders: {len(self._img_folders)} | days: {len(day_stats)}"
        )
        self._style_chart(day_stats)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh(self):
        if self.log_path.get():
            self._load_log(self.log_path.get())
        if self._img_folders:
            self._load_images()

    def _schedule_refresh(self):
        if AUTO_REFRESH_S > 0:
            self._refresh_lbl.config(text=f"auto-refresh: {AUTO_REFRESH_S}s")
            self.after(AUTO_REFRESH_S * 1000, self._auto_refresh)

    def _auto_refresh(self):
        self._refresh()
        self._schedule_refresh()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = AGVDashboard()
    app.mainloop()
