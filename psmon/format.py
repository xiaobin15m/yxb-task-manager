"""数值格式化工具：字节容量、速率、时长。"""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(num: float, per_second: bool = False) -> str:
    """把字节数格式化为带单位的可读字符串，例如 ``1536`` -> ``1.50 KB``。"""
    if num is None:
        return "—"
    sign = "-" if num < 0 else ""
    value = abs(float(num))
    index = 0
    while value >= 1024.0 and index < len(_UNITS) - 1:
        value /= 1024.0
        index += 1

    if index == 0:
        text = f"{value:.0f}"
    elif value < 10:
        text = f"{value:.2f}"
    elif value < 100:
        text = f"{value:.1f}"
    else:
        text = f"{value:.0f}"
    unit = _UNITS[index] + ("/s" if per_second else "")
    return f"{sign}{text} {unit}"


def format_rate(num: float) -> str:
    """把每秒字节数格式化为速率字符串，例如 ``1.50 MB/s``。"""
    return format_bytes(num, per_second=True)


def format_axis_bytes(num: float) -> str:
    """图表纵轴刻度使用的紧凑字节格式，例如 ``2.5M``。"""
    if num is None or num <= 0:
        return "0"
    value = float(num)
    index = 0
    while value >= 1024.0 and index < len(_UNITS) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{value:.0f}"
    if value < 10:
        return f"{value:.1f}{_UNITS[index][0]}"
    return f"{value:.0f}{_UNITS[index][0]}"


def format_duration(seconds: float) -> str:
    """把秒数格式化为 ``MM:SS`` 或 ``HH:MM:SS``。"""
    total = int(max(0.0, float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
