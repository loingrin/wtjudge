from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psutil

from .comparator import ComparisonCancelled

logger = logging.getLogger(__name__)


@dataclass
class Execution:
    status: str
    time_ms: float = 0
    peak_memory_kb: int = 0
    exit_code: int | None = None
    message: str = ""


def stream_copy(source, destination, cancel):
    with open(source, "rb") as inp, open(destination, "wb") as out:
        while data := inp.read(1024 * 1024):
            if cancel.is_set():
                raise ComparisonCancelled()
            out.write(data)


def compiler_env(compiler_path):
    env = os.environ.copy()
    env["PATH"] = str(Path(compiler_path).resolve().parent) + os.pathsep + env.get("PATH", "")
    return env


def _kill_portable(process):
    try:
        tree = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        tree = []
    for child in reversed(tree):
        try:
            child.kill()
        except psutil.Error:
            pass
    process.kill()
    process.wait(timeout=5)


def run_process(args, cwd, timeout_ms, memory_mb, output_limit_mb, cancel, env=None, output_path=None, log_dir=None):
    """OK means exit 0 only; the caller decides CE/AC/NO_OUTPUT.

    Output is checked every 5 ms, so a fast writer can overshoot the soft file
    size threshold between checks. This is resource control, not a sandbox.
    """
    start = time.perf_counter()
    process = None
    peak = 0
    status, message, code = "OK", "", None
    limit = output_limit_mb * 1024 * 1024
    logs = Path(log_dir or cwd)
    out_path, err_path = logs / "console.stdout", logs / "console.stderr"
    result = None
    try:
        logs.mkdir(parents=True, exist_ok=True)
        if cancel.is_set():
            return Execution("CANCELLED", message="已取消")
        with open(os.devnull, "rb") as stdin, open(out_path, "wb") as stdout, open(err_path, "wb") as stderr:
            if os.name == "nt":
                from .winjob import WindowsProcess
                process = WindowsProcess(args, cwd, env or os.environ.copy(), stdin, stdout, stderr, memory_mb * 1024 * 1024)
            else:
                process = subprocess.Popen(args, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            while True:
                code = process.poll()
                if os.name == "nt":
                    peak = max(peak, process.memory())
                    exceeded = process.memory_exceeded
                else:
                    try:
                        proc = psutil.Process(process.pid)
                        peak = max(peak, sum(p.memory_info().rss for p in [proc, *proc.children(recursive=True)] if p.is_running()))
                    except psutil.Error:
                        pass
                    exceeded = bool(memory_mb and peak > memory_mb * 1024 * 1024)
                elapsed = (time.perf_counter() - start) * 1000
                watched = [out_path, err_path] + ([Path(output_path)] if output_path else [])
                written = sum(p.stat().st_size for p in watched if p.is_file())
                if cancel.is_set():
                    status, message = "CANCELLED", "用户取消评测"
                elif exceeded:
                    status, message = "MLE", "Windows Job Object 报告内存限额事件" if os.name == "nt" else "采样内存已超过限额"
                elif written > limit:
                    status, message = "OUTPUT_LIMIT", f"输出文件及控制台输出合计超过 {output_limit_mb} MB（每 5 ms 检查）"
                elif elapsed > timeout_ms:
                    status, message = "TLE", f"墙钟时间超过 {timeout_ms} ms"
                elif code is not None:
                    if code != 0:
                        status, message = "RE", f"进程退出码 {code} (0x{code & 0xffffffff:08X})；未有内存超限证据时不推测 MLE"
                    break
                if status != "OK":
                    process.kill() if os.name == "nt" else _kill_portable(process)
                    code = process.poll()
                    break
                cancel.wait(0.005)
            # Kill descendants even if the root exited normally.
            if os.name == "nt":
                process.kill()
        for label, path in (("标准错误", err_path), ("标准输出", out_path)):
            with open(path, "rb") as stream:
                preview = stream.read(4096).decode("utf-8", errors="replace")
            if preview:
                message += f"\n{label}（最多 4 KB）：{preview}"
        result = Execution(status, round((time.perf_counter() - start) * 1000, 3), (peak + 1023) // 1024, code, message[:10000])
        return result
    except (OSError, psutil.Error, subprocess.SubprocessError) as error:
        logger.exception("无法运行外部程序")
        if process:
            try:
                process.kill() if os.name == "nt" else _kill_portable(process)
            except (OSError, psutil.Error, subprocess.SubprocessError):
                pass
        result = Execution("SYSTEM_ERROR", (time.perf_counter() - start) * 1000, peak // 1024, code,
                           f"无法启动、监测或读取程序：{error}。请检查路径、权限、磁盘空间及杀毒软件记录。")
        return result
    finally:
        if process and os.name == "nt":
            try:
                process.close()
            except OSError as error:
                logger.exception("进程树退出验证失败")
                if result is not None:
                    result.status = "SYSTEM_ERROR"
                    result.message = f"无法确认进程树已退出：{error}。本次结果无效，需重判。\n{result.message}"[:10000]


@contextmanager
def temporary_directory(prefix, on_cleanup_warning=None):
    """Retry transient Windows image/AV locks without abandoning the batch.

    The directory is allocated by mkdtemp and only that exact unique path is
    removed. Failed cleanup is reported with its path, never silently hidden.
    """
    directory = tempfile.mkdtemp(prefix=f"wtjudge-{prefix}-")
    try:
        yield directory
    finally:
        last_error = None
        for delay in (0, .05, .1, .2, .4, .8, 1.6):
            if delay:
                time.sleep(delay)
            try:
                shutil.rmtree(directory)
                last_error = None
                break
            except FileNotFoundError:
                last_error = None
                break
            except OSError as error:
                last_error = error
        if last_error is not None:
            warning = f"临时目录暂未清理：{directory}（已重试；{last_error}）。可能被安全软件或其他进程占用；不因此停止后续评测。"
            logger.warning(warning)
            if on_cleanup_warning is not None:
                on_cleanup_warning(warning)
