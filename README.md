# PsMon 系统监控

基于 Python + `psutil` + `tkinter` 实现的桌面系统监控程序，实时展示 CPU、内存、网络收发速率、磁盘 IO 读写速率与磁盘分区使用率。界面为深色主题，图表由 Canvas 自绘，除 `psutil` 外不依赖任何第三方库。

![界面预览](docs/images/main-window.png)

## 功能特性

- **CPU 监控**：总体占用率、每个逻辑核心占用率、主频、物理/逻辑核心数、1/5/15 分钟系统负载，并绘制 90 个采样点的历史曲线。
- **内存监控**：物理内存占用率、已用/总容量、交换分区使用情况与历史曲线。
- **网络速率**：基于 `psutil.net_io_counters` 累计字节数差分，实时计算下载/上传速率并绘制双曲线。
- **磁盘 IO 速率**：基于 `psutil.disk_io_counters` 计算读取/写入速率并绘制双曲线。
- **磁盘分区**：展示各分区的使用率进度条、已用容量/总容量，分区信息每 10 秒刷新。
- **交互**：可切换采样间隔（0.5/1/2/5 秒）、暂停/恢复采集，窗口尺寸自适应屏幕并可自由缩放。
- **工程化**：采集线程与界面线程解耦、异常隔离、单元测试、Git 版本管理。

## 环境要求

- Python 3.9 及以上（开发验证使用 Python 3.13.13）
- Windows / Linux / macOS（`tkinter` 与 `psutil` 可用即可）
- 依赖：`psutil >= 5.9`

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动程序
python main.py
```

Windows 下也可以直接双击 `run.bat` 启动。

Linux 若提示缺少 tkinter，请安装系统包，例如 `sudo apt install python3-tk`。

## 项目结构

```
.
├── main.py                  # 程序入口
├── psmon/
│   ├── __init__.py          # 版本信息
│   ├── collector.py         # psutil 采样线程与速率计算
│   ├── format.py            # 容量/速率/时长格式化
│   └── ui/
│       ├── app.py           # 主窗口、布局与交互
│       ├── theme.py         # 深色主题配色与字体
│       └── widgets.py       # 卡片、折线图、进度条等自绘控件
├── tests/test_psmon.py      # 单元测试
├── docs/
│   ├── 系统说明文档.md       # 完整系统文档（含用户操作手册）
│   └── images/main-window.png
├── requirements.txt
├── run.bat
└── README.md
```

## 运行测试

```bash
python -m unittest discover -s tests -v
```

## 系统文档

完整的需求分析、AI 工具使用说明、技术框架、系统设计与用户操作手册见
[docs/系统说明文档.md](docs/系统说明文档.md)。

## 代码仓库

- Gitee：`https://gitee.com/<你的账号>/psmon-system-monitor`（提交前请替换为实际地址）
- GitHub：`https://github.com/<你的账号>/psmon-system-monitor`（可选镜像）

## 许可

本项目为课程实验作品，仅供学习使用。
