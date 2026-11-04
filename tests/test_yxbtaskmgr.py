"""单元测试：数值格式化与采集线程。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yxbtaskmgr.collector import SystemCollector  # noqa: E402
from yxbtaskmgr.format import (  # noqa: E402
    format_axis_bytes,
    format_bytes,
    format_duration,
    format_process_status,
    format_rate,
    format_uptime,
)


class FormatTest(unittest.TestCase):
    def test_bytes_units(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1536), "1.50 KB")
        self.assertEqual(format_bytes(1024 ** 3), "1.00 GB")

    def test_rate_suffix(self) -> None:
        self.assertEqual(format_rate(0), "0 B/s")
        self.assertEqual(format_rate(1024 ** 2), "1.00 MB/s")

    def test_axis_format(self) -> None:
        self.assertEqual(format_axis_bytes(0), "0")
        self.assertEqual(format_axis_bytes(2048), "2.0K")
        self.assertEqual(format_axis_bytes(1024 ** 2 * 3), "3.0M")

    def test_duration(self) -> None:
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(95), "01:35")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_uptime(self) -> None:
        self.assertEqual(format_uptime(0), "0:00:00")
        self.assertEqual(format_uptime(3661), "1:01:01")
        self.assertEqual(format_uptime(90061), "1:01:01:01")

    def test_process_status(self) -> None:
        self.assertEqual(format_process_status("running"), "正在运行")
        self.assertEqual(format_process_status("sleeping"), "已挂起")
        self.assertEqual(format_process_status(""), "未知")
        # 未知状态原样返回，便于排查不同平台的特殊状态
        self.assertEqual(format_process_status("custom"), "custom")


class CollectorTest(unittest.TestCase):
    def test_snapshot_values(self) -> None:
        collector = SystemCollector(
            interval=0.3, partition_interval=0.5, process_interval=0.5
        )
        collector.start()
        snapshot = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            candidate = collector.poll()
            if candidate is not None and candidate.processes:
                snapshot = candidate
                break
            time.sleep(0.05)
        collector.stop()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertTrue(0.0 <= snapshot.cpu_percent <= 100.0)
        self.assertTrue(0.0 <= snapshot.mem_percent <= 100.0)
        self.assertGreater(snapshot.mem_total, 0)
        self.assertGreaterEqual(snapshot.net_recv_rate, 0.0)
        self.assertGreaterEqual(snapshot.disk_write_rate, 0.0)
        self.assertEqual(len(snapshot.cpu_per_core) >= 1, True)
        for part in snapshot.partitions:
            self.assertTrue(0.0 <= part.percent <= 100.0)

        # 新增字段：内存可用量、网络累计量、运行时长、适配器与进程列表
        self.assertGreaterEqual(snapshot.mem_available, 0)
        self.assertGreater(snapshot.net_recv_total, 0)
        self.assertGreater(snapshot.uptime, 0)
        self.assertGreaterEqual(snapshot.process_count, len(snapshot.processes))
        self.assertGreaterEqual(len(snapshot.processes), 1)
        for entry in snapshot.processes:
            self.assertGreaterEqual(entry.pid, 0)
            self.assertGreaterEqual(entry.memory_rss, 0)
            self.assertGreaterEqual(entry.cpu_percent, 0.0)
            self.assertLessEqual(entry.cpu_percent, 110.0)
        for adapter in snapshot.adapters:
            self.assertGreaterEqual(adapter.speed_mbps, 0)

    def test_pause_and_resume(self) -> None:
        collector = SystemCollector(interval=0.2)
        collector.start()
        time.sleep(0.5)
        collector.pause()
        self.assertTrue(collector.paused)
        collector.resume()
        time.sleep(0.1)
        self.assertFalse(collector.paused)
        collector.stop()
        self.assertFalse(collector.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
