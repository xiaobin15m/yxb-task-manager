"""主窗口：仿 Windows 任务管理器的“进程 / 性能”界面。"""

from __future__ import annotations

import platform
import sys
import time
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Sequence, Tuple

import psutil

from psmon import __version__
from psmon.collector import Snapshot, SystemCollector
from psmon.format import format_duration, format_rate
from psmon.ui import theme
from psmon.ui.performance import PerformancePage
from psmon.ui.processes import ProcessPage

#: 采样间隔选项：(显示文本, 秒)
INTERVAL_OPTIONS: Sequence[Tuple[str, float]] = (
    ("0.5 秒", 0.5),
    ("1 秒", 1.0),
    ("2 秒", 2.0),
    ("5 秒", 5.0),
)

TABS: Sequence[Tuple[str, str]] = (
    ("processes", "进程"),
    ("performance", "性能"),
)


def _enable_dpi_awareness() -> None:
    """在 Windows 高 DPI 屏幕上启用 DPI 感知，避免界面被系统位图拉伸而变模糊。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class MonitorApp:
    """系统监控主窗口。"""

    REFRESH_MS = 250  # 界面轮询队列的间隔

    def __init__(self) -> None:
        _enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title(f"PsMon 任务管理器  v{__version__}")
        self.root.configure(bg=theme.BG)

        # 窗口尺寸随屏幕自适应，避免在低分辨率屏幕上被裁切
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1180, max(960, screen_width - 40))
        height = min(780, max(640, screen_height - 90))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(1000, width), min(620, height))

        theme.font_family()  # 创建控件前先确定字体
        self._setup_styles()

        self._start_ts = time.monotonic()
        self._sample_count = 0
        self._paused = False
        self._last_snapshot: Optional[Snapshot] = None
        self._current_tab: Optional[str] = None

        self.collector = SystemCollector(interval=1.0)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.collector.start()
        self.root.after(self.REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ 样式
    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "TM.Treeview",
            background=theme.PANEL,
            fieldbackground=theme.PANEL,
            foreground=theme.TEXT,
            borderwidth=0,
            rowheight=27,
            font=theme.font(9),
        )
        style.map(
            "TM.Treeview",
            background=[("selected", theme.NAV_SELECTED)],
            foreground=[("selected", theme.TEXT)],
        )
        style.configure(
            "TM.Treeview.Heading",
            background=theme.PANEL,
            foreground=theme.SUBTEXT,
            relief="flat",
            borderwidth=0,
            font=theme.font(9),
            padding=(10, 8),
        )
        style.map(
            "TM.Treeview.Heading",
            background=[("active", theme.NAV_HOVER)],
        )
        # 去掉表格四周的立体边框，贴近任务管理器的扁平列表
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        style.configure(
            "TM.Vertical.TScrollbar",
            background=theme.BG,
            troughcolor=theme.PANEL,
            bordercolor=theme.PANEL,
            arrowcolor=theme.SUBTEXT,
            relief="flat",
            width=12,
        )
        style.map(
            "TM.Vertical.TScrollbar",
            background=[("active", theme.TRACK)],
        )

        style.configure(
            "TM.TCombobox",
            fieldbackground=theme.PANEL,
            background=theme.PANEL,
            foreground=theme.TEXT,
            bordercolor=theme.BORDER,
            lightcolor=theme.PANEL,
            darkcolor=theme.PANEL,
            arrowcolor=theme.SUBTEXT,
            padding=(6, 2),
        )
        style.map(
            "TM.TCombobox",
            fieldbackground=[("readonly", theme.PANEL)],
            selectbackground=[("readonly", theme.PANEL)],
            selectforeground=[("readonly", theme.TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", theme.PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.NAV_SELECTED)
        self.root.option_add("*TCombobox*Listbox.selectForeground", theme.TEXT)

    # ------------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        self._build_top_bar()
        self._build_status_bar()

        self._body = tk.Frame(self.root, bg=theme.PANEL)
        self._body.pack(fill="both", expand=True)
        self._body.rowconfigure(0, weight=1)
        self._body.columnconfigure(0, weight=1)

        self.performance = PerformancePage(self._body)
        self.processes = ProcessPage(self._body)
        self._pages: Dict[str, tk.Frame] = {
            "processes": self.processes,
            "performance": self.performance,
        }
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self._switch("performance")

    def _build_top_bar(self) -> None:
        top = tk.Frame(self.root, bg=theme.PANEL)
        top.pack(fill="x")

        tabs = tk.Frame(top, bg=theme.PANEL)
        tabs.pack(side="left", padx=(14, 0), pady=(8, 0))
        self._tabs: Dict[str, Tuple[tk.Label, tk.Frame]] = {}
        for key, title in TABS:
            holder = tk.Frame(tabs, bg=theme.PANEL, cursor="hand2")
            holder.pack(side="left", padx=(0, 8))
            label = tk.Label(
                holder,
                text=title,
                bg=theme.PANEL,
                fg=theme.SUBTEXT,
                font=theme.font(10),
                padx=10,
                pady=5,
            )
            label.pack()
            underline = tk.Frame(holder, bg=theme.PANEL, height=2)
            underline.pack(fill="x")
            for widget in (holder, label, underline):
                widget.bind("<Button-1>", lambda _event, name=key: self._switch(name))
                widget.bind("<Enter>", lambda _event, name=key: self._hover_tab(name, True))
                widget.bind("<Leave>", lambda _event, name=key: self._hover_tab(name, False))
            self._tabs[key] = (label, underline)

        controls = tk.Frame(top, bg=theme.PANEL)
        controls.pack(side="right", padx=16, pady=(8, 0))

        self.pause_button = tk.Button(
            controls,
            text="暂停",
            command=self._toggle_pause,
            bg=theme.PANEL,
            fg=theme.TEXT,
            activebackground=theme.NAV_HOVER,
            activeforeground=theme.TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=theme.font(9),
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.pause_button.pack(side="right", padx=(12, 0))

        self.interval_var = tk.StringVar(value=INTERVAL_OPTIONS[1][0])
        interval_combo = ttk.Combobox(
            controls,
            textvariable=self.interval_var,
            values=[label for label, _seconds in INTERVAL_OPTIONS],
            state="readonly",
            width=5,
            font=theme.font(9),
            style="TM.TCombobox",
        )
        interval_combo.pack(side="right")
        interval_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_interval_change(self.interval_var.get()),
        )

        tk.Label(
            controls,
            text="采样间隔",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(8),
        ).pack(side="right", padx=(0, 6))

        tk.Frame(self.root, bg=theme.BORDER, height=1).pack(fill="x")

    def _build_status_bar(self) -> None:
        tk.Frame(self.root, bg=theme.BORDER, height=1).pack(side="bottom", fill="x")
        bar = tk.Frame(self.root, bg=theme.BG, height=30)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg=theme.BG)
        inner.pack(fill="both", expand=True, padx=16)

        self._stat_values: Dict[str, tk.Label] = {}
        for index, (key, caption) in enumerate(
            (
                ("processes", "进程"),
                ("cpu", "CPU"),
                ("memory", "内存"),
                ("disk", "磁盘"),
                ("network", "网络"),
            )
        ):
            if index:
                tk.Label(
                    inner, text="│", bg=theme.BG, fg=theme.BORDER, font=theme.font(8)
                ).pack(side="left", padx=10)
            tk.Label(
                inner,
                text=f"{caption}:",
                bg=theme.BG,
                fg=theme.SUBTEXT,
                font=theme.font(8),
            ).pack(side="left", padx=(0, 4))
            value = tk.Label(
                inner, text="—", bg=theme.BG, fg=theme.TEXT, font=theme.font(8)
            )
            value.pack(side="left")
            self._stat_values[key] = value

        self._status_meta = tk.Label(
            inner, text="", bg=theme.BG, fg=theme.FAINT, font=theme.font(8)
        )
        self._status_meta.pack(side="right")

    # ------------------------------------------------------------------ 标签切换
    def _hover_tab(self, key: str, entering: bool) -> None:
        if key == self._current_tab:
            return
        label = self._tabs[key][0]
        label.configure(bg=theme.NAV_HOVER if entering else theme.PANEL)

    def _switch(self, key: str) -> None:
        if key == self._current_tab:
            return
        self._current_tab = key
        for name, page in self._pages.items():
            if name == key:
                page.grid()
            else:
                page.grid_remove()
        for name, (label, underline) in self._tabs.items():
            selected = name == key
            label.configure(
                fg=theme.TEXT if selected else theme.SUBTEXT,
                bg=theme.PANEL,
                font=theme.font(10, "bold" if selected else "normal"),
            )
            underline.configure(bg=theme.ACCENT if selected else theme.PANEL)

        if key == "performance":
            self.performance.on_show()
        elif self._last_snapshot is not None:
            self.processes.update(self._last_snapshot)

    # ------------------------------------------------------------------ 数据刷新
    def _tick(self) -> None:
        snapshot = self.collector.poll()
        if snapshot is not None:
            self._sample_count += 1
            self._last_snapshot = snapshot
            self.performance.update(snapshot)
            if self._current_tab == "processes":
                self.processes.update(snapshot)
            self._refresh_stats()
        self._refresh_meta()
        self.root.after(self.REFRESH_MS, self._tick)

    def _refresh_stats(self) -> None:
        snapshot = self._last_snapshot
        if snapshot is None:
            return
        self._stat_values["processes"].configure(
            text=str(snapshot.process_count) if snapshot.process_count else "—"
        )
        self._stat_values["cpu"].configure(text=f"{snapshot.cpu_percent:.0f}%")
        self._stat_values["memory"].configure(text=f"{snapshot.mem_percent:.0f}%")
        self._stat_values["disk"].configure(
            text=format_rate(snapshot.disk_read_rate + snapshot.disk_write_rate)
        )
        self._stat_values["network"].configure(
            text=(
                f"↑ {format_rate(snapshot.net_sent_rate)}  "
                f"↓ {format_rate(snapshot.net_recv_rate)}"
            )
        )

    def _refresh_meta(self) -> None:
        state = "已暂停" if self._paused else "采集中"
        elapsed = format_duration(time.monotonic() - self._start_ts)
        self._status_meta.configure(
            text=(
                f"{state} · 采样 {self._sample_count} 次 · 已运行 {elapsed}"
                f" · psutil {psutil.__version__} · Python {platform.python_version()}"
            )
        )

    # ------------------------------------------------------------------ 交互
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.collector.pause()
            self.pause_button.configure(text="继续", fg=theme.AMBER)
        else:
            self.collector.resume()
            self.pause_button.configure(text="暂停", fg=theme.TEXT)
        self._refresh_meta()

    def _on_interval_change(self, label: str) -> None:
        for name, seconds in INTERVAL_OPTIONS:
            if name == label:
                self.collector.set_interval(seconds)
                break
        self._refresh_meta()

    def _on_close(self) -> None:
        try:
            self.collector.stop()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------------ 启动
    def run(self) -> None:
        self.root.mainloop()
