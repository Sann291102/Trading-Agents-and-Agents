"""Turns an LLM's text response into a validated Pydantic model.

Research-department agents instruct the model to respond with raw JSON
matching a given schema. Models sometimes wrap that in a markdown code
fence anyway, so this strips one if present before validating.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AgentOutputParseError(RuntimeError):
    """Raised when an agent's LLM response can't be parsed into its
    declared output_schema. Carries the raw text for debugging."""

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(f"{message}\n--- raw model output ---\n{raw_text}")
        self.raw_text = raw_text


def extract_role_from_system_prompt(system: str) -> str:
    """Every agent's system_prompt starts with 'You are the <role>', and
    several *mention* other roles in passing (e.g. the Research
    Coordinator's says "reporting to the Executive AI"; the Domain
    Expert's says "reporting to the Research Coordinator"). Identifying
    which agent a prompt belongs to must key off the prompt's own declared
    role via this prefix, not an `in` substring check against the whole
    string -- otherwise those mentions cause misrouting. Shared by
    DemoAnthropicClient and the test suite's fake LLM clients so there is
    one correct implementation instead of two copies drifting apart.
    """
    text = system.removeprefix("You are the ")
    return text.split(",")[0].split(" of ")[0].split(" on ")[0].strip()


def json_response_instruction(model: type[BaseModel]) -> str:
    """A system-prompt suffix instructing the model to answer as raw JSON
    matching `model`'s schema. Shared by every research-department agent so
    the same wording/strictness is used everywhere."""
    schema = json.dumps(model.model_json_schema())
    return (
        "Respond with ONLY a single JSON object matching this JSON schema -- "
        "no markdown code fences, no commentary before or after the JSON:\n"
        f"{schema}"
    )


def parse_json_response(text: str, model: type[ModelT]) -> ModelT:
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AgentOutputParseError(
            f"{model.__name__}: response was not valid JSON ({exc})", text
        ) from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise AgentOutputParseError(
            f"{model.__name__}: response JSON did not match schema ({exc})", text
        ) from exc


_FILE_MARKER_RE = re.compile(r"^===FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)


def parse_delimited_files(text: str, max_files: int = 5) -> list["GeneratedFile"]:
    """Splits a `===FILE: path===`-delimited response into files.

    Used instead of `parse_json_response` for the Code Integrator: asking a
    model to embed multi-line source (backticks, JSX braces, template
    literals, nested quotes) inside a JSON string value is a well-known
    truncation/escaping failure mode. Plain delimited text sidesteps it
    entirely -- no `json.loads`, so no escaping to get wrong. Silently drops
    entries with an empty path or empty body rather than raising, since a
    partially-good response (e.g. 2 of 3 files) is still useful here.
    """
    from aio.models.preview import GeneratedFile

    markers = list(_FILE_MARKER_RE.finditer(text))
    files: list[GeneratedFile] = []
    for index, marker in enumerate(markers):
        path = marker.group(1).strip()
        if not path:
            continue
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        content = text[start:end]
        # `===END===` can appear anywhere in the last file's slice, not
        # just at the very end -- a real run had the model append trailing
        # commentary (a summary, a bash snippet) after it, which an
        # anchored `\s*$` strip left attached to the file content, corrupting
        # it. Truncate at the marker itself instead of trying to match what
        # follows it.
        end_marker = content.find("===END===")
        if end_marker != -1:
            content = content[:end_marker]
        content = content.strip("\n")
        if content.strip():
            files.append(GeneratedFile(path=path, content=content))
        if len(files) >= max_files:
            break
    return files
