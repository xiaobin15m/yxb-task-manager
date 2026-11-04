"""性能页：左侧组件列表 + 右侧大图表与统计信息，布局参考 Windows 任务管理器。"""

from __future__ import annotations

import tkinter as tk
from typing import Dict, List, Sequence, Tuple

import psutil

from yxbtaskmgr.collector import PartitionUsage, Snapshot
from yxbtaskmgr.format import format_bytes, format_rate, format_uptime
from yxbtaskmgr.ui import theme
from yxbtaskmgr.ui.widgets import (
    AdapterRow,
    AreaChart,
    BarRow,
    CoreGrid,
    NavItem,
    StatPanel,
    byte_axis_formatter,
    format_percent_axis,
)

#: 左侧组件列表宽度
NAV_WIDTH = 292


def _gigabytes(num: float) -> str:
    return f"{num / (1024 ** 3):.1f} GB"


def _freq_text(freq_mhz: float | None) -> str:
    return f"{freq_mhz / 1000:.2f} GHz" if freq_mhz else "未知"


def _partition_label(part: PartitionUsage) -> str:
    mount = part.mountpoint
    if mount in ("/", "\\"):
        return mount
    return mount.rstrip("\\/") or mount


class PerformancePage(tk.Frame):
    """任务管理器“性能”页。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.PANEL)
        self._physical_cores = psutil.cpu_count(logical=False) or 0
        self._logical_cores = psutil.cpu_count(logical=True) or 0
        self._current = "cpu"
        self._partition_key: Tuple[str, ...] = ()
        self._adapter_key: Tuple[str, ...] = ()
        self._partition_rows: List[BarRow] = []
        self._adapter_rows: List[Tuple[AdapterRow, str]] = []
        self._build_nav()
        self._build_views()
        self.select(self._current)

    # ------------------------------------------------------------------ 构建
    def _build_nav(self) -> None:
        nav = tk.Frame(self, bg=theme.PANEL, width=NAV_WIDTH)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Frame(self, bg=theme.BORDER, width=1).pack(side="left", fill="y")
        tk.Frame(nav, bg=theme.PANEL, height=10).pack(fill="x")

        self._nav_items: Dict[str, NavItem] = {}
        specs: Sequence[Tuple[str, str, str, str, float | None, float]] = (
            ("cpu", "CPU", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL, 100.0, 1.0),
            ("memory", "内存", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL, 100.0, 1.0),
            ("disk", "磁盘", theme.GRAPH_ORANGE, theme.GRAPH_ORANGE_FILL, None, 1024 * 512),
            ("network", "网络", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL, None, 1024 * 512),
        )
        for key, title, color, fill, fixed_max, min_max in specs:
            item = NavItem(
                nav,
                title,
                on_click=lambda name=key: self.select(name),
                color=color,
                fill=fill,
                fixed_max=fixed_max,
                min_max=min_max,
            )
            item.pack(fill="x")
            self._nav_items[key] = item

    def _build_views(self) -> None:
        self._detail = tk.Frame(self, bg=theme.PANEL)
        self._detail.pack(side="left", fill="both", expand=True)
        self._detail.rowconfigure(0, weight=1)
        self._detail.columnconfigure(0, weight=1)

        self._views: Dict[str, tk.Frame] = {}
        self._charts: Dict[str, AreaChart] = {}
        self._views["cpu"] = self._build_cpu_view()
        self._views["memory"] = self._build_memory_view()
        self._views["disk"] = self._build_disk_view()
        self._views["network"] = self._build_network_view()

    def _new_view(self) -> tk.Frame:
        view = tk.Frame(self._detail, bg=theme.PANEL)
        view.grid(row=0, column=0, sticky="nsew")
        view.columnconfigure(0, weight=1)
        view.rowconfigure(0, weight=0)
        view.rowconfigure(1, weight=3, minsize=190)
        view.rowconfigure(2, weight=2, minsize=108)
        return view

    def _add_header(self, view: tk.Frame, title: str) -> tk.Label:
        header = tk.Frame(view, bg=theme.PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        tk.Label(
            header,
            text=title,
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(18, "bold"),
            anchor="w",
        ).pack(side="left")
        subtitle = tk.Label(
            header,
            text="",
            bg=theme.PANEL,
            fg=theme.SUBTEXT,
            font=theme.font(8),
            anchor="w",
        )
        subtitle.pack(side="left", padx=(12, 0), pady=(6, 0))
        return subtitle

    def _add_chart_row(self, view: tk.Frame) -> tk.Frame:
        body = tk.Frame(view, bg=theme.PANEL)
        body.grid(row=1, column=0, sticky="nsew", padx=(18, 14))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        return body

    def _add_bottom(self, view: tk.Frame) -> tk.Frame:
        bottom = tk.Frame(view, bg=theme.PANEL)
        bottom.grid(row=2, column=0, sticky="nsew", padx=(18, 14), pady=(12, 12))
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(2, weight=1)
        return bottom

    @staticmethod
    def _bottom_title(parent: tk.Misc, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(9),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

    # ---- CPU -----------------------------------------------------------
    def _build_cpu_view(self) -> tk.Frame:
        view = self._new_view()
        self._cpu_subtitle = self._add_header(view, "CPU")

        body = self._add_chart_row(view)
        chart = AreaChart(
            body,
            [("cpu", "CPU", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL)],
            max_points=60,
            y_max=100,
            y_formatter=format_percent_axis,
            height=190,
        )
        chart.grid(row=0, column=0, sticky="nsew")
        self._charts["cpu"] = chart

        self._cpu_stats = StatPanel(
            body,
            (
                ("usage", "利用率"),
                ("speed", "速度"),
                ("physical", "内核"),
                ("logical", "逻辑处理器"),
                ("load", "系统负载（1/5/15 分钟）"),
                ("uptime", "运行时间"),
            ),
        )
        self._cpu_stats.grid(row=0, column=1, sticky="nsew", padx=(16, 0))

        bottom = self._add_bottom(view)
        self._bottom_title(bottom, "每个 CPU 的利用率")
        self._cores = CoreGrid(bottom, max_points=30, height=100)
        self._cores.grid(row=2, column=0, sticky="nsew")
        return view

    # ---- 内存 ----------------------------------------------------------
    def _build_memory_view(self) -> tk.Frame:
        view = self._new_view()
        self._memory_subtitle = self._add_header(view, "内存")

        body = self._add_chart_row(view)
        chart = AreaChart(
            body,
            [("memory", "内存", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL)],
            max_points=60,
            y_max=100,
            y_formatter=format_percent_axis,
            height=190,
        )
        chart.grid(row=0, column=0, sticky="nsew")
        self._charts["memory"] = chart

        self._memory_stats = StatPanel(
            body,
            (
                ("used", "使用中"),
                ("available", "可用"),
                ("swap", "交换分区"),
                ("percent", "使用率"),
            ),
        )
        self._memory_stats.grid(row=0, column=1, sticky="nsew", padx=(16, 0))

        bottom = self._add_bottom(view)
        self._bottom_title(bottom, "内存组成")
        self._memory_bar, self._memory_segments = self._build_composition(bottom, row=1)
        legend = tk.Frame(bottom, bg=theme.PANEL)
        legend.grid(row=2, column=0, sticky="nw", pady=(8, 0))
        self._memory_legend: Dict[str, tk.Label] = {}
        for key, color in (("used", theme.GRAPH_BLUE), ("free", theme.TRACK)):
            holder = tk.Frame(legend, bg=theme.PANEL)
            holder.pack(side="left", padx=(0, 22))
            swatch = tk.Frame(holder, bg=color, width=9, height=9)
            swatch.pack(side="left", padx=(0, 6))
            swatch.pack_propagate(False)
            label = tk.Label(
                holder,
                text="",
                bg=theme.PANEL,
                fg=theme.SUBTEXT,
                font=theme.font(8),
                anchor="w",
            )
            label.pack(side="left")
            self._memory_legend[key] = label
        self._memory_legend["used"].configure(text="使用中")
        self._memory_legend["free"].configure(text="可用")
        return view

    @staticmethod
    def _build_composition(
        parent: tk.Misc, row: int
    ) -> Tuple[tk.Frame, Dict[str, tk.Frame]]:
        bar = tk.Frame(parent, bg=theme.PANEL, height=16)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.rowconfigure(0, weight=1)
        segments: Dict[str, tk.Frame] = {}
        for index, (key, color) in enumerate(
            (("used", theme.GRAPH_BLUE), ("free", theme.TRACK))
        ):
            bar.columnconfigure(index, weight=1, minsize=1)
            segment = tk.Frame(bar, bg=color)
            segment.grid(row=0, column=index, sticky="nsew")
            segments[key] = segment
        return bar, segments

    # ---- 磁盘 ----------------------------------------------------------
    def _build_disk_view(self) -> tk.Frame:
        view = self._new_view()
        self._disk_subtitle = self._add_header(view, "磁盘")

        body = self._add_chart_row(view)
        chart = AreaChart(
            body,
            [
                ("read", "读取", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL),
                ("write", "写入", theme.GRAPH_ORANGE, ""),
            ],
            max_points=60,
            min_y_max=1024 * 512,
            y_formatter=byte_axis_formatter,
            height=190,
        )
        chart.grid(row=0, column=0, sticky="nsew")
        self._charts["disk"] = chart

        self._disk_stats = StatPanel(
            body,
            (
                ("read", "读取速度"),
                ("write", "写入速度"),
                ("partitions", "分区数量"),
                ("capacity", "总容量"),
            ),
        )
        self._disk_stats.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self._disk_stats.set_swatch("read", theme.GRAPH_BLUE)
        self._disk_stats.set_swatch("write", theme.GRAPH_ORANGE)

        bottom = self._add_bottom(view)
        self._bottom_title(bottom, "磁盘分区")
        self._partition_box = tk.Frame(bottom, bg=theme.PANEL)
        self._partition_box.grid(row=2, column=0, sticky="nsew")
        return view

    # ---- 网络 ----------------------------------------------------------
    def _build_network_view(self) -> tk.Frame:
        view = self._new_view()
        self._network_subtitle = self._add_header(view, "网络")

        body = self._add_chart_row(view)
        chart = AreaChart(
            body,
            [
                ("recv", "接收", theme.GRAPH_BLUE, theme.GRAPH_BLUE_FILL),
                ("sent", "发送", theme.GRAPH_ORANGE, ""),
            ],
            max_points=60,
            min_y_max=1024 * 512,
            y_formatter=byte_axis_formatter,
            height=190,
        )
        chart.grid(row=0, column=0, sticky="nsew")
        self._charts["network"] = chart

        self._network_stats = StatPanel(
            body,
            (
                ("recv", "接收速度"),
                ("sent", "发送速度"),
                ("recv_total", "累计接收"),
                ("sent_total", "累计发送"),
                ("adapters", "网络适配器"),
            ),
        )
        self._network_stats.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self._network_stats.set_swatch("recv", theme.GRAPH_BLUE)
        self._network_stats.set_swatch("sent", theme.GRAPH_ORANGE)

        bottom = self._add_bottom(view)
        self._bottom_title(bottom, "网络适配器")
        self._adapter_box = tk.Frame(bottom, bg=theme.PANEL)
        self._adapter_box.grid(row=2, column=0, sticky="nsew")
        return view

    # ------------------------------------------------------------------ 切换
    def select(self, key: str) -> None:
        if key not in self._views:
            return
        for name, view in self._views.items():
            if name == key:
                view.grid()
            else:
                view.grid_remove()
        for name, item in self._nav_items.items():
            item.set_selected(name == key)
        self._current = key
        self._redraw_current()

    def _redraw_current(self) -> None:
        chart = self._charts.get(self._current)
        if chart is not None:
            chart.redraw()
        if self._current == "cpu":
            self._cores.redraw()

    def on_show(self) -> None:
        """页面被切换到前台时补画图表（隐藏期间跳过了重绘）。"""
        self._redraw_current()

    # ------------------------------------------------------------------ 数据
    def update(self, snapshot: Snapshot) -> None:
        self._update_nav(snapshot)
        self._update_cpu(snapshot)
        self._update_memory(snapshot)
        self._update_disk(snapshot)
        self._update_network(snapshot)

    def _update_nav(self, snapshot: Snapshot) -> None:
        freq = _freq_text(snapshot.cpu_freq_mhz)
        self._nav_items["cpu"].set_value(f"{snapshot.cpu_percent:.0f}%  {freq}")
        self._nav_items["cpu"].push(snapshot.cpu_percent)

        self._nav_items["memory"].set_value(
            f"{_gigabytes(snapshot.mem_used)}/{_gigabytes(snapshot.mem_total)}"
            f"（{snapshot.mem_percent:.0f}%）"
        )
        self._nav_items["memory"].push(snapshot.mem_percent)

        self._nav_items["disk"].set_value(
            f"读 {format_rate(snapshot.disk_read_rate)} · "
            f"写 {format_rate(snapshot.disk_write_rate)}"
        )
        self._nav_items["disk"].push(
            snapshot.disk_read_rate + snapshot.disk_write_rate
        )

        self._nav_items["network"].set_value(
            f"发送 {format_rate(snapshot.net_sent_rate)} · "
            f"接收 {format_rate(snapshot.net_recv_rate)}"
        )
        self._nav_items["network"].push(
            snapshot.net_sent_rate + snapshot.net_recv_rate
        )

    def _update_cpu(self, snapshot: Snapshot) -> None:
        freq = _freq_text(snapshot.cpu_freq_mhz)
        self._cpu_subtitle.configure(
            text=f"{self._logical_cores} 个逻辑处理器 · {freq}"
        )
        self._cpu_stats.set(
            "usage", f"{snapshot.cpu_percent:.0f}%"
        )
        self._cpu_stats.set("speed", freq)
        self._cpu_stats.set("physical", f"{self._physical_cores or '—'} 个")
        self._cpu_stats.set("logical", f"{self._logical_cores} 个")
        if snapshot.load_avg:
            load = " / ".join(f"{value:.2f}" for value in snapshot.load_avg)
        else:
            load = "—"
        self._cpu_stats.set("load", load)
        self._cpu_stats.set("uptime", format_uptime(snapshot.uptime))

        self._charts["cpu"].push({"cpu": snapshot.cpu_percent})
        self._cores.update_values(snapshot.cpu_per_core)

    def _update_memory(self, snapshot: Snapshot) -> None:
        percent = snapshot.mem_percent
        self._memory_subtitle.configure(
            text=(
                f"{_gigabytes(snapshot.mem_used)} / {_gigabytes(snapshot.mem_total)}"
                f"（{percent:.0f}%）"
            )
        )
        self._memory_stats.set(
            "used", f"{_gigabytes(snapshot.mem_used)}（{percent:.0f}%）"
        )
        self._memory_stats.set("available", _gigabytes(snapshot.mem_available))
        if snapshot.swap_total:
            self._memory_stats.set(
                "swap",
                f"{_gigabytes(snapshot.swap_used)} / {_gigabytes(snapshot.swap_total)}"
                f"（{snapshot.swap_percent:.0f}%）",
            )
        else:
            self._memory_stats.set("swap", "未启用")
        self._memory_stats.set("percent", f"{percent:.0f}%")

        self._charts["memory"].push({"memory": percent})
        used_weight = max(int(round(percent)), 1)
        self._memory_bar.grid_columnconfigure(0, weight=used_weight)
        self._memory_bar.grid_columnconfigure(1, weight=max(100 - used_weight, 1))
        self._memory_legend["used"].configure(
            text=f"使用中 {_gigabytes(snapshot.mem_used)}"
        )
        self._memory_legend["free"].configure(
            text=f"可用 {_gigabytes(snapshot.mem_available)}"
        )

    def _update_disk(self, snapshot: Snapshot) -> None:
        parts = snapshot.partitions
        read = snapshot.disk_read_rate
        write = snapshot.disk_write_rate
        self._disk_subtitle.configure(
            text=f"{len(parts)} 个分区 · 实时读取 / 写入速率"
        )
        self._disk_stats.set("read", format_rate(read))
        self._disk_stats.set("write", format_rate(write))
        self._disk_stats.set("partitions", f"{len(parts)} 个")
        total = sum(part.total for part in parts)
        used = sum(part.used for part in parts)
        self._disk_stats.set(
            "capacity",
            f"{format_bytes(used)} / {format_bytes(total)}" if total else "—",
        )
        self._charts["disk"].push({"read": read, "write": write})
        self._refresh_partitions(parts)

    def _refresh_partitions(self, parts: Sequence[PartitionUsage]) -> None:
        key = tuple(part.mountpoint for part in parts)
        if key != self._partition_key:
            self._partition_key = key
            for child in self._partition_box.winfo_children():
                child.destroy()
            self._partition_rows = []
            if not parts:
                tk.Label(
                    self._partition_box,
                    text="未检测到可访问的磁盘分区",
                    bg=theme.PANEL,
                    fg=theme.FAINT,
                    font=theme.font(9),
                ).pack(anchor="w", pady=4)
            for index, part in enumerate(parts):
                row = BarRow(self._partition_box, _partition_label(part), part.fstype)
                row.pack(fill="x", pady=(0, 3) if index < len(parts) - 1 else 0)
                self._partition_rows.append(row)

        for row, part in zip(self._partition_rows, parts):
            row.set(
                part.percent,
                f"{format_bytes(part.used)} / {format_bytes(part.total)}",
            )

    def _update_network(self, snapshot: Snapshot) -> None:
        adapters = snapshot.adapters
        up_count = sum(1 for adapter in adapters if adapter.is_up)
        self._network_subtitle.configure(
            text=f"{up_count}/{len(adapters)} 个适配器已连接"
        )
        self._network_stats.set("recv", format_rate(snapshot.net_recv_rate))
        self._network_stats.set("sent", format_rate(snapshot.net_sent_rate))
        self._network_stats.set("recv_total", format_bytes(snapshot.net_recv_total))
        self._network_stats.set("sent_total", format_bytes(snapshot.net_sent_total))
        self._network_stats.set("adapters", f"{len(adapters)} 个")

        self._charts["network"].push(
            {"recv": snapshot.net_recv_rate, "sent": snapshot.net_sent_rate}
        )
        self._refresh_adapters(snapshot)

    def _refresh_adapters(self, snapshot: Snapshot) -> None:
        key = tuple(adapter.name for adapter in snapshot.adapters)
        if key != self._adapter_key:
            self._adapter_key = key
            for child in self._adapter_box.winfo_children():
                child.destroy()
            self._adapter_rows = []
            if not snapshot.adapters:
                tk.Label(
                    self._adapter_box,
                    text="未检测到网络适配器",
                    bg=theme.PANEL,
                    fg=theme.FAINT,
                    font=theme.font(9),
                ).pack(anchor="w", pady=4)
            for adapter in snapshot.adapters:
                row = AdapterRow(self._adapter_box, adapter.name)
                row.pack(fill="x", pady=(0, 3))
                self._adapter_rows.append((row, adapter.name))

        for row, name in self._adapter_rows:
            adapter = next(
                (item for item in snapshot.adapters if item.name == name), None
            )
            if adapter is None:
                continue
            row.set(adapter.is_up, adapter.ipv4, adapter.speed_mbps)
