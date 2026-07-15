"""Writes a GeneratedApp's files onto disk, safely.

`GeneratedFile.path` comes from an LLM response -- untrusted input. This is
the one place that trust boundary is enforced: only a fixed set of
subdirectories may be written to, `..`/absolute paths are rejected outright,
and the resolved path must stay inside `dest_dir` even after symlinks are
followed. Anything else is dropped (logged), not raised -- one bad path in
an otherwise-good response shouldn't sink the whole preview.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath

from aio.models.preview import GeneratedApp

logger = logging.getLogger("aio.preview.writer")

# A real run had the model reach for `socket.io-client` for a "live quote
# stream" feature -- a natural instinct, but nothing beyond next/react/
# react-dom is installed in the template, so that import would only ever
# 500 the dev server. Scanning for it here turns "cryptic Turbopack crash"
# into "this one generated file gets dropped, the rest of the app still
# boots" -- the same graceful-degradation shape as the path allowlist below.
_IMPORT_RE = re.compile(r'''from\s+["']([^"']+)["']''')
# "@/" is the standard Next.js path alias to the project root (wired up in
# the template's tsconfig.json paths field) -- a real run used it exactly
# as create-next-app scaffolds normally do, and it was wrongly flagged as
# an uninstalled package before this was added.
_ALLOWED_IMPORT_PREFIXES = ("react", "next", ".", "/", "@/")


def _first_disallowed_import(content: str) -> str | None:
    for match in _IMPORT_RE.finditer(content):
        package = match.group(1)
        if not package.startswith(_ALLOWED_IMPORT_PREFIXES):
            return package
    return None

# Exactly one file is permitted directly under app/ (the page itself) --
# NOT a prefix match, learned the hard way: a real run had the model emit
# an `app/globals.css` nobody asked for, containing garbled markdown-fence
# leftovers instead of CSS, which 500'd the whole preview. components/ and
# lib/ stay prefix-matched since the Code Integrator may emit a handful of
# files there, all equally fine to accept.
_ALLOWED_EXACT_PATHS = frozenset({"app/page.tsx"})
_ALLOWED_PREFIXES = ("components/", "lib/")


def _is_safe_relative_path(path_str: str) -> bool:
    if not path_str or path_str.startswith("/") or ".." in PurePosixPath(path_str).parts:
        return False
    if path_str in _ALLOWED_EXACT_PATHS:
        return True
    return path_str.startswith(_ALLOWED_PREFIXES)


def write_generated_app(app: GeneratedApp, dest_dir: Path) -> list[Path]:
    """Writes every safe file in `app.files` under `dest_dir`. Returns the
    list of paths actually written (may be shorter than `app.files` if any
    were rejected)."""
    dest_dir = dest_dir.resolve()
    written: list[Path] = []
    for file in app.files:
        if not _is_safe_relative_path(file.path):
            logger.warning("dropping generated file with unsafe path: %r", file.path)
            continue

        disallowed = _first_disallowed_import(file.content)
        if disallowed is not None:
            logger.warning(
                "dropping %r: imports %r, which isn't installed in the preview template",
                file.path,
                disallowed,
            )
            continue

        target = (dest_dir / file.path).resolve()
        if not target.is_relative_to(dest_dir):
            logger.warning("dropping generated file that escapes dest_dir: %r", file.path)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
        written.append(target)

    return written
