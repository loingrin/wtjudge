from __future__ import annotations

import copy
import logging
import threading
from datetime import datetime
from pathlib import Path

from .comparator import ComparisonCancelled, compare_files
from .compiler import compile_source, validate_compiler
from .executor import compiler_env, run_process, stream_copy, temporary_directory
from .models import BatchResult, PointResult
from .scanner import scan_project

logger = logging.getLogger(__name__)


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def judge_batch(project, cancel=None, emit=None):
    cancel = cancel or threading.Event()
    emit = emit or (lambda *args: None)
    scan = scan_project(project)
    if scan.errors:
        raise ValueError("预检未通过：\n" + "\n".join(scan.errors[:100]))
    if project.compile_timeout_sec < 1 or project.output_limit_mb < 1:
        raise ValueError("编译超时与输出上限必须为正数")
    emit("phase", "正在验证 G++ 版本和 C++14 编译运行能力…")
    valid, message = validate_compiler(project.compiler_path, project.compile_timeout_sec, cancel)
    if not valid and not cancel.is_set():
        raise ValueError(message)
    batch = BatchResult(project.project_name, scan.students, [p.id for p in scan.problems],
                        {p.id: p.full_score for p in scan.problems}, timestamp(),
                        len(scan.students) * sum(len(p.cases) for p in scan.problems),
                        testcase_ids={p.id: [c.id for c in p.cases] for p in scan.problems})
    emit("batch", copy.deepcopy(batch))

    def record(point):
        batch.points.append(point)
        emit("point", point)

    def cleanup_warning(message):
        batch.cleanup_warnings.append(message)
        emit("cleanup_warning", message)

    def process_submission(student, problem):
        submission = scan.submissions[student, problem.id]
        emit("phase", f"{student} — {problem.id}：编译中（每题仅编译一次）")
        with temporary_directory("compile", cleanup_warning) as cache:
            built = compile_source(project.compiler_path, submission.source, cache, project.compile_timeout_sec, cancel) if submission.source else None
            for case in problem.cases:
                if cancel.is_set():
                    break
                emit("phase", f"{student} — {problem.id} — {case.id}：执行中")
                max_score = problem.testcase_scores[case.id]
                point = PointResult(student, problem.id, case.id, "SYSTEM_ERROR", 0, max_score)
                if not built:
                    point.status, point.message = "NO_SOURCE", "未找到题目文件夹或 .cpp 源码"
                elif built.status != "OK":
                    point.status, point.message = built.status, built.message
                else:
                    try:
                        with temporary_directory("run", cleanup_warning) as folder, temporary_directory("run-log", cleanup_warning) as logs:
                            stream_copy(case.input_path, Path(folder) / problem.input_filename, cancel)
                            output = Path(folder) / problem.output_filename
                            run = run_process([built.executable], folder, problem.time_limit_ms, problem.memory_limit_mb,
                                              project.output_limit_mb, cancel, compiler_env(project.compiler_path), output, logs)
                            point.time_ms, point.peak_memory_kb, point.exit_code, point.message = run.time_ms, run.peak_memory_kb, run.exit_code, run.message
                            if run.status != "OK":
                                point.status = run.status
                            elif not output.is_file():
                                point.status = "NO_OUTPUT"
                                point.message = f"未生成 {problem.output_filename}；请检查 freopen 文件名。\n{run.message}"
                            else:
                                same, diagnostic = compare_files(output, case.output_path, problem.compare_mode, cancel)
                                point.status = "AC" if same else "WA"
                                point.message = diagnostic + ("\n" + run.message if run.message else "")
                                point.score = max_score if same else 0
                    except ComparisonCancelled:
                        point.status, point.message = "CANCELLED", "用户取消；未完成比较或输入复制"
                    except Exception as error:
                        logger.exception("测试点执行失败，继续后续测试点")
                        point.status, point.message = "SYSTEM_ERROR", f"本测试点执行或文件操作失败：{error}。后续测试点继续；本点需排查后重判。"
                record(point)

    try:
        for student in scan.students:
            if cancel.is_set():
                break
            for problem in scan.problems:
                if cancel.is_set():
                    break
                try:
                    process_submission(student, problem)
                except Exception as error:
                    logger.exception("当前提交异常，继续后续考生和题目")
                    emit("phase", f"{student} — {problem.id}：当前提交异常，已记录无效项，继续后续评测。")
                    done = {(p.student_id, p.problem_id, p.testcase_id) for p in batch.points}
                    for case in problem.cases:
                        if (student, problem.id, case.id) not in done:
                            record(PointResult(student, problem.id, case.id, "CANCELLED" if cancel.is_set() else "SYSTEM_ERROR", 0,
                                               problem.testcase_scores[case.id], message=f"当前提交无法完成：{error}。本项需重判，其他考生继续评测。"))
    except Exception as error:
        logger.exception("批次意外失败")
        batch.failure = f"评测中断：{error}；请排查后重新评测。"
    finally:
        batch.cancelled = cancel.is_set()
        done = {(p.student_id, p.problem_id, p.testcase_id) for p in batch.points}
        for student in scan.students:
            for problem in scan.problems:
                for case in problem.cases:
                    if (student, problem.id, case.id) not in done:
                        status = "CANCELLED" if batch.cancelled else "SYSTEM_ERROR"
                        record(PointResult(student, problem.id, case.id, status, 0, problem.testcase_scores[case.id],
                                           message="未评测；不可视作正式 0 分"))
        batch.finished_at = timestamp()
    return batch
