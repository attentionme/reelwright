"""
阶段 1 启动器：拉起 Gradio + FastAPI 两个子进程，再用 pywebview 开窗口。

- 端口已被占用时，跳过启动对应子进程（复用你手动开的 app.py）。
- pywebview 不可用时，退回默认浏览器打开 Gradio，终端等回车后收尾。
- 日志写到 logs/gradio.log、logs/api.log。
"""

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRADIO_PORT = 7860
API_PORT = 8765
GRADIO_URL = f"http://127.0.0.1:{GRADIO_PORT}"
API_URL = f"http://127.0.0.1:{API_PORT}/api/status"


def _pick_python() -> str:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.3)
    return False


def _spawn(args: list, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        args,
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    # 把文件句柄挂在 proc 上，避免被 GC 提前关闭
    proc._log_file = log_file
    return proc


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    log_file = getattr(proc, "_log_file", None)
    if log_file:
        try:
            log_file.close()
        except Exception:
            pass


def _open_window(url: str) -> None:
    try:
        import webview
    except Exception as exc:
        print(f"pywebview 不可用（{type(exc).__name__}: {exc}），改用默认浏览器。")
        print(f"Gradio: {GRADIO_URL}")
        print(f"API:    {API_URL}")
        webbrowser.open(url)
        try:
            input("窗口已用浏览器打开。关闭本终端或按回车退出（子进程会被收尾）...")
        except KeyboardInterrupt:
            pass
        return

    webview.create_window("Reelwright · 影匠", url, width=1280, height=860)
    webview.start()


def main() -> None:
    python = _pick_python()
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)

    procs = []

    if _port_open("127.0.0.1", GRADIO_PORT):
        print(f"端口 {GRADIO_PORT} 已被占用，复用现有 Gradio。")
    else:
        print(f"启动 Gradio（日志：logs/gradio.log）...")
        procs.append(_spawn([python, str(ROOT / "app.py")], logs / "gradio.log"))

    if _port_open("127.0.0.1", API_PORT):
        print(f"端口 {API_PORT} 已被占用，复用现有 API。")
    else:
        print(f"启动 FastAPI（日志：logs/api.log）...")
        procs.append(_spawn(
            [python, "-m", "uvicorn", "api:fastapi_app",
             "--host", "127.0.0.1", "--port", str(API_PORT)],
            logs / "api.log",
        ))

    try:
        if not _wait_port("127.0.0.1", GRADIO_PORT, timeout=90):
            print("Gradio 90 秒内未就绪，请看 logs/gradio.log")
            return
        if not _wait_port("127.0.0.1", API_PORT, timeout=30):
            print("API 30 秒内未就绪，请看 logs/api.log（窗口仍会打开，但 API 不可用）")

        _open_window(GRADIO_URL)
    finally:
        for proc in procs:
            _terminate(proc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass