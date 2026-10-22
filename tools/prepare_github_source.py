"""Prepare a fresh, allowlisted public source tree without touching originals."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.create_demo import make_demo
from tools.package_release import PUBLIC_DOCUMENTS, public_third_party_files
from wtjudge import __version__


ROOT_FILES = (
    "app.py", "setup.bat", "run.bat", "build.bat", "requirements.txt",
    "requirements-dev.txt", "requirements-lock.txt", "pytest.ini",
    "version_info.txt", "wtjudge.spec", "README.md", "CHANGELOG.md", ".gitignore",
)
TOOL_FILES = (
    "tools/create_demo.py", "tools/package_release.py",
    "tools/prepare_github_source.py", "tools/archive_release.py",
)
ASSET_FILES = ("assets/wotu.png", "assets/wotu.ico")
TREE_SUFFIXES = {"wtjudge": {".py"}, "tests": {".py"}}
EXCLUDED_PARTS = {
    "__pycache__", ".venv", ".git", ".pytest_cache", "results", "dist", "build",
}


def _is_link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def public_files(root):
    """Select project sources and named public docs; ignore all other files."""
    root = Path(root).resolve()
    selected = set(ROOT_FILES + TOOL_FILES + ASSET_FILES + PUBLIC_DOCUMENTS + public_third_party_files(root))
    for directory, suffixes in TREE_SUFFIXES.items():
        tree = root / directory
        if _is_link(tree):
            raise ValueError(f"Public source cannot contain links: {directory}")
        if tree.is_dir():
            for path in tree.rglob("*"):
                relative = path.relative_to(root)
                if any(part in EXCLUDED_PARTS or part.startswith("validation-") for part in relative.parts):
                    continue
                if path.is_file() and path.suffix in suffixes:
                    selected.add(relative.as_posix())
    result = []
    for name in sorted(selected):
        path = root / name
        if not path.is_file():
            continue
        if any(_is_link(parent) for parent in [path, *path.parents] if parent != root.parent):
            raise ValueError(f"Public source cannot contain links: {name}")
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Public source escapes project: {name}")
        result.append(path)
    return result


def _path_spellings(path):
    text = str(path)
    return {text.casefold(), text.replace("\\", "/").casefold(), text.replace("\\", "\\\\").casefold()}


def check_public_text(paths, root):
    """Reject local workspace/home paths while permitting generic setup examples."""
    forbidden = _path_spellings(Path(root).resolve()) | _path_spellings(Path.home())
    for path in paths:
        if path.suffix.lower() in {".png", ".ico"}:
            continue
        try:
            contents = path.read_text(encoding="utf-8-sig").casefold()
        except UnicodeDecodeError as exc:
            raise ValueError(f"Public source is not UTF-8 text: {path.name}") from exc
        if any(spelling and spelling in contents for spelling in forbidden):
            raise ValueError(f"Private local path found in public file: {path.relative_to(root).as_posix()}")


def prepare_source(root=ROOT, destination_parent=None, version=__version__):
    root = Path(root).resolve()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid release version")
    parent = Path(destination_parent).resolve() if destination_parent else root / "build"
    if parent == root or root.is_relative_to(parent):
        raise ValueError("Destination must not be the project root or its parent")
    paths = public_files(root)
    if not (root / "app.py").is_file() or not (root / "wtjudge" / "__init__.py").is_file():
        raise ValueError("Project app.py or wtjudge package is missing")
    check_public_text(paths, root)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / f"github-source-v{version}"
    if target.exists():
        target = parent / f"github-source-v{version}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    # mkdir without exist_ok prevents overwrites, including concurrent exports.
    target.mkdir()
    for path in paths:
        destination = target / path.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    make_demo(target / "demo")
    manifest = []
    for path in sorted(target.rglob("*")):
        if path.is_file():
            manifest.append({"path": path.relative_to(target).as_posix(), "size": path.stat().st_size,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (target / "source-manifest.json").write_text(
        json.dumps({"version": version, "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-parent", type=Path)
    args = parser.parse_args()
    print(f"Public source: {prepare_source(destination_parent=args.output_parent)}", flush=True)


if __name__ == "__main__":
    main()
