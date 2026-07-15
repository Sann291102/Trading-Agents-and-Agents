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

    # "anthropic" (default, real Claude calls) or "demo" (deterministic
    # canned responses -- see llm/demo_client.py). Lets the real event
    # pipeline / frontend be verified end-to-end without a paid API key;
    # production deployments should leave this at "anthropic".
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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


settings = Settings()
