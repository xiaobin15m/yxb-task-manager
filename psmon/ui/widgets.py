"""仿任务管理器的自绘控件：迷你趋势图、大图表、核心网格、统计面板等。

全部基于 tkinter.Canvas 自绘，界面风格参考 Windows 任务管理器“性能”页。
"""

from __future__ import annotations

import math
from collections import deque
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from psmon.ui import theme


def _nice_ceil(value: float) -> float:
    """把上限调整到 1 / 1.5 / 2 / 2.5 / 3 / 4 / 5 / 6 / 8 × 10ⁿ 的整齐数值。"""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if value <= multiplier * base:
            return multiplier * base
    return 10.0 * base


class Sparkline(tk.Canvas):
    """左侧组件列表中使用的小型趋势图。"""

    def __init__(
        self,
        master: tk.Misc,
        color: str = theme.GRAPH_BLUE,
        fill: str = theme.GRAPH_BLUE_FILL,
        width: int = 78,
        height: int = 30,
        max_points: int = 40,
        fixed_max: Optional[float] = None,
        min_max: float = 1.0,
        bg: str = theme.PANEL,
    ) -> None:
        super().__init__(
            master, bg=bg, width=width, height=height, highlightthickness=0, bd=0
        )
        self._color = color
        self._fill = fill
        self._values: deque = deque(maxlen=max_points)
        self._fixed_max = fixed_max
        self._min_max = min_max
        self.bind("<Configure>", lambda _event: self.redraw())

    def push(self, value: float) -> None:
        self._values.append(float(value))
        self.redraw()

    def clear(self) -> None:
        self._values.clear()
        self.redraw()

    def set_background(self, color: str) -> None:
        if self.cget("bg") != color:
            self.configure(bg=color)
            self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 10 or height < 6:
            return
        if not self._values:
            return
        top = 2
        bottom = height - 2
        span = bottom - top
        data_max = max(self._values)
        if self._fixed_max:
            y_max = self._fixed_max
        else:
            y_max = _nice_ceil(max(data_max * 1.1, self._min_max))

        step = width / (self._values.maxlen - 1)
        coords: List[float] = []
        for index, value in enumerate(self._values):
            x = width - (len(self._values) - 1 - index) * step
            ratio = min(max(value, 0.0), y_max) / y_max
            coords.extend((x, bottom - span * ratio))

        if len(coords) >= 4:
            self.create_polygon(
                coords + [coords[-2], bottom, coords[0], bottom],
                fill=self._fill,
                outline="",
            )
            self.create_line(*coords, fill=self._color, width=1)
        else:
            self.create_oval(
                coords[0] - 1,
                coords[1] - 1,
                coords[0] + 1,
                coords[1] + 1,
                fill=self._color,
                outline="",
            )


class AreaChart(tk.Canvas):
    """性能页中的大图表：白底、浅色网格、淡蓝色填充面积。"""

    LEFT_PAD = 46
    RIGHT_PAD = 10
    TOP_PAD = 10
    BOTTOM_PAD = 20
    GRID_ROWS = 4

    def __init__(
        self,
        master: tk.Misc,
        series: Sequence[Tuple[str, str, str, str]],
        max_points: int = 60,
        y_max: Optional[float] = None,
        min_y_max: Optional[float] = None,
        y_formatter: Optional[Callable[[float], str]] = None,
        height: int = 210,
    ) -> None:
        super().__init__(
            master, bg=theme.PANEL, height=height, highlightthickness=0, bd=0
        )
        self._series = [
            {
                "key": key,
                "color": color,
                "fill": fill,
                "points": deque(maxlen=max_points),
            }
            for key, _label, color, fill in series
        ]
        self._max_points = max(2, int(max_points))
        self._y_max_fixed = y_max
        self._min_y_max = min_y_max
        self._formatter = y_formatter or (lambda value: f"{value:g}")
        self._pending = False
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Map>", lambda _event: self.redraw())

    # ------------------------------------------------------------------ 数据
    def push(self, values: Dict[str, float]) -> None:
        for series in self._series:
            series["points"].append(float(values.get(series["key"], 0.0)))
        self._schedule()

    def clear(self) -> None:
        for series in self._series:
            series["points"].clear()
        self.redraw()

    def _schedule(self) -> None:
        if self._pending:
            return
        self._pending = True
        self.after_idle(self._flush)

    def _flush(self) -> None:
        self._pending = False
        self.redraw()

    # ------------------------------------------------------------------ 绘制
    def redraw(self) -> None:
        if not self.winfo_ismapped():
            # 页面不可见时不重绘，切换回来时由 <Map> / 显式调用补画
            return
        self.delete("all")
        width = max(self.winfo_width(), 150)
        height = max(self.winfo_height(), 90)
        left = self.LEFT_PAD
        right = width - self.RIGHT_PAD
        top = self.TOP_PAD
        bottom = height - self.BOTTOM_PAD
        if right - left < 40 or bottom - top < 30:
            return

        data_max = max(
            (value for series in self._series for value in series["points"]),
            default=0.0,
        )
        if self._y_max_fixed:
            y_max = float(self._y_max_fixed)
            if data_max > y_max:
                y_max = _nice_ceil(data_max)
        else:
            y_max = _nice_ceil(max(data_max * 1.1, self._min_y_max or 1.0))

        # 图表底框
        self.create_rectangle(
            left, top, right, bottom,
            fill=theme.GRAPH_BACKGROUND, outline=theme.BORDER,
        )
        self._draw_grid(left, right, top, bottom, y_max)

        empty = not any(series["points"] for series in self._series)
        if empty:
            self.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text="正在收集数据…",
                fill=theme.FAINT,
                font=theme.font(8),
            )
        else:
            self._draw_series(left, right, top, bottom, y_max)

        self.create_text(
            left, height - 8, text="60 秒", fill=theme.FAINT,
            font=theme.font(7), anchor="w",
        )
        self.create_text(
            right, height - 8, text="0", fill=theme.FAINT,
            font=theme.font(7), anchor="e",
        )

    def _draw_grid(self, left, right, top, bottom, y_max: float) -> None:
        span = bottom - top
        for index in range(self.GRID_ROWS + 1):
            y = bottom - span * index / self.GRID_ROWS
            self.create_line(left + 1, y, right - 1, y, fill=theme.GRID)
            self.create_text(
                left - 7,
                y,
                text=self._formatter(y_max * index / self.GRID_ROWS),
                fill=theme.FAINT,
                font=theme.font(7),
                anchor="e",
            )
        for index in range(1, 6):
            x = left + (right - left) * index / 6
            self.create_line(x, top + 1, x, bottom - 1, fill=theme.GRID)

    def _draw_series(self, left, right, top, bottom, y_max: float) -> None:
        span = bottom - top
        step = (right - left - 2) / (self._max_points - 1)
        for order, series in enumerate(self._series):
            points = list(series["points"])
            if not points:
                continue
            coords: List[float] = []
            for index, value in enumerate(points):
                x = right - 1 - (len(points) - 1 - index) * step
                ratio = min(max(value, 0.0), y_max) / y_max
                coords.extend((x, bottom - 1 - span * ratio))

            if order == 0 and len(coords) >= 4:
                # 主曲线绘制浅色填充，模拟任务管理器的面积图
                self.create_polygon(
                    coords + [coords[-2], bottom - 1, coords[0], bottom - 1],
                    fill=series["fill"],
                    outline="",
                )

            if len(coords) >= 4:
                self.create_line(*coords, fill=series["color"], width=2)
            else:
                self.create_oval(
                    coords[0] - 2,
                    coords[1] - 2,
                    coords[0] + 2,
                    coords[1] + 2,
                    fill=series["color"],
                    outline="",
                )


class CoreGrid(tk.Canvas):
    """CPU 详情页底部的“每个 CPU 的利用率”小图表矩阵。"""

    def __init__(self, master: tk.Misc, max_points: int = 20, height: int = 120) -> None:
        super().__init__(
            master,
            bg=theme.PANEL,
            height=height,
            highlightthickness=0,
            bd=0,
        )
        self._histories: List[deque] = []
        self._max_points = max_points
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Map>", lambda _event: self.redraw())

    def update_values(self, values: Iterable[float]) -> None:
        values = list(values)
        if len(values) != len(self._histories):
            self._histories = [deque(maxlen=self._max_points) for _ in values]
        for history, value in zip(self._histories, values):
            history.append(float(value))
        self.redraw()

    def redraw(self) -> None:
        if not self.winfo_ismapped():
            return
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        count = len(self._histories)
        if width < 60 or height < 30 or count == 0:
            return

        columns = 8 if width >= 640 else 4
        columns = min(columns, count)
        rows = math.ceil(count / columns)
        cell_width = width / columns
        cell_height = height / rows

        for index, history in enumerate(self._histories):
            row, column = divmod(index, columns)
            x0 = column * cell_width
            y0 = row * cell_height
            self.create_text(
                x0 + 4,
                y0 + 8,
                text=f"CPU {index}",
                fill=theme.FAINT,
                font=theme.font(7),
                anchor="w",
            )
            plot_left = x0 + 4
            plot_right = x0 + cell_width - 4
            plot_top = y0 + 15
            plot_bottom = y0 + cell_height - 4
            if plot_right - plot_left < 12 or plot_bottom - plot_top < 8:
                continue
            self.create_rectangle(
                plot_left,
                plot_top,
                plot_right,
                plot_bottom,
                fill=theme.GRAPH_BACKGROUND,
                outline=theme.BORDER,
            )
            if not history:
                continue
            span = plot_bottom - plot_top - 2
            step = (plot_right - plot_left - 2) / (self._max_points - 1)
            coords: List[float] = []
            for position, value in enumerate(history):
                x = plot_right - 1 - (len(history) - 1 - position) * step
                ratio = min(max(value, 0.0), 100.0) / 100.0
                coords.extend((x, plot_bottom - 1 - span * ratio))
            if len(coords) >= 4:
                self.create_polygon(
                    coords + [coords[-2], plot_bottom - 1, coords[0], plot_bottom - 1],
                    fill=theme.GRAPH_BLUE_FILL,
                    outline="",
                )
                self.create_line(*coords, fill=theme.GRAPH_BLUE, width=1)
            else:
                self.create_oval(
                    coords[0] - 1,
                    coords[1] - 1,
                    coords[0] + 1,
                    coords[1] + 1,
                    fill=theme.GRAPH_BLUE,
                    outline="",
                )


class StatPanel(tk.Frame):
    """性能页右侧的统计信息列（标签在上、数值在下）。"""

    def __init__(
        self,
        master: tk.Misc,
        rows: Sequence[Tuple[str, str]],
        width: int = 206,
    ) -> None:
        super().__init__(master, bg=theme.PANEL, width=width)
        self.pack_propagate(False)
        self._values: Dict[str, tk.Label] = {}
        self._swatches: Dict[str, Tuple[tk.Frame, tk.Label]] = {}
        for key, label in rows:
            block = tk.Frame(self, bg=theme.PANEL)
            block.pack(fill="x", pady=(0, 7))
            head = tk.Frame(block, bg=theme.PANEL)
            head.pack(fill="x")
            text = tk.Label(
                head,
                text=label,
                bg=theme.PANEL,
                fg=theme.SUBTEXT,
                font=theme.font(8),
                anchor="w",
                bd=0,
                padx=0,
                pady=0,
                highlightthickness=0,
            )
            text.pack(side="left")
            value = tk.Label(
                block,
                text="—",
                bg=theme.PANEL,
                fg=theme.TEXT,
                font=theme.font(9, "bold"),
                anchor="w",
                bd=0,
                padx=0,
                pady=0,
                highlightthickness=0,
            )
            value.pack(fill="x")
            self._values[key] = value
            self._swatches[key] = (head, text)

    def set(self, key: str, text: str, color: Optional[str] = None) -> None:
        label = self._values[key]
        label.configure(text=text, fg=color or theme.TEXT)

    def set_swatch(self, key: str, color: Optional[str]) -> None:
        """在标签前显示 / 隐藏颜色方块，用于区分读取与写入、发送与接收。"""
        head, text = self._swatches[key]
        square = getattr(head, "_swatch", None)
        if color is None:
            if square is not None:
                square.pack_forget()
            return
        if square is None:
            square = tk.Frame(head, width=9, height=9, bg=color)
            head._swatch = square  # type: ignore[attr-defined]
        square.configure(bg=color)
        square.pack(side="left", padx=(0, 6), before=text)
        square.pack_propagate(False)


class NavItem(tk.Frame):
    """性能页左侧的可选组件项：名称、实时数值、迷你趋势图。"""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        on_click: Callable[[], None],
        color: str = theme.GRAPH_BLUE,
        fill: str = theme.GRAPH_BLUE_FILL,
        fixed_max: Optional[float] = None,
        min_max: float = 1.0,
        spark_width: int = 72,
    ) -> None:
        super().__init__(master, bg=theme.PANEL, cursor="hand2")
        self._on_click = on_click
        self._selected = False

        self._bar = tk.Frame(self, width=3, bg=theme.PANEL)
        self._bar.pack(side="left", fill="y")
        self._container = tk.Frame(self, bg=theme.PANEL)
        self._container.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=7)

        self._text = tk.Frame(self._container, bg=theme.PANEL)
        self._text.pack(side="left", fill="y")
        self._title = tk.Label(
            self._text,
            text=title,
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(10),
            anchor="w",
        )
        self._title.pack(anchor="w")
        self._value = tk.Label(
            self._text,
            text="—",
            bg=theme.PANEL,
            fg=theme.SUBTEXT,
            font=theme.font(8),
            anchor="w",
        )
        self._value.pack(anchor="w", pady=(2, 0))

        self._spark = Sparkline(
            self._container,
            color=color,
            fill=fill,
            fixed_max=fixed_max,
            min_max=min_max,
            width=spark_width,
        )
        self._spark.pack(side="right")

        for widget in (self, self._bar, self._container, self._text, self._title,
                       self._value, self._spark):
            widget.bind("<Button-1>", self._handle_click)
            widget.bind("<Enter>", self._handle_enter)
            widget.bind("<Leave>", self._handle_leave)

    # ------------------------------------------------------------------ 交互
    def _handle_click(self, _event: tk.Event) -> None:
        self._on_click()

    def _handle_enter(self, _event: tk.Event) -> None:
        if not self._selected:
            self._paint(theme.NAV_HOVER)

    def _handle_leave(self, _event: tk.Event) -> None:
        if not self._selected:
            self._paint(theme.PANEL)

    def _paint(self, background: str) -> None:
        for widget in (self, self._container, self._text):
            widget.configure(bg=background)
        self._title.configure(bg=background)
        self._value.configure(bg=background)
        self._spark.set_background(background)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._paint(theme.NAV_SELECTED if selected else theme.PANEL)
        self._bar.configure(bg=theme.ACCENT if selected else theme.PANEL)

    # ------------------------------------------------------------------ 数据
    def set_value(self, text: str) -> None:
        self._value.configure(text=text)

    def push(self, value: float) -> None:
        self._spark.push(value)


class MeterBar(tk.Canvas):
    """细长的使用率进度条。"""

    def __init__(self, master: tk.Misc, height: int = 6, bg: str = theme.PANEL) -> None:
        super().__init__(
            master, bg=bg, height=height, highlightthickness=0, bd=0, width=80
        )
        self._percent = 0.0
        self.bind("<Configure>", lambda _event: self.redraw())

    def set(self, percent: float) -> None:
        self._percent = max(0.0, min(100.0, float(percent)))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 4:
            return
        self.create_rectangle(0, 0, width, height, fill=theme.TRACK, outline="")
        filled = width * self._percent / 100.0
        if filled >= 1:
            self.create_rectangle(
                0, 0, filled, height, fill=theme.load_color(self._percent), outline=""
            )


class BarRow(tk.Frame):
    """磁盘分区行：盘符、文件系统、使用率条、百分比与容量。"""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str = "",
    ) -> None:
        super().__init__(master, bg=theme.PANEL)
        self.columnconfigure(2, weight=1)
        self._title = tk.Label(
            self,
            text=title,
            width=5,
            anchor="w",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(9, "bold"),
        )
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = tk.Label(
            self,
            text=subtitle,
            width=8,
            anchor="w",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(8),
        )
        self._subtitle.grid(row=0, column=1, sticky="w")
        self._bar = MeterBar(self)
        self._bar.grid(row=0, column=2, sticky="ew", padx=10)
        self._percent = tk.Label(
            self,
            text="0%",
            width=5,
            anchor="e",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(9),
        )
        self._percent.grid(row=0, column=3, sticky="e")
        self._detail = tk.Label(
            self,
            text="—",
            width=20,
            anchor="e",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(8),
        )
        self._detail.grid(row=0, column=4, sticky="e")

    def set(self, percent: float, detail: str) -> None:
        self._bar.set(percent)
        self._percent.configure(text=f"{percent:.0f}%")
        self._detail.configure(text=detail)


class AdapterRow(tk.Frame):
    """网络适配器行：状态、名称、IPv4 地址与连接速度。"""

    def __init__(self, master: tk.Misc, name: str) -> None:
        super().__init__(master, bg=theme.PANEL)
        self.columnconfigure(1, weight=1)
        self._dot = tk.Label(
            self, text="●", bg=theme.PANEL, fg=theme.GREEN, font=theme.font(8)
        )
        self._dot.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._name = tk.Label(
            self,
            text=name,
            anchor="w",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.font(9),
        )
        self._name.grid(row=0, column=1, sticky="w")
        self._ip = tk.Label(
            self,
            text="—",
            width=16,
            anchor="w",
            bg=theme.PANEL,
            fg=theme.FAINT,
            font=theme.font(8),
        )
        self._ip.grid(row=0, column=2, sticky="w")
        self._speed = tk.Label(
            self,
            text="—",
            width=14,
            anchor="e",
            bg=theme.PANEL,
            fg=theme.SUBTEXT,
            font=theme.font(8),
        )
        self._speed.grid(row=0, column=3, sticky="e")

    def set(self, is_up: bool, ipv4: str, speed_mbps: int) -> None:
        self._dot.configure(fg=theme.GREEN if is_up else theme.FAINT)
        self._ip.configure(text=ipv4 or "—")
        self._speed.configure(
            text=(f"{speed_mbps / 1000:.0f} Gbps" if speed_mbps >= 1000
                  else f"{speed_mbps} Mbps") if speed_mbps else "—"
        )
        self._name.configure(fg=theme.TEXT if is_up else theme.FAINT)


class ProcessTable(tk.Frame):
    """任务管理器样式的进程表格（ttk.Treeview 封装，支持列排序）。"""

    def __init__(
        self,
        master: tk.Misc,
        columns: Sequence[Tuple[str, str, int, str]],
        on_sort: Callable[[str], None],
        height: int = 20,
    ) -> None:
        super().__init__(master, bg=theme.PANEL)
        keys = [column[0] for column in columns]
        self.tree = ttk.Treeview(
            self,
            columns=keys,
            show="headings",
            style="TM.Treeview",
            selectmode="browse",
            height=height,
        )
        for key, title, width, anchor in columns:
            self.tree.heading(
                key,
                text=title,
                anchor=anchor,
                command=lambda k=key: on_sort(k),
            )
            self.tree.column(
                key,
                width=width,
                minwidth=60,
                anchor=anchor,
                stretch=(key == "name"),
            )

        scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.tree.yview,
            style="TM.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def set_rows(self, rows: Sequence[Tuple[str, Tuple[str, ...]]]) -> None:
        """使用进程 PID 作为 iid，增量更新以减少闪烁。"""
        incoming = [row[0] for row in rows]
        existing = set(self.tree.get_children())

        for iid, values in rows:
            if iid in existing:
                if self.tree.item(iid, "values") != tuple(values):
                    self.tree.item(iid, values=values)
            else:
                self.tree.insert("", "end", iid=iid, values=values)

        for iid in existing - set(incoming):
            self.tree.delete(iid)

        if list(self.tree.get_children()) != incoming:
            for index, iid in enumerate(incoming):
                self.tree.move(iid, "", index)


def byte_axis_formatter(value: float) -> str:
    """速率纵轴的紧凑刻度，例如 2.0M/s。"""
    if value <= 0:
        return "0"
    units = ("B", "KB", "MB", "GB", "TB")
    number = float(value)
    index = 0
    while number >= 1024.0 and index < len(units) - 1:
        number /= 1024.0
        index += 1
    if index == 0:
        text = f"{number:.0f}"
    elif number < 10:
        text = f"{number:.1f}"
    else:
        text = f"{number:.0f}"
    return f"{text}{units[index][0]}/s"


def format_percent_axis(value: float) -> str:
    return f"{value:.0f}%"
