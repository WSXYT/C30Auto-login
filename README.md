# C30 智能教学自动登录工具

一个基于图像识别（OpenCV）与自动化控制（PyAutoGUI/SendInput）的 C30 教学软件自动登录工具。专为简化教室场景下的日常登录流程而设计，支持自动降级匹配、输入框回退定位以及完善的异常处理。

## 主要特性

*   **智能图像识别**：使用 OpenCV 模板匹配，支持多分辨率与自适应阈值扫描，提高在不同光照或界面微调下的识别率。
*   **鲁棒的自动化流程**：
    *   **失败重试**：关键步骤（如点击上课）支持自动重试。
    *   **回退机制**：若输入框识别失败，可根据"登录按钮"的位置进行相对坐标回退，确保输入准确。
    *   **多后端点击**：支持 `SendInput` (底层 API)、`win32api` 和 `pyautogui`，解决某些场景下点击无效的问题。
*   **安全与监控**：
    *   集成 **Sentry** 错误监控，自动上报崩溃与异常。
    *   执行前 **UI 警告弹窗**，防止误操作。
    *   **顶部滚动横幅**，提示正在运行，避免用户干扰。
*   **配置灵活**：所有关键参数（阈值、路径、账号、超时时间）均可在 `config.toml` 中配置。

## 快速使用

### 1. 下载程序

请前往本仓库的 [Releases](../../releases) 页面，下载最新版本的 `C30Auto-login-Windows.zip` 压缩包。

### 2. 解压说明

1.  下载后，请**解压整个压缩包**到任意文件夹。
2.  **重要的事说三遍**：不要只把 `.exe` 拖出来运行！不要只把 `.exe` 拖出来运行！程序依赖同级目录下的资源文件。
3.  解压后的目录结构如下：
    *   `C30Auto-login.exe`: 主程序入口
    *   `config.toml`: 配置文件（已预设好参数 **但是要更新c30目录**）
    *   `resources/`: 内含默认的模板图片（**开箱即用，通常不需要你自己截图**）
    *   `lib/`: 核心依赖库文件夹（请勿删除）

## 配置说明

### 1. 编辑配置文件 (必须步骤)

打开文件夹中的 `config.toml` 文件（记事本即可打开）。

**最重要的一步**：
请务必找到 `[app]` 下的 `exe_path`，将其修改为你电脑上 **C30 教学软件** 的实际安装路径。

```toml
[app]
# 修改为你本机 C30 的真实路径，注意路径中的斜杠
exe_path = "D:\\Program Files (x86)\\Datedu\\teach\\1.3.1460.0\\teach\\teachingtools\\teach.exe"
# 分别配置上课按钮和登录窗口的类名（使用 Spy++ 获取），空则不限制
window_class_on_course = ""
window_class_login = ""
```

如果没有配置正确的路径，程序将无法自动启动 C30 软件（只能操作已经手动打开的窗口）。

### 2. 模板图片 (一般无需修改)

发布包中已内置了通用的模板图片 (`resources/templates/`)。
*   默认配置已启用了**偏移点击**功能，能够适应大多数分辨率。
*   **只有当你发现程序完全无法识别界面时**，才需要参考 [TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md) 自行截图替换。

### 3. 详细配置参数

如果你需要微调识参数，可以参考文件中的注释。

```toml
# ================= 日志配置 =================
[logging]
level = "INFO"          # 日志等级：DEBUG (调试细节) / INFO (常规)
dir = "logs"            # 日志文件存放目录

# ================= 自动化参数 (核心与容错) =================
[automation]
max_retries = 2         # 单个步骤失败时的重试次数
max_fallbacks = 6       # 整个流程允许回退的总次数 (超过则报错退出)
on_course_retries = 2   # 第一步“上课”按钮的特殊重试次数
retry_interval = 0.5    # 重试前的等待秒数
on_course_wait = 5.0    # “上课”按钮点击后的等待时间 (秒)
step_timeout = 12.0     # 每个步骤寻找图片的最大超时时间 (秒)
match_threshold = 0.82  # 图片匹配相似度阈值 (0.0-1.0)，越高越严格
click_backend = "sendinput" # 点击方式：sendinput (推荐) / win32api / pyautogui
debug_level = 0         # 调试模式：0=正常; 2=跳过点击上课按钮 (直接输账号)

# ================= 界面显示 =================
[ui]
banner_text = "正在运行C30自动登录 请勿触摸一体机" # 屏幕顶部横幅文字
banner_height = 80      # 横幅高度
warning_timeout = 10    # 启动前的倒计时警告时间 (秒)

# ================= 模板图片 (支持多张) =================
[templates]
# 列表格式，若有多种样式的按钮，可放多个图片路径
sidebar_button = ["resources/templates/sidebar_button.png"]
on_course = ["resources/templates/on_course.png"]
# 输入框建议同时提供“未选中”和“选中”两种截图
account_input = [
    "resources/templates/account_input.png",
    "resources/templates/account_input_selected.png"
]
password_input = [
    "resources/templates/password_input.png",
    "resources/templates/password_input_selected.png"
]
login_button = ["resources/templates/login_button.png"]

# ================= 账号密码 =================
[credentials]
# 账号与密码（不建议提交到公共仓库，建议使用命令行参数传入）
# 密码可为空：如果为空，程序将跳过输入密码的步骤（直接点击登录），适用于已记住密码的场景
account = ""
password = ""

# ================= 目标程序路径 =================
[app]
# 【重要】C30 程序的完整路径。如果没填，程序只能操作已经打开的窗口，无法自动启动软件
# 注意 Windows 路径中的反斜杠 \ 需要写成双反斜杠 \\ 或使用单斜杠 /
exe_path = "D:\\Program Files (x86)\\Datedu\\teach\\1.3.1460.0\\teach\\teachingtools\\teach.exe"
startup_wait = 15.0      # 启动软件后等待其加载的时间 (秒)

# ================= 偏移点击 (高级功能) =================
# 当输入框内已有文字导致无法识别时，可以使用“相对定位法”：
# 1. 截图截取输入框左侧固定的“图标”或“文字”
# 2. 此处配置向右偏移多少像素去点击输入框
# 3. 基本不用动
[click_offsets]
account = [150, 0]    # 识别到图片中心后，向右偏 150px，Y轴不变（根据实际模板调整）
password = [150, 0]
```

## 运行方式 (使用最终打包程序)

如果你使用的是下载的压缩包 (`C30Auto-login-Windows.zip`)，请按照以下方式运行。

### 1. 普通运行 (推荐)
直接双击文件夹中的 **`C30Auto-login.exe`**。
*   程序会自动读取 `config.toml` 中的账号密码。
*   如果配置了 `exe_path`，会自动启动 C30。

### 2. 命令行传参 (临时登录)
如果你不想把密码写在文件里，或者需要通过脚本调用，可以使用命令行参数：

1.  在 `C30Auto-login.exe` 所在文件夹空白处 -> 右键 -> 在终端中打开。
2.  输入以下命令：

```powershell
```powershell
# 此时使用的是 set 的账号密码，优先级高于配置文件
# 注意：密码选项 -p 是可选的，如果未提供且配置文件也没写，将跳过密码输入步骤（适用于已保存密码的情况）
.\C30Auto-login.exe login -a "zhangsan"
```

### 3. 调试运行
如果遇到问题，可以开启调试模式查看详情：

```powershell
# 跳过第一步(上课按钮)，直接从输入账号开始测试
.\C30Auto-login.exe login --debug-level 2
```

### 4. Classisland自动化
建议配合Classisland自动化使用

## 常见问题处理

1.  **输入框内有文字导致识别失败（密码输了两遍）**：
    *   **原因**：如果输入框内已经有文字，原本截取的“空白输入框图片”就匹配不上了。
    *   **解决方法**：
        1.  **重新截图**：不要截整个输入框，改为截取输入框左侧**固定不变的图标或文字（如“账号：”）**。
        2.  **配置偏移**：在 `config.toml` 中设置 `[click_offsets]`，让程序识别到左侧图标后，向右偏 X 像素点击真正的输入区域。
        ```toml
        [click_offsets]
        # 向右偏移 150 像素点击
        account = [150, 0]
        ```

2.  **无法点击或无反应**：
    *   C30 程序通常需要**管理员权限**才能被控制。本工具会自动尝试提权，请在 UAC 弹窗中选择“是”。
    *   尝试在 `config.toml` 中修改 `click_backend` 为 `win32api` 或 `pyautogui`。

2.  **识别不到图片**：
    *   确保截图是在**实际运行分辨率**下截取的（不要缩放）。
    *   检查截图是否包含变动的背景或文字。
    *   在 `config.toml` 中适当降低 `match_threshold` (如 0.75)。

3.  **日志查看**：
    *   程序运行日志保存在 `logs/` 目录下，按日期分割。
    *   崩溃信息会自动发送至 Sentry 后台。

## 二次开发指南

如果你想修改源码使用：

1.  **环境准备**：Python 3.10+
2.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```
3.  **运行源码**：
    ```bash
    python main.py login
    ```
4.  **打包发布**：
    本项目使用 GitHub Actions 自动打包。若需本地打包：
    ```bash
    pyinstaller main.spec
    ```

## 许可证

本项目采用 [MIT License](LICENSE) 许可证。
