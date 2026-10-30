"""PsMon 系统监控 —— 程序入口。

运行方式：
    python main.py
"""

from psmon.ui.app import MonitorApp


def main() -> None:
    MonitorApp().run()


if __name__ == "__main__":
    main()
