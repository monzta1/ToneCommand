#!/usr/bin/env python3
"""Start the frozen app in simulator mode and prove its HTTP surface."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, response.read()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    app = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist" / "ToneCommand.app"
    binary = app / "Contents" / "MacOS" / "ToneCommand"
    if not binary.is_file():
        raise SystemExit(f"missing app executable: {binary}")
    port = free_port()
    env = os.environ.copy()
    env.update({"TONECOMMAND_SIM": "1", "TONECOMMAND_PORT": str(port),
                "TONECOMMAND_NO_BROWSER": "1"})
    process = subprocess.Popen([str(binary)], cwd=root, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        api_status = ui_status = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(f"app exited {process.returncode}: {output[-2000:]}")
            try:
                api_status, api_body = get(f"http://127.0.0.1:{port}/api/state")
                ui_status, ui_body = get(f"http://127.0.0.1:{port}/")
                if api_status == 200 and ui_status == 200 and b"<" in ui_body:
                    print(f"SMOKE_OK app={app} port={port} api_status={api_status} ui_status={ui_status} api_bytes={len(api_body)} ui_bytes={len(ui_body)}")
                    return 0
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.25)
        raise RuntimeError("timed out waiting for /api/state and /")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
