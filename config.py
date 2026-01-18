"""配置加载与数据结构定义。

本文件负责：
1. 定义配置项的类型（dataclass）。
2. 生成默认配置字典。
3. 从 JSON 文件读取并合并配置。
4. 对区域/偏移等数组型配置做安全校验与转换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from loguru import logger

try:
    import tomllib  # Python 3.11+
except Exception:  # noqa: BLE001
    tomllib = None
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except Exception:  # noqa: BLE001
        tomllib = None

# 当前项目根目录（与本文件同级）
# 适配 PyInstaller 打包环境：如果是打包后运行，使用 exe 所在目录
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# 默认配置文件路径：与代码放在同一目录（优先使用可注释的 TOML）
DEFAULT_CONFIG_PATH = BASE_DIR / "config.toml"


@dataclass
class LoggingConfig:
    """日志配置。"""

    # 日志等级：DEBUG / INFO / WARNING / ERROR 等
    level: str = "INFO"
    # 日志输出目录（相对或绝对路径）
    dir: str = "logs"


@dataclass
class AutomationConfig:
    """自动化流程参数（类定义中的值为缺省值，实际运行时会从 config.toml 加载并覆盖）。"""

    # 单个步骤失败时的最大重试次数
    max_retries: int = 2
    # 全局最大回退次数
    max_fallbacks: int = 5
    # 步骤 1 (上课按钮) 特殊重试次数（失败后回退步骤 0）
    on_course_retries: int = 2
    # 每次重试前的等待时间（秒）
    retry_interval: float = 0.5
    # 单步骤的最大等待时长（秒）
    step_timeout: float = 12.0
    # pyautogui 每一步动作之间的基础停顿（秒）
    pause: float = 0.2
    # 模板匹配基础阈值，越高越严格
    match_threshold: float = 0.82
    # 输入框识别最低阈值（降阈值搜索的下限）
    input_threshold_min: float = 0.45
    # 输入框识别降阈值步长
    input_threshold_step: float = 0.03
    # 点击后端：pyautogui / win32api / sendinput
    click_backend: str = "sendinput"
    # 调试等级：2 表示跳过步骤 1（点击上课按钮）
    debug_level: int = 0


@dataclass
class FallbackOffsetConfig:
    """输入框回退偏移配置。"""

    # 以“登录按钮中心”为基准的账号输入框偏移（dx, dy）
    account_from_login: tuple[int, int] | None = None
    # 以“登录按钮中心”为基准的密码输入框偏移（dx, dy）
    password_from_login: tuple[int, int] | None = None


@dataclass
class MatchClickOffsetConfig:
    """模板匹配后的点击偏移（用于“识别图标/文本 -> 点击右侧输入框”的场景）。"""

    # 账号输入框：识别到模板中心后，点击偏移 (dx, dy)
    account: tuple[int, int] | None = None
    # 密码输入框：识别到模板中心后，点击偏移 (dx, dy)
    password: tuple[int, int] | None = None


@dataclass
class TemplateConfig:
    """模板路径配置（可为多模板数组）。"""

    # 侧边栏按钮模板
    sidebar_button: list[str] = field(default_factory=list)
    # 上课按钮模板
    on_course: list[str] = field(default_factory=list)
    # 账号输入框模板
    account_input: list[str] = field(default_factory=list)
    # 密码输入框模板
    password_input: list[str] = field(default_factory=list)
    # 登录按钮模板
    login_button: list[str] = field(default_factory=list)


@dataclass
class RegionConfig:
    """识别区域限制配置。"""

    # 侧边栏按钮识别区域 [x, y, w, h]
    sidebar_button: tuple[int, int, int, int] | None = None
    # 上课按钮识别区域 [x, y, w, h]
    on_course: tuple[int, int, int, int] | None = None
    # 登录区域（账号/密码/登录按钮）识别区域 [x, y, w, h]
    login_area: tuple[int, int, int, int] | None = None


@dataclass
class CredentialConfig:
    """账号与密码。"""

    account: str = ""
    password: str = ""


@dataclass
class AppProcessConfig:
    """应用进程配置。"""

    # 可执行文件路径（用于检测不到进程时启动）
    exe_path: str = ""
    # 启动后等待时间（秒）
    startup_wait: float = 15.0


@dataclass
class UIConfig:
    """UI 提示配置。"""

    # 顶部滚动条文案
    banner_text: str = "正在运行希沃白板自动登录 请勿触摸一体机"
    # 滚动条高度（像素）
    banner_height: int = 80
    # 执行前警告弹窗倒计时（秒）
    warning_timeout: int = 10


@dataclass
class AppConfig:
    """最终汇总后的配置对象。"""

    logging: LoggingConfig = field(default_factory=LoggingConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    regions: RegionConfig = field(default_factory=RegionConfig)
    fallback_offsets: FallbackOffsetConfig = field(default_factory=FallbackOffsetConfig)
    # 新增点击偏移配置
    click_offsets: MatchClickOffsetConfig = field(default_factory=MatchClickOffsetConfig)
    credentials: CredentialConfig = field(default_factory=CredentialConfig)
    app: AppProcessConfig = field(default_factory=AppProcessConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _as_tuple(value: Any) -> tuple[int, int, int, int] | None:
    """把任意值转换为区域四元组 (x, y, w, h)。

    - None -> None
    - list/tuple 长度为 4 -> 转为 int 元组
    - 其他情况直接抛错，避免配置写错造成隐蔽问题
    """

    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(int(v) for v in value)
    raise ValueError("区域配置必须是长度为4的数组，例如 [x, y, w, h]")


def _as_tuple2(value: Any) -> tuple[int, int] | None:
    """把任意值转换为偏移二元组 (dx, dy)。"""

    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return tuple(int(v) for v in value)
    raise ValueError("偏移配置必须是长度为2的数组，例如 [dx, dy]")


def default_config_dict() -> dict[str, Any]:
    """返回默认配置的字典表示。

    注意：这里返回的是纯 dict，用于写入 JSON。
    """

    return {
        "logging": {"level": "INFO", "dir": "logs"},
        "automation": {
            "max_retries": 2,
            "max_fallbacks": 5,
            "on_course_retries": 2,
            "retry_interval": 0.5,
            "step_timeout": 12.0,
            "pause": 0.2,
            "match_threshold": 0.82,
            "input_threshold_min": 0.45,
            "input_threshold_step": 0.03,
            "click_backend": "pyautogui",
            "debug_level": 0,
        },
        "templates": {
            "sidebar_button": [
                "resources/templates/sidebar_button.png",
            ],
            "on_course": [
                "resources/templates/on_course.png",
            ],
            "account_input": [
                "resources/templates/account_input.png",
                "resources/templates/account_input_selected.png",
            ],
            "password_input": [
                "resources/templates/password_input.png",
                "resources/templates/password_input_selected.png",
            ],
            "login_button": [
                "resources/templates/login_button.png",
            ],
        },
        "regions": {"sidebar_button": None, "on_course": None, "login_area": None},
        "fallback_offsets": {"account_from_login": None, "password_from_login": None},
        "click_offsets": {"account": None, "password": None},
        "credentials": {"account": "", "password": ""},
        "app": {"exe_path": "", "startup_wait": 5.0},
        "ui": {
            "banner_text": "正在运行希沃白板自动登录 请勿触摸一体机",
            "banner_height": 80,
            "warning_timeout": 10,
        },
    }


def default_config_toml() -> str:
    """返回默认 TOML 配置文本（含可读注释）。"""

    return """
# C30 自动登录工具配置文件（TOML 支持 # 注释）

[logging]
# 日志等级：DEBUG/INFO/WARNING/ERROR
level = "INFO"
# 日志目录（相对或绝对路径）
dir = "logs"

[automation]
# 步骤失败最大重试次数
max_retries = 2
# 步骤回退总次数限制（超过此次数则程序报错退出）
max_fallbacks = 5
# 步骤1（上课按钮）特殊重试次数（失败后回退步骤0）
on_course_retries = 2
# 重试间隔（秒）
retry_interval = 0.5
# 单步骤等待超时（秒）
step_timeout = 12.0
# 每次鼠标/键盘动作间隔（秒）
pause = 0.2
# 模板匹配阈值（越高越严格）
match_threshold = 0.82
# 输入框最低阈值（降阈值下限）
input_threshold_min = 0.45
# 输入框降阈值步长
input_threshold_step = 0.03
# 点击后端：pyautogui / win32api / sendinput
click_backend = "sendinput"
# 调试等级：2 表示跳过点击上课按钮
debug_level = 0

[ui]
# 顶部滚动条显示文字
banner_text = "正在运行希沃白板自动登录 请勿触摸一体机"
# 顶部滚动条高度（像素）
banner_height = 80
# 执行前警告弹窗倒计时（秒）
warning_timeout = 10

[templates]
# 图像识别模板路径（可多个）
# 建议为输入框提供“未选中”和“已选中”两种状态的截图，以提高识别稳定性
sidebar_button = ["resources/templates/sidebar_button.png"]
on_course = ["resources/templates/on_course.png"]
account_input = [
    "resources/templates/account_input.png", 
    "resources/templates/account_input_selected.png"
]
password_input = [
    "resources/templates/password_input.png", 
    "resources/templates/password_input_selected.png"
]
login_button = ["resources/templates/login_button.png"]

[regions]
# 限制识别区域 [x, y, w, h]，空数组表示全屏
sidebar_button = []
on_course = []
login_area = []

[fallback_offsets]
# 相对于登录按钮的输入框偏移 [dx, dy]，空数组表示不启用
account_from_login = []
password_from_login = []

[click_offsets]
# 识别到输入框模板后，点击位置的偏移量 [dx, dy]
# 典型用法：模板截取左侧的“图标”或“文字”，通过偏移点击右侧的“输入框”
# 例如：account = [150, 0] 表示向右偏 150 像素点击
account = []
password = []

[credentials]
# 账号与密码（不建议提交到公共仓库）
account = ""
password = ""

[app]
# C30 可执行文件路径（未检测到进程时用于启动）
exe_path = ""
# 启动后等待时间（秒）
startup_wait = 5.0
""".lstrip()


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并配置字典。

    - base：默认值
    - override：用户配置
    """

    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _clean_dict(d: dict[str, Any]) -> dict[str, Any]:
    """移除所有以 _ 开头的键（注释键）。

    目的是允许在 JSON 中使用 "_comment" 等字段作为注释。
    """

    return {k: v for k, v in d.items() if not k.startswith("_")}


def _load_config_data(path: Path) -> dict[str, Any]:
    """加载 TOML 配置数据为字典。"""

    suffix = path.suffix.lower()
    if suffix != ".toml":
        raise ValueError("只支持 .toml 配置文件")
    if tomllib is None:
        raise ImportError("无法加载 TOML，请安装 tomli 或使用 Python 3.11+")
    with path.open("rb") as f:
        return tomllib.load(f)


def _write_default_config(path: Path) -> None:
    """写入默认 TOML 配置文件。"""

    suffix = path.suffix.lower()
    if suffix != ".toml":
        raise ValueError("只支持 .toml 配置文件")
    path.write_text(default_config_toml(), encoding="utf-8")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """加载配置文件并返回 `AppConfig`。

    - 如果配置文件不存在，自动写入默认配置。
    - 将用户配置与默认配置合并。
    - 自动清理 JSON 中的注释字段（以 _ 开头）。
    """

    path = Path(path)
    if not path.exists():
        # 确保目录存在，然后写入默认配置
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_default_config(path)

    # 读取配置（支持 TOML/JSON）
    data = _load_config_data(path)

    # 与默认值合并，避免缺字段
    merged = _merge(default_config_dict(), data)
    logger.debug(f"已加载配置文件，并与默认值合并: {merged}")

    # 逐个子配置构建 dataclass，便于类型检查与 IDE 友好提示
    logging_cfg = LoggingConfig(**_clean_dict(merged.get("logging", {})))
    automation_cfg = AutomationConfig(**_clean_dict(merged.get("automation", {})))
    templates_cfg = TemplateConfig(**_clean_dict(merged.get("templates", {})))
    regions_cfg = RegionConfig(
        sidebar_button=_as_tuple(merged.get("regions", {}).get("sidebar_button")),
        on_course=_as_tuple(merged.get("regions", {}).get("on_course")),
        login_area=_as_tuple(merged.get("regions", {}).get("login_area")),
    )
    fallback_cfg = FallbackOffsetConfig(
        account_from_login=_as_tuple2(merged.get("fallback_offsets", {}).get("account_from_login")),
        password_from_login=_as_tuple2(merged.get("fallback_offsets", {}).get("password_from_login")),
    )
    click_offsets_cfg = MatchClickOffsetConfig(
        account=_as_tuple2(merged.get("click_offsets", {}).get("account")),
        password=_as_tuple2(merged.get("click_offsets", {}).get("password")),
    )
    credentials_cfg = CredentialConfig(**_clean_dict(merged.get("credentials", {})))
    app_cfg = AppProcessConfig(**_clean_dict(merged.get("app", {})))
    ui_cfg = UIConfig(**_clean_dict(merged.get("ui", {})))

    return AppConfig(
        logging=logging_cfg,
        automation=automation_cfg,
        templates=templates_cfg,
        regions=regions_cfg,
        fallback_offsets=fallback_cfg,
        click_offsets=click_offsets_cfg,
        credentials=credentials_cfg,
        app=app_cfg,
        ui=ui_cfg,
    )
