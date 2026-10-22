from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from wtjudge.core.models import MODES, STATUS_TEXT
from .theme import colour_status
from .table_items import ColourPreservingDelegate


def cell(text, editable=False):
    item = QTableWidgetItem(str(text))
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def spin(value, minimum=1, maximum=1000000):
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    return widget


class ProblemDialog(QDialog):
    def __init__(self, problem, parent=None):
        super().__init__(parent)
        self.problem = copy.deepcopy(problem)
        self.setWindowTitle(f"配置题目 — {problem.id}")
        self.resize(860, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.input = QLineEdit(problem.input_filename)
        self.output = QLineEdit(problem.output_filename)
        self.source = QLineEdit(problem.source_file)
        self.time = spin(problem.time_limit_ms)
        self.memory = spin(problem.memory_limit_mb, maximum=65536)
        self.score = spin(problem.full_score, 0)
        self.compare = QComboBox()
        for key, name in MODES.items():
            self.compare.addItem(name, key)
        self.compare.setCurrentIndex(self.compare.findData(problem.compare_mode))
        self.mode = QComboBox()
        self.mode.addItem("平均分配", "equal")
        self.mode.addItem("自定义分值", "custom")
        self.mode.setToolTip("平均分配按测试点自然顺序分配余数。自定义分值之和须等于题目满分。")
        self.mode.setCurrentIndex(self.mode.findData(problem.score_mode))
        for label, widget in [("输入文件名", self.input), ("输出文件名", self.output), ("源码优先匹配名", self.source),
                              ("时限（ms）", self.time), ("内存限制（MB）", self.memory),
                              ("题目满分", self.score), ("答案比较", self.compare), ("分值分配", self.mode)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["测试点", "输入大小", "输出大小", "分值", "配对状态", "数据文件"])
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        bulk = QHBoxLayout()
        from PySide6.QtWidgets import QPushButton
        self.bulk_value = spin(0, 0)
        button = QPushButton("将选中测试点设为此分值")
        button.clicked.connect(self.bulk_scores)
        bulk.addWidget(self.bulk_value)
        bulk.addWidget(button)
        bulk.addStretch()
        layout.addLayout(bulk)
        self.confirm = QCheckBox("我已核对当前测试点及自定义分值（合计必须等于满分）")
        layout.addWidget(self.confirm)
        self.hint = QLabel()
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode.currentIndexChanged.connect(self.refresh_scores)
        self.score.valueChanged.connect(self.refresh_scores)
        self.table.itemChanged.connect(self.sum_hint)
        self.refresh_scores()

    def refresh_scores(self):
        custom = self.mode.currentData() == "custom"
        self.confirm.setVisible(custom)
        self.confirm.setChecked(False)
        self.problem.full_score = self.score.value()
        self.problem.score_mode = self.mode.currentData()
        self.problem.distribute()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.problem.cases))
        for i, case in enumerate(self.problem.cases):
            values = [case.id, f"{case.input_size:,} B", f"{case.output_size:,} B", self.problem.testcase_scores.get(case.id, 0),
                      "完整" if case.input_path and case.output_path else "数据缺失", Path(case.input_path).name]
            for j, value in enumerate(values):
                item = cell(value, editable=custom and j == 3)
                if j == 5:
                    item.setToolTip(f"输入：{case.input_path}\n输出：{case.output_path}")
                self.table.setItem(i, j, item)
        self.table.blockSignals(False)
        self.sum_hint()

    def sum_hint(self):
        try:
            values = [int(self.table.item(i, 3).text()) for i in range(self.table.rowCount())]
            self.hint.setText(f"{len(values)} 个测试点；分值合计 {sum(values)} / {self.score.value()}")
        except (ValueError, AttributeError):
            self.hint.setText("分值必须为非负整数")

    def bulk_scores(self):
        if self.mode.currentData() != "custom":
            return
        for i in {index.row() for index in self.table.selectedIndexes()}:
            self.table.item(i, 3).setText(str(self.bulk_value.value()))

    def accept(self):
        p = self.problem
        p.input_filename, p.output_filename, p.source_file = self.input.text().strip(), self.output.text().strip(), self.source.text().strip()
        p.time_limit_ms, p.memory_limit_mb, p.full_score = self.time.value(), self.memory.value(), self.score.value()
        p.compare_mode, p.score_mode = self.compare.currentData(), self.mode.currentData()
        if p.score_mode == "custom" and not self.confirm.isChecked():
            QMessageBox.warning(self, "请确认", "请先核对并勾选自定义分值确认。")
            return
        try:
            p.testcase_scores = {case.id: int(self.table.item(i, 3).text()) for i, case in enumerate(p.cases)}
        except ValueError:
            QMessageBox.warning(self, "分值无效", "请输入非负整数。")
            return
        p.scores_confirmed = True
        errors = [e for e in p.validate() if e not in p.errors and e != "没有测试点"]
        if errors:
            QMessageBox.warning(self, "配置无效", "\n".join(errors))
            return
        super().accept()


class DetailDialog(QDialog):
    def __init__(self, batch, student, problem=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"成绩详情 — {student}" + (f" / {problem}" if problem else ""))
        self.resize(1120, 620)
        layout = QVBoxLayout(self)
        points = [p for p in batch.points if p.student_id == student and (not problem or p.problem_id == problem)]
        maximum = batch.full_scores.get(problem, sum(batch.full_scores.values()))
        layout.addWidget(QLabel(f"当前得分：{sum(p.score for p in points)} / {maximum}　　{'完整批次' if batch.complete else '暂未评完 / 存在无效项，不能视作正式成绩'}"))
        table = QTableWidget(len(points), 9)
        self.table = table
        table.setItemDelegate(ColourPreservingDelegate(table))
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setHorizontalHeaderLabels(["题目", "测试点", "状态", "中文说明", "得分", "满分", "墙钟 ms", "峰值 KB", "退出码 / 诊断"])
        for i, p in enumerate(points):
            for j, value in enumerate([p.problem_id, p.testcase_id, p.status, STATUS_TEXT.get(p.status, p.status), p.score, p.max_score,
                                       round(p.time_ms, 2), p.peak_memory_kb, f"{p.exit_code}\n{p.message}"]):
                item = cell(value)
                item.setToolTip(str(value))
                if j in {2, 3}:
                    colour_status(item, p.status)
                if j == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setDefaultSectionSize(35)
        layout.addWidget(table)
        self.message = QPlainTextEdit()
        self.message.setPlaceholderText("选择测试点查看诊断")
        self.message.setReadOnly(True)
        self.message.setMaximumHeight(140)
        table.currentCellChanged.connect(lambda r, c, *_: self.message.setPlainText(table.item(r, c).text() if r >= 0 and table.item(r, c) else ""))
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
