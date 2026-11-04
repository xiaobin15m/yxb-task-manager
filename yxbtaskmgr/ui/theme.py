"""仿 Windows 任务管理器的浅色主题配色与字体。"""

from __future__ import annotations

import tkinter.font as tkfont
from typing import Optional

# ---- 基础颜色 ------------------------------------------------------------
BG = "#f3f3f3"            # 窗口 / 状态栏背景
PANEL = "#ffffff"         # 内容区背景
BORDER = "#e2e2e2"        # 分隔线
DIVIDER = "#dedede"
TEXT = "#1b1b1b"          # 主文本
SUBTEXT = "#5d5d5d"       # 次要文本
FAINT = "#8c8c8c"         # 坐标轴等弱化文本

ACCENT = "#0067c0"        # 选中标签下划线 / 强调色
NAV_SELECTED = "#e9f1f9"  # 左侧组件选中背景
NAV_HOVER = "#f5f5f5"
TRACK = "#e5e5e5"         # 进度条底槽

GRAPH_BACKGROUND = "#fcfcfc"
GRID = "#e8e8e8"
GRAPH_BLUE = "#0078d4"
GRAPH_BLUE_FILL = "#d9ecfb"
GRAPH_ORANGE = "#c2690a"
GRAPH_ORANGE_FILL = "#fbe7cd"
GRAPH_GREY = "#9a9a9a"
GRAPH_GREY_FILL = "#ededed"

GREEN = "#107c10"
AMBER = "#b26b00"
RED = "#c42b1c"

_FAMILY: Optional[str] = None


def font_family() -> str:
    """优先选择中文 UI 字体，保证中文与数字都接近系统原生观感。"""
    global _FAMILY
    if _FAMILY is None:
        try:
            families = set(tkfont.families())
        except Exception:
            families = set()
        for name in (
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Segoe UI",
            "PingFang SC",
            "Noto Sans CJK SC",
            "DejaVu Sans",
        ):
            if name in families:
                _FAMILY = name
                break
        else:
            _FAMILY = "Segoe UI"
    return _FAMILY


def font(size: int, weight: str = "normal") -> tuple:
    return (font_family(), size, weight)


def load_color(percent: float) -> str:
    """进度条颜色：正常为蓝色，过高时转为橙 / 红，与任务管理器的高占用提示一致。"""
    if percent >= 90:
        return RED
    if percent >= 75:
        return AMBER
    return GRAPH_BLUE
