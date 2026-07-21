"""Mission resume: a run that fails mid-graph must be resumable from its
last completed node -- not restarted -- after the operator "fixes" the LLM
(in production: edits .env and hits POST /projects/{id}/resume).

Uses a wrapper LLM that fails on one specific call, then succeeds after
being marked fixed. Call counts prove completed nodes are NOT re-executed
on resume: the swarm-less pipeline makes 11 LLM calls total, we fail call
#9 (Product Manager), so a correct resume makes exactly 3 more calls
(product retry, backend, ceo review) -- a restart-from-scratch would make
11 and double-bill the research stage.
"""

from __future__ import annotations

import uuid

import pytest

from aio.llm.demo_client import DemoAnthropicClient
from aio.orchestration.graph import (
    resumable_goal,
    resume_organization,
    run_legacy_organization,
)


class FlakyLLM:
    """Delegates to the demo client, but call number `fail_at` raises until
    `fixed` is set -- simulating an exhausted API key that the operator then
    replaces."""

    def __init__(self, fail_at: int) -> None:
        self._inner = DemoAnthropicClient()
        self.fail_at = fail_at
        self.calls = 0
        self.fixed = False

    def complete(self, system: str, user: str, max_tokens: int = 20000) -> str:
        self.calls += 1
        if self.calls == self.fail_at and not self.fixed:
            raise RuntimeError("simulated provider failure: API key exhausted")
        return self._inner.complete(system, user, max_tokens=max_tokens)


def test_failed_mission_resumes_from_checkpoint_without_rerunning_completed_nodes():
    llm = FlakyLLM(fail_at=9)
    project_id = str(uuid.uuid4())
    goal = "Build an internal tool for tracking customer feedback"

    with pytest.raises(RuntimeError, match="simulated provider failure"):
        run_legacy_organization(goal, llm=llm, persist=False, swarm=False, project_id=project_id)

    calls_at_failure = llm.calls
    assert calls_at_failure == 9  # 8 completed nodes + the failed product call
    assert resumable_goal(project_id) == goal

    llm.fixed = True  # the operator replaced the key / switched provider
    result = resume_organization(project_id, llm=llm, persist=False, swarm=False)

    # Product retried + backend + ceo review = 3 calls. Research (calls 1-8)
    # must NOT have re-run.
    assert llm.calls == calls_at_failure + 3
    assert result["project_id"] == project_id
    assert result["research_report"] is not None
    assert result["tech_plan"]
    assert result["review"]
    # Completed missions are no longer resumable.
    assert resumable_goal(project_id) is None


def test_resume_unknown_mission_raises_key_error():
    with pytest.raises(KeyError):
        resume_organization(str(uuid.uuid4()), persist=False, swarm=False)
