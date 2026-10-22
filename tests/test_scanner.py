from pathlib import Path

import pytest

from tools.create_demo import make_demo
from wtjudge.core.models import Project, filename_error
from wtjudge.core.scanner import scan_project
from wtjudge.storage.project import load_project, save_project


def fixture_project(tmp_path):
    make_demo(tmp_path)
    return Project(submissions_dir=str(tmp_path / "submissions"), testdata_dir=str(tmp_path / "testdata"))


def test_dynamic_scanner_and_exact_distribution(tmp_path):
    project = fixture_project(tmp_path)
    scan = scan_project(project)
    assert len(scan.students) == 3
    assert [len(p.cases) for p in scan.problems] == [3, 25, 6, 10]
    road = next(p for p in scan.problems if p.id == "road")
    assert list(road.testcase_scores.values()) == [17, 17, 17, 17, 16, 16]
    game = next(p for p in scan.problems if p.id == "game")
    assert [c.id for c in game.cases][:12] == [str(i) for i in range(1, 13)]
    assert scan.submissions["HBCSP26003", "road"].status == "NO_SOURCE"
    assert not scan.errors


def test_missing_pair_blocks_and_uppercase_extensions(tmp_path):
    project = fixture_project(tmp_path)
    folder = Path(project.testdata_dir) / "apple"
    (folder / "1.in").rename(folder / "1.IN")
    assert not scan_project(project).errors
    (folder / "2.out").unlink()
    assert any("数据缺失：2" in e for e in scan_project(project).errors)
    (folder / "nested").mkdir()
    (folder / "nested" / "extra.in").write_text("ignored")
    assert len(scan_project(project).problems[0].cases) == 3


def test_ambiguous_source_and_override(tmp_path):
    project = fixture_project(tmp_path)
    folder = Path(project.submissions_dir) / "HBCSP26001" / "apple"
    (folder / "apple.cpp").rename(folder / "a.cpp")
    (folder / "b.CPP").write_text("int main(){}")
    scan = scan_project(project)
    submission = scan.submissions["HBCSP26001", "apple"]
    assert submission.status == "AMBIGUOUS_SOURCE"
    assert scan.errors
    project.source_overrides["HBCSP26001/apple"] = submission.candidates[1]
    assert scan_project(project).submissions["HBCSP26001", "apple"].source.endswith("b.CPP")


@pytest.mark.parametrize("name", ["../apple.in", "C:\\a.out", "CON.out", "NUL", "a/b", "..", "a.", "bad:out"])
def test_reject_unsafe_filenames(name):
    assert filename_error(name)


def test_project_roundtrip_and_changed_custom_points(tmp_path):
    project = fixture_project(tmp_path)
    scan = scan_project(project)
    project.problems, project.data_snapshot = scan.problems, scan.snapshot
    road = next(p for p in project.problems if p.id == "road")
    road.score_mode = "custom"
    path = tmp_path / "考试.json"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.problems[2].testcase_scores == road.testcase_scores
    assert not scan_project(loaded).warnings[0].startswith("目录内容与保存时不同")
    folder = Path(project.testdata_dir) / "road"
    (folder / "7.in").write_text("1 2")
    (folder / "7.out").write_text("3")
    changed = scan_project(loaded)
    assert changed.warnings[0].startswith("目录内容与保存时不同")
    assert any("自定义分值" in error for error in changed.errors)


def test_conflict_on_normalized_stem(tmp_path):
    project = fixture_project(tmp_path)
    folder = Path(project.testdata_dir) / "apple"
    (folder / "test.in").write_text("1")
    (folder / "test.IN").write_text("2") if os_case_sensitive(folder) else (folder / "TEST.out").write_text("1")
    if os_case_sensitive(folder):
        assert any("重名冲突" in e for e in scan_project(project).errors)
    else:
        # NTFS normally disallows same-name extension-only conflicts. Pairing is case-insensitive.
        assert not scan_project(project).errors


def os_case_sensitive(folder):
    return not (folder / "TEST.in").exists()
