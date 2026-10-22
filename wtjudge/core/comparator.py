"""Bounded-memory comparison, including a single line/token larger than RAM."""
from __future__ import annotations

import re
import threading
from pathlib import Path

CHUNK = 64 * 1024


class ComparisonCancelled(Exception):
    pass


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise ComparisonCancelled()


def canonical(path: str | Path, mode: str, cancel=None):
    if mode == "strict":
        with open(path, "rb") as stream:
            while data := stream.read(CHUNK):
                _check(cancel)
                yield data
        return
    if mode not in {"tokens", "ignore_trailing_whitespace"}:
        raise ValueError(f"未知比较模式：{mode}")
    # A second file handle replays pending whitespace by offset. No unbounded
    # line, token or whitespace suffix is ever retained in memory.
    with open(path, "rb") as stream, open(path, "rb") as replay:
        offset = 0
        pending_start = pending_size = pending_newlines = 0
        previous_cr = False
        token_started = False
        token_gap = False
        pattern = rb"\s+|\S+" if mode == "tokens" else rb"\r\n|[\r\n]|[ \t]+|[^ \t\r\n]+"
        while data := stream.read(CHUNK):
            _check(cancel)
            for match in re.finditer(pattern, data):
                part = match.group()
                if mode == "tokens":
                    if part[:1].isspace():
                        token_gap = token_started
                    else:
                        if token_gap:
                            yield b" "
                        yield part
                        token_gap = False
                        token_started = True
                    continue
                if previous_cr and part == b"\n":
                    previous_cr = False
                    continue
                previous_cr = part == b"\r"
                if part[:1] in (b"\r", b"\n"):
                    pending_size = 0
                    pending_newlines += 1
                elif part[:1] in (b" ", b"\t"):
                    if not pending_size:
                        pending_start = offset + match.start()
                    pending_size += len(part)
                else:
                    while pending_newlines:
                        size = min(pending_newlines, CHUNK)
                        yield b"\n" * size
                        pending_newlines -= size
                    if pending_size:
                        replay.seek(pending_start)
                        while pending_size:
                            _check(cancel)
                            text = replay.read(min(CHUNK, pending_size))
                            if not text:
                                raise OSError("答案文件在比较过程中被修改或截断")
                            yield text
                            pending_size -= len(text)
                    yield part
            offset += len(data)
        # Pending line whitespace and final empty lines are intentionally dropped.


def compare_files(actual: str | Path, expected: str | Path, mode="ignore_trailing_whitespace", cancel: threading.Event | None = None) -> tuple[bool, str]:
    a, b = iter(canonical(actual, mode, cancel)), iter(canonical(expected, mode, cancel))
    left = right = b""
    position = 0
    try:
        while True:
            _check(cancel)
            if not left:
                left = next(a, b"")
            if not right:
                right = next(b, b"")
            if not left or not right:
                if left == right:
                    return True, "答案一致"
                return False, f"规范化字节位置 {position + 1}：输出长度不同；实际 {left[:120]!r}，标准 {right[:120]!r}"
            n = min(len(left), len(right))
            if left[:n] != right[:n]:
                index = next(i for i, (x, y) in enumerate(zip(left[:n], right[:n])) if x != y)
                return False, f"规范化字节位置 {position + index + 1}：实际 {left[index:index + 120]!r}，标准 {right[index:index + 120]!r}"
            position += n
            left, right = left[n:], right[n:]
    finally:
        # Tracebacks can retain generator locals on cancellation or I/O error.
        # Close both readers before the run directory is removed on Windows.
        a.close()
        b.close()
