#!/usr/bin/env python3
"""Self-scheduling tracker + health endpoint for Render/Fly free tier."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "10000"))
INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()
_running = threading.Lock()
_last_run: str = "never"
_last_status: str = "pending"


def _run_tracker_once() -> tuple[int, str]:
    """Run tracker.py --once, return (exit_code, output)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tracker.py"), "--once"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,
        env=os.environ.copy(),
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


def _scheduler_loop() -> None:
    """Background thread: run tracker every INTERVAL minutes."""
    global _last_run, _last_status
    time.sleep(5)
    while True:
        if _running.acquire(blocking=False):
            try:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                print(f"[scheduler] Starting check at {now}")
                code, output = _run_tracker_once()
                _last_run = now
                _last_status = "ok" if code == 0 else f"error (exit {code})"
                print(f"[scheduler] Done: {_last_status}")
                if output:
                    for line in output.strip().split("\n")[-10:]:
                        print(f"  {line}")
            finally:
                _running.release()
        else:
            print("[scheduler] Skipped — already running")
        time.sleep(INTERVAL * 60)


def _authorized(path: str, headers: dict) -> bool:
    if not CRON_SECRET:
        return True
    qs = parse_qs(urlparse(path).query)
    token = (qs.get("secret") or [""])[0]
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip() or token
    return token == CRON_SECRET


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            body = f"ok | last_run={_last_run} | status={_last_status}"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())
            return
        if self.path.startswith("/run"):
            self._manual_run()
            return
        if self.path.startswith("/status"):
            self._status()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.startswith("/run"):
            self._manual_run()
            return
        self.send_response(404)
        self.end_headers()

    def _status(self) -> None:
        body = f"last_run: {_last_run}\nstatus: {_last_status}\ninterval: {INTERVAL}min\n"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())

    def _manual_run(self) -> None:
        global _last_run, _last_status
        if not _authorized(self.path, dict(self.headers)):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return
        if not _running.acquire(blocking=False):
            self.send_response(409)
            self.end_headers()
            self.wfile.write(b"already running")
            return
        try:
            code, output = _run_tracker_once()
            _last_run = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            _last_status = "ok" if code == 0 else f"error (exit {code})"
            self.send_response(200 if code == 0 else 500)
            self.end_headers()
            self.wfile.write(output.encode("utf-8", errors="replace")[-8000:])
        finally:
            _running.release()


def main() -> None:
    print(f"Flight tracker — auto-check every {INTERVAL} min")
    print(f"Listening on 0.0.0.0:{PORT} — /health, /status, /run")

    scheduler = threading.Thread(target=_scheduler_loop, daemon=True)
    scheduler.start()

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
