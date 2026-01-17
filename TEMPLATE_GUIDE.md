# 模板文件添加与制作说明

本文档用于指导你为 C30 智能教学自动登录添加模板图片，并保证识别稳定。

## 一、模板文件放哪

请把模板图片放到以下目录：

- resources/templates/

默认文件名（与 [config.toml](config.toml) 对应）：

单模板场景请只准备以下 5 个文件（每类只要 1 张）：

- sidebar_button.png（侧边栏按钮）
- on_course.png（上课按钮）
- account_input.png（账号输入框）
- password_input.png（密码输入框）
- login_button.png（登录按钮）

只要文件名和路径与 [config.toml](config.toml) 一致即可，缺的文件会导致程序报错并提示缺失列表。

---

## 二、如何截图（非常关键）

### 1. 截图原则

- **紧凑**：只截按钮/输入框本体，尽量不要包含空白区域。
- **稳定**：避免截图中包含会变化的内容（如输入框里的文字）。
- **清晰**：保持与实际使用时相同的分辨率和缩放比例。

### 2. 推荐截图方式

1. 打开 C30 登录界面。
2. 用系统截图工具（Win+Shift+S）裁剪，**每个文件按下面要求截取**。
3. 保存为 PNG 文件，放到 resources/templates/ 目录。

### 3. 单模板场景：每个文件怎么截

以下是**单模板场景**的标准做法（你说的“都一张”）：

1) sidebar_button.png（侧边栏按钮）

- 截取区域：侧边栏按钮整体（图标 + 边框 + 背景）
- 不要包含：按钮外的空白区域

2) on_course.png（上课按钮）

- 截取区域：按钮整体（图标 + 文字 + 圆角背景）
- 不要包含：按钮外的空白区域
- 提示：如果按钮在左或右都可能出现，但样式一样，只需截一张即可

3) account_input.png（账号输入框）

- 截取区域：输入框左侧图标 + 边框 + 输入框主体
- **避免包含**：输入框里的账号文字（内容变化会干扰识别）
- 可以在输入框为空时截图

4) password_input.png（密码输入框）

- 截取区域：输入框左侧图标 + 边框 + 输入框主体
- **避免包含**：密码圆点或文本
- 建议在密码为空时截图

5) login_button.png（登录按钮）

- 截取区域：按钮整体（文字 + 背景）
- 不要包含：按钮外的空白区域

### 4. 多模板场景（可选）

如果你想更稳定，可以为同一控件增加多张模板，并在 [config.toml](config.toml) 的数组中追加。

---

## 三、输入框有内容怎么办？

输入框内容变化可能导致识别不准，因此建议：

- **截图时不要包含输入内容**（只截边框+图标区域）。
- 同时提供“默认态 + 聚焦态”模板：
  - account_input.png
  - account_input_active.png
  - password_input.png
  - password_input_active.png

程序会在多模板中选择最匹配的一张。

---

## 四、配置文件如何指定模板

打开 [config.toml](config.toml)，配置如下：

```toml
[templates]
on_course = [
  "resources/templates/on_course.png",
  "resources/templates/on_course_right.png"
]
account_input = [
  "resources/templates/account_input.png",
  "resources/templates/account_input_active.png"
]
password_input = [
  "resources/templates/password_input.png",
  "resources/templates/password_input_active.png"
]
login_button = [
  "resources/templates/login_button.png",
  "resources/templates/login_button_active.png"
]
```

如果你用了不同文件名，只要在这里改成你的文件名即可。

---

## 五、识别不稳定时的排查建议

1. **提高模板质量**：重新截取更紧凑的图片。
2. **补充多个模板**：同一控件多截几张，在数组中追加。
3. **限制识别区域**：在 [config.toml](config.toml) 中设置 `regions.login_area`，例如：

```toml
[regions]
on_course = null
login_area = [900, 200, 900, 700]
```

> 数组含义为 `[x, y, w, h]`，可通过截图工具读坐标。

---

## 六、常见问题

**Q1：截图后还是识别不到？**
- 检查是否缩放比例改变（例如显示设置 125%）。
- 确保登录界面未被遮挡。

**Q2：只想用一个模板可以吗？**
- 可以，把数组里只留一个文件即可。

**Q3：一定要 PNG 吗？**
- 推荐 PNG（无损），JPG 也能用，但可能影响识别。

---

如果你需要我根据你的截图做模板裁剪规范，直接发图即可，我可以给出具体裁剪建议。