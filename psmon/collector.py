"""后台采样线程：使用 psutil 周期性采集系统指标，并计算网络 / 磁盘 IO 速率。

设计要点：
1. 采集放在独立守护线程中，避免 psutil 的阻塞调用卡住 Tkinter 主线程；
2. 网络与磁盘 IO 使用 psutil 的累计字节计数器，通过两次采样的差值除以
   时间间隔得到速率；``nowrap=True`` 让计数器在溢出时自动修正；
3. 采集结果通过容量为 2 的队列交给界面线程，界面只取最新数据，避免堆积；
4. 磁盘分区容量变化缓慢，默认每 10 秒刷新一次，磁盘列表为空时立即读取。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import psutil

logger = logging.getLogger(__name__)

__all__ = ["PartitionUsage", "Snapshot", "SystemCollector"]


@dataclass(frozen=True)
class PartitionUsage:
    """单个磁盘分区的使用情况。"""

    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    percent: float


@dataclass(frozen=True)
class Snapshot:
    """一次采样的完整结果，供界面渲染使用。"""

    timestamp: float
    cpu_percent: float
    cpu_per_core: Tuple[float, ...]
    cpu_freq_mhz: Optional[float]
    load_avg: Optional[Tuple[float, float, float]]
    mem_percent: float
    mem_used: int
    mem_total: int
    swap_percent: float
    swap_used: int
    swap_total: int
    net_recv_rate: float
    net_sent_rate: float
    disk_read_rate: float
    disk_write_rate: float
    partitions: Tuple[PartitionUsage, ...]


def _rate(current: Optional[int], previous: Optional[int], elapsed: float) -> float:
    """由累计计数器差值计算每秒速率。"""
    if current is None or previous is None or elapsed <= 0:
        return 0.0
    delta = current - previous
    if delta <= 0:
        return 0.0
    return delta / elapsed


def _read_partitions() -> Tuple[PartitionUsage, ...]:
    """读取所有可访问磁盘分区的容量信息，跳过无权限的挂载点。"""
    result = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            # 光驱空介质、网络盘或权限不足时会抛异常，直接忽略该分区
            continue
        result.append(
            PartitionUsage(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype or "unknown",
                total=usage.total,
                used=usage.used,
                percent=usage.percent,
            )
        )
    return tuple(result)


def _read_cpu_freq() -> Optional[float]:
    try:
        return float(psutil.cpu_freq().current)
    except (NotImplementedError, AttributeError, OSError):
        return None


def _read_load_avg() -> Optional[Tuple[float, float, float]]:
    try:
        return tuple(psutil.getloadavg())  # type: ignore[return-value]
    except (AttributeError, NotImplementedError, OSError):
        return None


class SystemCollector(threading.Thread):
    """周期采样线程。"""

    def __init__(self, interval: float = 1.0, partition_interval: float = 10.0) -> None:
        super().__init__(name="psmon-collector", daemon=True)
        self._interval = max(0.2, float(interval))
        self._partition_interval = max(self._interval, float(partition_interval))
        self._stop_event = threading.Event()
        self._paused_event = threading.Event()
        self._reschedule = threading.Event()
        self._queue: "queue.Queue[Snapshot]" = queue.Queue(maxsize=2)

        self._samples = 0
        self._last_net: Optional[object] = None
        self._last_disk: Optional[object] = None
        self._last_ts = time.monotonic()
        self._partitions: Tuple[PartitionUsage, ...] = ()
        self._last_partition_ts = 0.0

        # 预热：psutil 的 cpu_percent(interval=None) 首次调用没有参照点，会返回 0.0，
        # 先调用一次可以让第一次真实采样就得到有效数值。
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    # ------------------------------------------------------------------ 属性
    @property
    def interval(self) -> float:
        return self._interval

    @property
    def samples(self) -> int:
        return self._samples

    @property
    def paused(self) -> bool:
        return self._paused_event.is_set()

    # ------------------------------------------------------------------ 控制
    def set_interval(self, interval: float) -> None:
        """调整采样间隔（秒），并在下一次循环立即生效。"""
        self._interval = max(0.2, float(interval))
        self._reschedule.set()

    def pause(self) -> None:
        self._paused_event.set()

    def resume(self) -> None:
        self._paused_event.clear()
        self._reschedule.set()

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=2.0)

    def poll(self) -> Optional[Snapshot]:
        """取回最新快照，没有新数据时返回 None。"""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------------ 线程主体
    def run(self) -> None:
        self._reset_baseline()
        deadline = time.monotonic() + self._interval
        while not self._stop_event.is_set():
            if self._sleep_until(deadline):
                break
            if self._paused_event.is_set():
                # 暂停期间不采样，重置基线，恢复后速率不会出现尖峰
                self._reset_baseline()
                deadline = time.monotonic() + self._interval
                continue
            try:
                snapshot = self._collect()
            except Exception:  # 采集异常不应终止监控线程
                logger.exception("采集系统指标失败")
                snapshot = None
            if snapshot is not None:
                self._push(snapshot)
            deadline = time.monotonic() + self._interval

    def _sleep_until(self, deadline: float) -> bool:
        """等待到 deadline；返回 True 表示收到停止信号。"""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._stop_event.wait(min(remaining, 0.2)):
                return True
            if self._reschedule.is_set():
                self._reschedule.clear()
                return False

    def _reset_baseline(self) -> None:
        try:
            self._last_net = psutil.net_io_counters(nowrap=True)
            self._last_disk = psutil.disk_io_counters(nowrap=True)
        except (RuntimeError, OSError):
            logger.debug("读取 IO 计数器失败", exc_info=True)
            self._last_net = None
            self._last_disk = None
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self._last_ts = time.monotonic()

    def _collect(self) -> Snapshot:
        now = time.monotonic()
        elapsed = max(1e-3, now - self._last_ts)
        self._last_ts = now

        cpu = psutil.cpu_percent(interval=None)
        cores = tuple(psutil.cpu_percent(interval=None, percpu=True))
        freq = _read_cpu_freq()
        load = _read_load_avg()

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        net = psutil.net_io_counters(nowrap=True)
        disk = psutil.disk_io_counters(nowrap=True)

        net_recv = _rate(
            getattr(net, "bytes_recv", None),
            getattr(self._last_net, "bytes_recv", None),
            elapsed,
        )
        net_sent = _rate(
            getattr(net, "bytes_sent", None),
            getattr(self._last_net, "bytes_sent", None),
            elapsed,
        )
        disk_read = _rate(
            getattr(disk, "read_bytes", None),
            getattr(self._last_disk, "read_bytes", None),
            elapsed,
        )
        disk_write = _rate(
            getattr(disk, "write_bytes", None),
            getattr(self._last_disk, "write_bytes", None),
            elapsed,
        )
        self._last_net = net
        self._last_disk = disk

        if (not self._partitions) or (now - self._last_partition_ts >= self._partition_interval):
            self._partitions = _read_partitions()
            self._last_partition_ts = now

        self._samples += 1
        return Snapshot(
            timestamp=time.time(),
            cpu_percent=cpu,
            cpu_per_core=cores,
            cpu_freq_mhz=freq,
            load_avg=load,
            mem_percent=memory.percent,
            mem_used=memory.used,
            mem_total=memory.total,
            swap_percent=swap.percent,
            swap_used=swap.used,
            swap_total=swap.total,
            net_recv_rate=net_recv,
            net_sent_rate=net_sent,
            disk_read_rate=disk_read,
            disk_write_rate=disk_write,
            partitions=self._partitions,
        )

    def _push(self, snapshot: Snapshot) -> None:
        try:
            self._queue.put_nowait(snapshot)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(snapshot)
            except queue.Full:
                pass
