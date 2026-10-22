"""Resolve the same brand assets in source and onedir distributions."""
from pathlib import Path
import sys


def asset_path(name: str) -> Path:
    roots = []
    if getattr(sys, "frozen", False):
        roots.extend([Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets",
                      Path(sys.executable).parent / "assets"])
    roots.append(Path(__file__).resolve().parents[2] / "assets")
    return next((root / name for root in roots if (root / name).is_file()), roots[0] / name)
