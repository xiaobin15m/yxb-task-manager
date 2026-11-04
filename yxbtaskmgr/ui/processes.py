"""进程页：任务管理器样式的进程列表，支持名称筛选与点击表头排序。"""

from __future__ import annotations

import tkinter as tk
from typing import Sequence, Tuple

from yxbtaskmgr.collector import ProcessEntry, Snapshot
from yxbtaskmgr.format import format_bytes, format_process_status
from yxbtaskmgr.ui import theme
from yxbtaskmgr.ui.widgets import ProcessTable

COLUMNS: Sequence[Tuple[str, str, int, str]] = (
    ("name", "名称", 300, "w"),
    ("status", "状态", 110, "w"),
    ("cpu", "CPU", 90, "e"),
    ("memory", "内存", 120, "e"),
    ("pid", "PID", 90, "e"),
)


class ProcessPage(tk.Frame):
    """任务管理器“进程”页。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.PANEL)
        self._sort_key = "cpu"
        self._sort_desc = True
        self._filter = ""
        self._entries: Tuple[ProcessEntry, ...] = ()
        self._count = 0
        self._build()
        self._refresh_headings()
        self._render()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        bar = tk.Frame(self, bg=theme.PANEL)
        bar.pack(fill="x", padx=18, pady=(12, 8))
        tk.Label(
            bar,
            text="进程",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(18, "bold"),
            anchor="w",
        ).pack(side="left")
        self._count_label = tk.Label(
            bar,
            text="正在读取进程…",
            bg=theme.PANEL,
            fg=theme.SUBTEXT,
            font=theme.font(8),
            anchor="w",
        )
        self._count_label.pack(side="left", padx=(12, 0), pady=(8, 0))

        search = tk.Frame(bar, bg=theme.PANEL)
        search.pack(side="right")
        tk.Label(
            search,
            text="筛选",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(8),
        ).pack(side="left", padx=(0, 6))
        self._search_var = tk.StringVar()
        entry = tk.Entry(
            search,
            textvariable=self._search_var,
            width=22,
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(9),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT,
            insertbackground=theme.TEXT,
        )
        entry.pack(side="left", ipady=3)
        entry.bind("<KeyRelease>", self._on_filter)

        tk.Label(
            self,
            text="本页只做监控展示，不提供结束进程操作，以免误杀系统进程。",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(7),
            anchor="w",
        ).pack(side="bottom", fill="x", padx=20, pady=(0, 8))

        table_wrap = tk.Frame(self, bg=theme.PANEL)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self._table = ProcessTable(table_wrap, COLUMNS, on_sort=self._on_sort)
        self._table.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ 数据
    def update(self, snapshot: Snapshot) -> None:
        self._entries = snapshot.processes
        self._count = snapshot.process_count
        self._render()

    def _render(self) -> None:
        entries = self._entries
        if self._filter:
            needle = self._filter.lower()
            entries = tuple(
                entry for entry in entries if needle in entry.name.lower()
            )
        entries = sorted(entries, key=self._sort_value, reverse=self._sort_desc)

        rows = [
            (
                str(entry.pid),
                (
                    entry.name,
                    format_process_status(entry.status),
                    f"{entry.cpu_percent:.1f}%",
                    format_bytes(entry.memory_rss),
                    str(entry.pid),
                ),
            )
            for entry in entries
        ]
        self._table.set_rows(rows)

        if not self._entries:
            self._count_label.configure(text="正在读取进程列表…")
            return
        if self._filter:
            self._count_label.configure(
                text=f"共 {self._count} 个进程 · 筛选后 {len(entries)} 个"
            )
        else:
            self._count_label.configure(
                text=f"共 {self._count} 个进程 · 按 CPU 降序显示前 {len(entries)} 个"
            )

    def _sort_value(self, entry: ProcessEntry):
        key = self._sort_key
        if key == "name":
            return entry.name.lower()
        if key == "status":
            return format_process_status(entry.status)
        if key == "memory":
            return entry.memory_rss
        if key == "pid":
            return entry.pid
        return entry.cpu_percent

    # ------------------------------------------------------------------ 交互
    def _on_sort(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key not in ("name", "status")
        self._refresh_headings()
        self._render()

    def _refresh_headings(self) -> None:
        for key, title, _width, _anchor in COLUMNS:
            if key == self._sort_key:
                title = title + (" ▼" if self._sort_desc else " ▲")
            self._table.tree.heading(key, text=title)

    def _on_filter(self, _event: tk.Event) -> None:
        self._filter = self._search_var.get().strip()
        self._render()
