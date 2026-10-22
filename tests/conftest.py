import os
import shutil
from pathlib import Path

import pytest

from tools.create_demo import make_demo
from wtjudge.core.models import Project


@pytest.fixture(scope="session")
def compiler():
    candidates = [os.environ.get("WTJUDGE_GXX"), shutil.which("g++"), r"C:\MinGW64\bin\g++.exe", r"C:\msys64\ucrt64\bin\g++.exe"]
    path = next((p for p in candidates if p and Path(p).is_file()), None)
    if path is None:
        pytest.skip("No installed MinGW-w64 G++; integration needs WTJUDGE_GXX")
    return path


@pytest.fixture
def demo(tmp_path, compiler):
    root = tmp_path / "中文 含空格考试"
    make_demo(root)
    return Project(project_name="中文 模拟赛", submissions_dir=str(root / "submissions"), testdata_dir=str(root / "testdata"),
                   report_dir=str(root / "results"), compiler_path=compiler)
