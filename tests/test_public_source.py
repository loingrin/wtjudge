import hashlib
import json

import pytest

from tools.prepare_github_source import prepare_source


def write(root, name, contents="public"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def fixture_project(root):
    write(root, "app.py", "print('demo')")
    write(root, "wtjudge/__init__.py", "__version__ = '1.1.1'")
    write(root, "tests/test_example.py", "def test_example(): assert True")
    write(root, "tools/create_demo.py")
    write(root, "README.md")
    write(root, "docs/INSTALL.md", "Example compiler: C:\\MinGW64\\bin\\g++.exe")
    write(root, "docs/VALIDATION.md")
    write(root, "docs/RELEASE-v1.1.1.md")
    for name in ["wtjudge/__pycache__/private.py", "wtjudge/validation-secret.py",
                 "tests/results/private.py", "dist/demo2/student.cpp", "results/report.json",
                 "validation-engine.json", "VALIDATION.md", "demo.project.json", "wtjudge_v1.0.md",
                 "tools/replay_exam_v110.py", "demo/submissions/real-student/exam.cpp", "docs/private-audit.md"]:
        write(root, name, "private examination material")


def snapshot(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_source_export_allowlist_preserves_originals_and_existing_exports(tmp_path):
    root = tmp_path / "project"
    fixture_project(root)
    before = snapshot(root)
    output = tmp_path / "exports"
    first = prepare_source(root, output, "1.1.1")
    write(first, "keep.txt", "teacher-owned marker")
    second = prepare_source(root, output, "1.1.1")
    assert first != second
    assert (first / "keep.txt").read_text() == "teacher-owned marker"
    assert snapshot(root) == before
    names = {path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file()}
    assert {"app.py", "wtjudge/__init__.py", "tests/test_example.py", "docs/INSTALL.md", "docs/VALIDATION.md"} <= names
    assert "demo/testdata/apple/1.in" in names
    assert not any("private" in name or "validation-" in name or name == "VALIDATION.md" or "demo2" in name or name.endswith("project.json") for name in names)
    assert not any("private examination material" in path.read_text(errors="ignore") for path in second.rglob("*") if path.is_file())
    manifest = json.loads((second / "source-manifest.json").read_text())
    assert manifest["version"] == "1.1.1"
    assert set(item["path"] for item in manifest["files"]) == names - {"source-manifest.json"}
    assert all(not item["path"].startswith(("/", "\\")) for item in manifest["files"])


@pytest.mark.parametrize("escaped", [False, True])
def test_source_export_rejects_private_local_workspace_paths(tmp_path, escaped):
    root = tmp_path / "project"
    fixture_project(root)
    local_path = str(root)
    write(root, "README.md", local_path.replace("\\", "\\\\") if escaped else local_path)
    output = tmp_path / "exports"
    with pytest.raises(ValueError, match="Private local path"):
        prepare_source(root, output, "1.1.1")
    assert not output.exists()


def test_source_export_never_uses_project_root_as_destination(tmp_path):
    root = tmp_path / "project"
    fixture_project(root)
    with pytest.raises(ValueError, match="Destination"):
        prepare_source(root, root, "1.1.1")
