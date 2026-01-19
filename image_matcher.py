"""图像匹配工具。

负责：
1. 截屏并转换为灰度图。
2. 使用 OpenCV 模板匹配定位目标。
3. 当模板匹配失败时，尝试边缘匹配兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from loguru import logger

try:
    import cv2
    # 模块加载时检查一次 OpenCV，避免每次函数调用都检查
    if cv2 is None:
        raise ImportError("cv2 导入失败")
    _cv2_available = True
    _cv2_import_error = None
except Exception as e:  # noqa: BLE001
    # 记录导入失败的异常，便于抛错时提示
    cv2 = None
    _cv2_available = False
    _cv2_import_error = e

import pyautogui


def _ensure_opencv():
    """确保 OpenCV 可用，否则抛出清晰错误。"""
    if not _cv2_available:
        raise ImportError(f"无法导入 OpenCV：{_cv2_import_error}")


@dataclass
class MatchResult:
    """模板匹配结果。"""

    # 匹配中心坐标（屏幕坐标）
    center: tuple[int, int]
    # 匹配置信度
    confidence: float
    # 使用的模板文件路径
    template_path: Path


def _load_template(path: Path) -> np.ndarray:
    """读取模板图片并转换为灰度图。"""

    _ensure_opencv()
    
    # fix: 彻底解决 Windows 中文路径问题
    # np.fromfile 有时对 Unicode 路径支持不稳定，改为 open() + np.frombuffer
    try:
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        # 使用 standard python open 读取二进制流，最稳妥
        with open(path, "rb") as f:
            bytes_data = f.read()
        
        data = np.frombuffer(bytes_data, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except Exception as e:
        # 若发生异常（如文件被占用、权限不足、解码失败），记录
        logger.error(f"读取或解码模板失败: {path}\n异常信息: {e}")
        img = None

    if img is None:
        raise FileNotFoundError(f"模板图片无法读取（可能已损坏或非图片格式）：{path}")
    return img


def _screenshot(region: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """截屏并返回灰度图。

    region: [x, y, w, h]，None 表示全屏。
    """

    shot = pyautogui.screenshot(region=region)
    img = np.array(shot)
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def _edges(img: np.ndarray) -> np.ndarray:
    """提取边缘，用于文本变化时的兜底匹配。"""

    _ensure_opencv()
    return cv2.Canny(img, 50, 150)


def find_template_center(
    template_paths: Iterable[Path],
    threshold: float,
    region: tuple[int, int, int, int] | None = None,
    attempt: int | None = None,
    show_log: bool = True,
) -> MatchResult | None:
    """寻找模板中心点。

    参数：
    - template_paths：模板路径列表
    - threshold：主匹配阈值
    - region：限定区域（可显著提高性能与准确率）
    - attempt：第几次检测（用于日志提示）
    - show_log：是否显示日志
    """
    _ensure_opencv()
    
    # 提前过滤不存在的文件
    valid_paths = [p for p in template_paths if p.exists()]
    if not valid_paths:
        if show_log:
            logger.warning(f"所有模板文件均不存在: {[p.name for p in template_paths]}")
        return None
    
    if show_log:
        attempt_str = f"第 {attempt} 次" if attempt is not None else ""
        logger.info(f"正在{attempt_str}检测图片模板: {[p.name for p in valid_paths]}")

    screenshot = _screenshot(region=region)
    best: MatchResult | None = None
    
    # 缓存屏幕边缘图，避免重复计算
    screen_edges = None

    def _match(screen_img: np.ndarray, tmpl_img: np.ndarray) -> tuple[float, tuple[int, int]]:
        # 使用归一化相关系数进行模板匹配
        result = cv2.matchTemplate(screen_img, tmpl_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return float(max_val), max_loc

    for path in valid_paths:
        try:
            template = _load_template(path)
        except Exception as e:  # noqa: BLE001
            logger.error(f"无法加载模板：{path}\n{e}")
            continue

        # 先进行常规模板匹配
        max_val, max_loc = _match(screenshot, template)
        if max_val < threshold:
            # 边缘匹配兜底（文本变化影响较小）
            try:
                # 懒加载屏幕边缘图
                if screen_edges is None:
                    screen_edges = _edges(screenshot)
                
                template_edges = _edges(template)
                edge_threshold = max(threshold - 0.1, 0.6)
                max_val, max_loc = _match(screen_edges, template_edges)
                if max_val < edge_threshold:
                    continue
            except Exception as e:  # noqa: BLE001
                logger.debug(f"边缘匹配失败：{path} {e}")
                continue

        # 计算模板中心坐标
        h, w = template.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2

        # 如果是局部区域，需要加上偏移
        if region is not None:
            center_x += region[0]
            center_y += region[1]

        match = MatchResult(center=(center_x, center_y), confidence=float(max_val), template_path=path)
        if best is None or match.confidence > best.confidence:
            best = match

    return best
