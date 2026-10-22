"""Documented Win32 APIs. The root starts suspended until job assignment."""
from __future__ import annotations

import ctypes as c
import os
import subprocess
import time
from ctypes import wintypes as w

if os.name == "nt":
    import msvcrt

    kernel = c.WinDLL("kernel32", use_last_error=True)
    SIZE_T = c.c_size_t
    ULONG_PTR = c.c_size_t

    class BasicLimit(c.Structure):
        _fields_ = [("PerProcessUserTimeLimit", c.c_int64), ("PerJobUserTimeLimit", c.c_int64),
                    ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", SIZE_T),
                    ("MaximumWorkingSetSize", SIZE_T), ("ActiveProcessLimit", w.DWORD),
                    ("Affinity", ULONG_PTR), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class IOCounters(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimit(c.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IOCounters),
                    ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
                    ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]

    class PortInfo(c.Structure):
        _fields_ = [("CompletionKey", c.c_void_p), ("CompletionPort", w.HANDLE)]

    class BasicAccounting(c.Structure):
        _fields_ = [("TotalUserTime", c.c_int64), ("TotalKernelTime", c.c_int64),
                    ("ThisPeriodTotalUserTime", c.c_int64), ("ThisPeriodTotalKernelTime", c.c_int64),
                    ("TotalPageFaultCount", w.DWORD), ("TotalProcesses", w.DWORD),
                    ("ActiveProcesses", w.DWORD), ("TotalTerminatedProcesses", w.DWORD)]

    class StartupInfo(c.Structure):
        _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
                    ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD),
                    ("dwXSize", w.DWORD), ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
                    ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                    ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                    ("lpReserved2", c.c_void_p), ("hStdInput", w.HANDLE),
                    ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE)]

    class ProcessInfo(c.Structure):
        _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]

    def signature(name, restype, *args):
        f = getattr(kernel, name)
        f.restype, f.argtypes = restype, args
        return f

    CreateJob = signature("CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
    SetJob = signature("SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
    QueryJob = signature("QueryInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p)
    AssignJob = signature("AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
    TerminateJob = signature("TerminateJobObject", w.BOOL, w.HANDLE, w.UINT)
    Close = signature("CloseHandle", w.BOOL, w.HANDLE)
    Resume = signature("ResumeThread", w.DWORD, w.HANDLE)
    CreateProcess = signature("CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(StartupInfo), c.POINTER(ProcessInfo))
    ExitCode = signature("GetExitCodeProcess", w.BOOL, w.HANDLE, c.POINTER(w.DWORD))
    Wait = signature("WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
    Terminate = signature("TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
    CreatePort = signature("CreateIoCompletionPort", w.HANDLE, w.HANDLE, w.HANDLE, ULONG_PTR, w.DWORD)
    GetPacket = signature("GetQueuedCompletionStatus", w.BOOL, w.HANDLE, c.POINTER(w.DWORD), c.POINTER(ULONG_PTR), c.POINTER(c.c_void_p), w.DWORD)
    GetErrorMode = signature("GetErrorMode", w.UINT)
    SetErrorMode = signature("SetErrorMode", w.UINT, w.UINT)

    def checked(value):
        if not value:
            raise c.WinError(c.get_last_error())
        return value


class WindowsProcess:
    def __init__(self, args, cwd, env, stdin, stdout, stderr, memory_bytes=0):
        # Child processes inherit the process error mode. Never let a hardware
        # exception wait in Windows Error Reporting until our wall timeout and
        # become a false TLE. This changes only this application process and its
        # children; it does not change Windows policy or error reporting globally.
        # Keep existing bits and apply a stable process-wide policy: a temporary
        # thread mode is not the documented process inheritance mechanism.
        SetErrorMode(GetErrorMode() | 0x8003)  # FAILCRITICAL | NOGPFAULT | NOOPENFILE
        self.job = self.port = self.handle = None
        self.memory_exceeded = False
        pi = ProcessInfo()
        handles = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, stdout, stderr)]
        try:
            self.job = checked(CreateJob(None, None))
            limits = ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if memory_bytes:
                limits.BasicLimitInformation.LimitFlags |= 0x100 | 0x200
                limits.ProcessMemoryLimit = limits.JobMemoryLimit = memory_bytes
            checked(SetJob(self.job, 9, c.byref(limits), c.sizeof(limits)))
            self.port = checked(CreatePort(w.HANDLE(-1), None, 0, 1))
            port_info = PortInfo(1, self.port)
            checked(SetJob(self.job, 7, c.byref(port_info), c.sizeof(port_info)))
            si = StartupInfo()
            si.cb, si.dwFlags = c.sizeof(si), 0x100 | 1  # USESTDHANDLES | USESHOWWINDOW
            si.wShowWindow = 0
            si.hStdInput, si.hStdOutput, si.hStdError = handles
            command = c.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in args]))
            environment = c.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in sorted(env.items(), key=lambda p: p[0].upper())) + "\0\0")
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            checked(CreateProcess(str(args[0]), command, None, None, True,
                                  0x4 | 0x400 | 0x08000000, environment, str(cwd), c.byref(si), c.byref(pi)))
            self.handle, self.pid = pi.hProcess, pi.dwProcessId
            checked(AssignJob(self.job, self.handle))
            if Resume(pi.hThread) == 0xFFFFFFFF:
                raise c.WinError(c.get_last_error())
        except Exception:
            if pi.hProcess:
                Terminate(pi.hProcess, 1)
                Wait(pi.hProcess, 5000)
            self.close()
            raise
        finally:
            if pi.hThread:
                Close(pi.hThread)
            for handle in handles:
                os.set_handle_inheritable(handle, False)

    def poll(self):
        state = Wait(self.handle, 0)
        if state == 0x102:
            return None
        if state != 0:
            raise c.WinError(c.get_last_error())
        code = w.DWORD()
        checked(ExitCode(self.handle, c.byref(code)))
        return code.value

    def memory(self):
        message, key, overlap = w.DWORD(), ULONG_PTR(), c.c_void_p()
        while GetPacket(self.port, c.byref(message), c.byref(key), c.byref(overlap), 0):
            if message.value in (9, 10):  # PROCESS_MEMORY_LIMIT / JOB_MEMORY_LIMIT
                self.memory_exceeded = True
        info = ExtendedLimit()
        checked(QueryJob(self.job, 9, c.byref(info), c.sizeof(info), None))
        return max(info.PeakJobMemoryUsed, info.PeakProcessMemoryUsed)

    def kill(self):
        if self.job:
            checked(TerminateJob(self.job, 1))
        if self.handle:
            state = Wait(self.handle, 5000)
            if state == 0x102:
                raise OSError("终止进程后等待退出超过 5 秒；本次结果无效")
            if state != 0:
                raise c.WinError(c.get_last_error())
        if self.job:
            deadline = time.monotonic() + 5
            while True:
                accounting = BasicAccounting()
                checked(QueryJob(self.job, 1, c.byref(accounting), c.sizeof(accounting), None))
                if accounting.ActiveProcesses == 0:
                    break
                if time.monotonic() >= deadline:
                    raise OSError("终止 Job 后子进程仍未完全退出；本次结果无效")
                time.sleep(.01)

    def close(self):
        error = None
        try:
            if self.job and self.handle:
                self.kill()
        except OSError as caught:
            error = caught
        finally:
            # Close the job even when exit verification fails: kill-on-close is
            # the final fallback, never permission to report an ordinary score.
            for name in ("job", "handle", "port"):
                handle = getattr(self, name, None)
                if handle:
                    Close(handle)
                    setattr(self, name, None)
        if error:
            raise error
