import json

import pytest

from tools import package_release
from tools.package_release import publish


def test_publish_keeps_existing_exam_and_release_untouched(tmp_path):
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "wtjudge.exe").write_bytes(b"test executable")
    (staged / "_internal").mkdir()
    (staged / "_internal" / "runtime.dll").write_bytes(b"test runtime")
    releases = tmp_path / "dist"
    exam = releases / "wtjudge" / "demo2" / "student.cpp"
    exam.parent.mkdir(parents=True)
    exam.write_bytes(b"teacher-owned exam; preserve exactly")
    first = publish(staged, releases)
    marker = first / "teacher-project.json"
    marker.write_text("keep")
    second = publish(staged, releases)
    assert first != second
    assert marker.read_text() == "keep"
    assert exam.read_bytes() == b"teacher-owned exam; preserve exactly"
    assert (first / "release-manifest.json").is_file()
    assert (second / "_internal" / "runtime.dll").read_bytes() == b"test runtime"


def test_publish_only_public_docs_and_regenerates_synthetic_demo(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    for name in ["README.md", "CHANGELOG.md", "requirements-lock.txt", "docs/VALIDATION.md"]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public documentation", encoding="utf-8")
    for name in ["VALIDATION.md", "validation-v110-audit.md", "validation-v110-engine.json", "demo/submissions/private.cpp"]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private examination material", encoding="utf-8")
    staged = tmp_path / "staged"
    (staged / "_internal").mkdir(parents=True)
    (staged / "wtjudge.exe").write_bytes(b"executable")
    (staged / "_internal" / "runtime.dll").write_bytes(b"runtime")
    (staged / "validation-secret.json").write_text("private")
    (staged / "demo2").mkdir()
    (staged / "demo2" / "student.cpp").write_text("private")
    monkeypatch.setattr(package_release, "ROOT", project)
    target = publish(staged, tmp_path / "dist")
    assert (target / "docs" / "VALIDATION.md").read_text() == "public documentation"
    assert (target / "demo" / "testdata" / "apple" / "1.out").read_text().strip() == "3"
    names = [path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()]
    assert not any(name.startswith("validation-") or "private" in name or "demo2" in name or name == "VALIDATION.md" for name in names)
    manifest = json.loads((target / "release-manifest.json").read_text())
    assert not any("private examination material" in path.read_text(errors="ignore") for path in target.rglob("*") if path.is_file())
    assert set(item["path"] for item in manifest["files"]) == set(names) - {"release-manifest.json"}
    assert (project / "demo" / "submissions" / "private.cpp").read_text() == "private examination material"


def test_publish_rejects_exam_material_in_runtime(tmp_path):
    staged = tmp_path / "staged"
    (staged / "_internal" / "demo2").mkdir(parents=True)
    (staged / "wtjudge.exe").write_bytes(b"executable")
    (staged / "_internal" / "demo2" / "student.cpp").write_text("private")
    releases = tmp_path / "dist"
    with pytest.raises(ValueError, match="拒绝分发"):
        publish(staged, releases)
    assert not releases.exists()


def test_public_license_manifest_only_includes_reviewed_text(tmp_path):
    import hashlib
    license_path = tmp_path / "third_party" / "example" / "LICENSE.txt"
    license_path.parent.mkdir(parents=True)
    license_path.write_bytes(b"actual upstream license")
    manifest_path = tmp_path / "third_party" / "manifest.json"
    manifest_path.write_text(json.dumps({"files": [{"path": "third_party/example/LICENSE.txt",
                                                  "sha256": hashlib.sha256(license_path.read_bytes()).hexdigest()}]}))
    private = tmp_path / "third_party" / "private-audit.json"
    private.write_text("not reviewed")
    target = tmp_path / "release"
    package_release.copy_public_documents(tmp_path, target)
    assert (target / "third_party" / "example" / "LICENSE.txt").read_bytes() == license_path.read_bytes()
    assert not (target / "third_party" / "private-audit.json").exists()
    license_path.write_text("changed after review")
    with pytest.raises(ValueError, match="checksum mismatch"):
        package_release.public_third_party_files(tmp_path)


def test_license_manifest_cannot_select_outside_third_party(tmp_path):
    directory = tmp_path / "third_party"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"files": [{"path": "README.md", "sha256": "unused"}]}))
    with pytest.raises(ValueError, match="Invalid public third-party"):
        package_release.public_third_party_files(tmp_path)
