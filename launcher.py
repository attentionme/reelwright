import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

GRADIO_PORT = 7860
API_PORT = 8765
GRADIO_URL = f"http://127.0.0.1:{GRADIO_PORT}"

IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    ROOT = Path(sys.executable).resolve().parent
    # 打包成无黑框后，print 会因为没有终端而报错，重定向到 logs 目录
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    sys.stdout = open(log_dir / "stdout.log", "w", encoding="utf-8")
    sys.stderr = open(log_dir / "stderr.log", "w", encoding="utf-8")
else:
    ROOT = Path(__file__).resolve().parent


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
        # 确保 Windows 下子进程也不弹黑框
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
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


def _run_uvicorn():
    """在后台线程运行 FastAPI。"""
    import uvicorn
    from api import fastapi_app
    uvicorn.run(fastapi_app, host="127.0.0.1", port=API_PORT, log_level="warning")


def _run_gradio():
    """在后台线程运行 Gradio。"""
    import app
    app.demo.launch(
        theme=app.gr.themes.Soft(),
        server_name="127.0.0.1",
        server_port=GRADIO_PORT,
        share=False,
        prevent_thread_lock=True
    )


def _open_window(url: str) -> None:
    try:
        import webview
    except Exception as exc:
        print(f"pywebview 不可用（{type(exc).__name__}: {exc}），改用默认浏览器。")
        webbrowser.open(url)
        try:
            input("窗口已用浏览器打开。关闭本终端退出...")
        except KeyboardInterrupt:
            pass
        return

    webview.create_window("Reelwright · 影匠", url, width=1280, height=860)
    webview.start()


def main() -> None:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)

    if IS_FROZEN:
        print("检测到 EXE 运行模式...")
        t_api = threading.Thread(target=_run_uvicorn, daemon=True)
        t_api.start()
        t_gradio = threading.Thread(target=_run_gradio, daemon=True)
        t_gradio.start()

        if not _wait_port("127.0.0.1", GRADIO_PORT, timeout=60):
            print("Gradio 60 秒内未就绪，请检查 logs 目录")
            return
        if not _wait_port("127.0.0.1", API_PORT, timeout=30):
            print("API 30 秒内未就绪，窗口仍会打开，但 API 不可用")

        _open_window(GRADIO_URL)
    else:
        python = _pick_python()
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
                print("API 30 秒内未就绪，请看 logs/api.log")

            _open_window(GRADIO_URL)
        finally:
            for proc in procs:
                _terminate(proc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass