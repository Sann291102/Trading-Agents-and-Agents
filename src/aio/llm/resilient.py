"""Wraps whichever LLM client `build_default_llm` would otherwise return so
a mission survives the user changing providers/keys mid-run.

`run_organization` builds one LLM client up front and hands it to every
agent for that mission (see orchestration/graph.py). Without this wrapper,
an operator editing `.env` (new key, `LLM_PROVIDER=nvidia` instead of
`anthropic`, ...) while a mission is in flight has no effect until the next
mission, and a call already in flight against a now-invalid key just fails.
`ResilientLLMClient` instead: on any `complete()` failure, reloads
`settings` from disk/env and rebuilds the underlying client, then retries
once. If the retry also fails (e.g. the new config is broken too), the
original error is the one that propagates -- callers see a real failure,
not a silently swallowed one.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("aio.llm.resilient")


class ResilientLLMClient:
    def __init__(self, build_client) -> None:
        # `build_client` is a zero-arg factory (not the client itself) so a
        # retry can construct a *new* client against reloaded settings
        # rather than reusing one pinned to the stale API key.
        self._build_client = build_client
        self._client = build_client()

    @property
    def model(self) -> str:
        return self._client.model

    def complete(self, system: str, user: str, max_tokens: int = 20000) -> str:
        try:
            return self._client.complete(system, user, max_tokens=max_tokens)
        except Exception as first_error:
            from aio.config import settings

            logger.warning(
                "LLM call failed (%s) -- reloading config and retrying once "
                "in case the provider/key changed mid-mission",
                first_error,
            )
            settings.reload()
            self._client = self._build_client()
            try:
                return self._client.complete(system, user, max_tokens=max_tokens)
            except Exception:
                # The reload didn't fix it -- surface the *original* error,
                # since it's more likely to point at the real root cause
                # than a second failure against config that was just reloaded.
                raise first_error from None
