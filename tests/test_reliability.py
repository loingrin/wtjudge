"""Regressions from the real demo2 contest, without changing its files."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from wtjudge.core import executor, judge
from wtjudge.core.comparator import ComparisonCancelled, compare_files
from wtjudge.core.compiler import Compilation
from wtjudge.core.executor import Execution
from wtjudge.core.models import BatchResult, PointResult, Project
from wtjudge.core.scanner import scan_project


def small_project(tmp_path):
    submissions, data = tmp_path / "submissions", tmp_path / "data"
    for student in ("001", "002"):
        folder = submissions / student / "sum"
        folder.mkdir(parents=True)
        (folder / "sum.cpp").write_text("int main(){}")
    folder = data / "sum"
    folder.mkdir(parents=True)
    for n in (1, 2):
        (folder / f"{n}.in").write_text("1 2")
        (folder / f"{n}.out").write_text("3")
    return Project(submissions_dir=str(submissions), testdata_dir=str(data), compiler_path="fake-g++.exe")


def mock_execution(monkeypatch):
    monkeypatch.setattr(judge, "validate_compiler", lambda *args: (True, "OK"))
    def compile_fake(compiler, source, cache, *args):
        executable = Path(cache) / "program.exe"
        executable.write_bytes(b"not executed")
        return Compilation("OK", str(executable))
    monkeypatch.setattr(judge, "compile_source", compile_fake)
    def run_fake(*args):
        Path(args[7]).write_text("3")
        return Execution("OK", 1, 10, 0)
    monkeypatch.setattr(judge, "run_process", run_fake)
    return compile_fake


def test_locked_cache_retries_and_does_not_abort_next_student(tmp_path, monkeypatch):
    project = small_project(tmp_path)
    mock_execution(monkeypatch)
    original = executor.shutil.rmtree
    locked = []
    def delete(path):
        if Path(path).name.startswith("wtjudge-compile-") and (not locked or str(path) == locked[0]):
            if not locked:
                locked.append(str(path))
            raise PermissionError("injected Windows executable lock")
        return original(path)
    monkeypatch.setattr(executor.shutil, "rmtree", delete)
    monkeypatch.setattr(executor.time, "sleep", lambda _: None)
    try:
        batch = judge.judge_batch(project)
        assert batch.complete and len(batch.points) == 4
        assert len(batch.cleanup_warnings) == 1 and locked[0] in batch.cleanup_warnings[0]
        assert all(point.status == "AC" for point in batch.points)
        assert any(point.student_id == "002" for point in batch.points)
    finally:
        for directory in locked:
            original(directory)


def test_submission_exception_is_local_and_next_student_runs(tmp_path, monkeypatch):
    project = small_project(tmp_path)
    compile_fake = mock_execution(monkeypatch)
    def fail_first(compiler, source, *args):
        if Path(source).parents[1].name == "001":
            raise PermissionError("injected compile cache failure")
        return compile_fake(compiler, source, *args)
    monkeypatch.setattr(judge, "compile_source", fail_first)
    batch = judge.judge_batch(project)
    assert not batch.complete and not batch.failure
    assert [p.status for p in batch.points if p.student_id == "001"] == ["SYSTEM_ERROR"] * 2
    assert [p.status for p in batch.points if p.student_id == "002"] == ["AC"] * 2
    assert batch.coverage_errors() == []


def test_one_point_error_does_not_abort_remaining_points(tmp_path, monkeypatch):
    project = small_project(tmp_path)
    mock_execution(monkeypatch)
    original = judge.stream_copy
    count = 0
    def fail_first(*args):
        nonlocal count
        count += 1
        if count == 1:
            raise OSError("injected copy failure")
        return original(*args)
    monkeypatch.setattr(judge, "stream_copy", fail_first)
    batch = judge.judge_batch(project)
    assert [point.status for point in batch.points] == ["SYSTEM_ERROR", "AC", "AC", "AC"]
    assert not batch.complete and batch.coverage_errors() == []


def test_duplicate_result_cannot_hide_missing_testcase():
    result = BatchResult("test", ["001"], ["sum"], {"sum":100}, "start", 2,
                         points=[PointResult("001", "sum", "1", "AC", 50, 50)] * 2, finished_at="end",
                         testcase_ids={"sum":["1", "2"]})
    assert not result.complete and not result.standings()[0]["completed"]
    assert any("重复" in e for e in result.coverage_errors())
    assert any("缺少" in e for e in result.coverage_errors())


def test_cancel_comparison_releases_both_open_files_before_cleanup(tmp_path):
    class LateCancel:
        calls = 0
        def is_set(self):
            self.calls += 1
            return self.calls >= 4
    a, b = tmp_path / "actual.out", tmp_path / "expected.out"
    a.write_bytes(b"x" * 200000)
    b.write_bytes(b"x" * 200000)
    try:
        compare_files(a, b, cancel=LateCancel())
        pytest.fail("expected cancellation")
    except ComparisonCancelled:
        # Keep traceback alive while deleting: this failed on Windows before
        # generators were explicitly closed in compare_files finally.
        a.unlink()
        b.unlink()


def test_flat_sources_strict_matching_and_teacher_mapping(tmp_path):
    project = small_project(tmp_path)
    root = Path(project.submissions_dir) / "001"
    (root / "sum" / "sum.cpp").rename(root / "sum.cpp")
    scan = scan_project(project)
    assert scan.submissions["001", "sum"].source == str((root / "sum.cpp").resolve())
    (root / "sum.cpp").rename(root / "unrelated.cpp")
    scan = scan_project(project)
    assert scan.submissions["001", "sum"].status == "NO_SOURCE"
    assert any("需人工确认映射" in warning for warning in scan.warnings)
    alias = root / "中文目录"
    alias.mkdir()
    (root / "unrelated.cpp").rename(alias / "代码.cpp")
    project.source_overrides["001/sum"] = str(alias / "代码.cpp")
    assert scan_project(project).submissions["001", "sum"].source == str((alias / "代码.cpp").resolve())
    project.source_overrides["001/sum"] = str(Path(project.submissions_dir) / "002" / "sum" / "sum.cpp")
    assert scan_project(project).submissions["001", "sum"].status == "AMBIGUOUS_SOURCE"
