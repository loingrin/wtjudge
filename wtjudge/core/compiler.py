from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from .executor import compiler_env, run_process, temporary_directory


@dataclass
class Compilation:
    status: str
    executable: str = ""
    message: str = ""


def compile_source(compiler, source, cache, timeout_sec=45, cancel=None):
    cancel = cancel or threading.Event()
    executable = str(Path(cache).resolve() / "program.exe")
    args = [str(Path(compiler).resolve()), "-std=gnu++14", "-O2", "-pipe", "-o", executable, str(Path(source).resolve())]
    result = run_process(args, cache, timeout_sec * 1000, 0, 8, cancel, compiler_env(compiler))
    if result.status == "OK" and Path(executable).is_file():
        return Compilation("OK", executable, result.message)
    if result.status in {"SYSTEM_ERROR", "CANCELLED"}:
        return Compilation(result.status, message=result.message)
    reason = "编译超时" if result.status == "TLE" else "编译失败或诊断输出超过上限"
    return Compilation("CE", message=f"{reason}\n{result.message}"[:10000])


def validate_compiler(compiler, timeout_sec=45, cancel=None):
    cancel = cancel or threading.Event()
    if not compiler or not Path(compiler).is_file():
        return False, "请选择本机 MinGW-w64 的 g++.exe。编译器路径不存在。"
    with temporary_directory("compiler-check") as folder:
        version = run_process([str(Path(compiler).resolve()), "--version"], folder, 10000, 0, 1, cancel, compiler_env(compiler))
        if version.status != "OK" or not any(s in version.message.lower() for s in ("g++", "gcc", "free software foundation")):
            return False, f"无法验证 GNU G++：{version.message}"
        source = Path(folder) / "cxx14.cpp"
        source.write_text('#include <cstdio>\nint main(){auto f=[](auto x){return x+1;}; puts("CXX14_OK"); return f(1)==2?0:1;}\n', encoding="utf-8")
        built = compile_source(compiler, source, folder, timeout_sec, cancel)
        if built.status != "OK":
            return False, f"C++14 试编失败：{built.message}"
        run = run_process([built.executable], folder, 3000, 256, 1, cancel, compiler_env(compiler))
        if run.status != "OK" or "CXX14_OK" not in run.message:
            return False, f"试编成功，但试运行失败：{run.message}"
        return True, f"{version.message.strip()}\nGNU++14 编译和运行测试通过。"
