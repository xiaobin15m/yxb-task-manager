"""主窗口：布局编排、指标刷新与交互控制。"""

from __future__ import annotations

import platform
import sys
import time
import tkinter as tk
from typing import List, Optional, Sequence, Tuple

import psutil

from psmon import __version__
from psmon.collector import PartitionUsage, Snapshot, SystemCollector
from psmon.format import format_bytes, format_duration, format_rate
from psmon.ui import theme
from psmon.ui.widgets import (
    Card,
    CoreMatrix,
    LineChart,
    PartitionRow,
    byte_axis_formatter,
)

#: 采样间隔选项：(显示文本, 秒)
INTERVAL_OPTIONS: Sequence[Tuple[str, float]] = (
    ("0.5 秒", 0.5),
    ("1 秒", 1.0),
    ("2 秒", 2.0),
    ("5 秒", 5.0),
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

    REFRESH_MS = 200          # 界面轮询队列的间隔
    HISTORY_POINTS = 90       # 每条曲线保留的采样点数

    def __init__(self) -> None:
        _enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("PsMon 系统监控")
        self.root.configure(bg=theme.BG)
        # 窗口默认尺寸随屏幕自适应，避免在低分辨率屏幕上被裁切
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1200, max(920, screen_width - 60))
        height = min(840, max(680, screen_height - 90))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(960, width), min(760, height))

        self._start_ts = time.monotonic()
        self._sample_count = 0
        self._paused = False
        self._last_snapshot: Optional[Snapshot] = None
        self._partition_key: Tuple[str, ...] = ()
        self._partition_rows: List[PartitionRow] = []
        self._physical_cores = psutil.cpu_count(logical=False)

        theme.font_family()  # 创建控件前确定字体
        self.collector = SystemCollector(interval=1.0, partition_interval=10.0)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.collector.start()
        self.root.after(self.REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ 界面构建
    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=theme.BG, padx=16, pady=12)
        outer.pack(fill="both", expand=True)

        self._build_header(outer)
        self._build_status_bar(outer)

        body = tk.Frame(outer, bg=theme.BG)
        body.pack(fill="both", expand=True, pady=(12, 0))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(0, weight=5)
        body.rowconfigure(1, weight=4)
        body.rowconfigure(2, weight=3)
        self._body = body
        self._row_weights = (5, 4, 3)
        # 窗口变矮时给底部两张卡片分配更多高度，避免分区行被裁切
        self.root.bind("<Configure>", self._on_root_configure)

        self._build_cpu_card(body).grid(
            row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6)
        )
        self._build_memory_card(body).grid(
            row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6)
        )
        self._build_network_card(body).grid(
            row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6)
        )
        self._build_disk_io_card(body).grid(
            row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6)
        )
        self._build_partition_card(body).grid(
            row=2, column=0, sticky="nsew", padx=(0, 6)
        )
        self._build_core_card(body).grid(
            row=2, column=1, sticky="nsew", padx=(6, 0)
        )

    def _build_header(self, parent: tk.Misc) -> None:
        header = tk.Frame(parent, bg=theme.BG)
        header.pack(fill="x")

        title_box = tk.Frame(header, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(
            title_box,
            text="PsMon 系统监控台",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.font(19, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="基于 psutil 的 CPU / 内存 / 磁盘 / 网络 实时监控",
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        controls = tk.Frame(header, bg=theme.BG)
        controls.pack(side="right")

        self.pause_button = tk.Button(
            controls,
            text="暂停采集",
            command=self._toggle_pause,
            bg=theme.CARD,
            fg=theme.TEXT,
            activebackground=theme.TRACK,
            activeforeground=theme.TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            font=theme.font(9),
            padx=14,
            pady=5,
            cursor="hand2",
        )
        self.pause_button.pack(side="right", padx=(8, 0))

        self.interval_var = tk.StringVar(value=INTERVAL_OPTIONS[1][0])
        interval_menu = tk.OptionMenu(
            controls,
            self.interval_var,
            *[label for label, _seconds in INTERVAL_OPTIONS],
            command=self._on_interval_change,
        )
        self._style_option_menu(interval_menu)
        interval_menu.pack(side="right", padx=(6, 0))

        tk.Label(
            controls,
            text="采样间隔",
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(9),
        ).pack(side="right")

    @staticmethod
    def _style_option_menu(menu: tk.OptionMenu) -> None:
        menu.configure(
            bg=theme.CARD,
            fg=theme.TEXT,
            activebackground=theme.TRACK,
            activeforeground=theme.TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            font=theme.font(9),
            padx=8,
            pady=4,
            cursor="hand2",
        )
        menu["menu"].configure(
            bg=theme.CARD,
            fg=theme.TEXT,
            activebackground=theme.ACCENT,
            activeforeground=theme.BG,
            font=theme.font(9),
            bd=0,
            relief="flat",
        )

    def _build_status_bar(self, parent: tk.Misc) -> None:
        bar = tk.Frame(parent, bg=theme.BG, pady=4)
        bar.pack(side="bottom", fill="x")
        self.status_dot = tk.Label(
            bar, text="●", bg=theme.BG, fg=theme.GREEN, font=theme.font(10)
        )
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(
            bar,
            text="正在启动采样线程…",
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.font(9),
        )
        self.status_text.pack(side="left", padx=(4, 0))
        self.status_meta = tk.Label(
            bar, text="", bg=theme.BG, fg=theme.MUTED, font=theme.font(9)
        )
        self.status_meta.pack(side="right")

    def _on_root_configure(self, event: tk.Event) -> None:
        """窗口高度变化时动态分配三行卡片的高度比例。"""
        if event.widget is not self.root:
            return
        weights = (5, 4, 4) if event.height < 800 else (5, 4, 3)
        if weights == self._row_weights:
            return
        self._row_weights = weights
        for index, weight in enumerate(weights):
            self._body.rowconfigure(index, weight=weight)

    def _build_cpu_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "CPU 使用率", "全部逻辑核心平均占用", theme.ACCENT)
        head = tk.Frame(card.body, bg=theme.CARD)
        head.pack(fill="x")
        self.cpu_value = tk.Label(
            head,
            text="0.0%",
            bg=theme.CARD,
            fg=theme.ACCENT,
            font=theme.font(26, "bold"),
            anchor="w",
        )
        self.cpu_value.pack(side="left")

        meta = tk.Frame(head, bg=theme.CARD)
        meta.pack(side="right")
        self.cpu_meta = tk.Label(
            meta,
            text="—",
            bg=theme.CARD,
            fg=theme.TEXT,
            font=theme.font(9),
            anchor="e",
            justify="right",
        )
        self.cpu_meta.pack(anchor="e")
        self.cpu_meta2 = tk.Label(
            meta,
            text="—",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(8),
            anchor="e",
            justify="right",
        )
        self.cpu_meta2.pack(anchor="e", pady=(2, 0))

        self.cpu_chart = LineChart(
            card.body,
            [("cpu", "总体占用", theme.ACCENT)],
            max_points=self.HISTORY_POINTS,
            y_max=100,
            axis_formatter=lambda value: f"{value:.0f}%",
        )
        self.cpu_chart.pack(fill="both", expand=True, pady=(6, 0))
        return card

    def _build_core_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "CPU 核心负载", "每个逻辑核心的实时占用率", theme.PURPLE)
        self.core_matrix = CoreMatrix(card.body, height=88)
        self.core_matrix.pack(fill="both", expand=True)
        return card

    def _build_memory_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "内存使用率", "物理内存 / 交换分区", theme.PURPLE)
        head = tk.Frame(card.body, bg=theme.CARD)
        head.pack(fill="x")
        self.mem_value = tk.Label(
            head,
            text="0.0%",
            bg=theme.CARD,
            fg=theme.PURPLE,
            font=theme.font(26, "bold"),
            anchor="w",
        )
        self.mem_value.pack(side="left")

        meta = tk.Frame(head, bg=theme.CARD)
        meta.pack(side="right")
        self.mem_detail = tk.Label(
            meta,
            text="—",
            bg=theme.CARD,
            fg=theme.TEXT,
            font=theme.font(9),
            anchor="e",
            justify="right",
        )
        self.mem_detail.pack(anchor="e")
        self.mem_swap = tk.Label(
            meta,
            text="—",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(8),
            anchor="e",
            justify="right",
        )
        self.mem_swap.pack(anchor="e", pady=(2, 0))

        self.mem_chart = LineChart(
            card.body,
            [("mem", "内存占用", theme.PURPLE)],
            max_points=self.HISTORY_POINTS,
            y_max=100,
            axis_formatter=lambda value: f"{value:.0f}%",
        )
        self.mem_chart.pack(fill="both", expand=True, pady=(6, 0))
        return card

    def _build_network_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "网络收发速率", "网卡累计字节差分计算", theme.GREEN)
        head = tk.Frame(card.body, bg=theme.CARD)
        head.pack(fill="x")
        self.net_down = self._build_rate_stat(head, "下载（接收）", theme.GREEN)
        self.net_up = self._build_rate_stat(head, "上传（发送）", theme.AMBER)
        self.net_chart = LineChart(
            card.body,
            [("down", "下载", theme.GREEN), ("up", "上传", theme.AMBER)],
            max_points=self.HISTORY_POINTS,
            min_y_max=1024,
            axis_formatter=byte_axis_formatter,
        )
        self.net_chart.pack(fill="both", expand=True, pady=(6, 0))
        return card

    def _build_disk_io_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "磁盘读写速率", "物理磁盘累计字节差分计算", theme.PINK)
        head = tk.Frame(card.body, bg=theme.CARD)
        head.pack(fill="x")
        self.disk_read = self._build_rate_stat(head, "读取", theme.PINK)
        self.disk_write = self._build_rate_stat(head, "写入", theme.BLUE)
        self.disk_chart = LineChart(
            card.body,
            [("read", "读取", theme.PINK), ("write", "写入", theme.BLUE)],
            max_points=self.HISTORY_POINTS,
            min_y_max=1024,
            axis_formatter=byte_axis_formatter,
        )
        self.disk_chart.pack(fill="both", expand=True, pady=(6, 0))
        return card

    def _build_rate_stat(
        self, parent: tk.Misc, title: str, color: str
    ) -> tk.Label:
        box = tk.Frame(parent, bg=theme.CARD)
        box.pack(side="left", padx=(0, 26))
        tk.Label(
            box,
            text=title,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        ).pack(anchor="w")
        value = tk.Label(
            box,
            text="0 B/s",
            bg=theme.CARD,
            fg=color,
            font=theme.font(15, "bold"),
            anchor="w",
        )
        value.pack(anchor="w", pady=(2, 0))
        return value

    def _build_partition_card(self, parent: tk.Misc) -> Card:
        card = Card(parent, "磁盘分区使用率", "分区容量每 10 秒刷新", theme.BLUE)
        self.partition_box = tk.Frame(card.body, bg=theme.CARD)
        self.partition_box.pack(fill="both", expand=True)
        tk.Label(
            self.partition_box,
            text="正在读取分区信息…",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(9),
        ).pack(anchor="w", pady=4)
        return card

    # ------------------------------------------------------------------ 数据刷新
    def _tick(self) -> None:
        snapshot = self.collector.poll()
        if snapshot is not None:
            self._sample_count += 1
            self._last_snapshot = snapshot
            self._apply(snapshot)
        self._refresh_status()
        self.root.after(self.REFRESH_MS, self._tick)

    def _apply(self, snapshot: Snapshot) -> None:
        self._apply_cpu(snapshot)
        self._apply_memory(snapshot)
        self._apply_rates(snapshot)
        self._apply_partitions(snapshot.partitions)

    def _apply_cpu(self, snapshot: Snapshot) -> None:
        percent = snapshot.cpu_percent
        self.cpu_value.configure(
            text=f"{percent:.1f}%", fg=theme.load_color(percent)
        )
        frequency = (
            f"{snapshot.cpu_freq_mhz / 1000.0:.2f} GHz"
            if snapshot.cpu_freq_mhz
            else "频率未知"
        )
        self.cpu_meta.configure(
            text=(
                f"{len(snapshot.cpu_per_core)} 逻辑核心 · "
                f"{self._physical_cores or '?'} 物理核心 · {frequency}"
            )
        )
        if snapshot.load_avg:
            load_text = " / ".join(f"{value:.2f}" for value in snapshot.load_avg)
        else:
            load_text = "—"
        self.cpu_meta2.configure(text=f"系统负载（1/5/15 分钟）：{load_text}")

        self.cpu_chart.push({"cpu": percent})
        self.core_matrix.update_values(snapshot.cpu_per_core)

    def _apply_memory(self, snapshot: Snapshot) -> None:
        self.mem_value.configure(
            text=f"{snapshot.mem_percent:.1f}%",
            fg=theme.load_color(snapshot.mem_percent),
        )
        self.mem_detail.configure(
            text=(
                f"已用 {format_bytes(snapshot.mem_used)} / "
                f"共 {format_bytes(snapshot.mem_total)}"
            )
        )
        if snapshot.swap_total:
            swap_text = (
                f"交换分区 {format_bytes(snapshot.swap_used)} / "
                f"{format_bytes(snapshot.swap_total)}（{snapshot.swap_percent:.0f}%）"
            )
        else:
            swap_text = "未启用交换分区"
        self.mem_swap.configure(text=swap_text)
        self.mem_chart.push({"mem": snapshot.mem_percent})

    def _apply_rates(self, snapshot: Snapshot) -> None:
        self.net_down.configure(text=format_rate(snapshot.net_recv_rate))
        self.net_up.configure(text=format_rate(snapshot.net_sent_rate))
        self.net_chart.push(
            {"down": snapshot.net_recv_rate, "up": snapshot.net_sent_rate}
        )

        self.disk_read.configure(text=format_rate(snapshot.disk_read_rate))
        self.disk_write.configure(text=format_rate(snapshot.disk_write_rate))
        self.disk_chart.push(
            {"read": snapshot.disk_read_rate, "write": snapshot.disk_write_rate}
        )

    def _apply_partitions(self, partitions: Sequence[PartitionUsage]) -> None:
        key = tuple(part.mountpoint for part in partitions)
        if key != self._partition_key:
            self._partition_key = key
            for child in self.partition_box.winfo_children():
                child.destroy()
            self._partition_rows = []
            if not partitions:
                tk.Label(
                    self.partition_box,
                    text="未检测到可访问的磁盘分区",
                    bg=theme.CARD,
                    fg=theme.MUTED,
                    font=theme.font(9),
                ).pack(anchor="w", pady=4)
            for index, part in enumerate(partitions):
                row = PartitionRow(
                    self.partition_box, part.device, part.mountpoint, part.fstype
                )
                row.pack(
                    fill="x",
                    pady=(0, 2) if index < len(partitions) - 1 else 0,
                )
                self._partition_rows.append(row)

        for row, part in zip(self._partition_rows, partitions):
            row.set(part.used, part.total, part.percent)

    # ------------------------------------------------------------------ 交互
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.collector.pause()
            self.pause_button.configure(text="继续采集", fg=theme.AMBER)
            self.status_dot.configure(fg=theme.AMBER)
        else:
            self.collector.resume()
            self.pause_button.configure(text="暂停采集", fg=theme.TEXT)
            self.status_dot.configure(fg=theme.GREEN)
        self._refresh_status()

    def _on_interval_change(self, label: str) -> None:
        for name, seconds in INTERVAL_OPTIONS:
            if name == label:
                self.collector.set_interval(seconds)
                break
        self._refresh_status()

    def _refresh_status(self) -> None:
        state = "已暂停" if self._paused else "采集中"
        elapsed = format_duration(time.monotonic() - self._start_ts)
        self.status_text.configure(
            text=f"{state} · 采样 {self._sample_count} 次 · 已运行 {elapsed}"
        )
        self.status_meta.configure(
            text=(
                f"采样间隔 {self.collector.interval:.1f} s · "
                f"psutil {psutil.__version__} · "
                f"Python {platform.python_version()} · v{__version__}"
            )
        )

    def _on_close(self) -> None:
        try:
            self.collector.stop()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------------ 启动
    def run(self) -> None:
        self.root.mainloop()
