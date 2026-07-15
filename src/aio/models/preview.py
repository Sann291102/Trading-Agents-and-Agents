"""Schemas for the live-preview stage.

After the swarm's specialists produce free-text output, the Code Integrator
agent synthesizes it into a small set of files (see
aio/agents/code_integrator.py), which get written to disk and run as a real
local Next.js dev server (see aio/preview/). These models are the contract
between those two steps; `PreviewInfo` is what the API/frontend see.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GeneratedFile(BaseModel):
    path: str
    content: str


class GeneratedApp(BaseModel):
    files: list[GeneratedFile]
    summary: str = ""


class PreviewInfo(BaseModel):
    status: Literal["ready", "error", "disabled"]
    url: str | None = None
    error: str | None = None
