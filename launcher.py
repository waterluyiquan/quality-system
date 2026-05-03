from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen


APP_URL = "http://127.0.0.1:8501"


def project_dir() -> Path:
    fallback = Path(r"C:\Users\water\Documents\New project 3")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [exe_dir, exe_dir.parent, fallback]
    else:
        script_dir = Path(__file__).resolve().parent
        candidates = [script_dir, fallback]
    for candidate in candidates:
        if (candidate / "app.py").exists():
            return candidate
    return fallback


def python_executable(root: Path) -> Path:
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def wait_until_ready(timeout: int = 45) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(APP_URL, timeout=2) as response:
                return response.status == 200
        except Exception:
            time.sleep(1)
    return False


def main() -> None:
    root = project_dir()
    python = python_executable(root)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    args = [
        str(python),
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        "8501",
        "--browser.gatherUsageStats",
        "false",
    ]
    subprocess.Popen(args, cwd=root, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    if wait_until_ready():
        webbrowser.open(APP_URL)
    else:
        webbrowser.open(APP_URL)


if __name__ == "__main__":
    main()
