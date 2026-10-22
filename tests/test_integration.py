import os
import shutil
import threading
import time
from pathlib import Path

import psutil
import pytest

from wtjudge.core.compiler import compile_source, validate_compiler
from wtjudge.core.executor import compiler_env, run_process, stream_copy
from wtjudge.core.judge import judge_batch
from wtjudge.core.scanner import scan_project

pytestmark = pytest.mark.integration


def build(tmp_path, compiler, code):
    source = tmp_path / "中文 程序.cpp"
    source.write_text(code, encoding="utf-8")
    result = compile_source(compiler, source, tmp_path)
    assert result.status == "OK", result.message
    return result.executable


def run(exe, folder, compiler, timeout=1000, output_mb=1, cancel=None, memory=256):
    return run_process([exe], folder, timeout, memory, output_mb, cancel or threading.Event(), compiler_env(compiler), folder / "answer.out")


def test_real_demo_all_statuses_and_no_stale_output(demo):
    scan = scan_project(demo)
    demo.problems = scan.problems
    # This matrix checks scoring and verdict propagation. Leave room for first
    # launch/AV latency; the dedicated timeout test still uses 1000 ms.
    for problem in demo.problems:
        problem.time_limit_ms = 3000
    result = judge_batch(demo)
    assert result.complete, result.failure
    rows = {r["student_id"]: r for r in result.standings()}
    assert rows["HBCSP26001"]["total"] == 400, [(p.problem_id, p.testcase_id, p.status, p.time_ms, p.message) for p in result.points if p.student_id == "HBCSP26001" and p.status != "AC"]
    assert rows["HBCSP26002"]["total"] == 0
    assert rows["HBCSP26003"]["total"] == 134
    assert {p.status for p in result.points} >= {"AC", "WA", "TLE", "CE", "NO_OUTPUT", "NO_SOURCE", "RE"}
    apple = [p.status for p in result.points if p.student_id == "HBCSP26003" and p.problem_id == "apple"]
    assert apple == ["AC", "NO_OUTPUT", "NO_OUTPUT"]
    assert len(result.points) == 3 * (3 + 6 + 10 + 25)


def test_real_compiler_check(compiler):
    valid, message = validate_compiler(compiler)
    assert valid, message
    assert "GNU++14" in message


def test_runtime_limits_cleanup_and_exit_codes(tmp_path, compiler):
    exe = build(tmp_path, compiler, '#include <windows.h>\n#include <cstdio>\nint main(){FILE*f=fopen("pid.txt","w");fprintf(f,"%lu",GetCurrentProcessId());fclose(f);for(;;){}}')
    result = run(exe, tmp_path, compiler, timeout=1000)
    assert result.status == "TLE"
    pid = int((tmp_path / "pid.txt").read_text())
    assert not psutil.pid_exists(pid)
    assert result.time_ms < 3000


def test_output_limit_and_re(tmp_path, compiler):
    exe = build(tmp_path, compiler, '#include <cstdio>\nint main(){freopen("answer.out","w",stdout);char b[8192]={};for(;;)fwrite(b,1,sizeof(b),stdout);}')
    assert run(exe, tmp_path, compiler, timeout=5000).status == "OUTPUT_LIMIT"
    (tmp_path / "answer.out").unlink()
    exe = build(tmp_path, compiler, 'int main(){return 23;}')
    result = run(exe, tmp_path, compiler)
    assert result.status == "RE" and result.exit_code == 23


def test_cancel_kills_process_and_incomplete_batch(tmp_path, compiler, demo):
    exe = build(tmp_path, compiler, '#include <windows.h>\nint main(){Sleep(10000);}')
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    result = run(exe, tmp_path, compiler, timeout=5000, cancel=cancel)
    timer.join()
    assert result.status == "CANCELLED" and result.time_ms < 2000
    cancel.clear()
    def event(kind, value):
        if kind == "point":
            cancel.set()
    result = judge_batch(demo, cancel, event)
    assert result.cancelled and not result.complete
    assert any(p.status == "CANCELLED" for p in result.points)
    assert all(r["rank"] == "" for r in result.standings())


def test_system_error_does_not_become_re_or_wa(tmp_path, compiler):
    result = run(str(tmp_path / "missing.exe"), tmp_path, compiler)
    assert result.status == "SYSTEM_ERROR"
    broken = tmp_path / "invalid.exe"
    broken.write_bytes(b"not an executable")
    assert run(str(broken), tmp_path, compiler).status == "SYSTEM_ERROR"


def test_hardware_division_fault_is_re_without_windows_error_dialog(tmp_path, compiler):
    exe = build(tmp_path, compiler, 'int main(){volatile int divisor=0; return 123/divisor;}')
    result = run(exe, tmp_path, compiler, timeout=3000)
    assert result.status == "RE", result
    assert result.exit_code & 0xffffffff == 0xC0000094


def test_cancel_active_compilation(tmp_path, compiler):
    sleeper = build(tmp_path, compiler, '#include <windows.h>\nint main(){Sleep(10000);}')
    source = tmp_path / "unused.cpp"
    source.write_text("int main(){}")
    cancel = threading.Event()
    timer = threading.Timer(.15, cancel.set)
    timer.start()
    started = time.monotonic()
    result = compile_source(sleeper, source, tmp_path, 45, cancel)
    timer.join()
    assert result.status == "CANCELLED"
    assert time.monotonic() - started < 2


def test_memory_evidence_is_conservative(tmp_path, compiler):
    exe = build(tmp_path, compiler, r'''#include <windows.h>
int main(){for(int i=0;i<64;++i){
 void*p=VirtualAlloc(NULL,4*1024*1024,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
 if(!p)return 19; ZeroMemory(p,4*1024*1024);
} return 0;}''')
    result = run(exe, tmp_path, compiler, memory=32)
    assert result.status in {"MLE", "RE"}, result
    if result.status == "MLE":
        assert "限额事件" in result.message
    else:
        assert result.exit_code == 19 and "不推测 MLE" in result.message


def test_chinese_and_space_compiler_path(tmp_path, compiler):
    # Resolve toolchain-relative programs and DLLs through an NTFS junction,
    # without modifying or duplicating the installed compiler.
    if os.name != "nt":
        pytest.skip("Windows path verification")
    import subprocess
    link = tmp_path / "中文 编译器"
    target = str(Path(compiler).resolve().parent.parent)
    # Junction creation is confined to pytest's own temporary directory.
    command = f'New-Item -ItemType Junction -Path \'{str(link).replace(chr(39), chr(39)*2)}\' -Target \'{target.replace(chr(39), chr(39)*2)}\' | Out-Null'
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, capture_output=True)
    try:
        valid, message = validate_compiler(str(link / "bin" / "g++.exe"))
        assert valid, message
    finally:
        os.rmdir(link)


def test_job_kills_descendant_when_parent_exits(tmp_path, compiler):
    exe = build(tmp_path, compiler, r'''#include <windows.h>
#include <cstdio>
int main(int argc,char**argv){
 if(argc>1){Sleep(30000);return 0;}
 STARTUPINFOA si={};si.cb=sizeof(si); PROCESS_INFORMATION pi={};
 char path[MAX_PATH],cmd[2*MAX_PATH];GetModuleFileNameA(NULL,path,MAX_PATH);
 sprintf(cmd,"\"%s\" child",path);
 if(!CreateProcessA(NULL,cmd,NULL,NULL,FALSE,0,NULL,NULL,&si,&pi))return 3;
 FILE*f=fopen("child.pid","w");fprintf(f,"%lu",pi.dwProcessId);fclose(f);
 CloseHandle(pi.hThread);CloseHandle(pi.hProcess);return 0;
}''')
    result = run(exe, tmp_path, compiler)
    assert result.status == "OK", result.message
    child = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not psutil.pid_exists(child):
            break
        time.sleep(0.01)
    assert not psutil.pid_exists(child)
