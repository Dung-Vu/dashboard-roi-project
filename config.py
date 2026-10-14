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


def _parse_int_tuple(raw: str) -> tuple[int, ...]:
    if not raw or not raw.strip():
        return ()
    items: list[int] = []
    for part in raw.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            items.append(int(cleaned))
        except ValueError:
            continue
    return tuple(items)


def _parse_str_tuple(raw: str, default: tuple[str, ...] = ("sale",)) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return default
    items = tuple(part.strip() for part in raw.split(",") if part.strip())
    return items or default


@dataclass(frozen=True)
class Settings:
    odoo_url: str
    odoo_db: str
    odoo_user_id: int
    odoo_api_key: str
    default_project_id: int
    port: int
    debug: bool
    dashboard_username: str = "bonario"
    dashboard_password: str = ""
    secret_key: str = ""
    behind_proxy: bool = False
    odoo_block_prod: bool = False
    shipping_analytic_ids: tuple[int, ...] = ()
    allowed_sale_order_states: tuple[str, ...] = ("sale",)


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
        dashboard_username=os.getenv("DASHBOARD_USERNAME", "bonario"),
        dashboard_password=_require_env("DASHBOARD_PASSWORD"),
        secret_key=_require_env("SECRET_KEY"),
        behind_proxy=os.getenv("BEHIND_PROXY", "0") == "1",
        odoo_block_prod=os.getenv("ODOO_BLOCK_PROD", "0") == "1",
        shipping_analytic_ids=_parse_int_tuple(os.getenv("SHIPPING_ANALYTIC_IDS", "")),
        allowed_sale_order_states=_parse_str_tuple(os.getenv("ALLOWED_SO_STATES", "sale")),
    )