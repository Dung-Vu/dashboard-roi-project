from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    odoo_url: str
    odoo_db: str
    odoo_user_id: int
    odoo_api_key: str
    default_project_id: int
    port: int
    debug: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        odoo_url=_require_env("ODOO_URL"),
        odoo_db=_require_env("ODOO_DB"),
        odoo_user_id=int(_require_env("ODOO_USER_ID")),
        odoo_api_key=_require_env("ODOO_API_KEY"),
        default_project_id=int(os.getenv("DEFAULT_PROJECT_ID", "1035")),
        port=int(os.getenv("PORT", "5056")),
        debug=os.getenv("DEBUG", "0") == "1",
    )