#!/usr/bin/env python3
"""Minimal HTTP server for free cloud hosts (Render/Fly/Railway) + external cron pings."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "10000"))
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()
_running = threading.Lock()


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
        print(f"[http] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path.startswith("/run"):
            self._run_tracker()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.startswith("/run"):
            self._run_tracker()
            return
        self.send_response(404)
        self.end_headers()

    def _run_tracker(self) -> None:
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
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tracker.py"), "--once"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=900,
                env=os.environ.copy(),
            )
            body = (proc.stdout or "") + (proc.stderr or "")
            code = 200 if proc.returncode == 0 else 500
            self.send_response(code)
            self.end_headers()
            self.wfile.write(body.encode("utf-8", errors="replace")[-8000:])
        finally:
            _running.release()


def main() -> None:
    print(f"Listening on 0.0.0.0:{PORT} — GET/POST /run?secret=... or Bearer token")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
