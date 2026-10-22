from __future__ import annotations

import copy
from pathlib import Path

from .models import Problem, Project, Scan, Submission, TestCase, natural_key


def visible(path: Path) -> bool:
    return not path.name.startswith((".", "~", "~$")) and not (getattr(path.stat(), "st_file_attributes", 0) & 2)


def children(root: Path):
    return sorted((p for p in root.iterdir() if visible(p) and not p.is_symlink()), key=lambda p: natural_key(p.name))


def scan_project(project: Project) -> Scan:
    """Only direct directories and direct testcase files are scanned."""
    roots = [Path(project.submissions_dir), Path(project.testdata_dir)]
    for label, root, raw in zip(("考生目录", "测试数据目录"), roots, (project.submissions_dir, project.testdata_dir)):
        if not raw or not root.is_dir():
            raise ValueError(f"{label}不存在或不可访问：{raw or '未选择'}")
    students = [p.name for p in children(roots[0]) if p.is_dir()]
    old = {p.id: p for p in project.problems}
    problems, warnings, snapshot = [], [], {"testdata": {}, "submissions": {}}
    for directory in children(roots[1]):
        if not directory.is_dir():
            continue
        problem = copy.deepcopy(old.get(directory.name, Problem(directory.name)))
        previous_ids = set(problem.testcase_scores)
        problem.cases, problem.errors = [], []
        pairs = {}
        entries = []
        for path in children(directory):
            ext = path.suffix.casefold()
            if not path.is_file() or ext not in {".in", ".out"}:
                continue
            key = path.stem.casefold()
            pair = pairs.setdefault(key, {"id": path.stem})
            if ext in pair:
                problem.errors.append(f"重名冲突：{pair[ext].name} 与 {path.name}")
            else:
                pair[ext] = path
            stat = path.stat()
            entries.append([path.name, stat.st_size, stat.st_mtime_ns])
        for pair in sorted(pairs.values(), key=lambda item: natural_key(item["id"])):
            inp, out = pair.get(".in"), pair.get(".out")
            if inp is None or out is None:
                problem.errors.append(f"数据缺失：{pair['id']} 缺少 {'.in' if inp is None else '.out'}")
            problem.cases.append(TestCase(pair["id"], str(inp.resolve()) if inp else "", str(out.resolve()) if out else "",
                                          inp.stat().st_size if inp else 0, out.stat().st_size if out else 0))
        if problem.score_mode == "custom" and previous_ids != {c.id for c in problem.cases}:
            problem.scores_confirmed = False
        if problem.score_mode == "custom" and project.data_snapshot and project.data_snapshot.get("testdata", {}).get(problem.id) != entries:
            problem.scores_confirmed = False
        problem.distribute()
        problems.append(problem)
        snapshot["testdata"][problem.id] = entries
    submissions = {}
    for student in students:
        student_root = (roots[0] / student).resolve()
        direct = children(student_root)
        flat_sources = [p for p in direct if p.is_file() and p.suffix.casefold() == ".cpp"]
        all_sources = list(flat_sources)
        for item in direct:
            if item.is_dir():
                all_sources.extend(p for p in children(item) if p.is_file() and p.suffix.casefold() == ".cpp")
        for problem in problems:
            folder = roots[0] / student / problem.id
            candidates = [p for p in children(folder) if p.is_file() and p.suffix.casefold() == ".cpp"] if folder.is_dir() else []
            if not candidates:
                # Flat contest submissions need an exact per-problem name. A
                # lone unrelated flat .cpp must not be used for every problem.
                names = {problem.source_file.casefold(), f"{problem.id}.cpp".casefold(), f"{Path(problem.input_filename).stem}.cpp".casefold()}
                candidates = [p for p in flat_sources if p.name.casefold() in names]
            submission = Submission(student, problem.id, candidates=[str(p.resolve()) for p in candidates])
            override = project.source_overrides.get(f"{student}/{problem.id}")
            override_path = Path(override).resolve() if override else None
            valid_override = bool(override_path and override_path.is_relative_to(student_root)
                                  and override_path.is_file() and override_path.suffix.casefold() == ".cpp")
            preferred = [p for p in candidates if p.name.casefold() == problem.source_file.casefold()]
            if override and not valid_override:
                submission.status = "AMBIGUOUS_SOURCE"
                submission.candidates = sorted(set(submission.candidates + [str(p.resolve()) for p in all_sources]), key=natural_key)
                warnings.append(f"{student}/{problem.id}：已保存的人工源码路径无效或不在该考生目录内，请重新指定")
            elif valid_override:
                submission.source = str(override_path)
                if submission.source not in submission.candidates:
                    submission.candidates.append(submission.source)
            elif len(candidates) == 1:
                submission.source = str(candidates[0].resolve())
            elif len(preferred) == 1:
                submission.source = str(preferred[0].resolve())
            else:
                submission.status = "AMBIGUOUS_SOURCE" if candidates else "NO_SOURCE"
                suggestions = [str(p.resolve()) for p in all_sources if p not in candidates]
                if submission.status == "NO_SOURCE":
                    submission.candidates = suggestions
                warning = f"{student}/{problem.id}：{submission.status}"
                if override and not valid_override:
                    warning += "；已保存的人工源码路径无效或不在该考生目录内，请重新指定"
                if submission.status == "NO_SOURCE" and suggestions:
                    warning += "；发现其他位置的 .cpp，需人工确认映射：" + "、".join(str(Path(p).relative_to(student_root)) for p in suggestions)
                warnings.append(warning)
            submissions[student, problem.id] = submission
    snapshot["submissions"] = {student: {p.id: [[s, Path(s).stat().st_size, Path(s).stat().st_mtime_ns]
                                              for s in submissions[student, p.id].candidates] for p in problems} for student in students}
    if project.data_snapshot and project.data_snapshot != snapshot:
        warnings.insert(0, "目录内容与保存时不同：题目、数据或源码的文件名/大小/修改时间已变更，请核对配置。平均分值已重算，自定义分值须重新确认。")
    return Scan(students, problems, submissions, warnings, snapshot)
