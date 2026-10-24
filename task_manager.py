import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path


TASKS_DIR = Path(__file__).with_name("tasks")
TASKS_DIR.mkdir(exist_ok=True)

ALLOWED_SCRIPTS = {
    "pipeline.py",
    "run_episode.py",
    "concat_episode.py",
    "plan_segments.py",
}


def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _log_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.log"


def _is_alive(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _tail_log(path: Path, n_bytes: int = 3000) -> str:
    if not path.exists():
        return ""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > n_bytes:
            f.seek(size - n_bytes)
        return f.read().decode("utf-8", errors="replace")


def start_task(script: str, args: list) -> dict:
    if script not in ALLOWED_SCRIPTS:
        raise ValueError(f"不允许执行：{script}")

    task_id = f"t{int(time.time())}_{uuid.uuid4().hex[:6]}"
    log_file = _log_path(task_id)

    cmd = [str(Path(".venv") / "Scripts" / "python.exe"), script] + args

    with log_file.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    task = {
        "task_id": task_id,
        "script": script,
        "args": args,
        "cmd": " ".join(cmd),
        "pid": proc.pid,
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "log": str(log_file),
    }
    _task_path(task_id).write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return task


def check_task(task_id: str) -> dict:
    p = _task_path(task_id)
    if not p.exists():
        return {"error": f"任务不存在：{task_id}"}

    task = json.loads(p.read_text(encoding="utf-8"))

    if task["status"] == "running":
        if not _is_alive(task["pid"]):
            log_tail = _tail_log(Path(task["log"]))
            success_markers = ["审片页面", "已生成", "完成", "所有段跑完"]
            success = any(m in log_tail for m in success_markers)

            task["status"] = "done" if success else "failed"
            task["end_time"] = datetime.now().isoformat(timespec="seconds")
            task["log_tail"] = log_tail[-2000:]
            _task_path(task_id).write_text(
                json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    return task


def list_tasks(limit: int = 10) -> list:
    tasks = []
    for p in sorted(
        TASKS_DIR.glob("t*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        try:
            tasks.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(tasks) >= limit:
            break
    return tasks