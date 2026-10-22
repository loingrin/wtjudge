from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, fields
from pathlib import Path

from wtjudge.core.models import BatchResult, PointResult, Problem, Project


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".wtjudge-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_project(project: Project, path):
    data = asdict(project)
    for problem in data["problems"]:
        problem.pop("cases", None)
        problem.pop("errors", None)
    atomic_json(path, data)


def load_project(path) -> Project:
    with open(path, encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("不支持的项目格式或版本（需要 schema_version=1）")
    allowed = {f.name for f in fields(Project)}
    args = {k: v for k, v in data.items() if k in allowed and k != "problems"}
    problem_fields = {f.name for f in fields(Problem)} - {"cases", "errors"}
    args["problems"] = [Problem(**{k: v for k, v in p.items() if k in problem_fields}) for p in data.get("problems", [])]
    project = Project(**args)
    if not all(isinstance(v, str) for v in [project.project_name, project.submissions_dir, project.testdata_dir, project.report_dir, project.compiler_path]):
        raise ValueError("项目路径或名称格式无效")
    for attribute in ("submissions_dir", "testdata_dir", "report_dir", "compiler_path"):
        value = getattr(project, attribute)
        if value:
            setattr(project, attribute, str((Path(path).resolve().parent / value).resolve()))
    return project


def load_result(path):
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    data["points"] = [PointResult(**p) for p in data["points"]]
    return BatchResult(**data)
