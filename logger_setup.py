"""日志初始化配置。"""

from __future__ import annotations

import sys
from pathlib import Path
from loguru import logger


def init_logger(level: str = "INFO", log_dir: str | Path = "logs") -> None:
    """初始化 Loguru 日志输出。

    - 控制台输出：带颜色、便于现场调试。
    - 文件输出：按日期滚动与保留，便于排查历史问题。
    """

    log_dir = Path(log_dir)
    # 确保日志目录存在
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler，避免重复输出
    logger.remove()
    # 控制台日志
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    )
    # 文件日志（按天写入，控制大小与保留天数）
    logger.add(
        log_dir / "C30Auto-login_{time:YYYY-MM-DD}.log",
        rotation="5 MB",
        retention="7 days",
        encoding="utf-8",
        level=level,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
