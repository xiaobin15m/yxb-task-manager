"""单元测试：数值格式化与采集线程。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psmon.collector import SystemCollector  # noqa: E402
from psmon.format import (  # noqa: E402
    format_axis_bytes,
    format_bytes,
    format_duration,
    format_rate,
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


class CollectorTest(unittest.TestCase):
    def test_snapshot_values(self) -> None:
        collector = SystemCollector(interval=0.3, partition_interval=0.5)
        collector.start()
        snapshot = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and snapshot is None:
            snapshot = collector.poll()
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
