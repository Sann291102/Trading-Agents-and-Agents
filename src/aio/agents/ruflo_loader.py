"""Loads the 30 imported ruflo agent definitions as `Agent` subclasses.

Each definition under `ruflo_defs/` is a markdown file with YAML
frontmatter, copied verbatim from the ruflo repo; `manifest.json` maps each
file to the role name and department it is registered under here. The
classes are generated with `type()` at import time, so the existing
subclass-walking registry (`all_agent_classes`) and `GET /agents` pick them
up with no per-agent wiring -- exactly the property registry.py promises
for hand-written agents.

The markdown bodies were written for ruflo's own runtime and reference
tooling that doesn't exist here (mcp__claude-flow__* calls, hooks, memory
namespaces). They are still valuable as specialist charters -- persona,
responsibilities, quality bars -- so the body is included in the system
prompt after a preamble telling the model to treat tool-specific
instructions as descriptions of intent, capped at `_BODY_CHAR_LIMIT` to
keep prompts bounded (some definitions run to hundreds of lines of
javascript examples that add cost but no persona).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from aio.agents.base import Agent

_DEFS_DIR = Path(__file__).resolve().parent / "ruflo_defs"
_BODY_CHAR_LIMIT = 6000

_PROMPT_TEMPLATE = (
    "You are the {role} on the organization's {department} team, a "
    "specialist member of the engineering swarm. You receive one focused "
    "task from the Queen Coordinator, produce your best specialist output "
    "as plain, well-structured text, and hand it back for validation.\n"
    "\n"
    "Your specialist charter (imported from the ruflo agent library) "
    "follows. It may reference tools, hooks, or memory systems from its "
    "original runtime that are not available here -- treat those passages "
    "as descriptions of intent and working style, not as literal "
    "instructions to call tools.\n"
    "\n"
    "{description}\n"
    "\n"
    "{body}"
)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Returns (frontmatter dict, body). Tolerates files without
    frontmatter by treating the whole file as body."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 2)
    if len(parts) < 2:
        return {}, text
    raw = parts[0].removeprefix("---")
    body = parts[1]
    if len(parts) == 3:
        body += parts[2]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), body


def _trim_body(body: str) -> str:
    body = body.strip()
    if len(body) <= _BODY_CHAR_LIMIT:
        return body
    cut = body.rfind("\n", 0, _BODY_CHAR_LIMIT)
    if cut == -1:
        cut = _BODY_CHAR_LIMIT
    return body[:cut].rstrip() + "\n\n[charter truncated]"


def _make_agent_class(role: str, department: str, system_prompt: str) -> type[Agent]:
    class_name = "".join(part for part in role.title().split() if part.isalnum()) + "RufloAgent"

    def execute(self: Agent, task: str) -> str:
        text, _ = self.run_logged(task, handoff_target="Production Validator")
        return text

    return type(
        class_name,
        (Agent,),
        {
            "role": role,
            "department": department,
            "system_prompt": system_prompt,
            "execute": execute,
            "__doc__": f"ruflo-imported specialist ({department}). See ruflo_defs/.",
        },
    )


def load_ruflo_agent_classes() -> dict[str, type[Agent]]:
    manifest = json.loads((_DEFS_DIR / "manifest.json").read_text(encoding="utf-8"))
    classes: dict[str, type[Agent]] = {}
    for entry in manifest["agents"]:
        # These agent-def markdown files are UTF-8; read them explicitly so
        # loading works on Windows too, where read_text() would otherwise
        # default to cp1252 and choke on non-Latin-1 bytes.
        text = (_DEFS_DIR / entry["file"]).read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        description = str(meta.get("description", "")).strip()
        system_prompt = _PROMPT_TEMPLATE.format(
            role=entry["role"],
            department=entry["department"],
            description=description,
            body=_trim_body(body),
        )
        classes[entry["role"]] = _make_agent_class(
            entry["role"], entry["department"], system_prompt
        )
    return classes


# Built once at import time -- importing this module (agents/__init__.py
# does, before registry) is what makes the 30 swarm agents exist.
RUFLO_AGENT_CLASSES: dict[str, type[Agent]] = load_ruflo_agent_classes()


def ruflo_role_names() -> set[str]:
    return set(RUFLO_AGENT_CLASSES)
