"""后台采样：主采样线程负责 CPU / 内存 / 网络 / 磁盘，进程列表由独立线程采集。

设计要点：
1. 采集放在守护线程中，避免 psutil 的阻塞调用卡住 Tkinter 主线程；
2. 网络与磁盘 IO 使用 psutil 的累计字节计数器，通过两次采样的差值除以
   时间间隔得到速率；``nowrap=True`` 让计数器在溢出时自动修正；
3. 采集结果通过容量为 2 的队列交给界面线程，界面只取最新数据，避免堆积；
4. 磁盘分区、网络适配器变化缓慢，默认每 10 秒刷新一次；
5. 遍历进程列表时读取名称 / 状态在每个进程上都有额外开销（实测 240 个进程
   约 1.7 秒），因此单独放在 ``ProcessSampler`` 线程中：名称按 PID 缓存、
   只对将要展示的前 N 个进程读取状态，主采样节奏不会被打断。
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)

__all__ = [
    "NetAdapter",
    "PartitionUsage",
    "ProcessEntry",
    "ProcessSampler",
    "Snapshot",
    "SystemCollector",
]


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
class NetAdapter:
    """单个网络适配器的状态。"""

    name: str
    is_up: bool
    speed_mbps: int
    ipv4: str


@dataclass(frozen=True)
class ProcessEntry:
    """进程列表中的一行。"""

    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_rss: int


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
    mem_available: int
    swap_percent: float
    swap_used: int
    swap_total: int
    net_recv_rate: float
    net_sent_rate: float
    net_recv_total: int
    net_sent_total: int
    disk_read_rate: float
    disk_write_rate: float
    partitions: Tuple[PartitionUsage, ...]
    adapters: Tuple[NetAdapter, ...]
    uptime: float
    process_count: int
    processes: Tuple[ProcessEntry, ...]


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


def _read_uptime() -> float:
    """系统运行时长（秒）。"""
    try:
        return max(0.0, time.time() - psutil.boot_time())
    except (AttributeError, OSError):
        return 0.0


def _read_adapters() -> Tuple[NetAdapter, ...]:
    """读取网络适配器的连接状态、IPv4 地址与链路速度。"""
    try:
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
    except (OSError, RuntimeError):
        return ()

    result = []
    for name, stat in stats.items():
        if name.lower().startswith("loopback"):
            continue
        ipv4 = ""
        for address in addresses.get(name, ()):
            if address.family == socket.AF_INET:
                ipv4 = address.address
                break
        result.append(
            NetAdapter(
                name=name,
                is_up=bool(getattr(stat, "isup", False)),
                speed_mbps=int(getattr(stat, "speed", 0) or 0),
                ipv4=ipv4,
            )
        )
    # 已连接的适配器排在前面，便于在界面上优先展示
    result.sort(key=lambda adapter: (not adapter.is_up, adapter.name.lower()))
    return tuple(result)


class ProcessSampler(threading.Thread):
    """独立线程维护进程列表缓存。

    psutil 的进程名称、状态读取在 Windows 上单次耗时约数毫秒，遍历全部进程
    需要 1 秒以上。为避免影响主采样节奏，这里：
    * 只按 CPU / 内存排序，名称按 PID 缓存（同一 PID 的名称不会变化）；
    * 仅为最终展示的前 ``limit`` 个进程读取状态。
    """

    def __init__(
        self,
        stop_event: threading.Event,
        paused_event: threading.Event,
        interval: float = 3.0,
        limit: int = 80,
    ) -> None:
        super().__init__(name="yxbtaskmgr-processes", daemon=True)
        self._stop_event = stop_event
        self._paused_event = paused_event
        self._interval = max(0.5, float(interval))
        self._limit = max(10, int(limit))
        self._cpu_count = max(1, psutil.cpu_count() or 1)
        self._lock = threading.Lock()
        self._entries: Tuple[ProcessEntry, ...] = ()
        self._count = 0
        self._names: Dict[int, str] = {}

    def latest(self) -> Tuple[Tuple[ProcessEntry, ...], int]:
        """返回 (进程列表, 进程总数) 的最新缓存。"""
        with self._lock:
            return self._entries, self._count

    # ------------------------------------------------------------------ 线程主体
    def run(self) -> None:
        while not self._stop_event.is_set():
            if not self._paused_event.is_set():
                try:
                    self._scan()
                except Exception:  # 进程扫描失败不应终止线程
                    logger.exception("采集进程列表失败")
            self._stop_event.wait(self._interval)

    def _scan(self) -> None:
        samples: List[Tuple[float, int, int]] = []
        for proc in psutil.process_iter(["pid", "cpu_percent", "memory_info"]):
            info = proc.info
            pid = info.get("pid")
            if not isinstance(pid, int) or pid < 0:
                continue
            if pid not in self._names:
                self._names[pid] = self._name_of(proc, pid)
            memory = info.get("memory_info")
            samples.append(
                (
                    float(info.get("cpu_percent") or 0.0) / self._cpu_count,
                    int(getattr(memory, "rss", 0) or 0),
                    pid,
                )
            )

        # 清理已退出进程的名称缓存，避免 PID 复用时显示旧名称
        valid = {sample[2] for sample in samples}
        for pid in [key for key in self._names if key not in valid]:
            self._names.pop(pid, None)

        samples.sort(reverse=True)
        entries = tuple(
            ProcessEntry(
                pid=pid,
                name=self._names.get(pid, f"进程 {pid}"),
                status=self._status_of(pid),
                cpu_percent=cpu,
                memory_rss=rss,
            )
            for cpu, rss, pid in samples[: self._limit]
        )

        with self._lock:
            self._entries = entries
            self._count = len(samples)

    @staticmethod
    def _name_of(proc: "psutil.Process", pid: int) -> str:
        try:
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            name = ""
        return name or f"进程 {pid}"

    @staticmethod
    def _status_of(pid: int) -> str:
        try:
            return psutil.Process(pid).status()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            return "unknown"


class SystemCollector(threading.Thread):
    """周期采样线程。"""

    def __init__(
        self,
        interval: float = 1.0,
        partition_interval: float = 10.0,
        adapter_interval: float = 10.0,
        process_interval: float = 3.0,
        process_limit: int = 80,
    ) -> None:
        super().__init__(name="yxbtaskmgr-collector", daemon=True)
        self._interval = max(0.2, float(interval))
        self._partition_interval = max(self._interval, float(partition_interval))
        self._adapter_interval = max(self._interval, float(adapter_interval))
        self._stop_event = threading.Event()
        self._paused_event = threading.Event()
        self._reschedule = threading.Event()
        self._queue: "queue.Queue[Snapshot]" = queue.Queue(maxsize=2)
        self._sampler = ProcessSampler(
            self._stop_event,
            self._paused_event,
            interval=process_interval,
            limit=process_limit,
        )

        self._samples = 0
        self._last_net: Optional[object] = None
        self._last_disk: Optional[object] = None
        self._last_ts = time.monotonic()
        self._partitions: Tuple[PartitionUsage, ...] = ()
        self._last_partition_ts = 0.0
        self._adapters: Tuple[NetAdapter, ...] = ()
        self._last_adapter_ts = 0.0

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
        self._sampler.join(timeout=2.0)

    def poll(self) -> Optional[Snapshot]:
        """取回最新快照，没有新数据时返回 None。"""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------------ 线程主体
    def run(self) -> None:
        self._reset_baseline()
        self._sampler.start()
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

        if (not self._adapters) or (now - self._last_adapter_ts >= self._adapter_interval):
            self._adapters = _read_adapters()
            self._last_adapter_ts = now

        processes, process_count = self._sampler.latest()

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
            mem_available=getattr(memory, "available", max(0, memory.total - memory.used)),
            swap_percent=swap.percent,
            swap_used=swap.used,
            swap_total=swap.total,
            net_recv_rate=net_recv,
            net_sent_rate=net_sent,
            net_recv_total=int(getattr(net, "bytes_recv", 0) or 0),
            net_sent_total=int(getattr(net, "bytes_sent", 0) or 0),
            disk_read_rate=disk_read,
            disk_write_rate=disk_write,
            partitions=self._partitions,
            adapters=self._adapters,
            uptime=_read_uptime(),
            process_count=process_count,
            processes=processes,
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
