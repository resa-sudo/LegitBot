"""Запуск бота отдельным фоновым процессом Windows с журналом."""
import os
from pathlib import Path
import subprocess
import sys
import time


def main() -> None:
    if os.name != "nt":
        raise SystemExit("На этой системе используйте python -m legitbot.")
    root = Path(__file__).resolve().parent
    root_text = str(root)
    if not root_text.startswith("\\\\?\\"):
        root_text = "\\\\?\\" + root_text
    runtime = Path(root_text) / ".runtime"
    runtime.mkdir(exist_ok=True)
    pid_path = runtime / "bot.pid"
    if pid_path.exists():
        # Проверка только на существование процесса; чужие процессы не завершаем.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            pid = int(pid_path.read_text(encoding="ascii"))
        except ValueError:
            raise SystemExit("Invalid .runtime/bot.pid; check running processes first.")
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                status = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)):
                    raise SystemExit("Cannot inspect previous process; refusing duplicate launch.")
                if status.value == 259:
                    raise SystemExit(f"Process {pid} is still running. No second bot started.")
            finally:
                kernel.CloseHandle(handle)
        elif ctypes.get_last_error() != 87:
            raise SystemExit("Cannot inspect previous process; refusing duplicate launch.")

    # Не передаём токен через аргументы или окружение: бот сам читает .env.
    bootstrap = (
        "import sys,runpy;"
        "sys.stdout.reconfigure(encoding='utf-8');"
        "sys.stderr.reconfigure(encoding='utf-8');"
        f"sys.path.insert(0,{root_text!r});"
        "runpy.run_module('legitbot',run_name='__main__')"
    )
    with (runtime / "bot.log").open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-c", bootstrap],
            cwd=root_text, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    pid_path.write_text(str(process.pid), encoding="ascii")
    time.sleep(3)
    if process.poll() is not None:
        raise SystemExit("Bot exited. See .runtime/bot.log.")
    print(f"Bot process started: PID {process.pid}. Log: .runtime/bot.log")


if __name__ == "__main__":
    main()
