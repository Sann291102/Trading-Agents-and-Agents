"""Spawns and waits on the `next dev` child process for a preview.

Binds to 127.0.0.1 only -- this runs LLM-generated code as real local
Node.js; it must never be reachable off the machine. Readiness is detected
by draining the child's stdout on a background thread and matching Next's
own "Ready in ..." line (confirmed verbatim against the pinned template
version during setup -- see the plan doc), rather than guessing a fixed
sleep duration.
"""

from __future__ import annotations

import logging
import queue
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger("aio.preview.runner")

_READY_RE = re.compile(r"ready in", re.IGNORECASE)
_DEFAULT_TIMEOUT_SECONDS = 25.0


def allocate_port() -> int:
    """OS-assigned free port on localhost -- bind to port 0, read it back,
    release it immediately. There's a narrow race between releasing the
    socket here and the child process binding it, acceptable given this
    process already serializes preview starts (see manager.py)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def spawn_dev_server(project_dir: Path, port: int) -> subprocess.Popen:
    next_bin = project_dir / "node_modules" / ".bin" / "next"
    return subprocess.Popen(
        [str(next_bin), "dev", "-p", str(port), "-H", "127.0.0.1"],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_for_ready(
    proc: subprocess.Popen, timeout: float = _DEFAULT_TIMEOUT_SECONDS
) -> tuple[bool, str]:
    """Blocks until the child's stdout shows a "Ready" line, the process
    exits, or `timeout` elapses. Returns (ready, log_tail) -- log_tail is
    every line seen so far, useful for surfacing a real error message
    instead of a bare "timed out"."""
    lines: list[str] = []
    line_queue: queue.Queue[str | None] = queue.Queue()

    def _drain() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line_queue.put(line)
        line_queue.put(None)

    threading.Thread(target=_drain, daemon=True).start()

    start = time.monotonic()
    while True:
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            return False, "".join(lines)
        try:
            line = line_queue.get(timeout=remaining)
        except queue.Empty:
            return False, "".join(lines)

        if line is None:
            # stdout closed -- the process exited before becoming ready.
            return False, "".join(lines)

        lines.append(line)
        if _READY_RE.search(line):
            return True, "".join(lines)
        if proc.poll() is not None:
            return False, "".join(lines)
