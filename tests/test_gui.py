import copy
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
from PySide6.QtWidgets import QFileDialog

from wtjudge.core.models import BatchResult, PointResult, Project
from wtjudge.core.scanner import scan_project
from wtjudge.gui.dialogs import DetailDialog, ProblemDialog
from wtjudge.gui.main_window import MainWindow
from wtjudge.presentation import SCORE_COLOURS, STATUS_COLOURS, score_colours


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def wait(app, window, timeout=30):
    deadline = time.monotonic() + timeout
    while window.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert window.worker is None, "GUI worker did not complete"


def test_gui_pages_scoring_sort_details_and_responsive_worker(app, demo, monkeypatch):
    window = MainWindow(auto_check=False)
    failures = []
    monkeypatch.setattr(window, "on_error", failures.append)
    window.reset_project(demo)
    window.resize(1366, 768)
    window.show()
    window.start_scan()
    wait(app, window)
    assert window.pages.count() == 5 and window.import_table.rowCount() == 3
    assert window.config_table.rowCount() == 4
    dialog = ProblemDialog(next(p for p in window.project.problems if p.id == "road"), window)
    assert [int(dialog.table.item(i, 3).text()) for i in range(6)] == [17,17,17,17,16,16]
    dialog.close()
    heartbeats = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: heartbeats.append(time.monotonic()))
    heartbeat.start(10)
    window.check_compiler()
    wait(app, window)
    assert window.compiler_verified == demo.compiler_path
    assert len(heartbeats) > 5  # Event loop remains responsive during real compiler check.
    heartbeat.stop()
    window.batch = BatchResult("图形测试", ["0001", "0002"], ["road"], {"road":100}, "today", 2,
                               points=[PointResult("0001","road","1","AC",100,100), PointResult("0002","road","1","WA",0,100)], finished_at="today")
    window.refresh_results()
    assert window.scores.item(0,1).text() == "0001"
    window.scores.sortItems(3, Qt.SortOrder.DescendingOrder)
    assert window.scores.item(0,1).text() == "0001"
    window.search.setText("0002")
    assert window.scores.isRowHidden(0)
    assert not failures
    window.close()


def test_gui_start_stop_retains_partial_result(app, demo, monkeypatch):
    window = MainWindow(auto_check=False)
    failures = []
    monkeypatch.setattr(window, "on_error", failures.append)
    window.reset_project(demo)
    window.auto_export.setChecked(False)
    window.apply_scan(scan_project(demo))
    window.compiler_verified = demo.compiler_path
    window.safety_confirmed = True
    window.start_judge()
    QTimer.singleShot(1200, window.stop_judge)
    wait(app, window)
    assert window.batch.cancelled and not window.batch.complete
    assert window.start_button.isEnabled() and not window.stop_button.isEnabled()
    assert any(p.status == "CANCELLED" for p in window.batch.points)
    assert not failures
    window.close()


def test_gui_incomplete_counts_and_cleanup_notice(app):
    window = MainWindow(auto_check=False)
    window.batch = BatchResult("中断考试", ["001"], ["road"], {"road":100}, "today", 2,
                               points=[PointResult("001","road","1","SYSTEM_ERROR",0,50),
                                       PointResult("001","road","2","SYSTEM_ERROR",0,50)],
                               finished_at="today", failure="临时目录清理失败导致中断")
    window.refresh_results()
    assert window.result_metrics["pending"].text() == "2"
    assert "未评测" in window.scores.item(0,2).text()
    assert "暂计" in window.scores.item(0,3).text()
    assert "中断原因" in window.result_notice.text()
    window.on_event("cleanup_warning", "延后清理缓存，后续提交继续")
    assert not window.cleanup_notice.isHidden()
    assert "后续提交继续" in window.cleanup_notice.text()
    assert "临时文件清理提醒" in window.logs.toPlainText()
    window.close()


def test_gui_can_map_missing_source_inside_student_directory(app, demo, monkeypatch):
    window = MainWindow(auto_check=False)
    window.reset_project(demo)
    window.apply_scan(scan_project(demo))
    student = "HBCSP26003"
    chosen = Path(demo.submissions_dir) / student / "中文别名" / "自选.cpp"
    chosen.parent.mkdir()
    chosen.write_text("int main(){}", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(chosen), ""))
    scanned = []
    monkeypatch.setattr(window, "start_scan", lambda: scanned.append(True))
    row = window.scan.students.index(student)
    col = 1 + [p.id for p in window.scan.problems].index("road")
    window.choose_source_for_cell(row, col)
    assert window.project.source_overrides[f"{student}/road"] == str(chosen.resolve())
    assert scanned == [True]
    window.close()


def test_compact_glass_layout_remains_readable_without_decorative_copy(app):
    window = MainWindow(auto_check=False)
    window.resize(1093, 614)
    window.show()
    app.processEvents()
    labels = [label.text() for label in window.findChildren(QLabel)]
    assert not any("离线运行" in text or "本地评测" in text for text in labels)
    assert window.name_edit.height() >= 30
    assert all(edit.height() >= 30 and edit.width() > 300 for edit in window.paths.values())
    assert window.pages.count() == 5
    for index in range(5):
        window.nav.setCurrentRow(index)
        app.processEvents()
        assert window.pages.currentWidget().width() <= window.width()
    window.close()


@pytest.mark.parametrize("full_score", [100, 200])
def test_score_heatmap_uniform_errors_and_numeric_sorting(app, full_score):
    students = ["zero", "low", "medium", "high", "full", "re", "ce", "tle", "mle", "mixed"]
    points = []
    point_score = full_score // 10
    for student, accepted in [("zero", 0), ("low", 1), ("medium", 4), ("high", 8), ("full", 10)]:
        points.extend(PointResult(student, "p", str(i), "AC" if i < accepted else "WA", point_score if i < accepted else 0, point_score)
                      for i in range(10))
    for student in ["re", "ce", "tle", "mle", "mixed"]:
        points.extend(PointResult(student, "p", str(i), "RE" if student == "mixed" and i < 5 else "CE" if student == "mixed" else student.upper(), 0, point_score)
                      for i in range(10))
    window = MainWindow(auto_check=False)
    window.batch = BatchResult("色彩检查", students, ["p"], {"p": full_score}, "today", 100,
                               points=points, finished_at="today", testcase_ids={"p": [str(i) for i in range(10)]})
    window.refresh_results()
    displayed = {window.scores.item(row, 1).text(): window.scores.item(row, 2) for row in range(window.scores.rowCount())}
    for student, colour in zip(["zero", "low", "medium", "high", "full"], SCORE_COLOURS):
        assert displayed[student].background().color().name() == colour
    for student in ["re", "ce", "tle", "mle"]:
        item = displayed[student]
        assert item.text() == student.upper()
        assert item.data(Qt.ItemDataRole.UserRole) == 0
        assert item.background().color().name() == STATUS_COLOURS[student.upper()][0]
        assert f"得分：0 / {full_score}" in item.toolTip() and "10 点" in item.toolTip()
    assert displayed["mixed"].text() == "0"
    assert displayed["mixed"].background().color().name() == "#ffffff"
    window.scores.sortItems(2, Qt.SortOrder.DescendingOrder)
    assert [window.scores.item(row, 2).data(Qt.ItemDataRole.UserRole) for row in range(5)] == [point_score * count for count in [10, 8, 4, 1, 0]]
    for row in range(window.scores.rowCount()):
        total = window.scores.item(row, 3)
        assert total.background().color().name() == score_colours(total.data(Qt.ItemDataRole.UserRole), full_score)[0]
    window.close()


@pytest.mark.parametrize("manifest", [True, False])
def test_incomplete_or_invalid_points_do_not_become_uniform_error(app, manifest):
    for points in [
        [PointResult("s", "p", "1", "RE", 0, 50)],
        # An omitted zero-mark point cannot be detected from max_score sums.
        [PointResult("s", "p", "1", "RE", 0, 100)],
        [PointResult("s", "p", "1", "RE", 0, 50), PointResult("s", "p", "1", "RE", 0, 50)],
        [PointResult("s", "p", "1", "RE", 0, 50), PointResult("s", "p", "2", "CANCELLED", 0, 50)],
    ]:
        window = MainWindow(auto_check=False)
        window.batch = BatchResult("未完成", ["s"], ["p"], {"p": 100}, "today", 2,
                                   points=points, finished_at="today", testcase_ids={"p": ["1", "2"]} if manifest else {})
        window.refresh_results()
        assert "未完成" in window.scores.item(0, 2).text()
        assert "暂计" in window.scores.item(0, 3).text()
        assert window.scores.item(0, 2).text() != "RE"
        window.close()


def test_detail_palette_and_selection_keep_verdict_background(app):
    statuses = ["AC", "RE", "CE", "TLE", "MLE"]
    batch = BatchResult("状态色", ["s"], ["p"], {"p": 100}, "today", 5,
                        points=[PointResult("s", "p", str(i), status, 20 if status == "AC" else 0, 20) for i, status in enumerate(statuses)],
                        finished_at="today", testcase_ids={"p": [str(i) for i in range(5)]})
    window = MainWindow(auto_check=False)
    dialog = DetailDialog(batch, "s", parent=window)
    dialog.show()
    app.processEvents()
    for row, status in enumerate(statuses):
        for column in [2, 3]:
            item = dialog.table.item(row, column)
            assert item.background().color().name() == STATUS_COLOURS[status][0]
            assert item.foreground().color().name() == STATUS_COLOURS[status][1]
    item = dialog.table.item(1, 2)
    dialog.table.setCurrentItem(item)
    app.processEvents()
    image = dialog.table.viewport().grab().toImage()
    rect = dialog.table.visualItemRect(item)
    ratio = image.devicePixelRatio()
    assert image.pixelColor(int((rect.left() + 10) * ratio), int((rect.top() + 7) * ratio)).name() == STATUS_COLOURS["RE"][0]
    dialog.close()
    window.close()
