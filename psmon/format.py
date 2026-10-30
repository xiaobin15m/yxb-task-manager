"""数值格式化工具：字节容量、速率、时长、进程状态。"""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")

#: psutil 的进程状态代码 -> 任务管理器风格的中文描述
_PROCESS_STATUS = {
    "running": "正在运行",
    "sleeping": "已挂起",
    "disk-sleep": "磁盘等待",
    "stopped": "已停止",
    "tracing-stop": "跟踪停止",
    "zombie": "僵尸进程",
    "dead": "已结束",
    "wake-kill": "唤醒终止",
    "wakeup": "唤醒等待",
    "idle": "空闲",
    "locked": "锁定",
    "waiting": "等待",
    "suspended": "已挂起",
    "parked": "驻留",
}


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


def format_uptime(seconds: float) -> str:
    """运行时长，采用任务管理器的 ``天:时:分:秒`` 写法，例如 ``3:12:05:40``。"""
    total = int(max(0.0, float(seconds)))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}:{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours}:{minutes:02d}:{secs:02d}"


def format_process_status(status: str) -> str:
    """把 psutil 的英文进程状态转换为中文描述。"""
    if not status:
        return "未知"
    return _PROCESS_STATUS.get(status, status)
