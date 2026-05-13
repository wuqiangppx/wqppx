import random
import sys
from collections import deque
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MetricCard(QFrame):
    def __init__(self, title, value="--", unit="", color="#2563eb"):
        super().__init__()
        self.setObjectName("MetricCard")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.value_label = QLabel(f"{value}{unit}")
        self.value_label.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value, unit="", color="#2563eb"):
        self.value_label.setText(f"{value}{unit}")
        self.value_label.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")


class CurveWidget(QWidget):
    def __init__(self, title="实时曲线", unit="", max_points=160):
        super().__init__()
        self.title = title
        self.unit = unit
        self.max_points = max_points
        self.values = deque(maxlen=max_points)
        self.target = None
        self.setMinimumHeight(210)

    def append_value(self, value):
        self.values.append(float(value))
        self.update()

    def set_target(self, value):
        self.target = float(value)
        self.update()

    def clear(self):
        self.values.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        painter.setPen(QColor("#0f172a"))
        painter.drawText(rect.adjusted(12, 8, -12, -8), Qt.AlignTop | Qt.AlignLeft, self.title)

        plot = rect.adjusted(20, 44, -20, -24)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for i in range(1, 5):
            y = plot.top() + i * plot.height() / 5
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))

        if not self.values:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(plot, Qt.AlignCenter, "等待控制数据...")
            return

        data = list(self.values)
        min_v = min(data + ([self.target] if self.target is not None else []))
        max_v = max(data + ([self.target] if self.target is not None else []))
        if abs(max_v - min_v) < 1e-6:
            max_v += 1.0
            min_v -= 1.0
        margin = (max_v - min_v) * 0.15
        min_v -= margin
        max_v += margin

        if self.target is not None:
            ty = plot.bottom() - (self.target - min_v) * plot.height() / (max_v - min_v)
            painter.setPen(QPen(QColor("#dc2626"), 2, Qt.DashLine))
            painter.drawLine(plot.left(), int(ty), plot.right(), int(ty))
            painter.setPen(QColor("#dc2626"))
            painter.drawText(plot.right() - 110, int(ty) - 6, f"目标 {self.target:.2f}{self.unit}")

        points = []
        denom = max(1, self.max_points - 1)
        for i, value in enumerate(data):
            x = plot.left() + i * plot.width() / denom
            y = plot.bottom() - (value - min_v) * plot.height() / (max_v - min_v)
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#2563eb"), 2))
        for i in range(1, len(points)):
            painter.drawLine(points[i - 1], points[i])

        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.setPen(QColor("#64748b"))
        painter.drawText(plot.left(), plot.top() - 6, f"max {max(data):.2f}{self.unit}")
        painter.drawText(plot.left(), plot.bottom() + 16, f"min {min(data):.2f}{self.unit}")


class ForcePositionControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("力位混合控制功能页面 - 电缆接头机器人")
        self.resize(1560, 930)
        self.force_data = []
        self.depth_data = []
        self.position_error_data = []
        self.control_running = False
        self.contact_established = False
        self.tick = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.simulate_control_loop)
        self.init_ui()
        self.apply_style()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addLayout(self.create_header())
        root.addLayout(self.create_metric_row())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.create_left_panel())
        splitter.addWidget(self.create_center_panel())
        splitter.addWidget(self.create_right_panel())
        splitter.setSizes([360, 820, 380])
        root.addWidget(splitter, 1)
        root.addWidget(self.create_log_panel())

    def create_header(self):
        layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("力位混合控制功能页面")
        title.setObjectName("PageTitle")
        subtitle = QLabel("面向电缆剥切、环切、打磨等接触式作业，实现恒力控制、定深控制、阻抗/导纳控制、实时力监测与自适应参数调整")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.time_label = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.time_label.setObjectName("TimeLabel")
        clock = QTimer(self)
        clock.timeout.connect(lambda: self.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        clock.start(1000)

        layout.addLayout(title_box)
        layout.addStretch()
        layout.addWidget(self.time_label)
        return layout

    def create_metric_row(self):
        layout = QGridLayout()
        layout.setSpacing(12)
        self.card_control = MetricCard("控制状态", "待启动", "", "#64748b")
        self.card_contact = MetricCard("接触状态", "未接触", "", "#64748b")
        self.card_force = MetricCard("当前接触力", "0.0", " N", "#2563eb")
        self.card_depth = MetricCard("当前切深/进给", "0.00", " mm", "#2563eb")
        self.card_fluct = MetricCard("力控波动", "--", "", "#64748b")
        self.card_safety = MetricCard("安全状态", "正常", "", "#16a34a")
        for i, card in enumerate([
            self.card_control,
            self.card_contact,
            self.card_force,
            self.card_depth,
            self.card_fluct,
            self.card_safety,
        ]):
            layout.addWidget(card, 0, i)
        return layout

    def create_left_panel(self):
        box = QGroupBox("控制参数配置")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        mode_group = QGroupBox("作业与控制模式")
        mode_layout = QGridLayout(mode_group)
        self.process_combo = QComboBox()
        self.process_combo.addItems(["电缆剥切", "环切入刀", "铅笔头打磨", "表面清理", "接触试探"])
        self.control_combo = QComboBox()
        self.control_combo.addItems(["力位混合控制", "恒力控制", "定深控制", "阻抗控制", "导纳控制", "位置控制观察模式"])
        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["剥切刀", "环切刀", "打磨头", "清理工具", "检测探头"])
        self.frame_combo = QComboBox()
        self.frame_combo.addItems(["Tool坐标系", "Base坐标系", "Cable_Frame", "接触法向坐标系"])
        mode_layout.addWidget(QLabel("当前工序"), 0, 0)
        mode_layout.addWidget(self.process_combo, 0, 1)
        mode_layout.addWidget(QLabel("控制模式"), 1, 0)
        mode_layout.addWidget(self.control_combo, 1, 1)
        mode_layout.addWidget(QLabel("末端工具"), 2, 0)
        mode_layout.addWidget(self.tool_combo, 2, 1)
        mode_layout.addWidget(QLabel("控制坐标系"), 3, 0)
        mode_layout.addWidget(self.frame_combo, 3, 1)
        layout.addWidget(mode_group)

        param_group = QGroupBox("力位控制参数")
        param_layout = QGridLayout(param_group)
        self.target_force = self.make_spin(12.0, 0, 100, 0.5, " N")
        self.max_force = self.make_spin(25.0, 1, 200, 1, " N")
        self.target_depth = self.make_spin(1.20, 0, 20, 0.05, " mm")
        self.feed_speed = self.make_spin(2.0, 0.1, 50, 0.1, " mm/s")
        self.stiffness = self.make_spin(800.0, 10, 5000, 10, " N/m")
        self.damping = self.make_spin(45.0, 1, 500, 1, " Ns/m")
        self.adapt_gain = self.make_spin(0.35, 0, 5, 0.05, "")
        self.force_filter = self.make_spin(20.0, 1, 200, 1, " Hz")
        params = [
            ("目标力", self.target_force),
            ("最大安全力", self.max_force),
            ("目标切深", self.target_depth),
            ("进给速度", self.feed_speed),
            ("阻抗刚度K", self.stiffness),
            ("阻抗阻尼D", self.damping),
            ("自适应增益", self.adapt_gain),
            ("力信号滤波", self.force_filter),
        ]
        for r, (name, widget) in enumerate(params):
            param_layout.addWidget(QLabel(name), r, 0)
            param_layout.addWidget(widget, r, 1)
        layout.addWidget(param_group)

        btn_group = QGroupBox("控制操作")
        btn_layout = QGridLayout(btn_group)
        self.btn_apply = QPushButton("应用参数")
        self.btn_contact = QPushButton("接触建立")
        self.btn_start = QPushButton("启动控制")
        self.btn_pause = QPushButton("暂停")
        self.btn_reset = QPushButton("复位")
        self.btn_estop = QPushButton("急停")
        self.btn_estop.setObjectName("EmergencyButton")
        buttons = [self.btn_apply, self.btn_contact, self.btn_start, self.btn_pause, self.btn_reset, self.btn_estop]
        for i, btn in enumerate(buttons):
            btn.setMinimumHeight(38)
            btn_layout.addWidget(btn, i // 2, i % 2)
        layout.addWidget(btn_group)

        self.btn_apply.clicked.connect(self.apply_params)
        self.btn_contact.clicked.connect(self.establish_contact)
        self.btn_start.clicked.connect(self.start_control)
        self.btn_pause.clicked.connect(self.pause_control)
        self.btn_reset.clicked.connect(self.reset_control)
        self.btn_estop.clicked.connect(self.emergency_stop)

        layout.addStretch()
        return box

    def make_spin(self, value, min_value, max_value, step, suffix):
        spin = QDoubleSpinBox()
        spin.setRange(min_value, max_value)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setDecimals(2 if step < 1 else 1)
        return spin

    def create_center_panel(self):
        tabs = QTabWidget()

        realtime_page = QWidget()
        realtime_layout = QVBoxLayout(realtime_page)
        self.force_curve = CurveWidget("接触力实时曲线 F(t)", "N")
        self.depth_curve = CurveWidget("切深/进给量实时曲线 d(t)", "mm")
        self.error_curve = CurveWidget("位置误差/轨迹偏差 e(t)", "mm")
        realtime_layout.addWidget(self.force_curve)
        realtime_layout.addWidget(self.depth_curve)
        realtime_layout.addWidget(self.error_curve)
        tabs.addTab(realtime_page, "实时控制曲线")

        monitor_page = QWidget()
        monitor_layout = QVBoxLayout(monitor_page)
        monitor_layout.addWidget(self.create_state_table_group())
        monitor_layout.addWidget(self.create_control_progress_group())
        tabs.addTab(monitor_page, "状态监控")

        logic_page = QWidget()
        logic_layout = QVBoxLayout(logic_page)
        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setObjectName("DescriptionBox")
        desc.setText(
            "力位混合控制逻辑：\n\n"
            "1. 接触建立阶段：机械臂沿接触法向低速接近，实时监测力传感器，当接触力超过阈值后切换为柔顺控制。\n"
            "2. 恒力/定深阶段：法向方向采用力控或阻抗/导纳控制，切向方向采用位置/轨迹控制，实现剥切、打磨轨迹跟踪。\n"
            "3. 自适应调整阶段：根据力控波动、轨迹误差、切深偏差和工具状态，在线调整刚度、阻尼、进给速度和目标力。\n"
            "4. 安全保护阶段：当力值突变、工具未锁紧、轨迹偏差或质量指标超限时，触发暂停、回退或急停。\n"
            "5. 质量闭环阶段：将切深、表面质量、力控波动等结果反馈给任务管理和数据追溯模块。\n\n"
            "典型控制分配：\n"
            "- 法向方向：恒力/阻抗/导纳控制，保证接触稳定。\n"
            "- 切向方向：位置轨迹跟踪，保证路径准确。\n"
            "- 工具轴向：定深约束，避免过切和欠切。\n"
            "- 安全层：最大力、最大切深、碰撞边界和CBF约束。"
        )
        logic_layout.addWidget(desc)
        tabs.addTab(logic_page, "控制逻辑")
        return tabs

    def create_state_table_group(self):
        group = QGroupBox("控制状态明细")
        layout = QVBoxLayout(group)
        self.state_table = QTableWidget(0, 8)
        self.state_table.setHorizontalHeaderLabels(["时间", "工序", "控制模式", "目标力/N", "实际力/N", "切深/mm", "力控波动", "状态"])
        self.state_table.verticalHeader().setVisible(False)
        self.state_table.setAlternatingRowColors(True)
        self.state_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.state_table.horizontalHeader().setStretchLastSection(True)
        self.state_table.setColumnWidth(0, 130)
        self.state_table.setColumnWidth(1, 100)
        self.state_table.setColumnWidth(2, 120)
        self.state_table.setColumnWidth(3, 90)
        self.state_table.setColumnWidth(4, 90)
        self.state_table.setColumnWidth(5, 90)
        self.state_table.setColumnWidth(6, 90)
        layout.addWidget(self.state_table)
        return group

    def create_control_progress_group(self):
        group = QGroupBox("控制过程进度")
        layout = QGridLayout(group)
        self.progress_contact = QProgressBar()
        self.progress_force = QProgressBar()
        self.progress_depth = QProgressBar()
        self.progress_quality = QProgressBar()
        for bar in [self.progress_contact, self.progress_force, self.progress_depth, self.progress_quality]:
            bar.setRange(0, 100)
            bar.setValue(0)
        self.progress_contact.setFormat("接触建立：%p%")
        self.progress_force.setFormat("力控稳定：%p%")
        self.progress_depth.setFormat("定深跟踪：%p%")
        self.progress_quality.setFormat("质量闭环：%p%")
        layout.addWidget(self.progress_contact, 0, 0)
        layout.addWidget(self.progress_force, 0, 1)
        layout.addWidget(self.progress_depth, 1, 0)
        layout.addWidget(self.progress_quality, 1, 1)
        return group

    def create_right_panel(self):
        box = QGroupBox("安全约束与质量闭环")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        safety_group = QGroupBox("安全约束")
        safety_layout = QGridLayout(safety_group)
        self.safe_force = QLabel("最大力≤25 N")
        self.safe_depth = QLabel("最大切深≤2.0 mm")
        self.safe_tool = QLabel("工具锁紧：已确认")
        self.safe_collision = QLabel("碰撞检测：通过")
        self.safe_person = QLabel("人员安全区：正常")
        for label in [self.safe_force, self.safe_depth, self.safe_tool, self.safe_collision, self.safe_person]:
            label.setObjectName("ValueText")
        rows = [
            ("力限保护", self.safe_force),
            ("定深保护", self.safe_depth),
            ("工具互锁", self.safe_tool),
            ("碰撞检测", self.safe_collision),
            ("人机安全", self.safe_person),
        ]
        for r, (name, label) in enumerate(rows):
            safety_layout.addWidget(QLabel(name), r, 0)
            safety_layout.addWidget(label, r, 1)
        layout.addWidget(safety_group)

        adapt_group = QGroupBox("自适应调整建议")
        adapt_layout = QVBoxLayout(adapt_group)
        self.adapt_text = QTextEdit()
        self.adapt_text.setReadOnly(True)
        self.adapt_text.setObjectName("OutputBox")
        self.adapt_text.setText("等待控制数据...\n\n建议内容包括：\n- 目标力调整\n- 进给速度调整\n- 刚度/阻尼增益调度\n- 轨迹法向修正\n- 异常恢复策略")
        adapt_layout.addWidget(self.adapt_text)
        layout.addWidget(adapt_group, 1)

        kpi_group = QGroupBox("质量KPI与判定")
        kpi_layout = QGridLayout(kpi_group)
        self.kpi_force = QLabel("--")
        self.kpi_depth = QLabel("--")
        self.kpi_error = QLabel("--")
        self.kpi_result = QLabel("待检测")
        for label in [self.kpi_force, self.kpi_depth, self.kpi_error, self.kpi_result]:
            label.setObjectName("ValueText")
        kpi_layout.addWidget(QLabel("力控波动"), 0, 0)
        kpi_layout.addWidget(self.kpi_force, 0, 1)
        kpi_layout.addWidget(QLabel("切深偏差"), 1, 0)
        kpi_layout.addWidget(self.kpi_depth, 1, 1)
        kpi_layout.addWidget(QLabel("轨迹误差"), 2, 0)
        kpi_layout.addWidget(self.kpi_error, 2, 1)
        kpi_layout.addWidget(QLabel("判定结论"), 3, 0)
        kpi_layout.addWidget(self.kpi_result, 3, 1)
        layout.addWidget(kpi_group)
        return box

    def create_log_panel(self):
        box = QGroupBox("系统日志")
        layout = QVBoxLayout(box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setObjectName("LogBox")
        layout.addWidget(self.log)
        self.add_log("系统初始化完成，等待接触建立与力位混合控制启动。")
        return box

    def apply_params(self):
        self.force_curve.set_target(self.target_force.value())
        self.depth_curve.set_target(self.target_depth.value())
        self.safe_force.setText(f"最大力≤{self.max_force.value():.1f} N")
        self.safe_depth.setText(f"最大切深≤{max(self.target_depth.value() + 0.8, self.target_depth.value()):.2f} mm")
        self.add_log(
            f"控制参数已应用：目标力{self.target_force.value():.1f}N，目标切深{self.target_depth.value():.2f}mm，"
            f"K={self.stiffness.value():.1f}N/m，D={self.damping.value():.1f}Ns/m。"
        )

    def establish_contact(self):
        self.contact_established = True
        self.card_contact.set_value("已接触", "", "#16a34a")
        self.progress_contact.setValue(100)
        self.add_log("完成接触建立：低速接近并检测到稳定接触力，允许切换至柔顺控制。")

    def start_control(self):
        if not self.contact_established:
            QMessageBox.warning(self, "提示", "请先执行接触建立，确认末端与电缆表面接触稳定。")
            return
        self.control_running = True
        self.card_control.set_value("运行中", "", "#2563eb")
        self.force_curve.set_target(self.target_force.value())
        self.depth_curve.set_target(self.target_depth.value())
        self.timer.start(300)
        self.add_log("启动力位混合控制闭环。")

    def pause_control(self):
        self.control_running = False
        self.timer.stop()
        self.card_control.set_value("已暂停", "", "#f59e0b")
        self.add_log("控制已暂停，机器人保持当前安全位姿。")

    def reset_control(self):
        self.timer.stop()
        self.control_running = False
        self.contact_established = False
        self.tick = 0
        self.force_data.clear()
        self.depth_data.clear()
        self.position_error_data.clear()
        self.force_curve.clear()
        self.depth_curve.clear()
        self.error_curve.clear()
        self.state_table.setRowCount(0)
        for bar in [self.progress_contact, self.progress_force, self.progress_depth, self.progress_quality]:
            bar.setValue(0)
        self.card_control.set_value("待启动", "", "#64748b")
        self.card_contact.set_value("未接触", "", "#64748b")
        self.card_force.set_value("0.0", " N", "#2563eb")
        self.card_depth.set_value("0.00", " mm", "#2563eb")
        self.card_fluct.set_value("--", "", "#64748b")
        self.card_safety.set_value("正常", "", "#16a34a")
        self.kpi_force.setText("--")
        self.kpi_depth.setText("--")
        self.kpi_error.setText("--")
        self.kpi_result.setText("待检测")
        self.adapt_text.setText("等待控制数据...")
        self.add_log("控制状态已复位。")

    def emergency_stop(self):
        self.timer.stop()
        self.control_running = False
        self.card_control.set_value("急停", "", "#dc2626")
        self.card_safety.set_value("急停", "", "#dc2626")
        self.add_log("急停触发：停止机械臂运动，关闭工具输出，进入安全保护状态。")
        QMessageBox.warning(self, "急停", "已触发急停，请检查现场接触力、工具锁紧和作业空间安全。")

    def simulate_control_loop(self):
        self.tick += 1
        target_f = self.target_force.value()
        target_d = self.target_depth.value()
        max_force = self.max_force.value()

        # 模拟闭环：初期逐步稳定，后期小幅波动
        settle = min(1.0, self.tick / 25.0)
        force = target_f * settle + random.gauss(0, 0.35 + 0.35 * (1 - settle))
        force = max(0.0, force)
        depth = target_d * min(1.0, self.tick / 35.0) + random.gauss(0, 0.025)
        depth = max(0.0, depth)
        position_error = max(0.0, random.gauss(0.65, 0.18))

        self.force_data.append(force)
        self.depth_data.append(depth)
        self.position_error_data.append(position_error)
        self.force_curve.append_value(force)
        self.depth_curve.append_value(depth)
        self.error_curve.append_value(position_error)

        window = self.force_data[-30:]
        mean_f = sum(window) / len(window)
        fluct = (sum((x - mean_f) ** 2 for x in window) / len(window)) ** 0.5 / max(mean_f, 1e-6) * 100
        depth_error = abs(depth - target_d)

        self.card_force.set_value(f"{force:.2f}", " N", "#16a34a" if force <= max_force else "#dc2626")
        self.card_depth.set_value(f"{depth:.2f}", " mm", "#16a34a" if depth_error <= 0.15 else "#f59e0b")
        self.card_fluct.set_value(f"{fluct:.2f}", "%", "#16a34a" if fluct <= 5 else "#dc2626")

        force_stable = max(0, min(100, int(100 - abs(force - target_f) / max(target_f, 1e-6) * 100)))
        depth_track = max(0, min(100, int(100 - depth_error / max(target_d, 1e-6) * 100)))
        quality_score = int((force_stable * 0.45 + depth_track * 0.35 + max(0, 100 - position_error * 15) * 0.2))
        self.progress_force.setValue(force_stable)
        self.progress_depth.setValue(depth_track)
        self.progress_quality.setValue(max(0, min(100, quality_score)))

        safe = force <= max_force and depth <= target_d + 0.8
        self.card_safety.set_value("正常" if safe else "超限", "", "#16a34a" if safe else "#dc2626")

        self.kpi_force.setText(f"{fluct:.2f}% / ≤5%")
        self.kpi_depth.setText(f"{depth_error:.3f} mm")
        self.kpi_error.setText(f"{position_error:.2f} mm")
        result_ok = fluct <= 5 and depth_error <= 0.15 and position_error <= 1.0 and safe
        self.kpi_result.setText("合格" if result_ok else "需调整")

        if result_ok:
            suggestion = "控制稳定：保持当前目标力、进给速度与阻抗参数。"
            result_color = QColor("#dcfce7")
        elif fluct > 5:
            suggestion = "力控波动偏大：建议降低进给速度，提高阻尼D，或降低自适应增益。"
            result_color = QColor("#fee2e2")
        elif depth_error > 0.15:
            suggestion = "切深偏差偏大：建议重新确认电缆表面法向，减小位置步长并更新定深补偿。"
            result_color = QColor("#fef3c7")
        else:
            suggestion = "轨迹误差偏大：建议重新规划局部轨迹或执行外参/工具TCP补偿。"
            result_color = QColor("#fef3c7")
        self.adapt_text.setText(
            f"自适应建议：\n{suggestion}\n\n"
            f"当前模式：{self.control_combo.currentText()}\n"
            f"当前工序：{self.process_combo.currentText()}\n"
            f"目标力：{target_f:.2f} N\n"
            f"实际力：{force:.2f} N\n"
            f"力控波动：{fluct:.2f}%\n"
            f"目标切深：{target_d:.2f} mm\n"
            f"实际切深：{depth:.2f} mm\n"
            f"轨迹误差：{position_error:.2f} mm"
        )

        self.add_state_row(force, depth, fluct, "合格" if result_ok else "需调整", result_color)

        if force > max_force:
            self.pause_control()
            self.card_safety.set_value("力超限", "", "#dc2626")
            self.add_log(f"安全暂停：当前力{force:.2f}N超过最大安全力{max_force:.2f}N。")
            return

    def add_state_row(self, force, depth, fluct, status, color):
        row = self.state_table.rowCount()
        if row > 120:
            self.state_table.removeRow(0)
            row -= 1
        self.state_table.insertRow(row)
        values = [
            datetime.now().strftime("%H:%M:%S.%f")[:-3],
            self.process_combo.currentText(),
            self.control_combo.currentText(),
            f"{self.target_force.value():.2f}",
            f"{force:.2f}",
            f"{depth:.3f}",
            f"{fluct:.2f}%",
            status,
        ]
        for c, val in enumerate(values):
            item = QTableWidgetItem(val)
            if c in [3, 4, 5, 6, 7]:
                item.setTextAlignment(Qt.AlignCenter)
            if c == 7:
                item.setBackground(color)
            self.state_table.setItem(row, c, item)
        self.state_table.scrollToBottom()

    def add_log(self, message):
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #f1f5f9; }
            QLabel { color: #0f172a; font-size: 13px; }
            #PageTitle { font-size: 23px; font-weight: 900; color: #0f172a; }
            #Subtitle { color: #64748b; font-size: 13px; }
            #TimeLabel { color: #334155; font-size: 14px; font-weight: 700; }
            #MetricCard {
                background: #ffffff;
                border: 1px solid #dbe3ef;
                border-radius: 14px;
            }
            #MetricTitle { color: #64748b; font-size: 12px; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dbe3ef;
                border-radius: 14px;
                margin-top: 12px;
                padding: 12px;
                font-weight: 800;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #0f172a;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                min-height: 28px;
                padding: 4px 8px;
            }
            QPushButton {
                background: #0f172a;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 10px;
                font-weight: 800;
            }
            QPushButton:hover { background: #1e293b; }
            #EmergencyButton { background: #dc2626; }
            #EmergencyButton:hover { background: #b91c1c; }
            QTabWidget::pane {
                border: 1px solid #dbe3ef;
                border-radius: 12px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #e2e8f0;
                padding: 9px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 3px;
                color: #334155;
            }
            QTabBar::tab:selected {
                background: #1e3a8a;
                color: #ffffff;
                font-weight: 800;
            }
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #dbe3ef;
                gridline-color: #e2e8f0;
                border-radius: 8px;
            }
            QHeaderView::section {
                background: #1e3a8a;
                color: white;
                padding: 8px;
                border: none;
                font-weight: 800;
            }
            QTextEdit {
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px;
                color: #334155;
            }
            #DescriptionBox, #OutputBox {
                font-family: Consolas, "Microsoft YaHei";
                line-height: 1.6;
            }
            #LogBox {
                background: #0f172a;
                color: #dbeafe;
                font-family: Consolas, "Microsoft YaHei";
            }
            #ValueText { color: #2563eb; font-weight: 800; }
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                text-align: center;
                height: 24px;
                background: #f8fafc;
            }
            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 9px;
            }
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = ForcePositionControlWindow()
    window.show()
    sys.exit(app.exec_())
