"""程序主入口模块。

职责：
1. 集成 Sentry 错误监控。
2. 解析命令行参数。
3. 加载配置文件并初始化日志系统。
4. 启动 GUI 界面（警告弹窗、滚动条）。
5. 在后台线程中运行自动化逻辑。
"""

from __future__ import annotations

import ctypes
import os
import sys
import signal
from argparse import ArgumentParser
from pathlib import Path

# 防止 Noconsole 模式下 argparse 报错崩溃 (AttributeError: 'NoneType' object has no attribute 'write')
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# 设置 Qt 平台环境变量，确保高 DPI 支持
os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=1"

import sentry_sdk
from loguru import logger
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

from automator import C30ImageAutomator
from config import DEFAULT_CONFIG_PATH, load_config
from logger_setup import init_logger
from ui_components import ScrollingBanner, WarningDialog

# 版本号 (CI构建时会自动替换此值)
__version__ = "v0.0.0-dev"

def _build_parser() -> ArgumentParser:
    """构建并配置命令行参数解析器。"""
    parser = ArgumentParser(
        prog="C30Auto-login",
        description="C30 智能教学自动登录工具（基于图像识别）"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认为当前目录下的 config.toml）",
    )

    # 使用子命令结构，便于未来扩展其他功能
    subparsers = parser.add_subparsers(title="子命令", dest="command")

    # 'login' 子命令
    login_parser = subparsers.add_parser("login", help="执行自动登录流程")
    login_parser.add_argument(
        "-a", "--account",
        help="登录账号（若未指定则使用配置文件中的值）"
    )
    login_parser.add_argument(
        "-p", "--password",
        help="登录密码（若未指定则使用配置文件中的值）"
    )
    login_parser.add_argument(
        "--debug-level",
        type=int,
        default=None,
        help="调试等级（例如：2 表示跳过点击上课按钮步骤）",
    )

    return parser


def _ensure_admin() -> bool:
    """检查并确保程序以管理员权限运行（仅限 Windows）。

    Returns:
        bool: 如果已是以管理员运行，返回 True；
              如果尝试提权（这将启动新进程），返回 False。
    """
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        # 如果无法检测（如非 Windows 环境或异常），默认放行
        return True

    if is_admin:
        return True

    # 允许通过参数强制跳过提权检查
    if "--no-elevate" in sys.argv:
        return True

    logger.warning("当前未以管理员权限运行，正在尝试请求提权...")
    
    # 重新拼接参数，确保带空格的路径被正确引用
    # 注意：打包后的 exe 运行时，sys.executable 为程序本身，ShellExecute 的 params 不应再次包含程序路径 (sys.argv[0])
    # 而脚本运行时，sys.executable 为 python.exe，params 需要包含脚本路径 (sys.argv[0])
    if getattr(sys, 'frozen', False):
        # 打包环境：排除 argv[0] (exe 路径)，只传递后续参数
        args_to_pass = sys.argv[1:]
    else:
        # 脚本环境：完整传递 argv (脚本路径 + 参数)
        args_to_pass = sys.argv

    params = " ".join([f'"{arg}"' if " " in arg else arg for arg in args_to_pass])
    
    # 使用 ShellExecuteW 触发 UAC 弹窗
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    
    # 返回 False 表示当前进程应结束，交由新进程接管
    return False


def main() -> int:
    """主程序逻辑。

    Returns:
        int: 进程退出码（0 表示成功，非 0 表示失败）。
    """
    # 允许 Ctrl+C 终止进程（避免 Qt 占用使得无法通过 KeyboardInterrupt 退出）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # 兼容双击直接运行：如果没有参数，默认自动追加 "login" 子命令
    if len(sys.argv) == 1:
        sys.argv.append("login")

    parser = _build_parser()
    args = parser.parse_args()

    # 1. 权限检查
    if not _ensure_admin():
        return 0

    # 2. 加载配置与初始化日志
    try:
        config_path = Path(args.config)
        config = load_config(config_path)
        init_logger(level=config.logging.level, log_dir=config.logging.dir)
    except Exception as e:
        # 配置加载失败属于严重错误，直接打印并退出
        print(f"配置文件加载失败: {e}")
        return 1

    # 3. 初始化Sentry
    sentry_sdk.init(
        dsn="https://8699bd10a68903162e72965024484190@o4510289605296128.ingest.de.sentry.io/4510726847332432",
        release=__version__,
        # 收集用户信息（如 IP 地址、Header 等），详情参考官方文档
        send_default_pii=True,
        # 启用日志发送到 Sentry
        enable_logs=True,
        # 设置 tracing 采样率为 1.0，即捕获 100% 的事务
        traces_sample_rate=1.0,
    )

    # 4. 校验子命令
    if args.command != "login":
        parser.print_help()
        logger.error("请指定子命令，例如：C30Auto-login login -a 账号 -p 密码")
        return 2

    # 5. 参数合并：命令行参数优先于配置文件
    account = args.account or config.credentials.account
    password = args.password or config.credentials.password

    if args.debug_level is not None:
        config.automation.debug_level = int(args.debug_level)

    # 6. 初始化 UI 应用程序
    # 获取现有实例或创建新实例
    app = QApplication.instance() or QApplication(sys.argv)

    # 7. 警告弹窗逻辑
    # 阻塞式弹窗，用户确认后才继续
    dialog = WarningDialog(timeout=config.ui.warning_timeout)
    # dialog.exec() 返回值通常为 1 (Accepted) 或 0 (Rejected)
    if dialog.exec() != 1:
        logger.info("用户在警告弹窗中取消或未确认，程序终止。")
        return 0

    # 8. 显示顶部滚动横幅（非阻塞）
    banner = ScrollingBanner(
        text=config.ui.banner_text,
        height=config.ui.banner_height
    )
    banner.show()

    # 9. 启动后台线程执行自动化任务
    # 确定基准目录：打包环境下为 exe 所在目录，开发环境下为代码所在目录
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).resolve().parent

    # 将自动化逻辑放入子线程，防止界面卡死
    automator = C30ImageAutomator(
        account=account,
        password=password,
        config=config,
        base_dir=base_dir
    )
    automator.app_instance = app

    thread = QThread()
    automator.moveToThread(thread)

    # 使用字典作为可变容器来接受线程的回调结果
    exit_status = {"success": False}

    def on_automation_finished(is_success: bool):
        """自动化任务结束后的回调函数。"""
        exit_status["success"] = is_success
        # 关闭横幅
        banner.close()
        # 退出 Qt 事件循环
        app.quit()

    # 信号连接
    automator.finished.connect(on_automation_finished)
    thread.started.connect(automator.run)
    
    # 任务完成后自动清理线程资源
    automator.finished.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)

    # 启动线程
    thread.start()

    # 进入 Qt 主事件循环，等待 app.quit() 被调用
    app.exec()

    # 确保线程已确实退出
    if thread.isRunning():
        thread.wait(2000)

    return 0 if exit_status["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
