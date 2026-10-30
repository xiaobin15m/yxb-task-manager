"""自绘界面控件：卡片、折线图、核心矩阵、进度条、分区行。

全部使用 tkinter.Canvas / Frame 绘制，不依赖第三方绘图库，
保证只需要安装 psutil 就能运行。
"""

from __future__ import annotations

import math
from collections import deque
from typing import Callable, Dict, Iterable, Optional, Sequence, Tuple

import tkinter as tk

from psmon.format import format_axis_bytes, format_bytes
from psmon.ui import theme


def _nice_ceil(value: float) -> float:
    """把纵轴上限调整到 1 / 1.5 / 2 / 2.5 / 3 / 4 / 5 / 6 / 8 * 10^n 这类整齐数值。"""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if value <= multiplier * base:
            return multiplier * base
    return 10.0 * base


class Card(tk.Frame):
    """带标题的卡片容器，内容放在 ``self.body`` 中。"""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str = "",
        accent: str = theme.ACCENT,
    ) -> None:
        super().__init__(
            master,
            bg=theme.CARD,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.BORDER,
            bd=0,
        )
        header = tk.Frame(self, bg=theme.CARD)
        header.pack(fill="x", padx=14, pady=(8, 0))
        tk.Frame(header, bg=accent, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(
            header,
            text=title,
            bg=theme.CARD,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
            anchor="w",
        ).pack(side="left")
        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                bg=theme.CARD,
                fg=theme.MUTED,
                font=theme.font(8),
                anchor="e",
            ).pack(side="right")

        self.body = tk.Frame(self, bg=theme.CARD)
        self.body.pack(fill="both", expand=True, padx=14, pady=(4, 10))


class LineChart(tk.Canvas):
    """轻量滚动折线图。

    - 数据右对齐，最新的采样点位于最右侧；
    - 纵轴可固定（如百分比 0~100）或根据数据自动取整；
    - 单条曲线带半透明填充（使用 stipple 模拟），多条曲线只画折线。
    """

    LEFT_PAD = 52
    RIGHT_PAD = 12
    TOP_PAD = 26
    BOTTOM_PAD = 16
    GRID_ROWS = 4

    def __init__(
        self,
        master: tk.Misc,
        series: Sequence[Tuple[str, str, str]],
        max_points: int = 90,
        y_max: Optional[float] = None,
        min_y_max: Optional[float] = None,
        axis_formatter: Optional[Callable[[float], str]] = None,
        height: int = 96,
        bg: str = theme.CARD,
    ) -> None:
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=height)
        self._series = [
            {"key": key, "label": label, "color": color, "points": deque(maxlen=max_points)}
            for key, label, color in series
        ]
        self._max_points = max(2, int(max_points))
        self._y_max_fixed = y_max
        self._min_y_max = min_y_max
        self._formatter = axis_formatter or (lambda value: f"{value:g}")
        self._pending = False
        self.bind("<Configure>", lambda _event: self.redraw())

    # ------------------------------------------------------------------ 数据
    def push(self, values: Dict[str, float]) -> None:
        """追加一组采样值（键为 series 中声明的 key）。"""
        for series in self._series:
            series["points"].append(float(values.get(series["key"], 0.0)))
        self._schedule_redraw()

    def reset(self) -> None:
        for series in self._series:
            series["points"].clear()
        self.redraw()

    def _schedule_redraw(self) -> None:
        if self._pending:
            return
        self._pending = True
        self.after_idle(self._redraw_pending)

    def _redraw_pending(self) -> None:
        self._pending = False
        self.redraw()

    # ------------------------------------------------------------------ 绘制
    def redraw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 120)
        height = max(self.winfo_height(), 70)
        left = self.LEFT_PAD
        right = width - self.RIGHT_PAD
        top = self.TOP_PAD
        bottom = height - self.BOTTOM_PAD
        if right - left < 40 or bottom - top < 20:
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
            y_max = _nice_ceil(max(data_max * 1.15, self._min_y_max or 1.0))

        self._draw_grid(left, right, top, bottom, y_max)
        self._draw_series(left, right, top, bottom, y_max)
        self._draw_legend()

        if not any(series["points"] for series in self._series):
            self.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text="等待采样数据…",
                fill=theme.MUTED,
                font=theme.font(8),
            )

    def _draw_grid(self, left, right, top, bottom, y_max: float) -> None:
        plot_height = bottom - top
        for index in range(self.GRID_ROWS + 1):
            y = bottom - plot_height * index / self.GRID_ROWS
            self.create_line(left, y, right, y, fill=theme.GRID)
            value = y_max * index / self.GRID_ROWS
            self.create_text(
                left - 8,
                y,
                text=self._formatter(value),
                fill=theme.MUTED,
                font=theme.font(7),
                anchor="e",
            )
        for index in range(1, 4):
            x = left + (right - left) * index / 4
            self.create_line(x, top, x, bottom, fill=theme.GRID)

    def _draw_series(self, left, right, top, bottom, y_max: float) -> None:
        plot_height = bottom - top
        step = (right - left) / (self._max_points - 1)
        single = len(self._series) == 1

        for series in self._series:
            points = list(series["points"])
            if not points:
                continue
            coords: list[float] = []
            for index, value in enumerate(points):
                x = right - (len(points) - 1 - index) * step
                ratio = min(max(value, 0.0), y_max) / y_max
                y = bottom - plot_height * ratio
                coords.extend((x, y))

            if single and len(points) > 1:
                fill_coords = coords + [coords[-2], bottom, coords[0], bottom]
                self.create_polygon(
                    fill_coords,
                    fill=series["color"],
                    stipple="gray25",
                    outline="",
                )
            if len(coords) >= 4:
                self.create_line(*coords, fill=series["color"], width=2)
            # 末端圆点：只有一个采样点时也保留一个点，避免首帧空白
            self.create_oval(
                coords[-2] - 2.5,
                coords[-1] - 2.5,
                coords[-2] + 2.5,
                coords[-1] + 2.5,
                fill=series["color"],
                outline="",
            )

    def _draw_legend(self) -> None:
        x = 8
        y = 11
        for series in self._series:
            self.create_line(x, y, x + 12, y, fill=series["color"], width=2)
            text_id = self.create_text(
                x + 16,
                y,
                text=series["label"],
                fill=theme.MUTED,
                font=theme.font(8),
                anchor="w",
            )
            box = self.bbox(text_id)
            if box:
                x = box[2] + 14


class CoreMatrix(tk.Canvas):
    """把每个逻辑核心的占用率画成一个小进度条矩阵。"""

    def __init__(self, master: tk.Misc, height: int = 84, bg: str = theme.CARD) -> None:
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=height)
        self._values: Tuple[float, ...] = ()
        self.bind("<Configure>", lambda _event: self.redraw())

    def update_values(self, values: Iterable[float]) -> None:
        self._values = tuple(float(value) for value in values)
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 80 or height < 30:
            return
        count = len(self._values)
        if count == 0:
            self.create_text(
                width / 2,
                height / 2,
                text="等待核心数据…",
                fill=theme.MUTED,
                font=theme.font(8),
            )
            return

        columns = 4 if count <= 16 else 6
        columns = min(columns, count)
        rows = math.ceil(count / columns)
        cell_width = (width - 16) / columns
        cell_height = height / rows

        for index, value in enumerate(self._values):
            row, column = divmod(index, columns)
            x0 = 8 + column * cell_width
            y0 = row * cell_height
            bar_height = max(5, min(12, cell_height * 0.35))
            bar_y0 = y0 + (cell_height - bar_height) / 2
            center_y = y0 + cell_height / 2
            bar_x0 = x0 + 15
            bar_x1 = x0 + cell_width - 36
            if bar_x1 <= bar_x0:
                continue

            self.create_text(
                x0,
                center_y,
                text=str(index),
                fill=theme.MUTED,
                font=theme.font(7),
                anchor="w",
            )
            self.create_rectangle(
                bar_x0, bar_y0, bar_x1, bar_y0 + bar_height, fill=theme.TRACK, outline=""
            )
            fill_x1 = bar_x0 + (bar_x1 - bar_x0) * min(max(value, 0.0), 100.0) / 100.0
            if fill_x1 > bar_x0:
                self.create_rectangle(
                    bar_x0,
                    bar_y0,
                    fill_x1,
                    bar_y0 + bar_height,
                    fill=theme.load_color(value),
                    outline="",
                )
            self.create_text(
                x0 + cell_width - 4,
                center_y,
                text=f"{value:.0f}%",
                fill=theme.TEXT,
                font=theme.font(7),
                anchor="e",
            )


class MeterBar(tk.Canvas):
    """单条水平进度条，颜色随占用率变化。"""

    def __init__(
        self, master: tk.Misc, height: int = 10, width: int = 100, bg: str = theme.CARD
    ) -> None:
        super().__init__(
            master, bg=bg, highlightthickness=0, bd=0, height=height, width=width
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
        fill_width = width * self._percent / 100.0
        if fill_width >= 1:
            self.create_rectangle(
                0,
                0,
                fill_width,
                height,
                fill=theme.load_color(self._percent),
                outline="",
            )


class PartitionRow(tk.Frame):
    """磁盘分区信息行：设备名 + 挂载点 + 使用条 + 百分比 + 容量。"""

    def __init__(
        self,
        master: tk.Misc,
        device: str,
        mountpoint: str,
        fstype: str,
    ) -> None:
        super().__init__(master, bg=theme.CARD)
        self.columnconfigure(2, weight=1)
        name = device.rstrip("\\/") or device
        tk.Label(
            self,
            text=name,
            width=4,
            anchor="w",
            bg=theme.CARD,
            fg=theme.TEXT,
            font=theme.font(9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            self,
            text=f"{mountpoint} · {fstype}",
            width=13,
            anchor="w",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(8),
        ).grid(row=0, column=1, sticky="w")
        self.bar = MeterBar(self, height=8)
        self.bar.grid(row=0, column=2, sticky="ew", padx=10)
        self.percent = tk.Label(
            self,
            text="0%",
            width=6,
            anchor="e",
            bg=theme.CARD,
            fg=theme.TEXT,
            font=theme.font(9, "bold"),
        )
        self.percent.grid(row=0, column=3, sticky="e")
        self.capacity = tk.Label(
            self,
            text="—",
            width=18,
            anchor="e",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=theme.font(8),
        )
        self.capacity.grid(row=0, column=4, sticky="e")

    def set(self, used: int, total: int, percent: float) -> None:
        self.bar.set(percent)
        self.percent.configure(text=f"{percent:.0f}%", fg=theme.load_color(percent))
        self.capacity.configure(text=f"{format_bytes(used)} / {format_bytes(total)}")


def byte_axis_formatter(value: float) -> str:
    """速率图纵轴刻度格式化。"""
    return format_axis_bytes(value) + "/s"
