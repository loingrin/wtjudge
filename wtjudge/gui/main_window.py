from __future__ import annotations

import copy
import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QStackedWidget, QTableWidget, QToolBar, QVBoxLayout, QWidget)

from wtjudge.core.compiler import validate_compiler
from wtjudge import __version__
from wtjudge.core.judge import judge_batch
from wtjudge.core.models import MODES, STATUS_TEXT, Project, natural_key
from wtjudge.core.scanner import scan_project
from wtjudge.reports.exporter import NOTICE, WARNING, export_reports
from wtjudge.storage.project import load_project, save_project
from wtjudge.presentation import score_colours, uniform_error
from .dialogs import DetailDialog, ProblemDialog, cell, spin
from .worker import Worker
from .resources import asset_path
from .theme import GLASS_STYLE, GlassBackdrop, colour_status, line_icon, notice_tone, soft_shadow
from .table_items import ColourPreservingDelegate

SAFETY = "学生程序将以当前 Windows 用户权限运行，可能访问本机文件。请仅评测可信来源的提交；如有风险，请在 Windows Sandbox 或独立虚拟机内运行。"


def page(title, subtitle=""):
    widget = QWidget()
    widget.setObjectName("workPage")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(28, 10, 28, 22)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("heading")
    layout.addWidget(heading)
    return widget, layout


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().setVisible(False)
    widget.verticalHeader().setDefaultSectionSize(38)
    return widget


def metric(label, tone="green"):
    frame = QFrame()
    frame.setObjectName("metric")
    frame.setProperty("tone", tone)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 3, 18, 3)
    layout.setSpacing(8)
    value = QLabel("—")
    value.setObjectName("metricValue")
    layout.addWidget(value)
    caption = QLabel(label)
    caption.setObjectName("metricLabel")
    layout.addWidget(caption)
    layout.addStretch()
    return frame, value


def result_counts(batch):
    if batch is None:
        return 0, 0, 0, 0
    valid = sum(p.status not in {"CANCELLED", "SYSTEM_ERROR", "AMBIGUOUS_SOURCE"} for p in batch.points)
    ran = sum(p.exit_code is not None for p in batch.points)
    return valid, max(0, batch.expected_points - valid), ran, sum(p.status == "AC" for p in batch.points)


class NumericItem(type(cell(""))):
    def __lt__(self, other):
        a, b = self.data(Qt.ItemDataRole.UserRole), other.data(Qt.ItemDataRole.UserRole)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return natural_key(self.text()) < natural_key(other.text())


class MainWindow(QMainWindow):
    def __init__(self, auto_check=True):
        super().__init__()
        self.setWindowTitle(f"wtjudge v{__version__}")
        self.setWindowIcon(QIcon(str(asset_path("wotu.ico"))))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#91af76"))
        self.setPalette(palette)
        self.setMinimumSize(960, 600)
        available = self.screen().availableGeometry()
        self.resize(min(1240, int(available.width() * .94)), min(800, int(available.height() * .92)))
        self.settings = QSettings("wtjudge", "wtjudge")
        self.project = Project(compiler_path=self.settings.value("compiler_path", ""))
        self.project_path = ""
        self.scan = self.batch = self.worker = None
        self.compiler_verified = ""
        self.busy_kind = ""
        self.safety_confirmed = False
        self.last_export = ""
        self.judge_started = 0
        self.last_result_refresh = 0
        self.result_sort_initialized = False
        self.cleanup_notices = []
        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_elapsed)
        self.timer.start(250)
        if not self.project.compiler_path:
            candidates = [shutil.which("g++"), r"C:\msys64\ucrt64\bin\g++.exe", r"C:\mingw64\bin\g++.exe"]
            self.project.compiler_path = next((p for p in candidates if p and Path(p).is_file()), "")
        self.sync_fields()
        if auto_check and self.project.compiler_path:
            QTimer.singleShot(100, self.check_compiler)

    def _build(self):
        backdrop = GlassBackdrop()
        backdrop_layout = QVBoxLayout(backdrop)
        backdrop_layout.setContentsMargins(15, 13, 15, 13)
        shell = QFrame()
        shell.setObjectName("applicationShell")
        soft_shadow(shell)
        backdrop_layout.addWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(178)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(7, 27, 7, 20)
        branding = QHBoxLayout()
        branding.setContentsMargins(13, 0, 10, 24)
        self.logo = QLabel()
        self.logo.setObjectName("logo")
        self.logo.setPixmap(QPixmap(str(asset_path("wotu.png"))).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        branding.addWidget(self.logo)
        brand = QLabel("wtjudge")
        brand.setObjectName("brand")
        branding.addWidget(brand, 1)
        side_layout.addLayout(branding)
        self.nav = QListWidget()
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setSpacing(2)
        for title, icon in [("导入考试", "folder"), ("题目配置", "settings"), ("评测", "play"), ("成绩", "chart"), ("导出", "export")]:
            self.nav.addItem(QListWidgetItem(line_icon(icon), title))
        self.nav.setObjectName("navigation")
        side_layout.addWidget(self.nav)
        root.addWidget(side)
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(28, 19, 23, 12)
        self.exam_caption = QLabel("CSP 模拟赛")
        self.exam_caption.setObjectName("examCaption")
        top_layout.addWidget(self.exam_caption, 1)
        self.project_actions = []
        for title, action in [("新建", self.new_project), ("打开", self.open_project), ("保存", self.save), ("演示", self.load_demo)]:
            button = QPushButton(title)
            button.setObjectName("quiet")
            button.clicked.connect(action)
            self.project_actions.append(button)
            top_layout.addWidget(button)
        workspace_layout.addWidget(top)
        self.pages = QStackedWidget()
        workspace_layout.addWidget(self.pages, 1)
        root.addWidget(workspace, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self._import_page()
        self._config_page()
        self._judge_page()
        self._results_page()
        self._export_page()
        self.nav.setCurrentRow(0)
        self.setCentralWidget(backdrop)
        status = self.statusBar()
        status.hide()
        status.messageChanged.connect(lambda message: status.setVisible(bool(message)))
        self.setStyleSheet(GLASS_STYLE)

    def flash_status(self, message):
        self.statusBar().showMessage(message, 4500)

    def _import_page(self):
        widget, layout = page("考试资料")
        panel = QFrame()
        panel.setObjectName("surface")
        form = QFormLayout(panel)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(9)
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(lambda text: self.exam_caption.setText(text or "新建考试"))
        form.addRow("考试名称", self.name_edit)
        self.paths = {}
        self.path_buttons = []
        for key, label in [("submissions_dir", "考生提交"), ("testdata_dir", "测试数据"), ("report_dir", "报告目录")]:
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("请选择文件夹…")
            self.paths[key] = edit
            if key != "report_dir":
                edit.textEdited.connect(self.invalidate_scan)
            button = QPushButton("选择…")
            button.clicked.connect(lambda _, k=key: self.choose_directory(k))
            self.path_buttons.append(button)
            row.addWidget(edit, 1)
            row.addWidget(button)
            form.addRow(label, row)
        layout.addWidget(panel)
        actions = QHBoxLayout()
        self.scan_button = QPushButton("检查资料")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.start_scan)
        self.resolve_button = QPushButton("指定源码…")
        self.resolve_button.clicked.connect(self.resolve_sources)
        actions.addWidget(self.scan_button)
        actions.addWidget(self.resolve_button)
        actions.addStretch()
        self.warning_toggle = QPushButton("检查详情")
        self.warning_toggle.setObjectName("quiet")
        self.warning_toggle.setCheckable(True)
        actions.addWidget(self.warning_toggle)
        layout.addLayout(actions)
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.scan_metrics = {}
        for key, label, tone in [("students", "考生", "green"), ("problems", "题目", "green"), ("cases", "测试点", "blue"), ("issues", "待确认", "amber")]:
            frame, value = metric(label, tone)
            self.scan_metrics[key] = value
            tiles.addWidget(frame, 1)
        layout.addLayout(tiles)
        self.summary = QLabel("尚未导入资料")
        self.summary.setObjectName("count")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.import_table = table(["准考证号", "提交状态"])
        self.import_table.cellDoubleClicked.connect(self.choose_source_for_cell)
        layout.addWidget(self.import_table, 3)
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.warnings.setPlaceholderText("没有需要处理的问题")
        self.warnings.setMaximumHeight(110)
        self.warnings.hide()
        self.warning_toggle.toggled.connect(self.warnings.setVisible)
        layout.addWidget(self.warnings, 1)
        # A scaled 1366×768 display has fewer logical pixels. Keep the import
        # controls readable and scroll this page instead of squeezing its form.
        widget.setMinimumHeight(580)
        scrolling = QScrollArea()
        scrolling.setWidgetResizable(True)
        scrolling.setFrameShape(QFrame.Shape.NoFrame)
        scrolling.setWidget(widget)
        self.pages.addWidget(scrolling)

    def _config_page(self):
        widget, layout = page("题目配置")
        panel = QFrame()
        panel.setObjectName("surface")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(12)
        row = QHBoxLayout()
        self.compiler_edit = QLineEdit()
        self.compiler_edit.setPlaceholderText("g++.exe 路径")
        self.compiler_edit.textChanged.connect(lambda: setattr(self, "compiler_verified", ""))
        self.compiler_choose = QPushButton("选择…")
        self.compiler_choose.clicked.connect(self.choose_compiler)
        self.compiler_check = QPushButton("验证编译器")
        self.compiler_check.clicked.connect(self.check_compiler)
        row.addWidget(self.compiler_edit, 1)
        row.addWidget(self.compiler_choose)
        row.addWidget(self.compiler_check)
        panel_layout.addLayout(row)
        self.compiler_status = QLabel("编译器尚未验证")
        self.compiler_status.setObjectName("count")
        self.compiler_status.setWordWrap(True)
        self.compiler_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        panel_layout.addWidget(self.compiler_status)
        options = QHBoxLayout()
        self.compile_timeout = spin(45, 1, 600)
        self.output_limit = spin(64, 1, 4096)
        options.addWidget(QLabel("编译超时（秒）"))
        options.addWidget(self.compile_timeout)
        options.addWidget(QLabel("输出上限（MB）"))
        options.addWidget(self.output_limit)
        options.addStretch()
        panel_layout.addLayout(options)
        layout.addWidget(panel)
        self.config_table = table(["题目", "点数", "满分", "时限 ms", "内存 MB", "输入文件名", "输出文件名", "计分 / 数据状态"])
        self.config_table.cellDoubleClicked.connect(lambda *_: self.edit_problem())
        layout.addWidget(self.config_table, 1)
        actions = QHBoxLayout()
        self.edit_button = QPushButton("编辑题目…")
        self.edit_button.clicked.connect(self.edit_problem)
        self.bulk_button = QPushButton("批量设置限制…")
        self.bulk_button.clicked.connect(self.bulk_limits)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.bulk_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.pages.addWidget(widget)

    def _judge_page(self):
        widget, layout = page("评测")
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始评测")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_judge)
        self.stop_button = QPushButton("停止评测")
        self.stop_button.setObjectName("stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_judge)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m 项（已判定）")
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.current = QLabel("尚未开始评测")
        self.current.setObjectName("stage")
        self.current.setWordWrap(True)
        layout.addWidget(self.current)
        self.elapsed = QLabel("0 / 0 项　　0.0 秒")
        self.elapsed.setObjectName("count")
        self.elapsed.setWordWrap(True)
        layout.addWidget(self.elapsed)
        self.cleanup_notice = QLabel()
        self.cleanup_notice.setObjectName("notice")
        self.cleanup_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.cleanup_notice.setWordWrap(True)
        self.cleanup_notice.hide()
        layout.addWidget(self.cleanup_notice)
        self.logs = QPlainTextEdit()
        self.logs.setObjectName("executionLog")
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(4000)
        layout.addWidget(self.logs, 1)
        self.pages.addWidget(widget)

    def _results_page(self):
        widget, layout = page("成绩")
        self.result_notice = QLabel("尚未评分")
        self.result_notice.setObjectName("notice")
        self.result_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.result_notice.setWordWrap(True)
        layout.addWidget(self.result_notice)
        metrics = QHBoxLayout()
        self.result_metrics = {}
        for key, label, tone in [("processed", "已判定", "green"), ("pending", "未完成", "amber"), ("ac", "正确", "blue")]:
            frame, value = metric(label, tone)
            self.result_metrics[key] = value
            metrics.addWidget(frame, 1)
        layout.addLayout(metrics)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索准考证号")
        self.search.setMaximumWidth(300)
        self.search.textChanged.connect(self.filter_results)
        layout.addWidget(self.search)
        self.scores = table(["名次", "准考证号", "总分", "完成"])
        self.scores.setItemDelegate(ColourPreservingDelegate(self.scores))
        self.scores.cellDoubleClicked.connect(self.show_details)
        layout.addWidget(self.scores, 1)
        self.pages.addWidget(widget)

    def _export_page(self):
        widget, layout = page("导出报告")
        panel = QFrame()
        panel.setObjectName("surface")
        panel.setMaximumWidth(760)
        content = QVBoxLayout(panel)
        content.setContentsMargins(24, 24, 24, 24)
        content.setSpacing(18)
        types = QLabel("Excel  ·  CSV  ·  HTML")
        types.setStyleSheet("font-size:18px;color:#536b46;font-weight:500")
        content.addWidget(types)
        directory_row = QHBoxLayout()
        self.export_directory_label = QLabel()
        self.export_directory_label.setWordWrap(True)
        self.export_directory_label.setObjectName("count")
        self.paths["report_dir"].textChanged.connect(self.export_directory_label.setText)
        directory_row.addWidget(self.export_directory_label, 1)
        directory_button = QPushButton("更改目录…")
        directory_button.clicked.connect(lambda: self.choose_directory("report_dir"))
        self.path_buttons.append(directory_button)
        directory_row.addWidget(directory_button)
        content.addLayout(directory_row)
        self.auto_export = QCheckBox("评测结束后自动导出")
        self.auto_export.setChecked(True)
        content.addWidget(self.auto_export)
        actions = QHBoxLayout()
        self.export_button = QPushButton("导出报告")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.start_export)
        actions.addWidget(self.export_button)
        self.open_export = QPushButton("打开报告目录")
        self.open_export.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_export)) if self.last_export else None)
        actions.addWidget(self.open_export)
        actions.addStretch()
        content.addLayout(actions)
        self.export_path = QLabel("尚无评测结果")
        self.export_path.setWordWrap(True)
        self.export_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.export_path)
        layout.addWidget(panel)
        layout.addStretch()
        self.pages.addWidget(widget)

    def sync_fields(self):
        self.name_edit.setText(self.project.project_name)
        for key, edit in self.paths.items():
            edit.setText(getattr(self.project, key))
        self.compiler_edit.setText(self.project.compiler_path)
        self.compile_timeout.setValue(self.project.compile_timeout_sec)
        self.output_limit.setValue(self.project.output_limit_mb)
        self.auto_export.setChecked(self.project.auto_export)

    def pull_fields(self):
        self.project.project_name = self.name_edit.text().strip() or "CSP 模拟赛"
        for key, edit in self.paths.items():
            setattr(self.project, key, edit.text().strip())
        self.project.compiler_path = self.compiler_edit.text().strip()
        self.project.compile_timeout_sec = self.compile_timeout.value()
        self.project.output_limit_mb = self.output_limit.value()
        self.project.auto_export = self.auto_export.isChecked()

    def launch(self, action, success, kind):
        if self.worker:
            return False
        self.busy_kind = kind
        self.worker = Worker(action, self)
        self.worker.event.connect(self.on_event)
        self.worker.succeeded.connect(success)
        self.worker.failed.connect(self.on_error)
        self.worker.finished.connect(self.task_finished)
        self.set_busy(True)
        self.worker.start()
        return True

    def set_busy(self, busy):
        for widget in [*self.path_buttons, *self.paths.values(), self.name_edit, self.scan_button, self.resolve_button,
                       self.compiler_edit, self.compiler_choose, self.compiler_check, self.compile_timeout, self.output_limit,
                       self.edit_button, self.bulk_button, self.start_button, self.export_button, self.auto_export]:
            widget.setEnabled(not busy)
        for action in self.project_actions:
            action.setEnabled(not busy)
        self.stop_button.setEnabled(busy and self.busy_kind == "judge")

    def task_finished(self):
        worker = self.worker
        self.worker = None
        kind = self.busy_kind
        self.busy_kind = ""
        self.set_busy(False)
        worker.deleteLater()
        if kind == "judge" and self.batch and self.batch.finished_at and self.auto_export.isChecked():
            QTimer.singleShot(0, self.start_export)

    def on_error(self, message):
        self.flash_status(message.splitlines()[0])
        if self.busy_kind == "judge":
            self.current.setText("评测未能完成，请检查错误提示后重试。")
            self.judge_started = 0
        QMessageBox.warning(self, "wtjudge 提示", message)

    def choose_directory(self, key):
        selected = QFileDialog.getExistingDirectory(self, "选择文件夹", self.paths[key].text())
        if selected:
            self.paths[key].setText(selected)
            if key != "report_dir" and all(self.paths[k].text() for k in ("submissions_dir", "testdata_dir")):
                self.start_scan()

    def start_scan(self):
        if self.worker:
            return
        self.pull_fields()
        if not self.project.report_dir:
            base = Path(self.project_path).parent if self.project_path else Path(self.project.submissions_dir).parent
            self.project.report_dir = str(base / "results")
            self.paths["report_dir"].setText(self.project.report_dir)
        project = copy.deepcopy(self.project)
        self.flash_status("正在后台扫描目录…")
        self.launch(lambda *_: scan_project(project), self.apply_scan, "scan")

    def invalidate_scan(self):
        self.scan = None
        self.batch = None
        self.summary.setText("资料已更改，待检查")
        for value in self.scan_metrics.values():
            value.setText("—")
        self.refresh_results()

    def apply_scan(self, scan):
        if self.scan and self.scan.snapshot != scan.snapshot:
            self.batch = None
            self.refresh_results()
        self.scan = scan
        self.project.problems = scan.problems
        self.project.data_snapshot = scan.snapshot
        executions = len(scan.students) * sum(len(p.cases) for p in scan.problems)
        available = sum(any(scan.submissions[s, p.id].source for p in scan.problems) for s in scan.students)
        missing = sum(s.status == "NO_SOURCE" for s in scan.submissions.values())
        ambiguous = sum(s.status == "AMBIGUOUS_SOURCE" for s in scan.submissions.values())
        for key, value in {"students": len(scan.students), "problems": len(scan.problems), "cases": sum(len(p.cases) for p in scan.problems),
                           "issues": len(scan.errors) + missing}.items():
            self.scan_metrics[key].setText(str(value))
        text = f"{executions:,} 项待评测"
        if missing:
            text += f"  ·  {missing} 题缺少源码"
        if ambiguous:
            text += f"  ·  {ambiguous} 题需指定源码"
        if scan.errors:
            text += f"  ·  {len(scan.errors)} 项检查未通过"
        self.summary.setText(text)
        self.warnings.setPlainText("\n".join([*scan.errors, *scan.warnings]) or "目录与题目分值检查通过。")
        self.warning_toggle.setText(f"检查详情（{len(scan.errors) + len(scan.warnings)}）")
        self.warning_toggle.setChecked(bool(scan.errors))
        headers = ["准考证号", *[p.id for p in scan.problems]]
        self.import_table.setColumnCount(len(headers))
        self.import_table.setHorizontalHeaderLabels(headers)
        self.import_table.setRowCount(len(scan.students))
        for i, student in enumerate(scan.students):
            self.import_table.setItem(i, 0, cell(student))
            for j, p in enumerate(scan.problems, 1):
                submission = scan.submissions[student, p.id]
                source_status = {"NO_SOURCE": "缺少源码", "AMBIGUOUS_SOURCE": "需指定源码"}.get(submission.status, STATUS_TEXT.get(submission.status, submission.status))
                item = cell(source_status if submission.status else Path(submission.source).name)
                item.setToolTip(submission.source or "\n".join(submission.candidates) or f"未找到源码。检查目录：{Path(self.project.submissions_dir) / student / p.id}")
                if submission.status:
                    colour_status(item, submission.status)
                self.import_table.setItem(i, j, item)
        self.refresh_config()
        self.flash_status("资料检查完成")

    def refresh_config(self):
        self.config_table.setRowCount(len(self.project.problems))
        for i, p in enumerate(self.project.problems):
            for j, value in enumerate([p.id, len(p.cases), p.full_score, p.time_limit_ms, p.memory_limit_mb,
                                       p.input_filename, p.output_filename, ("平均分配" if p.score_mode == "equal" else "自定义") + " / " + ("异常：" + "; ".join(p.validate()) if p.validate() else "完整")]):
                item = cell(value)
                item.setToolTip(str(value))
                if j == 7:
                    colour_status(item, "SYSTEM_ERROR" if p.validate() else "AC")
                self.config_table.setItem(i, j, item)

    def edit_problem(self):
        if self.worker:
            return
        index = self.config_table.currentRow()
        if index < 0:
            return
        dialog = ProblemDialog(self.project.problems[index], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project.problems[index] = dialog.problem
            self.batch = None
            self.refresh_results()
            self.start_scan()

    def bulk_limits(self):
        if not self.project.problems:
            return
        limit, accepted = QInputDialog.getInt(self, "统一时限", "墙钟时限（ms）", 1000, 1, 1000000)
        if not accepted:
            return
        memory, accepted = QInputDialog.getInt(self, "统一内存", "内存限额（MB）", 256, 1, 65536)
        if accepted:
            for p in self.project.problems:
                p.time_limit_ms, p.memory_limit_mb = limit, memory
            self.batch = None
            self.refresh_results()
            self.refresh_config()

    def resolve_sources(self):
        if not self.scan:
            return
        row, column = self.import_table.currentRow(), self.import_table.currentColumn()
        if row >= 0 and column > 0:
            self.choose_source_for_cell(row, column)
            return
        unresolved = [s for s in self.scan.submissions.values() if s.status in {"AMBIGUOUS_SOURCE", "NO_SOURCE"}]
        submissions = unresolved or list(self.scan.submissions.values())
        labels = [f"{s.student_id} / {s.problem_id} — {STATUS_TEXT.get(s.status, '已识别，可更换')}" for s in submissions]
        chosen, accepted = QInputDialog.getItem(self, "选择要指定源码的提交", "选择考生与题目；也可直接双击导入表格的题目格。", labels, 0, False)
        if accepted:
            submission = submissions[labels.index(chosen)]
            self.choose_source_for_cell(self.scan.students.index(submission.student_id), 1 + [p.id for p in self.scan.problems].index(submission.problem_id))

    def choose_source_for_cell(self, row, column):
        if self.worker or not self.scan or column < 1 or row < 0 or column > len(self.scan.problems):
            return
        student, problem = self.scan.students[row], self.scan.problems[column - 1].id
        student_root = (Path(self.project.submissions_dir) / student).resolve()
        chosen, _ = QFileDialog.getOpenFileName(self, f"指定源码 — {student} / {problem}", str(student_root), "C++ 源码 (*.cpp *.CPP)")
        if not chosen:
            return
        source = Path(chosen).resolve()
        if not source.is_relative_to(student_root) or source.suffix.casefold() != ".cpp":
            QMessageBox.warning(self, "源码路径无效", "请选择该考生目录内的一个 .cpp 文件，不能使用其他考生的源码。")
            return
        self.project.source_overrides[f"{student}/{problem}"] = str(source)
        self.batch = None
        self.refresh_results()
        self.start_scan()

    def choose_compiler(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 MinGW-w64 G++", self.compiler_edit.text(), "G++ (g++.exe);;可执行文件 (*.exe)")
        if path:
            self.compiler_edit.setText(path)
            self.check_compiler()

    def check_compiler(self):
        if self.worker:
            return
        self.pull_fields()
        path, timeout = self.project.compiler_path, self.project.compile_timeout_sec
        self.compiler_status.setText("正在验证…")
        def done(result):
            valid, message = result
            version = next((line.strip() for line in message.splitlines() if "g++" in line.lower() or "gcc" in line.lower()), "C++14")
            self.compiler_status.setText(f"已验证  ·  {version}" if valid else message.splitlines()[0][:180])
            self.compiler_status.setToolTip(message[:5000])
            self.compiler_verified = path if valid else ""
            if valid:
                self.settings.setValue("compiler_path", path)
                self.flash_status("G++ 编译器验证通过。")
        self.launch(lambda cancel, _: validate_compiler(path, timeout, cancel), done, "compiler")

    def start_judge(self):
        if self.worker:
            return
        self.pull_fields()
        if not self.scan:
            self.nav.setCurrentRow(0)
            QMessageBox.information(self, "请先预检", "请导入目录并完成扫描。")
            return
        if self.scan.errors:
            self.nav.setCurrentRow(0)
            QMessageBox.warning(self, "预检未通过", "\n".join(self.scan.errors[:30]))
            return
        if self.compiler_verified != self.project.compiler_path:
            self.nav.setCurrentRow(1)
            QMessageBox.information(self, "请验证编译器", "开始前需点击“验证编译器”并通过实际 C++14 编译运行检查。")
            return
        if not self.safety_confirmed:
            if QMessageBox.warning(self, "首次评测前确认", SAFETY, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.safety_confirmed = True
        self.batch = None
        self.refresh_results()
        self.logs.clear()
        self.cleanup_notices.clear()
        self.cleanup_notice.hide()
        self.progress.setRange(0, 0)
        self.judge_started = time.monotonic()
        self.nav.setCurrentRow(2)
        project = copy.deepcopy(self.project)
        self.launch(lambda cancel, emit: judge_batch(project, cancel, emit), self.judge_done, "judge")

    def stop_judge(self):
        if self.worker and self.busy_kind == "judge":
            self.worker.cancel.set()
            self.stop_button.setEnabled(False)
            self.current.setText("正在终止编译器或学生进程并清理本次临时目录…")

    def on_event(self, kind, payload):
        if kind == "phase":
            payload = str(payload).replace("（每题仅编译一次）", "")
            self.current.setText(payload)
            self.logs.appendPlainText(payload)
        elif kind == "batch":
            self.batch = payload
            self.progress.setRange(0, payload.expected_points)
            self.refresh_results()
        elif kind == "cleanup_warning":
            self.cleanup_notices.append(str(payload))
            self.logs.appendPlainText("[临时文件清理提醒] " + str(payload))
            self.cleanup_notice.setText(f"临时文件清理提醒 {len(self.cleanup_notices)} 项：{str(payload)[:240]}\n后续提交继续评测；已获得的有效结果予以保留。")
            notice_tone(self.cleanup_notice, "warning")
            self.cleanup_notice.show()
        elif kind == "point" and self.batch:
            self.batch.points.append(payload)
            self.progress.setValue(result_counts(self.batch)[0])
            self.logs.appendPlainText(f"{payload.student_id} / {payload.problem_id} / {payload.testcase_id}  {payload.status}  {payload.score}/{payload.max_score}  {payload.time_ms:.1f} ms" + (f"\n{payload.message[:600]}" if payload.status != "AC" else ""))
            if time.monotonic() - self.last_result_refresh > .25:
                self.refresh_results()
                self.last_result_refresh = time.monotonic()

    def update_elapsed(self):
        if self.judge_started:
            elapsed = time.monotonic() - self.judge_started
            done, pending, ran, _ = result_counts(self.batch)
            total = self.batch.expected_points if self.batch else 0
            self.elapsed.setText(f"{done:,} / {total:,} 项  ·  已运行 {ran:,} 点  ·  未完成 {pending:,} 项  ·  {elapsed:.1f} 秒")

    def judge_done(self, result):
        self.batch = result
        self.update_elapsed()
        self.judge_started = 0
        done, pending, ran, _ = result_counts(result)
        self.current.setText(f"评测完成 · 已判定 {done:,} 项" if result.complete else f"已取消 · {pending:,} 项未完成" if result.cancelled else f"结果不完整 · {pending:,} 项未评测或无效，请重判")
        self.progress.setRange(0, result.expected_points)
        self.progress.setValue(done)
        cleanup = getattr(result, "cleanup_warnings", [])
        if cleanup:
            self.cleanup_notice.setText(f"有 {len(cleanup)} 项临时文件清理提醒，未中止后续评测。\n" + "\n".join(str(s)[:200] for s in cleanup[:2]))
            notice_tone(self.cleanup_notice, "warning")
            self.cleanup_notice.show()
        self.refresh_results()
        self.export_path.setText("本批次可导出。" + ("" if result.complete else WARNING))

    def refresh_results(self):
        batch = self.batch
        if not batch:
            self.scores.setRowCount(0)
            self.result_sort_initialized = False
            self.result_notice.setText("尚无评测结果")
            notice_tone(self.result_notice, "")
            for value in self.result_metrics.values():
                value.setText("—")
            return
        done, pending, ran, ac = result_counts(batch)
        for key, value in {"processed": done, "pending": pending, "ac": ac}.items():
            self.result_metrics[key].setText(f"{value:,}")
        notice = f"评测完成  ·  {len(batch.students)} 名考生  ·  {ran:,} 个测试点已运行" if batch.complete else f"{WARNING}\n未评测 / 无效 {pending:,} 项。"
        if batch.failure:
            notice += "\n中断原因：" + batch.failure[:450]
        coverage = batch.coverage_errors() if hasattr(batch, "coverage_errors") else []
        if coverage:
            notice += "\n覆盖检查：" + "；".join(coverage[:2])
        self.result_notice.setText(notice)
        notice_tone(self.result_notice, "" if batch.complete else "error")
        headers = ["名次", "准考证号", *batch.problems, "总分", "AC 点数", "状态"]
        self.scores.setSortingEnabled(False)
        self.scores.setColumnCount(len(headers))
        self.scores.setHorizontalHeaderLabels(headers)
        rows = batch.standings()
        grouped = {}
        for point in batch.points:
            grouped.setdefault((point.student_id, point.problem_id), []).append(point)
        self.scores.setRowCount(len(rows))
        for i, row in enumerate(rows):
            missing = sum(bool(grouped.get((row["student_id"], problem))) and all(p.status == "NO_SOURCE" for p in grouped[row["student_id"], problem]) for problem in batch.problems)
            completion = (f"缺交 {missing} 题" if missing else "完成") if row["completed"] else "未完成"
            values = [row["rank"], row["student_id"], *[row["scores"][p] for p in batch.problems], row["total"], row["ac_count"], completion]
            for j, value in enumerate(values):
                item = NumericItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, value)
                item.setData(Qt.ItemDataRole.UserRole + 1, row["student_id"])
                if 2 <= j < 2 + len(batch.problems):
                    problem = batch.problems[j - 2]
                    points = grouped.get((row["student_id"], problem), [])
                    invalid = sum(p.status not in STATUS_TEXT or p.status in {"CANCELLED", "SYSTEM_ERROR", "AMBIGUOUS_SOURCE"} for p in points)
                    statuses = {s: sum(p.status == s for p in points) for s in dict.fromkeys(p.status for p in points)}
                    expected_ids = batch.testcase_ids.get(problem) if problem in batch.testcase_ids else None
                    ids = [p.testcase_id for p in points]
                    unique = len(ids) == len(set(ids))
                    if expected_ids is not None:
                        complete_points = bool(points) and unique and len(ids) == len(expected_ids) and set(ids) == set(expected_ids)
                    else:
                        complete_points = bool(points) and unique and row["completed"]
                    details = "\n".join(f"{s} / {STATUS_TEXT.get(s, s)}：{count} 点" for s, count in statuses.items()) or "尚未评测"
                    item.setToolTip(f"得分：{value} / {batch.full_scores[problem]}\n" + details + ("" if complete_points and not invalid else "\n未完成 / 存在无效项，得分暂计"))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if not points or invalid == len(points):
                        item.setText("未评测 / 无效")
                        colour_status(item, "SYSTEM_ERROR" if "SYSTEM_ERROR" in statuses else "CANCELLED")
                    elif invalid or not complete_points:
                        item.setText(f"{value} · 未完成")
                        colour_status(item, "SYSTEM_ERROR")
                    else:
                        error = uniform_error(points, expected_ids)
                        if error:
                            item.setText("缺源码" if error == "NO_SOURCE" else error)
                            colour_status(item, error)
                        else:
                            background, foreground = score_colours(value, batch.full_scores[problem])
                            item.setBackground(QColor(background))
                            item.setForeground(QColor(foreground))
                elif j == 2 + len(batch.problems):
                    maximum = sum(batch.full_scores.values())
                    background, foreground = score_colours(value, maximum)
                    item.setBackground(QColor(background))
                    item.setForeground(QColor(foreground))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(f"总分：{value} / {maximum}" + ("" if row["completed"] else "\n未完成 / 存在无效项，得分暂计"))
                    if not row["completed"]:
                        item.setText(f"{value} · 暂计")
                if j == len(headers) - 1 and not row["completed"]:
                    item.setForeground(QColor("#b45309"))
                self.scores.setItem(i, j, item)
        if not self.result_sort_initialized:
            self.scores.horizontalHeader().setSortIndicator(2 + len(batch.problems), Qt.SortOrder.DescendingOrder)
            self.result_sort_initialized = True
        self.scores.setSortingEnabled(True)
        self.filter_results()

    def filter_results(self):
        query = self.search.text().casefold()
        for i in range(self.scores.rowCount()):
            item = self.scores.item(i, 1)
            self.scores.setRowHidden(i, bool(item and query not in item.text().casefold()))

    def show_details(self, row, column):
        if not self.batch:
            return
        student = self.scores.item(row, column).data(Qt.ItemDataRole.UserRole + 1)
        problem = self.batch.problems[column - 2] if 2 <= column < 2 + len(self.batch.problems) else None
        DetailDialog(self.batch, student, problem, self).exec()

    def start_export(self):
        if self.worker:
            return
        if not self.batch or not self.batch.finished_at:
            QMessageBox.information(self, "没有可导出报告", "请先完成或停止一批评测。")
            return
        self.pull_fields()
        if not self.project.report_dir:
            self.choose_directory("report_dir")
            self.pull_fields()
            if not self.project.report_dir:
                return
        batch, root = copy.deepcopy(self.batch), self.project.report_dir
        def done(path):
            self.last_export = path
            self.export_path.setText(f"已生成全部报告：\n{path}\n" + ("完整成绩" if batch.complete else WARNING))
            self.flash_status(f"报告已导出：{path}")
        self.launch(lambda *_: export_reports(batch, root), done, "export")

    def confirm_discard(self):
        return QMessageBox.question(self, "切换考试", "切换将清空界面中的当前配置和成绩。请先保存需要的项目或导出结果。继续？",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def reset_project(self, project, path=""):
        self.project, self.project_path = project, path
        self.scan = self.batch = None
        self.compiler_verified = ""
        self.import_table.setRowCount(0)
        self.compiler_status.setText("编译器尚未验证")
        self.config_table.setRowCount(0)
        self.summary.setText("资料待检查")
        for value in self.scan_metrics.values():
            value.setText("—")
        self.warnings.clear()
        self.warning_toggle.setChecked(False)
        self.sync_fields()
        self.refresh_results()
        self.nav.setCurrentRow(0)

    def new_project(self):
        if self.confirm_discard():
            self.reset_project(Project(compiler_path=self.settings.value("compiler_path", "")))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开考试项目", self.project_path, "考试项目 (*.json)")
        if not path or not self.confirm_discard():
            return
        def done(project):
            self.reset_project(project, path)
            QTimer.singleShot(0, self.start_scan)
        self.launch(lambda *_: load_project(path), done, "open")

    def save(self):
        self.pull_fields()
        path, _ = QFileDialog.getSaveFileName(self, "保存考试项目", self.project_path or str(Path.cwd() / "wtjudge.project.json"), "考试项目 (*.json)")
        if not path:
            return
        self.project_path = path
        if not self.project.report_dir:
            self.project.report_dir = str(Path(path).parent / "results")
            self.paths["report_dir"].setText(self.project.report_dir)
        project = copy.deepcopy(self.project)
        self.launch(lambda *_: save_project(project, path), lambda _: self.flash_status(f"考试项目已保存：{path}"), "save")

    def load_demo(self):
        if not self.confirm_discard():
            return
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        project = Project(project_name="wtjudge 内置演示考试", submissions_dir=str(base / "demo" / "submissions"),
                          testdata_dir=str(base / "demo" / "testdata"), report_dir=str(base / "results"), compiler_path=self.compiler_edit.text())
        self.reset_project(project)
        self.start_scan()

    def closeEvent(self, event):
        if self.worker:
            if self.busy_kind == "judge":
                self.stop_judge()
            QMessageBox.information(self, "后台任务尚未结束", "正在完成或停止后台任务，请稍后再关闭窗口。")
            event.ignore()
            return
        event.accept()
