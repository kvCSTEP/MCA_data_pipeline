import os
from dataclasses import dataclass
import logging


@dataclass(frozen=True)
class Settings:
    azure_client_id: str
    azure_tenant_id: str

    teams_team_id: str
    teams_channel_id: str

    # e.g. postgresql://user:pass@postgres:5432/prefect
    # Reuses the same Postgres instance already running in the compose stack.
    database_url: str

    # External, browser-reachable base URL for the Prefect UI (through
    # NGINX/oauth2-proxy) -- NOT the internal PREFECT_API_URL used for
    # container-to-container API calls. Used only to build clickable links
    # in Teams messages.
    prefect_ui_base_url: str


def _require(name: str) -> str:
    value = os.environ.get(name)
    logging.info("--- db_url value ---", value)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


settings = Settings(
    azure_client_id=_require("APP_CLIENT_ID"),
    azure_tenant_id=_require("APP_TENANT_ID"),
    teams_team_id=_require("MS_TEAMS_GROUP_ID"),
    teams_channel_id=_require("MS_TEAMS_CHANNEL_ID"),
    database_url=_require("DB_URL"),
    prefect_ui_base_url=os.environ.get(
        "ACTUAL_PREFCE_URL", ""
    ).rstrip("/"),
)
