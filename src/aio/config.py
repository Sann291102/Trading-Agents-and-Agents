from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved relative to this file, not the process cwd -- uvicorn's working
# directory depends on how/where it's launched from (e.g. an IDE preview
# runner), so a cwd-relative ".env" path can silently fail to load.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # NVIDIA's OpenAI-compatible hosted inference API (build.nvidia.com) --
    # a second real provider, used when llm_provider == "nvidia". Handy as a
    # free-tier alternative to cut Anthropic spend during development; see
    # llm/nvidia_client.py.
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # "anthropic" (default, real Claude calls), "nvidia" (real calls against
    # NVIDIA's hosted API, see above), or "demo" (deterministic canned
    # responses -- see llm/demo_client.py). Lets the real event pipeline /
    # frontend be verified end-to-end without a paid API key; production
    # deployments should leave this at "anthropic".
    llm_provider: str = "anthropic"

    database_url: str = "postgresql+psycopg2://aio:aio@localhost:5432/aio"

    # Semantic (vector) memory is backed by the same `database_url` as
    # everything else (see memory/semantic.py) -- no separate vector-DB
    # server. This is just the logical collection/namespace name for the
    # project embeddings within that database.
    semantic_collection: str = "aio_projects"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Comma-separated, not JSON, so a plain .env line is easy to edit by hand.
    cors_origins_raw: str = "http://localhost:3000"

    # Azure Application Insights connection string. Empty (the default)
    # keeps the Azure exporter dormant -- local runs need no Azure account.
    # See observability/logging_setup.py.
    applicationinsights_connection_string: str = ""
    log_dir: str = "logs"

    # Where each mission's generated preview app is written, and where the
    # shared, pre-installed Next.js scaffold it's copied from lives. Both
    # resolved relative to the repo root (same convention as log_dir --
    # see observability/logging_setup.py) if not given as absolute paths.
    preview_workspace_dir: str = "workspace/previews"
    preview_template_dir: str = "src/aio/templates/nextjs-preview"

    # Brave Search (https://api.search.brave.com) -- gives research agents a
    # real web-search tool. Empty (the default) keeps research purely
    # model-knowledge-based; see tools/brave_search.py.
    brave_api_key: str = ""
    brave_search_base_url: str = "https://api.search.brave.com/res/v1/web/search"

    # Obsidian's "Local REST API" community plugin
    # (https://github.com/coddingtonbear/obsidian-local-rest-api) -- must be
    # installed and enabled in the target vault; its settings tab shows the
    # API key and port. Empty key keeps JARVIS's memory writes local-DB-only;
    # see integrations/obsidian.py.
    obsidian_api_url: str = "https://127.0.0.1:27124"
    obsidian_api_key: str = ""

    # n8n (self-hosted, e.g. `docker compose up n8n`) -- JARVIS fires a
    # best-effort webhook here when a mission completes, so an n8n workflow
    # can react (notify, file, sync, whatever the user builds). Empty base
    # URL keeps this a no-op; see integrations/n8n.py.
    n8n_base_url: str = ""
    n8n_api_key: str = ""
    n8n_mission_webhook_path: str = "/webhook/jarvis-mission-complete"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    def reload(self) -> None:
        """Re-reads `.env` + the process environment into this same object,
        in place, so every module holding `from aio.config import settings`
        sees the update immediately -- no process restart needed to pick up
        a changed API key or LLM_PROVIDER. Safe to call mid-mission: agents
        read `settings.*` fresh each time they build an LLM client
        (`build_default_llm`), never caching field values themselves."""
        fresh = Settings()
        for field_name in type(self).model_fields:
            setattr(self, field_name, getattr(fresh, field_name))


settings = Settings()
