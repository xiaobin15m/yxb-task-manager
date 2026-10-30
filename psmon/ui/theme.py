"""统一的深色主题配色与字体工具。"""

from __future__ import annotations

import tkinter.font as tkfont
from typing import Optional

# ---- 颜色 ----------------------------------------------------------------
BG = "#0e1319"          # 窗口背景
CARD = "#161d26"        # 卡片背景
BORDER = "#243040"      # 卡片描边
GRID = "#243040"        # 图表网格
TRACK = "#1f2833"       # 进度条底槽
TEXT = "#e8eef5"        # 主文本
MUTED = "#8296ab"       # 次要文本

ACCENT = "#38bdf8"      # CPU / 主强调色
GREEN = "#34d399"       # 网络下载
AMBER = "#fbbf24"       # 网络上传 / 警告
RED = "#f87171"         # 危险
PURPLE = "#c084fc"      # 内存
PINK = "#f472b6"        # 磁盘读取
BLUE = "#60a5fa"        # 磁盘写入

_FAMILY: Optional[str] = None


def font_family() -> str:
    """挑选一个当前系统可用的中文字体，只探测一次。"""
    global _FAMILY
    if _FAMILY is None:
        try:
            families = set(tkfont.families())
        except Exception:  # 尚未创建 Tk 根窗口时可能失败
            families = set()
        for name in (
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "PingFang SC",
            "Noto Sans CJK SC",
            "Segoe UI",
            "DejaVu Sans",
        ):
            if name in families:
                _FAMILY = name
                break
        else:
            _FAMILY = "Segoe UI"
    return _FAMILY


def font(size: int, weight: str = "normal") -> tuple:
    """构造字体元组，供 tk 控件使用。"""
    return (font_family(), size, weight)


def load_color(percent: float) -> str:
    """按占用率返回绿 / 黄 / 红三档颜色。"""
    if percent >= 85:
        return RED
    if percent >= 65:
        return AMBER
    return GREEN
