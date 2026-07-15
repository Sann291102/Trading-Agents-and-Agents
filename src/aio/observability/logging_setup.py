"""Process-wide logging: JSONL file always, Azure Monitor when configured.

Every agent already logs through `logging` (see Agent._log) and publishes
OrgEvents; this module makes sure those logs land somewhere durable:

- Always: a rotating JSONL file under `settings.log_dir` (one object per
  line, tagged with the current project_id contextvar), plus whatever
  console handlers the host process (uvicorn, pytest) installed.
- When `APPLICATIONINSIGHTS_CONNECTION_STRING` is set in .env AND the
  `azure-monitor-opentelemetry` package is installed: the Azure Monitor
  OpenTelemetry distro is enabled, which exports logs/traces/metrics to
  Application Insights. With no connection string the exporter stays
  dormant -- local runs need zero Azure setup and zero subscriptions.

Call `setup_logging()` once at process start (api/main.py does, at import
time, so uvicorn workers are covered). Repeat calls are no-ops.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path

from aio.config import settings
from aio.observability.context import current_project_id

logger = logging.getLogger("aio.observability.logging_setup")

_configured = False


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "project_id": current_project_id.get(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _enable_azure_monitor() -> bool:
    connection_string = settings.applicationinsights_connection_string
    if not connection_string:
        logger.info("Azure Monitor export dormant (APPLICATIONINSIGHTS_CONNECTION_STRING not set)")
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning(
            "APPLICATIONINSIGHTS_CONNECTION_STRING is set but the "
            "'azure-monitor-opentelemetry' package is not installed -- "
            "run: pip install azure-monitor-opentelemetry"
        )
        return False
    configure_azure_monitor(connection_string=connection_string)
    logger.info("Azure Monitor export enabled (Application Insights)")
    return True


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        # Anchor to the repo root (config.py's .env location), not the
        # process cwd -- same rationale as _ENV_FILE in config.py.
        log_dir = Path(settings.__class__.model_config["env_file"]).parent / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "aio.jsonl", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(console)

    _enable_azure_monitor()
    logger.info("logging configured (file=%s)", log_dir / "aio.jsonl")
