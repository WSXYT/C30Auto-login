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

## 目录结构

```text
C30Auto-login/
├── main.py              # 程序主入口
├── automator.py         # 核心自动化逻辑
├── image_matcher.py     # 图像识别与处理封装
├── config.py            # 配置加载与校验
├── config.toml          # 用户配置文件 (可自动生成)
├── logger_setup.py      # 日志初始化
├── ui_components.py     # PyQt6 UI 组件 (警告窗、横幅)
├── TEMPLATE_GUIDE.md    # 模板图片制作指南 (必读)
├── requirements.txt     # Python 依赖列表
└── resources/
    └── templates/       # 存放模板图片 (.png)
```

## 安装指南

### 1. 环境准备

确保已安装 [Python 3.10+](https://www.python.org/downloads/)。

### 2. 克隆项目

```bash
git clone https://github.com/your-username/C30Auto-login.git
cd C30Auto-login
```

### 3. 安装依赖

推荐使用虚拟环境：

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

安装所需包：

```bash
pip install -r requirements.txt
```

## 获取可执行文件 (无需安装 Python)

本项目支持通过 GitHub Actions 自动构建 Windows 可执行程序。

1.  在 GitHub 仓库的 **Actions** 页面下载最新的 `C30Auto-login-Windows` 压缩包。
2.  **解压整个压缩包**（不要只运行 exe，它依赖同级目录下的文件）。
3.  目录结构如下：
    *   `C30Auto-login.exe`: 主程序入口
    *   `lib/`: **核心依赖库文件夹**（DLL都在这里，请勿删除）
    *   `config.toml`: 配置文件
    *   `resources/`: 资源目录
4.  双击 `C30Auto-login.exe` 即可运行。

## 配置说明

### 1. 准备模板图片

这是最关键的一步。程序依赖图片模板来定位按钮。请详细阅读 [TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md) 指南，截取以下图片并放入 `resources/templates/` 目录：

*   `sidebar_button.png` (侧边栏按钮，可选)
*   `on_course.png` (上课按钮)
*   `account_input.png` (账号输入框)
*   `account_input_selected.png` (账号输入框-选中态，可选，推荐)
*   `password_input.png` (密码输入框)
*   `password_input_selected.png` (密码输入框-选中态，可选，推荐)
*   `login_button.png` (登录按钮)

💡 **提示**：为输入框同时准备“未选中”和“选中”两种状态的截图，可以大幅提高识别稳定性。程序会自动尝试匹配任意一张。

### 2. 编辑配置文件

首次运行会自动生成 `config.toml`。你可以手动创建并编辑它：

```toml
[credentials]
# 建议在此配置好账号密码，实现全自动
account = "your_username"
password = "your_password"

[app]
# 如果配置了路径，程序会尝试自动启动 C30
exe_path = "C:/Program Files/C30/C30.exe"
startup_wait = 10.0

[automation]
# 匹配精度，默认 0.82，识别困难可降低
match_threshold = 0.82
# 点击方式，推荐 sendinput
click_backend = "sendinput"
```

## 运行方式

### 命令行模式

```powershell
python main.py login -a "你的账号" -p "你的密码"
```

如果已在配置文件中填写了账号密码：

```powershell
python main.py login
```

### 调试模式

跳过部分步骤（例如跳过点击“上课”，直接开始输入账号）：

```powershell
python main.py login --debug-level 2
```

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

## 许可证

本项目采用 [MIT License](LICENSE) 许可证。
