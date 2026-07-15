"""Tracks the single running preview dev server for the whole process.

Only one preview runs at a time -- starting a new one tears down whatever
was running before, matching the "submit a prompt, wait, see the result"
mental model this feature is built around. `stop_all()` is wired into the
API's shutdown hook so a `next dev` child never outlives the API process.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from aio.config import Settings, settings
from aio.models.preview import GeneratedApp, PreviewInfo
from aio.preview.runner import allocate_port, spawn_dev_server, wait_for_ready
from aio.preview.writer import write_generated_app

logger = logging.getLogger("aio.preview.manager")

_SCAFFOLD_ITEMS = ("package.json", "tsconfig.json", "next.config.ts", "app")


def _repo_root() -> Path:
    # Same anchor as _ENV_FILE in config.py / log_dir in logging_setup.py --
    # the .env file's directory, not the process cwd.
    return Path(Settings.model_config["env_file"]).parent


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else _repo_root() / path


@dataclass
class _RunningPreview:
    project_id: str
    popen: subprocess.Popen
    port: int
    project_dir: Path


class PreviewManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: _RunningPreview | None = None

    def start(self, project_id: str, app: GeneratedApp) -> PreviewInfo:
        with self._lock:
            self._stop_locked()

            if not app.files:
                return PreviewInfo(status="error", error="No preview files were generated.")

            template_dir = _resolve(settings.preview_template_dir)
            project_dir = _resolve(settings.preview_workspace_dir) / project_id

            try:
                self._scaffold(template_dir, project_dir)
                written = write_generated_app(app, project_dir)
                if not written:
                    return PreviewInfo(
                        status="error", error="Every generated file had an unsafe path."
                    )

                port = allocate_port()
                popen = spawn_dev_server(project_dir, port)
                ready, log_tail = wait_for_ready(popen)
                if not ready:
                    popen.kill()
                    tail = log_tail[-800:] if log_tail else "no output before timeout"
                    return PreviewInfo(
                        status="error", error=f"Preview server did not become ready: {tail}"
                    )

                self._current = _RunningPreview(project_id, popen, port, project_dir)
                return PreviewInfo(status="ready", url=f"http://127.0.0.1:{port}")
            except Exception as exc:
                logger.exception("preview start failed for project %s", project_id)
                return PreviewInfo(status="error", error=str(exc))

    def stop_all(self) -> None:
        with self._lock:
            self._stop_locked()

    def _scaffold(self, template_dir: Path, project_dir: Path) -> None:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True)
        for item in _SCAFFOLD_ITEMS:
            src = template_dir / item
            dst = project_dir / item
            if src.is_dir():
                shutil.copytree(src, dst)
            elif src.exists():
                shutil.copy2(src, dst)
        self._copy_node_modules(
            template_dir / "node_modules", project_dir / "node_modules"
        )

    def _copy_node_modules(self, src: Path, dst: Path) -> None:
        # A symlink here (the original plan) is much faster but Turbopack
        # -- Next's default dev bundler as of Next 16 -- hard-rejects a
        # node_modules symlink that resolves outside the project directory
        # ("Symlink [project]/node_modules is invalid, it points out of
        # the filesystem root"), so a real copy is required. `cp -c` uses
        # APFS clonefile() (copy-on-write, ~4-5s for this template's ~340MB
        # node_modules) where available; shutil.copytree is the portable
        # fallback elsewhere (including Windows, which has no `cp` at all --
        # there subprocess.run raises FileNotFoundError rather than returning
        # a non-zero code, so that case must be caught explicitly).
        try:
            result = subprocess.run(
                ["cp", "-Rc", str(src), str(dst)], capture_output=True, text=True
            )
            if result.returncode == 0:
                return
        except (FileNotFoundError, OSError):
            pass
        shutil.copytree(src, dst, dirs_exist_ok=True)

    def _stop_locked(self) -> None:
        if self._current is None:
            return
        popen = self._current.popen
        try:
            popen.terminate()
            popen.wait(timeout=5)
        except Exception:
            try:
                popen.kill()
            except Exception:
                pass
        self._current = None


preview_manager = PreviewManager()
