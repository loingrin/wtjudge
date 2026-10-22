import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from tools import archive_release


def write(root, name, contents=b"public"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return path


def make_inputs(tmp_path):
    release, source = tmp_path / "windows", tmp_path / "source"
    write(release, "wtjudge.exe", b"synthetic executable")
    for name in (*archive_release.RUNTIME_FILES, "python312.dll"):
        write(release, "_internal/" + name, name.encode())
    write(release, "demo/testdata/apple/1.out", b"3\n")
    manifest = {"version": archive_release.__version__, "files": [
        {"path": path.relative_to(release).as_posix(), "size": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(release.rglob("*")) if path.is_file()
    ]}
    write(release, "release-manifest.json", json.dumps(manifest).encode())
    write(source, "wtjudge/__init__.py", f"__version__ = '{archive_release.__version__}'\n".encode())
    write(source, "README.md", b"installation instructions")
    write(source, ".git/config", b"private git metadata must remain local")
    write(source, ".github/workflows/test.yml", b"public workflow")
    (source / "demo" / "empty").mkdir(parents=True)
    return release, source


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_checked_archives_have_expected_layout_checksums_and_preserve_inputs(tmp_path):
    release, source = make_inputs(tmp_path)
    before = snapshot(release), snapshot(source)
    output = tmp_path / "archives"
    first = archive_release.create_archives(release, source, output)
    old_archives = snapshot(output)
    second = archive_release.create_archives(release, source, output)
    assert first["directory"] != second["directory"]
    assert first["inputs_unchanged"] is True
    assert (snapshot(release), snapshot(source)) == before
    assert all((output / name).read_bytes() == contents for name, contents in old_archives.items())
    version = archive_release.__version__
    with zipfile.ZipFile(first["windows_zip"]) as archive:
        assert f"wtjudge-{version}/wtjudge.exe" in archive.namelist()
        assert all(name.startswith(f"wtjudge-{version}/") for name in archive.namelist())
        assert archive.testzip() is None
    with zipfile.ZipFile(first["source_zip"]) as archive:
        names = archive.namelist()
        assert f"wtjudge-{version}-source/demo/empty/" in names
        assert any(".github/workflows/test.yml" in name for name in names)
        assert not any("/.git/" in name for name in names)
        assert archive.testzip() is None
    for line in Path(first["checksums"]).read_text().splitlines():
        digest, name = line.split("  ")
        assert digest == hashlib.sha256((Path(first["directory"]) / name).read_bytes()).hexdigest()


@pytest.mark.parametrize("private_name", ["results/report.html", "demo2/student.cpp",
                                         ".venv/python.exe", "validation-secret.json",
                                         "exam.project.json", ".env", ".ssh/id_rsa"])
@pytest.mark.parametrize("input_name", ["release", "source"])
def test_private_material_rejected_before_output_created(tmp_path, private_name, input_name):
    release, source = make_inputs(tmp_path)
    write(release if input_name == "release" else source, private_name, b"private")
    output = tmp_path / "archives"
    with pytest.raises(ValueError, match="Private project material"):
        archive_release.create_archives(release, source, output)
    assert not output.exists()


@pytest.mark.parametrize("damage", ["changed", "unlisted", "version", "missing-runtime", "source-version"])
def test_manifest_and_version_and_runtime_validated(tmp_path, damage):
    release, source = make_inputs(tmp_path)
    if damage == "changed":
        write(release, "wtjudge.exe", b"corrupted")
    elif damage == "unlisted":
        write(release, "extra.txt")
    elif damage == "version":
        manifest = json.loads((release / "release-manifest.json").read_text())
        manifest["version"] = "1.0.0"
        write(release, "release-manifest.json", json.dumps(manifest).encode())
    elif damage == "source-version":
        write(source, "wtjudge/__init__.py", b"__version__ = '1.0.0'")
    else:
        (release / "_internal" / "PySide6" / "Qt6Widgets.dll").unlink()
    output = tmp_path / "archives"
    with pytest.raises(ValueError):
        archive_release.create_archives(release, source, output)
    assert not output.exists()


def test_output_cannot_be_inside_either_original_tree(tmp_path):
    release, source = make_inputs(tmp_path)
    with pytest.raises(ValueError, match="outside both inputs"):
        archive_release.create_archives(release, source, source / "archives")
    assert not (source / "archives").exists()


def test_detects_input_change_during_compression(tmp_path, monkeypatch):
    release, source = make_inputs(tmp_path)
    write_zip = archive_release.write_zip

    def changing_zip(root, destination, prefix, files, directories):
        write_zip(root, destination, prefix, files, directories)
        if root == source:
            write(source, "README.md", b"changed during archive")

    monkeypatch.setattr(archive_release, "write_zip", changing_zip)
    with pytest.raises(ValueError, match="Input changed during archiving"):
        archive_release.create_archives(release, source, tmp_path / "archives")
    assert not list((tmp_path / "archives").rglob("SHA256SUMS.txt"))


def test_rejects_unsafe_manifest_entry(tmp_path):
    release, source = make_inputs(tmp_path)
    manifest = json.loads((release / "release-manifest.json").read_text())
    manifest["files"][0]["path"] = "../teacher-files/private.txt"
    write(release, "release-manifest.json", json.dumps(manifest).encode())
    with pytest.raises(ValueError, match="Unsafe manifest path"):
        archive_release.create_archives(release, source, tmp_path / "archives")
