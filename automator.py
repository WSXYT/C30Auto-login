"""图像识别驱动的自动化登录流程。

核心职责：
1. 通过模板匹配定位按钮/输入框。
2. 控制鼠标点击与键盘输入。
3. 支持重试、超时、回退偏移等策略。
4. 通过 Qt 信号将执行结果返回给 UI。
"""

from __future__ import annotations

import time
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyautogui
import psutil
from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal

from config import AppConfig
from image_matcher import find_template_center, MatchResult, _screenshot, _load_template, _edges, _ensure_opencv

# 鼠标移动到屏幕角落会触发 PyAutoGUI 的安全中断
pyautogui.FAILSAFE = True

try:
    # 更底层的点击方式（需要 pywin32）
    import win32api
    import win32con
except Exception:  # noqa: BLE001
    win32api = None
    win32con = None

try:
    # sendinput 点击后端使用的系统 API
    import ctypes
except Exception:  # noqa: BLE001
    ctypes = None

try:
    import win32gui
except Exception:  # noqa: BLE001
    win32gui = None


@dataclass
class StepResult:
    """单步骤执行结果。"""

    ok: bool
    message: str


class C30ImageAutomator(QObject):
    """自动化执行器（运行在 Qt 线程中）。"""

    # 结束信号：True 表示成功，False 表示失败
    finished = pyqtSignal(bool)

    def __init__(self, account: str, password: str, config: AppConfig, base_dir: Path) -> None:
        """初始化自动化执行器。

        参数：
        - account/password：账号密码
        - config：配置对象
        - base_dir：项目基准目录（用于解析相对模板路径）
        """
        super().__init__()
        self.account = account
        self.password = password
        self.config = config
        self.base_dir = base_dir
        # QApplication 实例（用于在 GUI 线程下处理事件）
        self.app_instance = None
        # 设置 PyAutoGUI 全局操作节奏
        pyautogui.PAUSE = self.config.automation.pause
        
        # 性能优化：缓存解析后的模板路径
        self._cached_paths = {}
        
        # 性能优化：缓存阈值序列（避免重复计算）
        self._cached_thresholds = None

    def run(self) -> None:
        """自动化执行入口（支持步骤回退重试）。"""

        ok = False
        if not self.account:
            logger.error("账号为空，请在参数或配置文件中填写")
        else:
            try:
                # 1) 确保目标应用已启动
                self._ensure_app_running()
                # 2) 校验模板图片是否存在
                self._validate_templates()

                # 定义步骤函数映射
                # 步骤0: 尝试展开侧边栏
                # 步骤1: 点击上课按钮
                # 步骤2: 输入账号
                # 步骤3: 输入密码
                # 步骤4: 点击登录
                steps = [
                    (self._step_open_sidebar, "展开侧边栏"),
                    (self._step_click_on_course, "点击上课按钮"),
                    (self._step_fill_account, "输入账号"),
                    (self._step_fill_password, "输入密码"),
                    (self._step_click_login, "点击登录"),
                ]

                # 程序启动默认步骤1 (尝试点击上课按钮)
                current_step = 1
                fallback_count = 0
                max_fallbacks = self.config.automation.max_fallbacks

                if self.config.automation.debug_level >= 2:
                    logger.warning("调试模式：从步骤 2 开始（输入账号）")
                    current_step = 2

                while current_step < len(steps):
                    func, name = steps[current_step]
                    logger.info(f"正在执行步骤 {current_step}: {name}")

                    # 执行当前步骤
                    result = func()

                    if result.ok:
                        logger.success(f"步骤 {current_step} ({name}) 执行成功")
                        current_step += 1
                    else:
                        logger.warning(f"步骤 {current_step} ({name}) 执行失败: {result.message}")
                        if current_step > 0:
                            fallback_count += 1
                            if fallback_count > max_fallbacks:
                                logger.error(f"回退次数 ({fallback_count}) 超过最大限制 ({max_fallbacks})，停止执行")
                                raise RuntimeError(f"达到最大回退次数限制 ({max_fallbacks})")

                            # 特殊规则：步骤 4 (点击登录) 失败直接回退到步骤 2 (输入账号)
                            if current_step == 4:
                                current_step = 2
                            else:
                                current_step -= 1

                            logger.info(f"回退到步骤 {current_step} (当前累计回退 {fallback_count} 次)")
                        else:
                            # 步骤0也失败了
                            raise RuntimeError(f"步骤 0 ({name}) 执行失败，无法继续")

                logger.success("登录流程全部完成")
                ok = True
            except Exception:  # noqa: BLE001
                logger.exception("登录流程执行过程中发生异常")

        # 通过 Qt 信号通知 UI 层完成状态
        self.finished.emit(ok)

    def _ensure_app_running(self) -> None:
        """确保 C30 应用处于运行状态。

        逻辑：
        1. 根据路径检测进程，若存在则结束。
        2. 启动（或重启）应用。
        """

        exe_path = (self.config.app.exe_path or "").strip()
        if not exe_path:
            logger.warning("未配置 exe_path，跳过进程检测与启动")
            return

        # 1. 检测并结束进程
        proc = self._check_process_by_path(exe_path)
        if proc:
            try:
                logger.info(f"检测到 C30 正在运行 (PID={proc.pid})，正在结束...")
                proc.kill()
                proc.wait(timeout=5)
                logger.info("进程已结束")
                time.sleep(1)  # 稍作等待
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                logger.warning("进程已结束或无权操作")
            except psutil.TimeoutExpired:
                logger.error("结束进程超时")

        # 2. 启动应用
        exe = Path(exe_path)
        if not exe.exists():
            logger.error(f"配置的 exe_path 不存在：{exe}")
            raise FileNotFoundError("C30 路径不存在")

        logger.info(f"启动应用：{exe}")
        try:
            # os.startfile 是 Windows 专用
            os.startfile(exe)
            # 启动后等待应用加载
            self._sleep(self.config.app.startup_wait)
        except Exception:
            logger.exception("启动 C30 失败")
            raise

    def _check_process_by_path(self, target_path: str) -> psutil.Process | None:
        """根据路径检测进程。"""
        target_path_obj = Path(target_path).resolve()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # 直接使用 exe() 方法获取可执行文件路径
                proc_exe = Path(proc.exe()).resolve()
                if proc_exe == target_path_obj:
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue  # 忽略无权限或已结束的进程
        return None

    def _validate_templates(self) -> None:
        """校验所有模板图片是否存在。"""

        missing_categories: list[str] = []
        
        # 定义需要校验的模板类别及其配置列表
        categories = {
            "sidebar_button": self.config.templates.sidebar_button,
            "on_course": self.config.templates.on_course,
            "account_input": self.config.templates.account_input,
            "password_input": self.config.templates.password_input,
            "login_button": self.config.templates.login_button,
        }

        for name, paths in categories.items():
            valid_count = 0
            for path in paths:
                abs_path = self._resolve_path(path)
                if abs_path.exists():
                    valid_count += 1
                else:
                    logger.debug(f"模板文件缺失 (非致命): {abs_path}")
            
            if valid_count == 0:
                missing_categories.append(name)
                logger.error(f"类别 '{name}' 的所有模板文件均不存在！")

        if missing_categories:
            raise FileNotFoundError(f"关键模板缺失: {', '.join(missing_categories)}")

    def _resolve_path(self, path: str) -> Path:
        """将相对路径转为绝对路径（带缓存）。"""
        # 使用缓存避免重复解析
        if path in self._cached_paths:
            return self._cached_paths[path]
        
        p = Path(path)
        if p.is_absolute():
            resolved = p
        else:
            resolved = (self.base_dir / p).resolve()
        
        self._cached_paths[path] = resolved
        return resolved

    def _sleep(self, seconds: float) -> None:
        """带事件循环处理的休眠（UI 线程中会处理事件）。"""

        if self.app_instance and self.thread() == self.app_instance.thread():
            # 在 GUI 线程中避免长时间阻塞，保持 UI 响应
            start = time.time()
            while time.time() - start < seconds:
                self.app_instance.processEvents()
                time.sleep(0.02)
        else:
            time.sleep(seconds)

    def _do_single_scan(
        self,
        templates: list[str],
        region: tuple[int, int, int, int] | None,
        attempt: int | None = None,
        show_log: bool = True,
    ) -> MatchResult | None:
        """执行单次完整扫描逻辑（尝试所有阈值）。"""
        thresholds = self._build_input_thresholds()
        if show_log:
            attempt_str = f"第 {attempt} 次" if attempt is not None else ""
            logger.info(
                f"正在{attempt_str}检测图片模板 (包含 {len(thresholds)} 个阈值等级): "
                f"{[Path(p).name for p in templates]}"
            )

        # 性能优化：在阈值循环外只截一次屏
        _ensure_opencv()
        screenshot = _screenshot(region=region)

        # 预加载模板
        loaded_templates = []
        for path in [self._resolve_path(p) for p in templates]:
            try:
                loaded_templates.append((path, _load_template(path)))
            except Exception as e:
                logger.error(f"无法加载模板：{path}\n{e}")

        for threshold in thresholds:
            best_match: MatchResult | None = None
            for path, template in loaded_templates:
                res = self._match_in_image(screenshot, template, threshold)
                if res:
                    conf, loc = res
                    h, w = template.shape[:2]
                    cx = loc[0] + w // 2 + (region[0] if region else 0)
                    cy = loc[1] + h // 2 + (region[1] if region else 0)

                    match = MatchResult(center=(cx, cy), confidence=conf, template_path=path)
                    if best_match is None or match.confidence > best_match.confidence:
                        best_match = match

            if best_match:
                return best_match
        return None

    def _wait_and_click(
        self,
        templates: list[str],
        region: tuple[int, int, int, int] | None,
        timeout: float | None = None,
        attempt: int | None = None,
        use_multi_threshold: bool = False,
    ) -> StepResult:
        """等待并点击指定模板。

        - templates：模板列表（会依次尝试匹配）
        - region：限制识别区域，提高性能与准确率
        - timeout：搜索超时时间，None 则使用配置中的 step_timeout
        - attempt：当前重试次数（用于日志）
        - use_multi_threshold：是否使用多阈值扫描
        """

        abs_paths = [self._resolve_path(p) for p in templates]

        # 如果是由 _retry 调用（传入了 attempt），则执行单次尝试模式
        if attempt is not None and timeout is None:
            if use_multi_threshold:
                match = self._do_single_scan(templates, region, attempt=attempt)
            else:
                match = find_template_center(abs_paths, self.config.automation.match_threshold, region, attempt=attempt)

            if match:
                logger.info(f"识别到目标：{match.template_path.name}，置信度 {match.confidence:.2f}")
                self._click_at(match.center)
                return StepResult(True, f"点击 {match.template_path.name}")
            return StepResult(False, "未识别到目标")

        # 否则，在 timeout 时间内循环等待（通常用于非步骤重试的场景）
        start = time.time()
        wait_timeout = timeout if timeout is not None else self.config.automation.step_timeout

        while time.time() - start <= wait_timeout:
            if self.app_instance and self.thread() == self.app_instance.thread():
                self.app_instance.processEvents()

            if use_multi_threshold:
                match = self._do_single_scan(templates, region, attempt=attempt)
            else:
                match = find_template_center(abs_paths, self.config.automation.match_threshold, region, attempt=attempt)

            if match:
                logger.info(f"识别到目标：{match.template_path.name}，置信度 {match.confidence:.2f}")
                self._click_at(match.center)
                return StepResult(True, f"点击 {match.template_path.name}")

            self._sleep(0.4)
        return StepResult(False, "超时未识别到目标")

    def _wait_and_type(
        self,
        templates: list[str],
        text: str,
        region: tuple[int, int, int, int] | None,
        fallback_offset: tuple[int, int] | None,  # 回退：以登录按钮为基准
        click_offset: tuple[int, int] | None = None,  # 正常：以识别模板为基准的相对点击偏移
        timeout: float | None = None,
        attempt: int | None = None,
    ) -> StepResult:
        """等待输入框并输入文本。
        ... (docstring unchanged) ...
        """

        # 计算点击位置辅助函数
        def get_click_point(match_center: tuple[int, int]) -> tuple[int, int]:
            if click_offset:
                return (match_center[0] + click_offset[0], match_center[1] + click_offset[1])
            return match_center

        # 如果是由 _retry 调用，执行单次尝试
        if attempt is not None and timeout is None:
            match = self._do_single_scan(templates, region, attempt=attempt)
            if match:
                logger.info(
                    f"识别到输入框：{match.template_path.name}，置信度 {match.confidence:.2f}"
                )
                self._click_at(get_click_point(match.center))
                self._clear_and_type(text)
                return StepResult(True, f"输入 {match.template_path.name}")

            # 尝试回退
            if fallback_offset and self._try_fallback_by_login_button(fallback_offset):
                self._clear_and_type(text)
                return StepResult(True, "使用登录按钮偏移回退输入")

            return StepResult(False, "未识别到输入框")

        # 循环等待模式
        start = time.time()
        wait_timeout = timeout if timeout is not None else self.config.automation.step_timeout

        while time.time() - start <= wait_timeout:
            if self.app_instance and self.thread() == self.app_instance.thread():
                self.app_instance.processEvents()

            match = self._do_single_scan(templates, region, attempt=attempt)
            if match:
                logger.info(
                    f"识别到输入框：{match.template_path.name}，置信度 {match.confidence:.2f}"
                )
                self._click_at(get_click_point(match.center))
                self._clear_and_type(text)
                return StepResult(True, f"输入 {match.template_path.name}")

            self._sleep(0.4)

        # 兜底：用登录按钮的偏移来定位输入框
        if fallback_offset:
            if self._try_fallback_by_login_button(fallback_offset):
                self._clear_and_type(text)
                return StepResult(True, "使用登录按钮偏移回退输入")

        return StepResult(False, "超时未识别到输入框")

    def _build_input_thresholds(self) -> list[float]:
        """生成输入框匹配阈值序列（从高到低）。"""
        # 使用缓存避免重复计算
        if self._cached_thresholds is not None:
            return self._cached_thresholds
        
        start = self.config.automation.match_threshold
        minimum = self.config.automation.input_threshold_min
        step = max(self.config.automation.input_threshold_step, 0.03)
        
        thresholds: list[float] = []
        value = start
        while value >= minimum:
            thresholds.append(round(value, 2))
            value -= step
        
        # 确保最小值在列表中
        if thresholds[-1] > minimum:
            thresholds.append(minimum)
        
        # 缓存结果
        self._cached_thresholds = thresholds
        return thresholds

    def _click_at(self, point: tuple[int, int]) -> None:
        """根据配置的点击后端执行点击。"""

        x, y = point
        backend = (self.config.automation.click_backend or "pyautogui").lower()
        if backend == "sendinput":
            if ctypes is None:
                logger.error("无法导入 ctypes，无法使用 sendinput 点击后端")
                raise RuntimeError("sendinput 不可用")
            self._click_sendinput(x, y)
        elif backend == "win32api":
            if win32api is None or win32con is None:
                logger.error("未安装 pywin32，无法使用 win32api 点击后端")
                raise RuntimeError("win32api 不可用")
            win32api.SetCursorPos((x, y))
            self._sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self._sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self._sleep(0.05)
        else:
            # 默认使用 PyAutoGUI
            pyautogui.moveTo(x, y, duration=0.05)
            self._sleep(0.05)
            pyautogui.click(x, y, button="left")
            self._sleep(0.05)

    def _click_sendinput(self, x: int, y: int) -> None:
        """使用 SendInput 进行绝对坐标点击（更底层）。"""

        user32 = ctypes.windll.user32

        # 获取屏幕尺寸，用于转换到 0~65535 的绝对坐标
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        absolute_x = int(x * 65535 / (screen_w - 1))
        absolute_y = int(y * 65535 / (screen_h - 1))

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

        def send(flags: int):
            # 构造输入结构并发送给系统
            inp = INPUT()
            inp.type = 0
            inp.mi = MOUSEINPUT(absolute_x, absolute_y, 0, flags, 0, None)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

        # 移动到目标位置并点击
        send(0x8000 | 0x0001)  # MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE
        time.sleep(0.02)
        send(0x0002)  # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.02)
        send(0x0004)  # MOUSEEVENTF_LEFTUP

    def _clear_and_type(self, text: str) -> None:
        """清空输入框并输入文本。"""

        self._sleep(0.5)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyautogui.typewrite(text, interval=0.02)

    def _match_in_image(
        self, screen_img: np.ndarray, tmpl_img: np.ndarray, threshold: float
    ) -> tuple[float, tuple[int, int]] | None:
        """执行实际的模板匹配和边缘匹配。"""
        import cv2

        # 1. 常规模板匹配
        result = cv2.matchTemplate(screen_img, tmpl_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            return float(max_val), max_loc

        # 2. 边缘匹配兜底
        try:
            screen_edges = _edges(screen_img)
            template_edges = _edges(tmpl_img)
            edge_threshold = max(threshold - 0.1, 0.6)
            
            result_edge = cv2.matchTemplate(screen_edges, template_edges, cv2.TM_CCOEFF_NORMED)
            _, max_val_edge, _, max_loc_edge = cv2.minMaxLoc(result_edge)
            
            if max_val_edge >= edge_threshold:
                return float(max_val_edge), max_loc_edge
        except Exception:
            pass

        return None

    def _try_fallback_by_login_button(self, offset: tuple[int, int]) -> bool:
        """使用“登录按钮中心+偏移”定位输入框。"""

        logger.warning("尝试使用登录按钮偏移回退定位输入框")
        match = find_template_center(
            [self._resolve_path(p) for p in self.config.templates.login_button],
            self.config.automation.match_threshold,
            self.config.regions.login_area,
            show_log=False,
        )
        if not match:
            return False
        dx, dy = offset
        target = (match.center[0] + dx, match.center[1] + dy)
        self._click_at(target)
        return True


    def _has_account_input(self) -> bool:
        """判断是否检测到账号输入框。"""
        # 使用多阈值扫描，但不显示日志
        match = self._do_single_scan(
            self.config.templates.account_input,
            self.config.regions.login_area,
            attempt=None,
            show_log=False
        )
        return match is not None

    def _retry(self, func, step_name: str, max_retries: int | None = None) -> StepResult:
        """通用重试封装。"""

        retries = 0
        limit = max_retries if max_retries is not None else self.config.automation.max_retries
        while True:
            # 这里的 attempt 传给 func，从 1 开始
            result = func(retries + 1)
            if result.ok:
                return result
            retries += 1
            if retries > limit:
                return StepResult(False, f"{step_name}超过最大重试次数")
            logger.warning(f"{step_name}失败，{self.config.automation.retry_interval} 秒后重试")
            self._sleep(self.config.automation.retry_interval)

    def _step_click_on_course(self) -> StepResult:
        """步骤 1：点击“上课”按钮。"""

        logger.info("正在执行：点击上课按钮")
        # 特殊规则：如果检测 2 次（或其他配置值）检测不到就回退步骤 0
        # 预先获取模板尺寸，避免每次重试都重复计算（虽然 _get_window_region 内会计算，但 lambda 获取一次即可）
        min_size = self._get_templates_size(self.config.templates.on_course)

        return self._retry(
            lambda att: self._wait_and_click(
                self.config.templates.on_course,
                self._get_window_region(self.config.app.window_class_on_course, min_size) or self.config.regions.on_course,
                attempt=att
            ),
            "点击上课按钮",
            max_retries=self.config.automation.on_course_retries - 1
        )

    def _has_on_course_button(self) -> bool:
        """快速判断当前界面是否已出现“上课”按钮。"""

        # 尝试获取目标窗口区域
        min_size = self._get_templates_size(self.config.templates.on_course)
        region = self._get_window_region(self.config.app.window_class_on_course, min_size=min_size)
        if region is None:
            region = self.config.regions.on_course

        match = find_template_center(
            [self._resolve_path(p) for p in self.config.templates.on_course],
            self.config.automation.match_threshold,
            region,
            show_log=False,
        )
        return match is not None

    def _get_templates_size(self, templates: list[str]) -> tuple[int, int]:
        """获取模板列表中第一个有效模板的尺寸 (w, h)。"""
        for path_str in templates:
            try:
                path = self._resolve_path(path_str)
                # 使用 image_matcher 的加载函数（带缓存或直接读取）
                # 这里简单直接加载，考虑到 _load_template 耗时较小且通常模板不多
                img = _load_template(path)
                if img is not None:
                    h, w = img.shape[:2]
                    return (w, h)
            except Exception:
                pass
        # 默认返回较小尺寸作为兜底
        return (10, 10)

    def _get_window_region(self, class_name: str, min_size: tuple[int, int] | None = None) -> tuple[int, int, int, int] | None:
        """获取指定类名窗口的屏幕区域 (x, y, w, h)。"""
        if not class_name or win32gui is None:
            return None
        
        try:
            hwnd = win32gui.FindWindow(class_name, None)
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                x, y, r, b = rect
                w = r - x
                h = b - y
                
                # 基础校验
                if w <= 0 or h <= 0:
                     return None

                # 尺寸校验：窗口必须大于等于模板尺寸
                if min_size:
                    min_w, min_h = min_size
                    if w < min_w or h < min_h:
                        logger.warning(
                            f"窗口 {class_name} 尺寸 ({w}x{h}) 小于模板尺寸 ({min_w}x{min_h})，回退到全局区域"
                        )
                        return None
                
                return (x, y, w, h)
        except Exception:
            pass
        
        logger.debug(f"未找到类名为 {class_name} 的窗口，回退到全局/默认区域")
        return None

    def _step_open_sidebar(self) -> StepResult:
        """步骤 0：展开侧边栏（如需要）。"""

        if not self.config.templates.sidebar_button:
            return StepResult(True, "未配置侧边栏按钮模板，跳过")

        logger.info("正在执行：展开侧边栏")
        return self._retry(
            lambda att: self._wait_and_click(
                self.config.templates.sidebar_button,
                self.config.regions.sidebar_button,
                attempt=att
            ),
            "展开侧边栏",
        )

    def _step_fill_account(self) -> StepResult:
        """步骤 2：输入账号。"""

        logger.info("正在执行：输入账号")
        min_size = self._get_templates_size(self.config.templates.account_input)
        
        return self._retry(
            lambda att: self._wait_and_type(
                self.config.templates.account_input,
                self.account,
                self._get_window_region(self.config.app.window_class_login, min_size) or self.config.regions.login_area,
                self.config.fallback_offsets.account_from_login,
                click_offset=self.config.click_offsets.account,
                attempt=att
            ),
            "输入账号",
        )

    def _step_fill_password(self) -> StepResult:
        """步骤 3：输入密码（如果配置了密码）。"""

        if not self.password:
            logger.info("未配置密码，跳过输入密码步骤（假设已记住密码）")
            return StepResult(True, "未配置密码，跳过")

        logger.info("正在执行：输入密码")
        min_size = self._get_templates_size(self.config.templates.password_input)

        return self._retry(
            lambda att: self._wait_and_type(
                self.config.templates.password_input,
                self.password,
                self._get_window_region(self.config.app.window_class_login, min_size) or self.config.regions.login_area,
                self.config.fallback_offsets.password_from_login,
                click_offset=self.config.click_offsets.password,
                attempt=att
            ),
            "输入密码",
        )

    def _step_click_login(self) -> StepResult:
        """步骤 4：点击登录按钮（带验证逻辑）。"""

        logger.info("正在执行：点击登录")
        min_size = self._get_templates_size(self.config.templates.login_button)

        # 内部重试逻辑：点击后检查按钮是否消失
        max_retries = 3
        for i in range(max_retries):
            # 1. 点击 (启用多阈值扫描)
            # 注意：这里每次循环都重新获取 region，以防窗口移动/改变，但也带来了微小的性能开销
            region = self._get_window_region(self.config.app.window_class_login, min_size) or self.config.regions.login_area
            
            result = self._wait_and_click(
                self.config.templates.login_button,
                region,
                timeout=5.0,  # 登录按钮点击不应等待太久
                attempt=i + 1,
                use_multi_threshold=True
            )

            if not result.ok:
                # 如果连按钮都找不到，可能是已经登录了，或者是真的找不到
                if not self._has_login_button():
                    return StepResult(True, "未找到登录按钮，推测已成功登录")
            else:
                # 2. 验证：等待几秒看按钮是否消失
                if self._wait_login_success(timeout=3.0):
                    return StepResult(True, "登录成功（登录按钮已消失）")

            logger.warning(f"点击登录后按钮仍存在，重试 ({i+1}/{max_retries})")
            time.sleep(1.0)

        return StepResult(False, "多次点击登录后，登录按钮仍未消失")

    def _has_login_button(self) -> bool:
        """检查登录按钮当前是否可见。"""
        # 也使用多阈值扫描来确保一致性，但不显示日志
        min_size = self._get_templates_size(self.config.templates.login_button)
        region = self._get_window_region(self.config.app.window_class_login, min_size) or self.config.regions.login_area

        match = self._do_single_scan(
            self.config.templates.login_button,
            region,
            attempt=None,
            show_log=False
        )
        return match is not None

    def _wait_login_success(self, timeout: float) -> bool:
        """等待登录按钮消失。"""
        start = time.time()
        while time.time() - start < timeout:
            if not self._has_login_button():
                return True
            if self.app_instance:
                self.app_instance.processEvents()
            time.sleep(0.2)
        return False
