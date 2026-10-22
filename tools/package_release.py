"""Build in owned staging, publish to a NEW directory; preserve teacher files."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wtjudge import __version__
from tools.create_demo import make_demo


PUBLIC_DOCUMENTS = (
    "README.md", "CHANGELOG.md", "requirements-lock.txt",
    "docs/INSTALL.md", "docs/VALIDATION.md", "docs/RELEASE-v1.1.1.md",
    "docs/THIRD_PARTY_NOTICES.md",
    "docs/images/scores.png", "docs/images/details.png",
)


def public_third_party_files(root):
    """Use the reviewed license manifest; never recursively copy arbitrary data."""
    root = Path(root).resolve()
    manifest_path = root / "third_party" / "manifest.json"
    if not manifest_path.is_file():
        return ()
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {"third_party/manifest.json"}
    for entry in document["files"]:
        name = entry["path"]
        relative = Path(name)
        path = root / relative
        if (not name.startswith("third_party/") or ".." in relative.parts or relative.is_absolute()
                or not path.resolve().is_relative_to(root / "third_party") or path.is_symlink()
                or not path.is_file()):
            raise ValueError("Invalid public third-party license path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Public third-party license checksum mismatch")
        result.add(relative.as_posix())
    return tuple(sorted(result))


def copy_public_documents(root, target):
    """Copy only reviewed public documentation, never local audit evidence."""
    root, target = Path(root), Path(target)
    for name in PUBLIC_DOCUMENTS + public_third_party_files(root):
        source = root / name
        if source.is_file():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def publish(staged, releases):
    staged, releases = Path(staged).resolve(), Path(releases).resolve()
    if not (staged / "wtjudge.exe").is_file() or not (staged / "_internal").is_dir():
        raise ValueError("暂存目录缺少 EXE 或运行依赖，无法分发")
    for path in (staged / "_internal").rglob("*"):
        relative = path.relative_to(staged / "_internal")
        if (any(part.lower() in {"demo2", "results", "score", "submissions", "testdata"}
                or part.lower().startswith("validation-") for part in relative.parts)
                or path.suffix.lower() in {".cpp", ".in", ".out"}
                or path.name.lower().endswith(".project.json")):
            raise ValueError("运行依赖中发现考试或本地验收资料，拒绝分发")
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / f"wtjudge-{__version__}"
    if target.exists():
        target = releases / f"wtjudge-{__version__}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    # Never overwrite an earlier release, even if the same version is rebuilt.
    target.mkdir()
    shutil.copy2(staged / "wtjudge.exe", target / "wtjudge.exe")
    shutil.copytree(staged / "_internal", target / "_internal", dirs_exist_ok=False)
    # Regenerate the synthetic demo instead of copying a possibly edited demo
    # directory that a teacher might have used for a real examination.
    make_demo(target / "demo")
    copy_public_documents(ROOT, target)
    manifest = []
    for path in sorted(target.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            manifest.append({"path": path.relative_to(target).as_posix(), "size": path.stat().st_size, "sha256": digest.hexdigest()})
    (target / "release-manifest.json").write_text(json.dumps({"version": __version__, "files": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    staging_root = ROOT / "build" / "release"
    if not args.skip_build:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(staging_root), str(ROOT / "wtjudge.spec")], cwd=ROOT, check=True)
    target = publish(staging_root / "wtjudge", ROOT / "dist")
    print(f"Release: {target}", flush=True)
    (ROOT / "validation-latest-release.json").write_text(json.dumps({"version": __version__, "directory": str(target)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
