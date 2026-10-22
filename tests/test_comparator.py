import threading
import tracemalloc

import pytest

from wtjudge.core.comparator import ComparisonCancelled, compare_files


@pytest.mark.parametrize("actual,expected,mode,ok", [
    (b"1 2 \t\r\n3\t\r\n \t\n", b"1 2\n3\n", "ignore_trailing_whitespace", True),
    (b"1  2", b"1 2", "ignore_trailing_whitespace", False),
    (b"\n1", b"1", "ignore_trailing_whitespace", False),
    (b"1\r\n", b"1\n", "strict", False),
    (b"1\t2\n3", b" 1 2   3\n", "tokens", True),
    (b"12", b"1 2", "tokens", False),
    (b"\n \t\r\n", b"", "ignore_trailing_whitespace", True),
    (b"A", b"a", "ignore_trailing_whitespace", False),
])
def test_comparison(tmp_path, actual, expected, mode, ok):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(actual)
    b.write_bytes(expected)
    assert compare_files(a, b, mode)[0] is ok


def test_50mb_single_line_is_bounded_memory(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for path in (a, b):
        with path.open("wb") as stream:
            for _ in range(51):
                stream.write(b"x" * (1024 * 1024))
            stream.write(b" \t" * 40000 + b"end\r\n\n")
    tracemalloc.start()
    assert compare_files(a, b)[0]
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 4 * 1024 * 1024
    stop = threading.Event()
    stop.set()
    with pytest.raises(ComparisonCancelled):
        compare_files(a, b, cancel=stop)
