from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUS_TEXT = {
    "AC": "答案正确", "WA": "答案错误", "TLE": "超过墙钟时限",
    "MLE": "有证据的内存超限", "RE": "程序异常退出", "CE": "编译失败",
    "NO_SOURCE": "未找到源码", "AMBIGUOUS_SOURCE": "源码歧义，需人工指定",
    "NO_OUTPUT": "未生成指定输出文件", "OUTPUT_LIMIT": "输出超过上限",
    "SYSTEM_ERROR": "系统错误，需重判", "CANCELLED": "已取消，未评测",
}
INVALID = {"SYSTEM_ERROR", "CANCELLED", "AMBIGUOUS_SOURCE"}
MODES = {"ignore_trailing_whitespace": "忽略行末空白", "strict": "严格比较", "tokens": "按单词比较"}


def natural_key(value: str):
    return tuple((1, int(s), len(s)) if s.isdigit() else (0, s.casefold())
                 for s in re.split(r"(\d+)", str(value)))


def filename_error(name: str) -> str:
    if not name or name != name.strip() or name.endswith((".", " ")):
        return "文件名不能为空、含首尾空白或以点结尾"
    if any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name) or name in {".", ".."}:
        return "请输入纯文件名，不能包含路径或 Windows 非法字符"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        return "不能使用 Windows 保留设备名"
    return ""


@dataclass
class TestCase:
    id: str
    input_path: str = ""
    output_path: str = ""
    input_size: int = 0
    output_size: int = 0


@dataclass
class Problem:
    id: str
    input_filename: str = ""
    output_filename: str = ""
    source_file: str = ""
    time_limit_ms: int = 1000
    memory_limit_mb: int = 256
    full_score: int = 100
    compare_mode: str = "ignore_trailing_whitespace"
    score_mode: str = "equal"
    testcase_scores: dict[str, int] = field(default_factory=dict)
    scores_confirmed: bool = True
    cases: list[TestCase] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.input_filename = self.input_filename or f"{self.id}.in"
        self.output_filename = self.output_filename or f"{self.id}.out"
        self.source_file = self.source_file or f"{Path(self.input_filename).stem}.cpp"

    def distribute(self):
        if self.score_mode == "equal":
            n = len(self.cases)
            self.testcase_scores = {c.id: self.full_score // n + (i < self.full_score % n)
                                    for i, c in enumerate(self.cases)} if n else {}

    def validate(self) -> list[str]:
        errors = list(self.errors)
        if not self.cases:
            errors.append("没有测试点")
        for label, name in [("输入文件名", self.input_filename), ("输出文件名", self.output_filename), ("源码优先匹配名", self.source_file)]:
            if error := filename_error(name):
                errors.append(f"{label}：{error}")
        if self.input_filename.casefold() == self.output_filename.casefold():
            errors.append("输入与输出文件名不能相同")
        if self.time_limit_ms < 1 or self.memory_limit_mb < 1 or self.full_score < 0:
            errors.append("时间、内存须为正数，总分须为非负整数")
        if self.compare_mode not in MODES or self.score_mode not in {"equal", "custom"}:
            errors.append("比较或计分模式无效")
        if not self.scores_confirmed:
            errors.append("测试点或满分已变更，请重新确认自定义分值")
        if set(self.testcase_scores) != {c.id for c in self.cases}:
            errors.append("分值映射与当前测试点不一致")
        if any(type(s) is not int or s < 0 for s in self.testcase_scores.values()) or sum(self.testcase_scores.values()) != self.full_score:
            errors.append("单点分值必须是非负整数且总和等于满分")
        return errors


@dataclass
class Project:
    schema_version: int = 1
    project_name: str = "CSP 模拟赛"
    submissions_dir: str = ""
    testdata_dir: str = ""
    report_dir: str = ""
    compiler_path: str = ""
    compile_timeout_sec: int = 45
    output_limit_mb: int = 64
    auto_export: bool = True
    problems: list[Problem] = field(default_factory=list)
    source_overrides: dict[str, str] = field(default_factory=dict)
    data_snapshot: dict = field(default_factory=dict)


@dataclass
class Submission:
    student_id: str
    problem_id: str
    source: str = ""
    status: str = ""
    candidates: list[str] = field(default_factory=list)


@dataclass
class Scan:
    students: list[str]
    problems: list[Problem]
    submissions: dict[tuple[str, str], Submission]
    warnings: list[str]
    snapshot: dict

    @property
    def errors(self):
        errors = [f"{p.id}：{e}" for p in self.problems for e in p.validate()]
        errors += [f"{s.student_id}/{s.problem_id}：源码歧义，请指定源码" for s in self.submissions.values() if s.status == "AMBIGUOUS_SOURCE"]
        if not self.students:
            errors.append("没有可评测的考生")
        if not self.problems:
            errors.append("没有题目")
        return errors


@dataclass
class PointResult:
    student_id: str
    problem_id: str
    testcase_id: str
    status: str
    score: int
    max_score: int
    time_ms: float = 0
    peak_memory_kb: int = 0
    exit_code: int | None = None
    message: str = ""


@dataclass
class BatchResult:
    project_name: str
    students: list[str]
    problems: list[str]
    full_scores: dict[str, int]
    started_at: str
    expected_points: int
    points: list[PointResult] = field(default_factory=list)
    finished_at: str = ""
    cancelled: bool = False
    failure: str = ""
    testcase_ids: dict[str, list[str]] = field(default_factory=dict)
    cleanup_warnings: list[str] = field(default_factory=list)

    def coverage_errors(self):
        """Validate identities, not only list length (duplicates can hide gaps)."""
        keys = [(p.student_id, p.problem_id, p.testcase_id) for p in self.points]
        actual = set(keys)
        errors = []
        if len(keys) != len(actual):
            errors.append(f"重复测试点结果 {len(keys) - len(actual)} 项")
        if len(self.points) != self.expected_points:
            errors.append(f"结果条数 {len(self.points)} / 预期 {self.expected_points}")
        unknown = [key for key in actual if key[0] not in self.students or key[1] not in self.problems]
        if unknown:
            errors.append(f"存在未知考生或题目结果 {len(unknown)} 项")
        if self.testcase_ids:
            expected = {(s, p, t) for s in self.students for p in self.problems for t in self.testcase_ids.get(p, [])}
            if self.expected_points != len(expected):
                errors.append("预期测试点清单与预期总数不一致")
            if expected - actual:
                errors.append(f"缺少测试点结果 {len(expected - actual)} 项")
            if actual - expected:
                errors.append(f"存在非预期测试点结果 {len(actual - expected)} 项")
        return errors

    @property
    def complete(self):
        return bool(self.finished_at) and not self.cancelled and not self.failure and not self.coverage_errors() and all(p.status in STATUS_TEXT and p.status not in INVALID for p in self.points)

    def standings(self):
        grouped = {student: [] for student in self.students}
        for point in self.points:
            if point.student_id in grouped:
                grouped[point.student_id].append(point)
        rows = []
        for student in self.students:
            points = grouped[student]
            scores = {problem: sum(p.score for p in points if p.problem_id == problem) for problem in self.problems}
            identities = {(p.problem_id, p.testcase_id) for p in points}
            expected = {(p, t) for p in self.problems for t in self.testcase_ids.get(p, [])} if self.testcase_ids else None
            completed = (bool(self.finished_at) and not self.failure and len(points) == self.expected_points // max(1, len(self.students))
                         and len(identities) == len(points) and (expected is None or identities == expected)
                         and all(p.status in STATUS_TEXT and p.status not in INVALID for p in points))
            rows.append({**scores, "student_id": student, "total": sum(scores.values()), "completed": completed,
                         "scores": scores,
                         "ac_count": sum(p.status == "AC" for p in points),
                         "error_counts": {s: sum(p.status == s for p in points) for s in STATUS_TEXT if s != "AC"}})
        rows.sort(key=lambda r: (-r["total"], natural_key(r["student_id"])))
        previous = None
        for i, row in enumerate(rows, 1):
            if row["total"] != previous:
                rank = i
            row["rank"] = rank if self.complete else ""
            previous = row["total"]
        return rows

    def to_dict(self):
        return asdict(self)
