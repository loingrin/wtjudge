"""Create checked, public release ZIPs without modifying either input tree."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wtjudge import __version__


PRIVATE_PARTS = {
    "results", "demo2", ".venv", "venv", ".aws", ".ssh", ".codex", ".agents",
    ".env", ".git-credentials", ".gitconfig", ".npmrc", ".pypirc", "__pycache__",
}
PRIVATE_NAMES = {"id_rsa", "id_ed25519", "credentials", "credentials.json"}
RUNTIME_FILES = (
    "base_library.zip", "PySide6/QtCore.pyd", "PySide6/Qt6Core.dll",
    "PySide6/Qt6Gui.dll", "PySide6/Qt6Widgets.dll",
    "PySide6/plugins/platforms/qwindows.dll",
)
CHUNK_SIZE = 1024 * 1024


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, *, source: bool = False) -> tuple[dict, list[str]]:
    """Inspect an input tree; Git metadata is deliberately never traversed."""
    files, directories = {}, []

    def visit(directory: Path):
        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            relative = path.relative_to(root)
            parts = [part.casefold() for part in relative.parts]
            if source and ".git" in parts:
                continue
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"Refusing linked input: {relative}")
            if (any(part in PRIVATE_PARTS or part == ".git" or part.startswith("validation-")
                    or part.startswith(".env.") for part in parts)
                    or path.name.casefold().endswith(".project.json")
                    or path.name.casefold() in PRIVATE_NAMES):
                raise ValueError(f"Private project material in input: {relative}")
            if path.is_dir():
                directories.append(relative.as_posix())
                visit(path)
            elif path.is_file():
                files[relative.as_posix()] = {
                    "size": path.stat().st_size, "sha256": digest_file(path),
                }
            else:
                raise ValueError(f"Unsupported input: {relative}")

    visit(root)
    return files, directories


def check_manifest(root: Path, name: str, files: dict, version: str):
    try:
        manifest = json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Invalid {name}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("version") != version:
        raise ValueError(f"Version mismatch in {name}; expected {version}")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError(f"Invalid file list in {name}")
    listed = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid entry in {name}")
        relative = entry.get("path", "")
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or ":" in relative or relative.startswith("/")
                or any(part in {".", "..", ""} for part in relative.split("/"))
                or PurePosixPath(relative).as_posix() != relative):
            raise ValueError(f"Unsafe manifest path in {name}")
        if relative in listed:
            raise ValueError(f"Duplicate manifest path: {relative}")
        if (type(entry.get("size")) is not int or entry["size"] < 0
                or not isinstance(entry.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError(f"Invalid size or SHA256 in {name}: {relative}")
        listed[relative] = {"size": entry["size"], "sha256": entry["sha256"]}
    expected = {path: value for path, value in files.items() if path != name}
    if listed != expected:
        changed = sorted(set(listed) ^ set(expected))
        changed += sorted(path for path in set(listed) & set(expected)
                          if listed[path] != expected[path])
        raise ValueError(f"Manifest size/SHA256 or coverage mismatch in {name}: {', '.join(changed[:8])}")


def check_source_version(source: Path, version: str):
    try:
        tree = ast.parse((source / "wtjudge" / "__init__.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as error:
        raise ValueError("Cannot read source version") from error
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(target, ast.Name) and target.id == "__version__"
                        for target in node.targets)]
    if versions != [version]:
        raise ValueError(f"Source version mismatch; expected {version}")


def check_runtime(release: Path):
    runtime = release / "_internal"
    if not (release / "wtjudge.exe").is_file() or not runtime.is_dir():
        raise ValueError("Windows release must contain wtjudge.exe and _internal")
    missing = [name for name in RUNTIME_FILES if not (runtime / name).is_file()]
    if not any(path.is_file() for path in runtime.glob("python3[0-9]*.dll")):
        missing.append("python3*.dll")
    if missing:
        raise ValueError(f"Missing Windows runtime dependencies: {', '.join(missing)}")


def write_zip(root: Path, destination: Path, prefix: str, files: dict, directories: list[str]):
    with zipfile.ZipFile(destination, mode="x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        archive.mkdir(prefix + "/")
        for relative in directories:
            archive.mkdir(prefix + "/" + relative + "/")
        for relative in sorted(files):
            path = root / relative
            info = zipfile.ZipInfo.from_file(path, prefix + "/" + relative)
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as source, archive.open(info, mode="w", force_zip64=True) as target:
                shutil.copyfileobj(source, target, length=CHUNK_SIZE)
    # Read back every compressed member; ZipFile.testzip checks CRCs, while the
    # streamed hashes also verify correspondence with the audited input bytes.
    with zipfile.ZipFile(destination) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != len(files):
            raise ValueError("Archive file coverage mismatch")
        for item in members:
            relative = item.filename.removeprefix(prefix + "/")
            digest = hashlib.sha256()
            with archive.open(item) as stream:
                for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                    digest.update(chunk)
            if files.get(relative) != {"size": item.file_size, "sha256": digest.hexdigest()}:
                raise ValueError(f"Archive verification failed: {relative}")


def create_archives(release_dir, source_dir, output_root=None) -> dict:
    version = __version__
    release, source = Path(release_dir).resolve(), Path(source_dir).resolve()
    output = Path(output_root or ROOT / "dist" / "releases").resolve()
    if not release.is_dir() or not source.is_dir():
        raise ValueError("Release and source directories must already exist")
    if (release == source or release in source.parents or source in release.parents
            or output == release or release in output.parents
            or output == source or source in output.parents):
        raise ValueError("Inputs must be distinct; archive output must be outside both inputs")
    check_runtime(release)
    release_files, release_dirs = inventory(release)
    source_files, source_dirs = inventory(source, source=True)
    check_manifest(release, "release-manifest.json", release_files, version)
    check_source_version(source, version)
    if "source-manifest.json" in source_files:
        check_manifest(source, "source-manifest.json", source_files, version)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"v{version}"
    while True:
        try:
            destination.mkdir()
            break
        except FileExistsError:
            destination = output / f"v{version}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    windows_zip = destination / f"wtjudge-v{version}-windows-x64.zip"
    source_zip = destination / f"wtjudge-v{version}-source.zip"
    write_zip(release, windows_zip, f"wtjudge-{version}", release_files, release_dirs)
    write_zip(source, source_zip, f"wtjudge-{version}-source", source_files, source_dirs)
    if (inventory(release) != (release_files, release_dirs)
            or inventory(source, source=True) != (source_files, source_dirs)):
        raise ValueError("Input changed during archiving; do not publish these archives")
    sums = {path.name: digest_file(path) for path in (windows_zip, source_zip)}
    checksum_file = destination / "SHA256SUMS.txt"
    checksum_file.write_text("".join(f"{digest}  {name}\n" for name, digest in sums.items()),
                             encoding="ascii", newline="\n")
    return {"version": version, "directory": str(destination), "windows_zip": str(windows_zip),
            "source_zip": str(source_zip), "checksums": str(checksum_file), "sha256": sums,
            "release_directory": str(release), "source_directory": str(source),
            "inputs_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "dist" / "releases")
    args = parser.parse_args()
    try:
        result = create_archives(args.release_dir, args.source_dir, args.output_root)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Cannot create release archives: {error}\n")
    metadata = ROOT / "build" / "github-archives.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Archives: {result['directory']}", flush=True)


if __name__ == "__main__":
    main()
