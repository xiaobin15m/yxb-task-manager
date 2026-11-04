"""yxb的任务管理器 —— 程序入口。

运行方式：
    python main.py
"""

from yxbtaskmgr.ui.app import MonitorApp


def main() -> None:
    MonitorApp().run()


if __name__ == "__main__":
    main()
