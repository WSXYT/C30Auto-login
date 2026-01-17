"""UI 组件。

包含：
1. WarningDialog：执行前确认/倒计时弹窗
2. ScrollingBanner：顶部滚动警示条
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QFontMetrics

class WarningDialog(QDialog):
    """执行前确认弹窗（带倒计时）。"""

    def __init__(self, timeout=10):
        super().__init__()
        self.timeout = timeout
        # 0: cancel, 1: run now, 2: delay（保留字段，便于后续扩展）
        self.result_code = None
        self.setWindowTitle("C30Auto-login")
        self.setFixedSize(450, 280)
        # 始终置顶且无边框
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        # 样式表定义界面风格
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
                border: 1px solid #dcdcdc;
            }
            QLabel#Title {
                font-size: 28px;
                font-weight: bold;
                color: #333333;
            }
            QLabel#SubTitle {
                font-size: 18px;
                color: #666666;
            }
            QPushButton {
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 16px;
                min-width: 80px;
            }
            QPushButton#Cancel {
                background-color: white;
                border: 1px solid #dcdcdc;
                color: #333333;
            }
            QPushButton#Delay {
                background-color: white;
                border: 1px solid #dcdcdc;
                color: #333333;
            }
            QPushButton#RunNow {
                background-color: #3498db;
                color: white;
                border: none;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 40, 30, 30)
        layout.setSpacing(20)

        # Header：警告图标 + 标题
        header_layout = QHBoxLayout()
        warning_icon_label = QLabel("⚠️")
        warning_icon_label.setStyleSheet("font-size: 40px;")
        header_layout.addWidget(warning_icon_label)

        title_label = QLabel("正在运行C30自动登录")
        title_label.setObjectName("Title")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 倒计时提示
        self.time_label = QLabel(f"将在 {self.timeout} 秒后继续执行")
        self.time_label.setObjectName("SubTitle")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        cancel_btn = QPushButton("✕ 取消")
        cancel_btn.setObjectName("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        delay_btn = QPushButton("⏸ 推迟")
        delay_btn.setObjectName("Delay")
        # 这里的“推迟”暂时实现为停止倒计时
        delay_btn.clicked.connect(self.stop_timer)

        run_btn = QPushButton("✓ 立即执行")
        run_btn.setObjectName("RunNow")
        run_btn.clicked.connect(self.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(delay_btn)
        btn_layout.addWidget(run_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # 启动倒计时
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

    def update_timer(self):
        """倒计时更新。"""

        self.timeout -= 1
        if self.timeout <= 0:
            # 时间到自动确认
            self.accept()
        else:
            self.time_label.setText(f"将在 {self.timeout} 秒后继续执行")

    def stop_timer(self):
        """停止倒计时并提示已推迟。"""

        self.timer.stop()
        self.time_label.setText("执行已推迟")

class ScrollingBanner(QWidget):
    """顶部滚动警示条。"""

    def __init__(self, text="正在运行希沃白板自动登录 请勿触摸一体机", height=80):
        super().__init__()
        # 显示内容前加入警告标识
        self.display_text = f"⚠️WARNING⚠️ {text}"
        # 增加空格以增大间距，实现首尾相接
        spacing = " " * 15
        self.scroll_text_content = f"{self.display_text}{spacing}"

        # 无边框 + 置顶 + 工具窗口
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 获取屏幕尺寸，铺满整个宽度
        screen = QApplication.primaryScreen().geometry()
        self.setFixedWidth(screen.width())
        self.setFixedHeight(height)
        self.move(0, 0)

        # 配色：红色背景 + 黄色条纹/文字
        self.bg_color = QColor("#d90000")
        self.stripe_color = QColor("#ffcc00")
        self.text_color = QColor("#ffcc00")

        # 使用浮点 offset 实现更平滑的滚动
        self.offset = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scroll_text)
        self.timer.start(16)

    def paintEvent(self, event):
        """自定义绘制：背景、条纹、滚动文字。"""

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            # 1) 绘制主体背景（红色）
            painter.setBrush(QBrush(self.bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(0, 0, self.width(), self.height())

            # 2) 绘制上下警示条纹（更密集的黄红相间）
            stripe_height = 15
            self._draw_stripes(painter, 0, stripe_height)
            self._draw_stripes(painter, self.height() - stripe_height, stripe_height)

            # 3) 绘制滚动文字
            painter.setPen(self.text_color)
            font_text = QFont("Microsoft YaHei", 32, QFont.Weight.Bold)
            painter.setFont(font_text)

            metrics = painter.fontMetrics()
            single_text_width = metrics.horizontalAdvance(self.scroll_text_content)

            if single_text_width <= 0:
                return

            x_pos = -self.offset

            # 循环绘制，实现首尾衔接
            while x_pos < self.width():
                painter.drawText(
                    int(x_pos),
                    0,
                    int(single_text_width),
                    self.height(),
                    Qt.AlignmentFlag.AlignVCenter,
                    self.scroll_text_content,
                )
                x_pos += single_text_width
        finally:
            painter.end()

    def _draw_stripes(self, painter, y, h):
        """绘制斜向警示条纹（黄红相间）。"""

        painter.save()
        painter.setClipRect(0, y, self.width(), h)

        stripe_width = 15  # 缩小宽度使其更密集
        painter.setBrush(QBrush(self.stripe_color))

        # 每隔一个 stripe_width 绘制一个黄色平行四边形
        for i in range(-stripe_width * 4, self.width() + stripe_width * 2, stripe_width * 2):
            points = [
                QPoint(i, y),
                QPoint(i + stripe_width, y),
                QPoint(i + stripe_width * 2, y + h),
                QPoint(i + stripe_width, y + h),
            ]
            painter.drawPolygon(points)
        painter.restore()

    def scroll_text(self):
        """滚动逻辑：更新偏移并触发重绘。"""

        self.offset += 2.5

        font_text = QFont("Microsoft YaHei", 32, QFont.Weight.Bold)
        metrics = QFontMetrics(font_text)
        single_text_width = metrics.horizontalAdvance(self.scroll_text_content)

        # 文字滚动一轮后从头开始
        if single_text_width > 0 and self.offset >= single_text_width:
            self.offset -= single_text_width

        self.update()
