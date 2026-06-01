from __future__ import annotations

import logging
import time
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock
from time import monotonic
from typing import Any
import unicodedata

from odoo_client import OdooAPI, OdooAPIError
from cache import PersistentCache


logger = logging.getLogger(__name__)


TWO_DECIMALS = Decimal("0.01")
PROJECTS_DASHBOARD_TTL_SECONDS = 1800  # 30 minutes
PROJECTS_DASHBOARD_MAX_WORKERS = 24
DASHBOARD_TARGET_TAGS = ("Nội thất rời", "Giấy dán tường", "Rèm", "Vải nội thất")
EXCLUDED_SALESPERSONS = ("CEO office", "Đỗ Thị Hải Yến", "CEO office, Đỗ Thị Hải Yến")
BG_TIERS = (
    ("<10tr", Decimal("10000000")),
    ("10-100tr", Decimal("100000000")),
    ("100-200tr", Decimal("200000000")),
    (">200tr", None),
)
PRODUCT_TYPE_LABELS = {
    "service": "Service",
    "product": "Storable Product",
    "consu": "Consumable",
    "combo": "Combo",
}
SERVICE_OPERATION_KEYWORDS = (
    "thi công",
    "thi cong",
    "[lc]-dv",
    "business travel",
    "công tác",
    "congtac",
    "vé xe",
    "ve xe",
    "đặt vé",
    "dat ve",
    "đội thợ",
    "doi tho",
)
MATERIAL_LOGISTICS_KEYWORDS = (
    "ship",
    "giao",
)
COMPANY_SCOPES = {
    "all": {"label": "Tất cả công ty", "aliases": ("all", "tat ca", "tatca")},
    "bonario": {"label": "Bonario", "aliases": ("bonario",)},
    "ordinaire": {"label": "Ordinaire", "aliases": ("ordinaire",)},
}


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def as_money(value: Decimal | int | float) -> float:
    if isinstance(value, (int, float)):
        value = Decimal(str(value))
    return float(value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP))


def relation_name(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1]
    return None


def relation_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return text.encode("ascii", "ignore").decode("ascii").lower()


class DashboardService:
    def __init__(self, client: OdooAPI):
        self.client = client
        self._projects_dashboard_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_lock = Lock()
        self._db_cache = PersistentCache(ttl=86400 * 30)
        self._active_updates: set[str] = set()
        self._active_updates_lock = Lock()

    def test_connection(self) -> dict[str, Any]:
        return self.client.test_connection()

    def _fetch_projects_dashboard_from_odoo(self, date_from: str, company_key: str) -> dict[str, Any]:
        sale_orders = self._get_dashboard_sale_orders(date_from, company_key)
        sale_order_ids = [order["id"] for order in sale_orders]
        sale_orders_by_id = {order["id"]: order for order in sale_orders}
        tag_map = self._get_sale_order_tag_map(sale_orders)
        
        # Filter: chỉ giữ sale orders có ít nhất 1 tag trong target tags
        filtered_so_ids = [so_id for so_id, tags in tag_map.items() if tags]
        if not filtered_so_ids:
            # Không có SO nào match tags - build empty dashboard payload directly
            return {
                "projects": [],
                "summary": {
                    "total_projects": 0,
                    "valid_project_count": 0,
                    "total_bg_untaxed": 0,
                    "total_native_expected_cost": 0,
                    "total_adjusted_expected_cost": 0,
                    "total_cost_adjustment_amount": 0,
                    "total_gp_amount": 0,
                    "weighted_gp_percent": 0,
                },
                "tag_buckets": {},
                "tag_gp_ranks": {},
                "meta": self._build_projects_dashboard_meta([], [], date_from, company_key),
                "date_from": date_from,
                "company": self._company_payload(company_key),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        
        projects = self._get_projects_for_sale_orders(filtered_so_ids)
        sale_orders_by_id = {so_id: sale_orders_by_id[so_id] for so_id in filtered_so_ids if so_id in sale_orders_by_id}
        analytic_adjustments = self._build_dashboard_analytic_adjustments(projects, sale_orders_by_id)

        rows: list[dict[str, Any]] = []
        if projects:
            worker_count = min(PROJECTS_DASHBOARD_MAX_WORKERS, len(projects))
            logger.info(f"Fetching {len(projects)} projects with {worker_count} workers...")
            completed = 0
            total = len(projects)
            
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(
                        self._build_projects_dashboard_row,
                        project,
                        sale_orders_by_id,
                        tag_map,
                        analytic_adjustments,
                    )
                    for project in projects
                ]
                for future in as_completed(futures):
                    try:
                        row = future.result()
                        rows.append(row)
                    except Exception as e:
                        logger.error(f"Failed to build dashboard row: {e}")
                        # Skip failed project, continue with others
                    completed += 1
                    if completed % 50 == 0 or completed == total:
                        logger.info(f"Progress: {completed}/{total} projects")

        rows.sort(key=lambda row: (row.get("date_order") or "", row.get("sale_order_name") or "", row["project_id"]), reverse=True)
        
        # Filter rows for statistics: chỉ tính summary/buckets/ranks với Order State = Done
        done_rows = [row for row in rows if row.get("order_state") == "Done"]
        
        # Filter rows by company_key to build the company-specific subset filtered_rows
        # If a row has no company_key, include it to preserve compatibility
        filtered_rows = [
            row for row in rows
            if company_key == "all" or not row.get("company_key") or row.get("company_key") == company_key
        ]
        filtered_done_rows = [row for row in filtered_rows if row.get("order_state") == "Done"]
        
        payload = {
            "projects": filtered_rows,
            "summary": self._build_projects_dashboard_summary(filtered_done_rows),
            "tag_buckets": self._build_tag_buckets(done_rows),
            "tag_gp_ranks": self._build_tag_gp_ranks(done_rows),
            "meta": self._build_projects_dashboard_meta(filtered_rows, filtered_done_rows, date_from, company_key),
            "date_from": date_from,
            "company": self._company_payload(company_key),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        return payload

    def _async_update_projects_dashboard(
        self,
        date_from: str,
        company_key: str,
        cache_key: str,
        db_cache_key: str,
    ) -> None:
        try:
            logger.info(f"Starting background cache revalidation for {cache_key}")
            payload = self._fetch_projects_dashboard_from_odoo(date_from, company_key)
            payload["cached_at"] = time.time()
            
            # Write to SQLite Persistent Cache
            self._db_cache.set(db_cache_key, payload)
            
            # Write to In-Memory Cache
            with self._cache_lock:
                self._projects_dashboard_cache[cache_key] = (monotonic(), payload)
                
            logger.info(f"Background cache revalidation completed successfully for {cache_key}")
        except Exception as e:
            logger.error(f"Error in background revalidation thread for {cache_key}: {e}", exc_info=True)
        finally:
            with self._active_updates_lock:
                self._active_updates.discard(cache_key)

    def build_projects_dashboard(
        self,
        date_from: str = "2026-01-01",
        *,
        company: str = "all",
        refresh: bool = False,
    ) -> dict[str, Any]:
        date_from = self._normalize_date_from(date_from)
        company_key = self._normalize_company_key(company)
        cache_key = f"{company_key}:{date_from}"
        db_cache_key = f"dashboard_payload:{company_key}:{date_from}"

        # If refresh=True: clear caches, fetch synchronously from Odoo, cache, and return
        if refresh:
            self._db_cache.clear("profitability:")
            self._db_cache.clear(db_cache_key)
            with self._cache_lock:
                self._projects_dashboard_cache.pop(cache_key, None)
            
            logger.info(f"Forced refresh: cleared caches for {cache_key}")
            payload = self._fetch_projects_dashboard_from_odoo(date_from, company_key)
            payload["cached_at"] = time.time()
            
            self._db_cache.set(db_cache_key, payload)
            with self._cache_lock:
                self._projects_dashboard_cache[cache_key] = (monotonic(), payload)
            return payload

        # If refresh=False:
        # 1. Check in-memory cache
        with self._cache_lock:
            cached = self._projects_dashboard_cache.get(cache_key)
            if cached and monotonic() - cached[0] < PROJECTS_DASHBOARD_TTL_SECONDS:
                logger.debug(f"Memory cache hit for {cache_key}")
                return cached[1]

        # 2. Check SQLite cache
        db_cached = self._db_cache.get(db_cache_key)
        if db_cached is not None:
            cached_at = db_cached.get("cached_at")
            if cached_at is not None:
                age = time.time() - cached_at
                
                # Save to memory cache, preserving age
                with self._cache_lock:
                    self._projects_dashboard_cache[cache_key] = (monotonic() - age, db_cached)
                
                # If fresh (< 5 minutes), return immediately
                if age < 300:
                    logger.info(f"SQLite cache hit & fresh (age: {age:.1f}s) for {cache_key}")
                    return db_cached
                
                # Stale (>= 5 minutes): return stale instantly, and spawn background revalidation thread
                logger.info(f"SQLite cache hit but stale (age: {age:.1f}s) for {cache_key}. Triggering revalidation.")
                with self._active_updates_lock:
                    if cache_key not in self._active_updates:
                        self._active_updates.add(cache_key)
                        t = threading.Thread(
                            target=self._async_update_projects_dashboard,
                            args=(date_from, company_key, cache_key, db_cache_key),
                            daemon=True
                        )
                        t.start()
                return db_cached

        # 3. SQLite cache miss: fetch synchronously from Odoo
        logger.info(f"SQLite cache miss for {cache_key}. Fetching synchronously from Odoo.")
        payload = self._fetch_projects_dashboard_from_odoo(date_from, company_key)
        payload["cached_at"] = time.time()
        
        self._db_cache.set(db_cache_key, payload)
        with self._cache_lock:
            self._projects_dashboard_cache[cache_key] = (monotonic(), payload)
        return payload

    def _build_empty_dashboard(self, date_from: str, company_key: str = "all") -> dict[str, Any]:
        payload = {
            "projects": [],
            "summary": {
                "total_projects": 0,
                "valid_project_count": 0,
                "total_bg_untaxed": 0,
                "total_native_expected_cost": 0,
                "total_adjusted_expected_cost": 0,
                "total_cost_adjustment_amount": 0,
                "total_gp_amount": 0,
                "weighted_gp_percent": 0,
            },
            "tag_buckets": {},
            "tag_gp_ranks": {},
            "meta": self._build_projects_dashboard_meta([], [], date_from, company_key),
            "date_from": date_from,
            "company": self._company_payload(company_key),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._cache_lock:
            self._projects_dashboard_cache[f"{company_key}:{date_from}"] = (monotonic(), payload)
        return payload

    def _normalize_date_from(self, date_from: str) -> str:
        try:
            return datetime.fromisoformat(date_from.strip()).date().isoformat()
        except ValueError as exc:
            raise OdooAPIError(
                "date_from must use YYYY-MM-DD format.",
                model="sale.order",
                method="search_read",
            ) from exc

    def _normalize_company_key(self, company: str | None) -> str:
        normalized = normalized_text(company or "all").strip()
        for key, scope in COMPANY_SCOPES.items():
            if normalized == key or normalized in scope["aliases"]:
                return key
        raise OdooAPIError(
            f"Unsupported company scope: {company}",
            model="res.company",
            method="search_read",
        )

    def _company_payload(self, company_key: str) -> dict[str, str]:
        return {"key": company_key, "label": COMPANY_SCOPES[company_key]["label"]}

    def _company_key_from_ref(self, company_ref: Any) -> str | None:
        company_name = relation_name(company_ref)
        normalized = normalized_text(company_name)
        for key, scope in COMPANY_SCOPES.items():
            if any(alias in normalized for alias in scope["aliases"]):
                return key
        return None

    def _get_dashboard_sale_orders(self, date_from: str, company_key: str) -> list[dict[str, Any]]:
        fields = [
            "id",
            "name",
            "partner_id",
            "date_order",
            "amount_untaxed",
            "x_sale_order_tag_ids",
            "x_studio_selection_field_q4_1imrcsjj8",
            "user_id",
            "company_id",
        ]
        
        companies = []
        try:
            companies = self.client.search_read("res.company", [], ["id", "name"])
        except Exception as e:
            logger.warning(f"Failed to retrieve companies from Odoo: {e}. Falling back to single query.")

        if not companies:
            sale_orders = self.client.search_read(
                "sale.order",
                [["date_order", ">=", date_from]],
                fields,
            )
        else:
            sale_orders = []
            max_workers = min(PROJECTS_DASHBOARD_MAX_WORKERS, len(companies) + 1)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for company in companies:
                    c_id = company["id"]
                    future = executor.submit(
                        self.client.call_method,
                        "sale.order",
                        "search_read",
                        [[["date_order", ">=", date_from], ["company_id", "=", c_id]]],
                        {
                            "fields": fields,
                            "context": {"allowed_company_ids": [c_id]}
                        }
                    )
                    futures[future] = c_id

                # Query for no-company sale orders
                no_company_future = executor.submit(
                    self.client.search_read,
                    "sale.order",
                    [["date_order", ">=", date_from], ["company_id", "=", False]],
                    fields,
                )
                futures[no_company_future] = False

                for future in as_completed(futures):
                    comp_identifier = futures[future]
                    try:
                        res = future.result()
                        if res:
                            sale_orders.extend(res)
                    except Exception as e:
                        logger.error(f"Failed to fetch sale orders for company {comp_identifier}: {e}")

        # Deduplicate all fetched sale orders by id
        seen_ids = set()
        dedup_sale_orders = []
        for order in sale_orders:
            if order["id"] not in seen_ids:
                seen_ids.add(order["id"])
                dedup_sale_orders.append(order)
        
        # Filter out sale orders owned by the excluded Hai Yen sales account.
        return [
            order for order in dedup_sale_orders
            if not self._is_excluded_salesperson(order)
        ]

    def _sale_order_matches_company(self, order: dict[str, Any], company_key: str) -> bool:
        detected_key = self._company_key_from_ref(order.get("company_id"))
        if detected_key is None:
            return True
        return detected_key == company_key

    @staticmethod
    def _is_excluded_salesperson(order: dict[str, Any]) -> bool:
        user_id = order.get("user_id")
        if (
            user_id
            and isinstance(user_id, (list, tuple))
            and len(user_id) > 1
            and user_id[1] in EXCLUDED_SALESPERSONS
        ):
            return True
        return False

    def _get_projects_for_sale_orders(self, sale_order_ids: list[int]) -> list[dict[str, Any]]:
        if not sale_order_ids:
            return []
        return self.client.call_method(
            "project.project",
            "search_read",
            [[["sale_order_id", "in", sale_order_ids]]],
            {
                "fields": ["id", "name", "partner_id", "sale_order_id", "account_id", "company_id", "active"],
                "context": {"active_test": False},
            },
        )

    def _build_dashboard_analytic_adjustments(
        self,
        projects: list[dict[str, Any]],
        sale_orders_by_id: dict[int, dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        adjustments = {
            project["id"]: {
                "foreign_cost_removed": Decimal("0"),
                "foreign_cost_added": Decimal("0"),
            }
            for project in projects
        }
        project_by_sale_order_id = {
            relation_id(project.get("sale_order_id")): project
            for project in projects
            if relation_id(project.get("sale_order_id"))
        }
        project_by_account_id = {
            relation_id(project.get("account_id")): project
            for project in projects
            if relation_id(project.get("account_id"))
        }
        foreign_account_sources = self._find_foreign_analytic_account_sources(
            sale_orders_by_id,
            project_by_sale_order_id,
        )
        self._apply_foreign_invoice_cost_adjustments(
            project_by_account_id,
            project_by_sale_order_id,
            adjustments,
            foreign_account_sources,
        )
        return adjustments

    def _find_foreign_analytic_account_sources(
        self,
        sale_orders_by_id: dict[int, dict[str, Any]],
        project_by_sale_order_id: dict[int | None, dict[str, Any]],
    ) -> dict[int, set[int]]:
        sale_order_ids = sorted(sale_orders_by_id)
        if not sale_order_ids:
            return {}
        foreign_account_sources: dict[int, set[int]] = defaultdict(set)
        lines = self.client.search_read(
            "sale.order.line",
            [["order_id", "in", sale_order_ids]],
            ["id", "name", "order_id", "price_subtotal", "analytic_distribution"],
            limit=0,
        )
        for line in lines:
            sale_order_id = relation_id(line.get("order_id"))
            project = project_by_sale_order_id.get(sale_order_id)
            expected_account_id = relation_id(project.get("account_id")) if project else None
            if not project or not expected_account_id:
                continue
            distribution = line.get("analytic_distribution")
            if not isinstance(distribution, dict):
                continue
            for raw_account_id, percent in distribution.items():
                if abs(as_decimal(line.get("price_subtotal")) * as_decimal(percent) / Decimal("100")) < TWO_DECIMALS:
                    continue
                account_ids = self._parse_analytic_account_ids(raw_account_id)
                if not account_ids or expected_account_id in account_ids:
                    continue
                for account_id in account_ids:
                    foreign_account_sources[account_id].add(sale_order_id)
        return foreign_account_sources

    def _apply_foreign_invoice_cost_adjustments(
        self,
        project_by_account_id: dict[int | None, dict[str, Any]],
        project_by_sale_order_id: dict[int | None, dict[str, Any]],
        adjustments: dict[int, dict[str, Any]],
        foreign_account_sources: dict[int, set[int]] | None = None,
    ) -> None:
        account_ids = sorted(
            set(account_id for account_id in project_by_account_id if account_id)
            | set((foreign_account_sources or {}).keys())
        )
        if not account_ids:
            return
        analytic_entries = self.client.search_read(
            "account.analytic.line",
            [["account_id", "in", account_ids], ["category", "=", "invoice"]],
            ["id", "name", "amount", "account_id", "move_line_id", "product_id", "category"],
            limit=1000,
        )
        move_line_ids = sorted(
            {
                relation_id(entry.get("move_line_id"))
                for entry in analytic_entries
                if relation_id(entry.get("move_line_id"))
            }
        )
        if not move_line_ids:
            return
        move_lines = self.client.search_read(
            "account.move.line",
            [["id", "in", move_line_ids]],
            ["id", "name", "move_id", "sale_line_ids", "product_id"],
            limit=len(move_line_ids),
        )
        move_line_map = {line["id"]: line for line in move_lines}
        sale_line_ids = sorted(
            {
                sale_line_id
                for line in move_lines
                for sale_line_id in self._extract_relation_ids(line.get("sale_line_ids"))
            }
        )
        if not sale_line_ids:
            return
        sale_lines = self.client.search_read(
            "sale.order.line",
            [["id", "in", sale_line_ids]],
            ["id", "order_id", "name"],
            limit=len(sale_line_ids),
        )
        sale_line_order_map = {line["id"]: relation_id(line.get("order_id")) for line in sale_lines}

        for entry in analytic_entries:
            amount = as_decimal(entry.get("amount"))
            if amount >= -TWO_DECIMALS:
                continue
            account_id = relation_id(entry.get("account_id"))
            target_project = project_by_account_id.get(account_id)
            target_sale_order_id = relation_id(target_project.get("sale_order_id")) if target_project else None
            move_line = move_line_map.get(relation_id(entry.get("move_line_id")) or 0)
            if not move_line:
                continue
            source_order_ids = {
                sale_line_order_map.get(sale_line_id)
                for sale_line_id in self._extract_relation_ids(move_line.get("sale_line_ids"))
            }
            source_order_ids.discard(None)
            if target_sale_order_id:
                foreign_order_ids = sorted(order_id for order_id in source_order_ids if order_id != target_sale_order_id)
            else:
                foreign_order_ids = sorted(source_order_ids)
            if not foreign_order_ids:
                continue

            cost_amount = -amount
            if target_project and target_project["id"] in adjustments:
                target_adjustment = adjustments[target_project["id"]]
                target_adjustment["foreign_cost_removed"] += cost_amount

            for foreign_order_id in foreign_order_ids:
                source_project = project_by_sale_order_id.get(foreign_order_id)
                if not source_project or source_project["id"] not in adjustments:
                    continue
                source_adjustment = adjustments[source_project["id"]]
                source_adjustment["foreign_cost_added"] += cost_amount

    def _parse_analytic_account_ids(self, value: Any) -> set[int]:
        if value is None:
            return set()
        values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
        account_ids: set[int] = set()
        for raw_value in values:
            text = str(raw_value).strip()
            digits = []
            for char in text:
                if not char.isdigit():
                    break
                digits.append(char)
            if not digits:
                continue
            account_ids.add(int("".join(digits)))
        return account_ids

    def _build_projects_dashboard_row(
        self,
        project: dict[str, Any],
        sale_orders_by_id: dict[int, dict[str, Any]],
        tag_map: dict[int, list[str]],
        analytic_adjustments: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        sale_order_id = relation_id(project.get("sale_order_id"))
        sale_order = sale_orders_by_id.get(sale_order_id or 0, {})
        bg_untaxed = as_decimal(sale_order.get("amount_untaxed"))
        native_expected_cost = as_decimal(
            self._get_profitability_costs(project["id"])["expected_cost_total"]
        )
        adjustments = analytic_adjustments.get(project["id"], {})
        foreign_cost_removed = as_decimal(adjustments.get("foreign_cost_removed"))
        foreign_cost_added = as_decimal(adjustments.get("foreign_cost_added"))
        cost_adjustment_amount = foreign_cost_removed - foreign_cost_added
        adjusted_expected_cost = native_expected_cost - foreign_cost_removed + foreign_cost_added
        gp_amount = bg_untaxed - adjusted_expected_cost
        gp_percent = None
        if bg_untaxed > 0:
            gp_percent = as_money((gp_amount / bg_untaxed) * Decimal("100"))
        company_key = (
            self._company_key_from_ref(sale_order.get("company_id"))
            or self._company_key_from_ref(project.get("company_id"))
            or ""
        )
        return {
            "project_id": project["id"],
            "project_name": project.get("name") or "",
            "sale_order_id": sale_order_id,
            "sale_order_name": sale_order.get("name") or relation_name(project.get("sale_order_id")),
            "customer": relation_name(sale_order.get("partner_id")) or relation_name(project.get("partner_id")),
            "date_order": sale_order.get("date_order"),
            "company_key": company_key,
            "company_name": relation_name(sale_order.get("company_id")) or relation_name(project.get("company_id")) or "",
            "tags": tag_map.get(sale_order_id or 0, []),
            "order_state": sale_order.get("x_studio_selection_field_q4_1imrcsjj8") or "",
            "project_active": bool(project.get("active", True)),
            "bg_untaxed": as_money(bg_untaxed),
            "native_expected_cost": as_money(native_expected_cost),
            "adjusted_expected_cost": as_money(adjusted_expected_cost),
            "cost_adjustment_amount": as_money(cost_adjustment_amount),
            "cost_removed_amount": as_money(foreign_cost_removed),
            "cost_added_amount": as_money(foreign_cost_added),
            "gp_amount": as_money(gp_amount),
            "gp_percent": gp_percent,
        }

    def _build_projects_dashboard_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        valid_rows = [row for row in rows if as_decimal(row["bg_untaxed"]) > 0]
        bg_total = sum(as_decimal(row["bg_untaxed"]) for row in valid_rows)
        native_cost_total = sum(as_decimal(row["native_expected_cost"]) for row in valid_rows)
        adjusted_cost_total = sum(as_decimal(row.get("adjusted_expected_cost", row["native_expected_cost"])) for row in valid_rows)
        adjustment_total = sum(as_decimal(row.get("cost_adjustment_amount")) for row in valid_rows)
        gp_total = bg_total - adjusted_cost_total
        weighted_gp_percent = Decimal("0")
        if bg_total > 0:
            weighted_gp_percent = (gp_total / bg_total) * Decimal("100")

        return {
            "total_projects": len(rows),
            "valid_project_count": len(valid_rows),
            "total_bg_untaxed": as_money(bg_total),
            "total_native_expected_cost": as_money(native_cost_total),
            "total_adjusted_expected_cost": as_money(adjusted_cost_total),
            "total_cost_adjustment_amount": as_money(adjustment_total),
            "total_gp_amount": as_money(gp_total),
            "weighted_gp_percent": as_money(weighted_gp_percent),
        }

    def _build_projects_dashboard_meta(
        self,
        rows: list[dict[str, Any]],
        done_rows: list[dict[str, Any]],
        date_from: str,
        company_key: str,
    ) -> dict[str, Any]:
        valid_done_rows = [row for row in done_rows if as_decimal(row["bg_untaxed"]) > 0]
        state_counts = Counter(row.get("order_state") or "No state" for row in rows)
        archived_rows = [row for row in rows if row.get("project_active") is False]
        return {
            "date_field": "sale.order.date_order",
            "company": self._company_payload(company_key),
            "odoo_url": self.client.url,
            "project_scope": "all_order_states",
            "project_active_scope": "active_and_archived",
            "summary_scope": "done_only",
            "cost_scope": "adjusted_expected_cost",
            "target_tags": list(DASHBOARD_TARGET_TAGS),
            "excluded_salespersons": list(EXCLUDED_SALESPERSONS),
            "counts": {
                "list_projects": len(rows),
                "done_projects": len(done_rows),
                "valid_done_projects": len(valid_done_rows),
                "non_done_projects": len(rows) - len(done_rows),
                "archived_projects": len(archived_rows),
            },
            "state_counts": dict(sorted(state_counts.items())),
            "date_from": date_from,
        }

    def _build_tag_buckets(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        buckets: dict[str, dict[str, dict[str, Any]]] = {
            tag: {
                tier: {
                    "count": 0,
                    "bg_untaxed": Decimal("0"),
                    "native_expected_cost": Decimal("0"),
                    "adjusted_expected_cost": Decimal("0"),
                    "gp_amount": Decimal("0"),
                    "weighted_gp_percent": None,
                }
                for tier, _ in BG_TIERS
            }
            for tag in DASHBOARD_TARGET_TAGS
        }

        for row in rows:
            bg_untaxed = as_decimal(row["bg_untaxed"])
            if bg_untaxed <= 0:
                continue
            native_expected_cost = as_decimal(row["native_expected_cost"])
            adjusted_expected_cost = as_decimal(row.get("adjusted_expected_cost", row["native_expected_cost"]))
            tier = self._tier_for_amount(bg_untaxed)
            for tag in row.get("tags", []):
                if tag not in buckets:
                    continue
                bucket = buckets[tag][tier]
                bucket["count"] += 1
                bucket["bg_untaxed"] += bg_untaxed
                bucket["native_expected_cost"] += native_expected_cost
                bucket["adjusted_expected_cost"] += adjusted_expected_cost
                bucket["gp_amount"] += bg_untaxed - adjusted_expected_cost

        return {
            tag: {
                tier: self._serialize_aggregate_bucket(bucket)
                for tier, bucket in tag_buckets.items()
            }
            for tag, tag_buckets in buckets.items()
        }

    def _serialize_aggregate_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        bg_untaxed = as_decimal(bucket["bg_untaxed"])
        gp_amount = as_decimal(bucket["gp_amount"])
        weighted_gp_percent = None
        if bg_untaxed > 0:
            weighted_gp_percent = as_money((gp_amount / bg_untaxed) * Decimal("100"))

        return {
            "count": int(bucket["count"]),
            "bg_untaxed": as_money(bg_untaxed),
            "native_expected_cost": as_money(as_decimal(bucket["native_expected_cost"])),
            "adjusted_expected_cost": as_money(as_decimal(bucket.get("adjusted_expected_cost", bucket["native_expected_cost"]))),
            "gp_amount": as_money(gp_amount),
            "weighted_gp_percent": weighted_gp_percent,
        }

    def _build_tag_gp_ranks(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        tag_ranges: dict[str, dict[str, dict[str, Any]]] = {
            tag: defaultdict(lambda: {"count": 0, "bg_untaxed": Decimal("0")})
            for tag in DASHBOARD_TARGET_TAGS
        }

        for row in rows:
            bg_untaxed = as_decimal(row["bg_untaxed"])
            gp_percent = row.get("gp_percent")
            if bg_untaxed <= 0 or gp_percent is None:
                continue
            label = self._gp_range_label(as_decimal(gp_percent))
            for tag in row.get("tags", []):
                if tag not in tag_ranges:
                    continue
                entry = tag_ranges[tag][label]
                entry["count"] += 1
                entry["bg_untaxed"] += bg_untaxed

        ranks: dict[str, list[dict[str, Any]]] = {}
        for tag, ranges in tag_ranges.items():
            sorted_ranges = sorted(
                ranges.items(),
                key=lambda item: (item[1]["count"], item[1]["bg_untaxed"]),
                reverse=True,
            )
            ranks[tag] = [
                {
                    "rank": index + 1,
                    "range": label,
                    "count": int(values["count"]),
                    "bg_untaxed": as_money(as_decimal(values["bg_untaxed"])),
                }
                for index, (label, values) in enumerate(sorted_ranges)
            ]
        return ranks

    def _tier_for_amount(self, amount: Decimal) -> str:
        for label, upper_bound in BG_TIERS:
            if upper_bound is None or amount < upper_bound:
                return label
        return ">200tr"

    def _gp_range_label(self, gp_percent: Decimal) -> str:
        val = int(gp_percent)
        if val < 0:
            return "<0%"
        if val <= 20:
            return "0-20%"
        if val <= 40:
            return "21-40%"
        # Từ 41% trở đi: bước nhảy 5 điểm.
        start = 41 + ((val - 41) // 5) * 5
        end = start + 4
        return f"{start}-{end}%"

    def _get_sale_order_tag_map(self, sale_orders: list[dict[str, Any]]) -> dict[int, list[str]]:
        raw_tag_ids = sorted(
            {
                tag_id
                for order in sale_orders
                for tag_id in self._extract_relation_ids(order.get("x_sale_order_tag_ids"))
            }
        )
        tag_names_by_id = self._get_sale_order_tag_names(raw_tag_ids)
        tag_map: dict[int, list[str]] = {}

        for order in sale_orders:
            names = [
                tag_names_by_id[tag_id]
                for tag_id in self._extract_relation_ids(order.get("x_sale_order_tag_ids"))
                if tag_names_by_id.get(tag_id) in DASHBOARD_TARGET_TAGS
            ]
            inline_names = [
                name
                for name in self._extract_relation_names(order.get("x_sale_order_tag_ids"))
                if name in DASHBOARD_TARGET_TAGS
            ]
            tag_map[order["id"]] = sorted(set(names + inline_names), key=DASHBOARD_TARGET_TAGS.index)

        return tag_map

    def _get_sale_order_tag_names(self, tag_ids: list[int]) -> dict[int, str]:
        if not tag_ids:
            return {}

        relation_models: list[str] = []
        try:
            fields = self.client.call_method(
                "sale.order",
                "fields_get",
                [["x_sale_order_tag_ids"]],
                {"attributes": ["relation"]},
            )
            relation = fields.get("x_sale_order_tag_ids", {}).get("relation") if isinstance(fields, dict) else None
            if relation:
                relation_models.append(relation)
        except OdooAPIError:
            pass

        for fallback in ("crm.tag", "sale.order.tag"):
            if fallback not in relation_models:
                relation_models.append(fallback)

        for model in relation_models:
            for name_field in ("name", "x_name", "display_name"):
                try:
                    tags = self.client.search_read(model, [["id", "in", tag_ids]], ["id", name_field])
                except OdooAPIError:
                    continue
                if tags:
                    return {tag["id"]: tag.get(name_field) or tag.get("display_name") or "" for tag in tags}
        return {}

    def _extract_relation_ids(self, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        ids: list[int] = []
        for item in value:
            if isinstance(item, int):
                ids.append(item)
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], int):
                ids.append(item[0])
        return ids

    def _extract_relation_names(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        names: list[str] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) > 1 and isinstance(item[1], str):
                names.append(item[1])
        return names

    def build_project_dashboard(self, project_id: int) -> dict[str, Any]:
        project = self._get_project(project_id)
        sale_order_ref = project.get("sale_order_id")
        if not sale_order_ref:
            raise OdooAPIError(
                "Project is not linked to any sale order.",
                model="project.project",
                method="search_read",
            )

        sale_order = self._get_sale_order(sale_order_ref[0])
        if self._is_excluded_salesperson(sale_order):
            salesperson_name = relation_name(sale_order.get("user_id")) or "unknown"
            raise OdooAPIError(
                f"Project linked to excluded salesperson '{salesperson_name}' is not tracked in this dashboard.",
                model="sale.order",
                method="search_read",
            )
        raw_lines = self._get_sale_order_lines(sale_order["id"])
        product_map = self._get_product_map(raw_lines)
        profitability_costs = self._get_profitability_costs(project_id)
        cost_model = self._build_cost_model(project, raw_lines, product_map, profitability_costs)
        lines = [
            self._serialize_line(line, product_map, cost_model["line_cost_map"])
            for line in raw_lines
            if not line.get("display_type")
        ]
        line_groups = self._build_line_groups(lines)
        summary = self._build_summary(
            sale_order,
            lines,
            line_groups,
            cost_model["summary"],
            profitability_costs,
        )

        return {
            "project": {
                "id": project["id"],
                "name": project["name"],
                "customer": relation_name(project.get("partner_id")),
                "sale_order_name": relation_name(project.get("sale_order_id")),
                "account_name": relation_name(project.get("account_id")),
                "allow_timesheets": bool(project.get("allow_timesheets")),
            },
            "sale_order": {
                "id": sale_order["id"],
                "name": sale_order["name"],
                "customer": relation_name(sale_order.get("partner_id")),
                "currency": relation_name(sale_order.get("currency_id")) or "VND",
                "date_order": sale_order.get("date_order"),
                "amount_untaxed": as_money(as_decimal(sale_order.get("amount_untaxed"))),
                "amount_total": as_money(as_decimal(sale_order.get("amount_total"))),
            },
            "summary": summary,
            "cost_summary": self._serialize_cost_summary(cost_model["summary"]),
            "cost_sources": self._serialize_cost_sources(cost_model["cost_sources"]),
            "reconciliation": self._serialize_reconciliation(cost_model["reconciliation"]),
            "line_groups": line_groups,
            "project_cost_entries": cost_model["project_cost_entries"],
            "profitability_costs": self._serialize_profitability_costs(profitability_costs),
            "alerts": self._build_alerts(project, summary),
            "lines": lines,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_profitability_costs(self, project_id: int) -> dict[str, Decimal | dict[str, dict[str, Decimal]]]:
        cache_key = f"profitability:{project_id}"
        cached = self._db_cache.get(cache_key)
        if cached is not None:
            return {
                "billed_cost_total": as_decimal(cached.get("billed_cost_total")),
                "open_commitment_total": as_decimal(cached.get("open_commitment_total")),
                "expected_cost_total": as_decimal(cached.get("expected_cost_total")),
                "breakdown": {k: {kk: as_decimal(vv) for kk, vv in v.items()} for k, v in cached.get("breakdown", {}).items()},
                "items": [],
            }
        try:
            panel = self.client.call_method("project.project", "get_panel_data", [[project_id]])
        except OdooAPIError:
            return {
                "billed_cost_total": Decimal("0"),
                "open_commitment_total": Decimal("0"),
                "expected_cost_total": Decimal("0"),
                "breakdown": {},
                "items": [],
            }

        cost_items = panel.get("profitability_items", {}).get("costs", {}).get("data", [])
        breakdown: dict[str, dict[str, Decimal]] = {}
        items: list[dict[str, Any]] = []
        billed_cost_total = Decimal("0")
        open_commitment_total = Decimal("0")

        for item in cost_items:
            billed_cost = -as_decimal(item.get("billed"))
            open_commitment = -as_decimal(item.get("to_bill"))
            expected_cost = billed_cost + open_commitment
            item_key = str(item.get("id") or "other")
            item_label = (
                item.get("name")
                or item.get("display_name")
                or item.get("title")
                or item.get("label")
                or item_key
            )

            breakdown[item_key] = {
                "billed": billed_cost,
                "open_commitment": open_commitment,
                "expected": expected_cost,
            }
            items.append(
                {
                    "id": item_key,
                    "label": item_label,
                    "type": item.get("type") or item.get("model") or item.get("res_model"),
                    "billed": billed_cost,
                    "open_commitment": open_commitment,
                    "expected": expected_cost,
                }
            )
            billed_cost_total += billed_cost
            open_commitment_total += open_commitment

        result = {
            "billed_cost_total": billed_cost_total,
            "open_commitment_total": open_commitment_total,
            "expected_cost_total": billed_cost_total + open_commitment_total,
            "breakdown": breakdown,
            "items": items,
        }
        
        # Cache to SQLite (serialize Decimal to string)
        cache_data = {
            "billed_cost_total": str(billed_cost_total),
            "open_commitment_total": str(open_commitment_total),
            "expected_cost_total": str(billed_cost_total + open_commitment_total),
            "breakdown": {k: {kk: str(vv) for kk, vv in v.items()} for k, v in breakdown.items()},
        }
        self._db_cache.set(cache_key, cache_data)
        
        return result

    def _serialize_profitability_costs(
        self,
        profitability_costs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "billed_cost_total": as_money(as_decimal(profitability_costs["billed_cost_total"])),
            "open_commitment_total": as_money(as_decimal(profitability_costs["open_commitment_total"])),
            "expected_cost_total": as_money(as_decimal(profitability_costs["expected_cost_total"])),
            "items": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "type": item.get("type"),
                    "billed": as_money(as_decimal(item["billed"])),
                    "open_commitment": as_money(as_decimal(item["open_commitment"])),
                    "expected": as_money(as_decimal(item["expected"])),
                }
                for item in profitability_costs.get("items", [])
                if (
                    abs(as_decimal(item.get("billed"))) >= TWO_DECIMALS
                    or abs(as_decimal(item.get("open_commitment"))) >= TWO_DECIMALS
                )
            ],
        }

    def _serialize_cost_summary(self, cost_summary: dict[str, Any]) -> dict[str, Any]:
        money_keys = {
            "actual_cost_total",
            "posted_actual_total",
            "draft_bill_commitment_total",
            "po_open_commitment_total",
            "open_commitment_total",
            "final_cost_total",
            "allocated_cost_total",
            "project_extra_cost_total",
            "costed_revenue_total",
            "unmapped_revenue_total",
            "stock_valuation_total",
        }
        serialized: dict[str, Any] = {}
        for key, value in cost_summary.items():
            if key in money_keys:
                serialized[key] = as_money(as_decimal(value))
            elif isinstance(value, Decimal):
                serialized[key] = as_money(value)
            else:
                serialized[key] = value
        return serialized

    def _serialize_cost_sources(self, cost_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized = []
        for source in cost_sources:
            item = dict(source)
            item["amount"] = as_money(as_decimal(source.get("amount")))
            if source.get("raw_amount") is not None:
                item["raw_amount"] = as_money(as_decimal(source.get("raw_amount")))
            serialized.append(item)
        return serialized

    def _serialize_reconciliation(self, reconciliation: dict[str, Any]) -> dict[str, Any]:
        return {
            key: as_money(as_decimal(value)) if isinstance(value, Decimal) else value
            for key, value in reconciliation.items()
        }

    def _get_project(self, project_id: int) -> dict[str, Any]:
        projects = self.client.call_method(
            "project.project",
            "search_read",
            [[["id", "=", project_id]]],
            {
                "fields": ["id", "name", "allow_timesheets", "partner_id", "sale_order_id", "account_id", "active"],
                "context": {"active_test": False},
                "limit": 1,
            },
        )
        if not projects:
            raise OdooAPIError(
                f"Project {project_id} was not found.",
                model="project.project",
                method="search_read",
            )
        return projects[0]

    def _get_sale_order(self, sale_order_id: int) -> dict[str, Any]:
        orders = self.client.search_read(
            "sale.order",
            [["id", "=", sale_order_id]],
            ["id", "name", "partner_id", "currency_id", "date_order", "amount_untaxed", "amount_total", "user_id"],
            limit=1,
        )
        if not orders:
            raise OdooAPIError(
                f"Sale order {sale_order_id} was not found.",
                model="sale.order",
                method="search_read",
            )
        return orders[0]

    def _get_sale_order_lines(self, sale_order_id: int) -> list[dict[str, Any]]:
        return self.client.search_read(
            "sale.order.line",
            [["order_id", "=", sale_order_id]],
            [
                "id",
                "sequence",
                "name",
                "display_type",
                "is_downpayment",
                "product_id",
                "product_uom_qty",
                "qty_invoiced",
                "qty_to_invoice",
                "price_unit",
                "discount",
                "price_subtotal",
                "untaxed_amount_invoiced",
                "untaxed_amount_to_invoice",
            ],
        )

    def _get_product_map(self, lines: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        product_ids = sorted(
            {
                line["product_id"][0]
                for line in lines
                if line.get("product_id")
            }
        )
        if not product_ids:
            return {}

        products = self.client.search_read(
            "product.product",
            [["id", "in", product_ids]],
            ["id", "type"],
        )
        return {product["id"]: product for product in products}

    def _serialize_line(
        self,
        line: dict[str, Any],
        product_map: dict[int, dict[str, Any]],
        line_cost_map: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        quoted_net = as_decimal(line.get("price_subtotal"))
        invoiced_net = as_decimal(line.get("untaxed_amount_invoiced"))
        remaining_net = quoted_net - invoiced_net
        odoo_remaining_net = as_decimal(line.get("untaxed_amount_to_invoice"))
        drift_vs_odoo = remaining_net - odoo_remaining_net
        is_stale = abs(drift_vs_odoo) >= TWO_DECIMALS

        product_ref = line.get("product_id")
        product_id = product_ref[0] if product_ref else None
        product_type = product_map.get(product_id, {}).get("type") if product_id else None

        if line.get("is_downpayment"):
            line_kind = "downpayment"
            line_kind_label = "Downpayment"
        elif product_type == "service":
            line_kind = "service"
            line_kind_label = "Service line"
        else:
            line_kind = "non_service"
            line_kind_label = "Non-service line"

        product_type_label = PRODUCT_TYPE_LABELS.get(product_type, "Manual / Unknown")
        cost_entry = line_cost_map.get(line["id"])
        actual_cost = as_decimal(cost_entry["actual_cost"] if cost_entry else 0)
        gross_profit = quoted_net - actual_cost
        has_actual_cost = bool(cost_entry and abs(actual_cost) >= TWO_DECIMALS)

        if line_kind == "downpayment":
            cost_source_label = "No cost on downpayment"
        elif has_actual_cost:
            cost_source_label = cost_entry["source_label"]
        else:
            cost_source_label = "No allocated line cost"

        return {
            "id": line["id"],
            "sequence": line.get("sequence") or 0,
            "name": line.get("name") or "Unnamed line",
            "product": relation_name(product_ref) or "Manual line",
            "kind": line_kind,
            "kind_label": line_kind_label,
            "product_type": product_type or "manual",
            "product_type_label": product_type_label,
            "quantity": float(as_decimal(line.get("product_uom_qty"))),
            "qty_invoiced": float(as_decimal(line.get("qty_invoiced"))),
            "qty_to_invoice": float(as_decimal(line.get("qty_to_invoice"))),
            "discount": float(as_decimal(line.get("discount"))),
            "unit_price": as_money(as_decimal(line.get("price_unit"))),
            "quoted_net": as_money(quoted_net),
            "invoiced_net": as_money(invoiced_net),
            "remaining_net": as_money(remaining_net),
            "odoo_remaining_net": as_money(odoo_remaining_net),
            "drift_vs_odoo": as_money(drift_vs_odoo),
            "actual_cost": as_money(actual_cost),
            "gross_profit": as_money(gross_profit),
            "has_actual_cost": has_actual_cost,
            "cost_source": cost_entry["source"] if cost_entry else None,
            "cost_source_label": cost_source_label,
            "cost_reference": cost_entry["reference"] if cost_entry else None,
            "is_stale": is_stale,
        }

    def _build_cost_model(
        self,
        project: dict[str, Any],
        raw_lines: list[dict[str, Any]],
        product_map: dict[int, dict[str, Any]],
        profitability_costs: dict[str, Any],
    ) -> dict[str, Any]:
        accounting_pipeline = self._build_accounting_cost_pipeline(
            project,
            raw_lines,
            profitability_costs,
        )
        analytic_entries = accounting_pipeline["posted_actual_entries"]
        stock_cost_map = self._get_stock_cost_map(raw_lines)

        if analytic_entries:
            model = self._build_analytic_cost_model(raw_lines, product_map, analytic_entries, stock_cost_map)
        else:
            model = self._build_stock_only_cost_model(raw_lines, stock_cost_map)

        stock_valuation_total = sum(
            as_decimal(entry["actual_cost"])
            for entry in stock_cost_map.values()
        )
        model["summary"].update(accounting_pipeline["summary"])
        model["summary"]["stock_valuation_total"] = stock_valuation_total
        model["cost_sources"] = accounting_pipeline["cost_sources"]
        model["reconciliation"] = {
            **accounting_pipeline["reconciliation"],
            "stock_valuation_total": stock_valuation_total,
            "accounting_vs_stock_valuation_gap": (
                as_decimal(accounting_pipeline["summary"]["posted_actual_total"])
                - stock_valuation_total
            ),
        }
        return model

    def _build_accounting_cost_pipeline(
        self,
        project: dict[str, Any],
        raw_lines: list[dict[str, Any]],
        profitability_costs: dict[str, Any],
    ) -> dict[str, Any]:
        account_id = relation_id(project.get("account_id"))
        if not account_id:
            empty_summary = {
                "cost_model": "accounting_posted_plus_commitments",
                "cost_source_label": "Accounting posted + draft commitments",
                "actual_cost_total": Decimal("0"),
                "posted_actual_total": Decimal("0"),
                "draft_bill_commitment_total": Decimal("0"),
                "po_open_commitment_total": Decimal("0"),
                "open_commitment_total": Decimal("0"),
                "final_cost_total": Decimal("0"),
            }
            return {
                "posted_actual_entries": [],
                "cost_sources": [],
                "summary": empty_summary,
                "reconciliation": {
                    "accounting_actual_total": Decimal("0"),
                    "native_billed_cost_total": as_decimal(profitability_costs["billed_cost_total"]),
                    "native_expected_cost_total": as_decimal(profitability_costs["expected_cost_total"]),
                    "native_open_commitment_total": as_decimal(profitability_costs["open_commitment_total"]),
                    "draft_bill_commitment_total": Decimal("0"),
                    "po_open_commitment_total": Decimal("0"),
                    "purchase_order_open_total": Decimal("0"),
                },
            }

        posted_entries, posted_sources = self._get_posted_actual_costs(account_id)
        draft_sources = self._get_draft_bill_commitments(account_id)
        draft_purchase_line_ids = {
            source["purchase_line_id"]
            for source in draft_sources
            if source.get("purchase_line_id")
        }
        po_sources, raw_po_open_total = self._get_po_open_commitments(
            account_id,
            draft_purchase_line_ids,
        )

        posted_actual_total = sum(as_decimal(source["amount"]) for source in posted_sources)
        draft_bill_commitment_total = sum(as_decimal(source["amount"]) for source in draft_sources)
        po_open_commitment_total = sum(as_decimal(source["amount"]) for source in po_sources)
        open_commitment_total = draft_bill_commitment_total + po_open_commitment_total
        final_cost_total = posted_actual_total + open_commitment_total
        native_billed_cost_total = as_decimal(profitability_costs["billed_cost_total"])
        native_open_commitment_total = as_decimal(profitability_costs["open_commitment_total"])
        native_expected_cost_total = as_decimal(profitability_costs["expected_cost_total"])

        summary = {
            "cost_model": "accounting_posted_plus_commitments",
            "cost_source_label": "Accounting posted + draft commitments",
            "actual_cost_total": posted_actual_total,
            "posted_actual_total": posted_actual_total,
            "draft_bill_commitment_total": draft_bill_commitment_total,
            "po_open_commitment_total": po_open_commitment_total,
            "open_commitment_total": open_commitment_total,
            "final_cost_total": final_cost_total,
        }
        reconciliation = {
            "accounting_actual_total": posted_actual_total,
            "native_billed_cost_total": native_billed_cost_total,
            "native_expected_cost_total": native_expected_cost_total,
            "native_open_commitment_total": native_open_commitment_total,
            "draft_bill_commitment_total": draft_bill_commitment_total,
            "po_open_commitment_total": po_open_commitment_total,
            "purchase_order_open_total": raw_po_open_total,
            "accounting_vs_native_billed_gap": posted_actual_total - native_billed_cost_total,
            "commitment_vs_native_open_gap": open_commitment_total - native_open_commitment_total,
            "final_vs_native_expected_gap": final_cost_total - native_expected_cost_total,
        }

        cost_sources = posted_sources + draft_sources + po_sources
        cost_sources.sort(
            key=lambda source: (
                source.get("date") or "",
                source.get("reference") or "",
                source.get("id") or 0,
            ),
            reverse=True,
        )

        return {
            "posted_actual_entries": posted_entries,
            "cost_sources": cost_sources,
            "summary": summary,
            "reconciliation": reconciliation,
        }

    def _get_posted_actual_costs(self, account_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        analytic_entries = self._get_project_analytic_entries({"account_id": [account_id, ""]})
        move_line_ids = sorted(
            {
                relation_id(entry.get("move_line_id"))
                for entry in analytic_entries
                if relation_id(entry.get("move_line_id"))
            }
        )
        if not move_line_ids:
            return [], []

        move_lines = self.client.search_read(
            "account.move.line",
            [["id", "in", move_line_ids]],
            [
                "id",
                "date",
                "name",
                "move_id",
                "parent_state",
                "move_type",
                "balance",
                "product_id",
                "purchase_line_id",
            ],
            limit=len(move_line_ids),
        )
        move_line_map = {line["id"]: line for line in move_lines}
        posted_entries: list[dict[str, Any]] = []
        sources_by_move_line: dict[int, dict[str, Any]] = {}
        processed_move_line_ids: set[int] = set()

        for analytic_entry in analytic_entries:
            move_line_id = relation_id(analytic_entry.get("move_line_id"))
            move_line = move_line_map.get(move_line_id)
            if not move_line or move_line.get("parent_state") != "posted":
                continue
            if move_line["id"] in processed_move_line_ids:
                continue
            if move_line.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
                continue

            amount = as_decimal(move_line.get("balance"))
            if abs(amount) < TWO_DECIMALS:
                continue
            processed_move_line_ids.add(move_line["id"])

            posted_entry = {
                **analytic_entry,
                "amount": -amount,
                "product_id": move_line.get("product_id") or analytic_entry.get("product_id"),
                "move_line_id": analytic_entry.get("move_line_id") or [move_line["id"], move_line.get("name")],
            }
            posted_entries.append(posted_entry)

            source = sources_by_move_line.setdefault(
                move_line["id"],
                {
                    "id": move_line["id"],
                    "source": "posted_actual_cost",
                    "source_label": "Posted actual cost",
                    "state": "posted",
                    "amount": Decimal("0"),
                    "product": relation_name(move_line.get("product_id"))
                    or relation_name(analytic_entry.get("product_id")),
                    "reference": relation_name(move_line.get("move_id"))
                    or relation_name(analytic_entry.get("move_line_id")),
                    "label": move_line.get("name") or analytic_entry.get("name") or "Posted cost",
                    "date": move_line.get("date") or analytic_entry.get("date"),
                    "purchase_line_id": relation_id(move_line.get("purchase_line_id")),
                },
            )
            source["amount"] += amount

        return posted_entries, list(sources_by_move_line.values())

    def _get_draft_bill_commitments(self, account_id: int) -> list[dict[str, Any]]:
        try:
            lines = self.client.search_read(
                "account.move.line",
                [
                    ["parent_state", "=", "draft"],
                    ["move_type", "in", ["in_invoice", "in_refund", "in_receipt"]],
                    ["analytic_distribution", "ilike", str(account_id)],
                ],
                [
                    "id",
                    "date",
                    "name",
                    "move_id",
                    "parent_state",
                    "move_type",
                    "balance",
                    "product_id",
                    "purchase_line_id",
                    "analytic_distribution",
                ],
                limit=1000,
            )
        except OdooAPIError:
            return []
        sources: list[dict[str, Any]] = []
        for line in lines:
            if not self._analytic_distribution_matches(line.get("analytic_distribution"), account_id):
                continue
            amount = as_decimal(line.get("balance"))
            if abs(amount) < TWO_DECIMALS:
                continue
            sources.append(
                {
                    "id": line["id"],
                    "source": "draft_bill_commitment",
                    "source_label": "Draft vendor bill commitment",
                    "state": "draft",
                    "amount": amount,
                    "product": relation_name(line.get("product_id")),
                    "reference": relation_name(line.get("move_id")),
                    "label": line.get("name") or "Draft vendor bill line",
                    "date": line.get("date"),
                    "purchase_line_id": relation_id(line.get("purchase_line_id")),
                }
            )
        return sources

    def _get_po_open_commitments(
        self,
        account_id: int,
        excluded_purchase_line_ids: set[int],
    ) -> tuple[list[dict[str, Any]], Decimal]:
        try:
            lines = self.client.search_read(
                "purchase.order.line",
                [
                    ["order_id.state", "in", ["purchase", "done"]],
                    ["analytic_distribution", "ilike", str(account_id)],
                ],
                [
                    "id",
                    "name",
                    "order_id",
                    "product_id",
                    "product_qty",
                    "qty_invoiced",
                    "price_subtotal",
                    "currency_id",
                    "company_id",
                    "date_planned",
                    "analytic_distribution",
                ],
                limit=1000,
            )
        except OdooAPIError:
            return [], Decimal("0")
        sources: list[dict[str, Any]] = []
        raw_open_total = Decimal("0")
        for line in lines:
            if line["id"] in excluded_purchase_line_ids:
                continue
            if not self._analytic_distribution_matches(line.get("analytic_distribution"), account_id):
                continue

            product_qty = as_decimal(line.get("product_qty"))
            qty_invoiced = as_decimal(line.get("qty_invoiced"))
            open_qty = product_qty - qty_invoiced
            if product_qty <= 0 or open_qty <= 0:
                continue

            raw_amount = as_decimal(line.get("price_subtotal")) * open_qty / product_qty
            raw_open_total += raw_amount
            company_id = relation_id(line.get("company_id"))
            currency_id = relation_id(line.get("currency_id"))
            amount = self._convert_to_company_currency(
                raw_amount,
                currency_id,
                company_id,
                line.get("date_planned"),
            )
            if amount is None or abs(amount) < TWO_DECIMALS:
                continue

            sources.append(
                {
                    "id": line["id"],
                    "source": "po_open_commitment",
                    "source_label": "PO open commitment",
                    "state": "purchase",
                    "amount": amount,
                    "product": relation_name(line.get("product_id")),
                    "reference": relation_name(line.get("order_id")),
                    "label": line.get("name") or "Purchase order line",
                    "date": line.get("date_planned"),
                    "purchase_line_id": line["id"],
                    "raw_amount": raw_amount,
                    "raw_currency": relation_name(line.get("currency_id")),
                }
            )
        return sources, raw_open_total

    def _analytic_distribution_matches(self, distribution: Any, account_id: int) -> bool:
        if not distribution:
            return False
        if isinstance(distribution, dict):
            return any(
                account_id in self._parse_analytic_account_ids(key)
                for key in distribution
            )
        return account_id in self._parse_analytic_account_ids(distribution)

    def _convert_to_company_currency(
        self,
        amount: Decimal,
        currency_id: int | None,
        company_id: int | None,
        date: str | None,
    ) -> Decimal | None:
        if not currency_id or not company_id:
            return amount

        company_currency_id = self._get_company_currency_id(company_id)
        if not company_currency_id or company_currency_id == currency_id:
            return amount

        try:
            converted = self.client.call_method(
                "res.currency",
                "_convert",
                [[currency_id], float(amount), company_currency_id, company_id, date or datetime.now().date().isoformat(), True],
            )
        except OdooAPIError:
            return None
        return as_decimal(converted)

    def _get_company_currency_id(self, company_id: int) -> int | None:
        companies = self.client.search_read(
            "res.company",
            [["id", "=", company_id]],
            ["currency_id"],
            limit=1,
        )
        if not companies:
            return None
        return relation_id(companies[0].get("currency_id"))

    def _get_project_analytic_entries(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        account_id = relation_id(project.get("account_id"))
        if not account_id:
            return []

        entries = self.client.search_read(
            "account.analytic.line",
            [["account_id", "=", account_id]],
            ["id", "date", "name", "amount", "product_id", "move_line_id", "category"],
            limit=1000,
        )
        return [
            entry
            for entry in entries
            if entry.get("category") != "invoice" and as_decimal(entry.get("amount")) != 0
        ]

    def _build_analytic_cost_model(
        self,
        raw_lines: list[dict[str, Any]],
        product_map: dict[int, dict[str, Any]],
        analytic_entries: list[dict[str, Any]],
        stock_cost_map: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        sale_lines = [line for line in raw_lines if not line.get("display_type")]
        product_to_line_ids: dict[int, list[int]] = defaultdict(list)
        for line in sale_lines:
            if line.get("is_downpayment") or not line.get("product_id"):
                continue
            product_to_line_ids[line["product_id"][0]].append(line["id"])

        line_cost_map: dict[int, dict[str, Any]] = {}
        allocated_entry_ids: set[int] = set()
        exact_match_line_ids: set[int] = set()

        for entry in analytic_entries:
            product_ref = entry.get("product_id")
            if not product_ref:
                continue

            candidate_line_ids = product_to_line_ids.get(product_ref[0], [])
            if len(candidate_line_ids) != 1:
                continue

            line_id = candidate_line_ids[0]
            self._add_line_cost(
                line_cost_map,
                line_id,
                -as_decimal(entry.get("amount")),
                source="analytic_account",
                source_label="Exact product match",
                reference=relation_name(entry.get("move_line_id")),
            )
            allocated_entry_ids.add(entry["id"])
            exact_match_line_ids.add(line_id)

        primary_service_line_id = self._pick_primary_service_line_id(sale_lines, product_map)
        material_targets = self._build_material_allocation_targets(sale_lines, line_cost_map, product_map)

        for entry in analytic_entries:
            if entry["id"] in allocated_entry_ids:
                continue

            bucket = self._classify_project_cost_entry(entry)
            cost_amount = -as_decimal(entry.get("amount"))
            reference = relation_name(entry.get("move_line_id"))

            if bucket == "service_operations" and primary_service_line_id:
                self._add_line_cost(
                    line_cost_map,
                    primary_service_line_id,
                    cost_amount,
                    source="analytic_rule",
                    source_label="Service operations allocation",
                    reference=reference,
                )
                allocated_entry_ids.add(entry["id"])
                continue

            if bucket == "material_logistics" and material_targets:
                self._allocate_proportionally(
                    line_cost_map,
                    material_targets,
                    cost_amount,
                    source="analytic_rule",
                    source_label="Material logistics allocation",
                    reference=reference,
                )
                allocated_entry_ids.add(entry["id"])

        for line_id, stock_entry in stock_cost_map.items():
            if line_id in exact_match_line_ids:
                continue
            self._add_line_cost(
                line_cost_map,
                line_id,
                stock_entry["actual_cost"],
                source="stock_valuation",
                source_label="Stock valuation fallback",
                reference=stock_entry["reference"],
            )

        self._finalize_line_cost_map(line_cost_map)

        project_cost_entries = self._aggregate_project_cost_entries([
            entry
            for entry in analytic_entries
            if entry["id"] not in allocated_entry_ids
        ])

        quoted_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
        )
        allocated_cost_total = sum(
            as_decimal(entry["actual_cost"])
            for entry in line_cost_map.values()
        )
        actual_cost_total = -sum(
            as_decimal(entry.get("amount"))
            for entry in analytic_entries
        )
        project_extra_cost_total = sum(
            as_decimal(entry["amount"])
            for entry in project_cost_entries
        )
        costed_revenue_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
            if line_cost_map.get(line["id"])
        )
        unmapped_revenue_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
            if not line_cost_map.get(line["id"])
            and not line.get("is_downpayment")
            and as_decimal(line.get("price_subtotal")) > 0
        )
        costed_line_count = sum(
            1
            for line in sale_lines
            if line_cost_map.get(line["id"]) and as_decimal(line.get("price_subtotal")) > 0
        )
        unmapped_line_count = sum(
            1
            for line in sale_lines
            if not line_cost_map.get(line["id"])
            and not line.get("is_downpayment")
            and as_decimal(line.get("price_subtotal")) > 0
        )
        coverage_percent = Decimal("0")
        if quoted_total:
            coverage_percent = (costed_revenue_total / quoted_total) * Decimal("100")

        return {
            "line_cost_map": line_cost_map,
            "project_cost_entries": project_cost_entries,
            "summary": {
                "cost_model": "analytic_account",
                "cost_source_label": "Project analytic account",
                "actual_cost_total": actual_cost_total,
                "allocated_cost_total": allocated_cost_total,
                "project_extra_cost_total": project_extra_cost_total,
                "project_extra_cost_count": len(project_cost_entries),
                "costed_revenue_total": costed_revenue_total,
                "unmapped_revenue_total": unmapped_revenue_total,
                "costed_line_count": costed_line_count,
                "unmapped_line_count": unmapped_line_count,
                "cost_coverage_percent": coverage_percent,
            },
        }

    def _aggregate_project_cost_entries(
        self,
        analytic_entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        aggregates: dict[str, dict[str, Any]] = {}

        for entry in analytic_entries:
            signed_amount = as_decimal(entry.get("amount"))
            cost_amount = -signed_amount
            if abs(cost_amount) < TWO_DECIMALS:
                continue

            move_line_ref = entry.get("move_line_id")
            key = str(relation_id(move_line_ref) or entry["id"])
            aggregate = aggregates.setdefault(
                key,
                {
                    "amount": Decimal("0"),
                    "source": "analytic_account",
                    "source_label": "Project-level analytic cost",
                    "category": entry.get("category") or "other",
                    "label": entry.get("name") or relation_name(entry.get("product_id")) or "Unnamed cost",
                    "product": relation_name(entry.get("product_id")),
                    "reference": relation_name(move_line_ref),
                    "date": entry.get("date"),
                },
            )
            aggregate["amount"] += cost_amount

        project_cost_entries = []
        for entry in aggregates.values():
            if abs(entry["amount"]) < TWO_DECIMALS:
                continue
            project_cost_entries.append(
                {
                    **entry,
                    "amount": as_money(entry["amount"]),
                }
            )

        project_cost_entries.sort(key=lambda entry: abs(entry["amount"]), reverse=True)
        return project_cost_entries

    def _pick_primary_service_line_id(
        self,
        sale_lines: list[dict[str, Any]],
        product_map: dict[int, dict[str, Any]],
    ) -> int | None:
        candidates = []
        for line in sale_lines:
            if line.get("is_downpayment") or not line.get("product_id"):
                continue
            product_type = product_map.get(line["product_id"][0], {}).get("type")
            quoted_net = as_decimal(line.get("price_subtotal"))
            if product_type == "service" and quoted_net > 0:
                candidates.append((quoted_net, line["id"]))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        return candidates[0][1]

    def _build_material_allocation_targets(
        self,
        sale_lines: list[dict[str, Any]],
        line_cost_map: dict[int, dict[str, Any]],
        product_map: dict[int, dict[str, Any]],
    ) -> list[tuple[int, Decimal]]:
        targets: list[tuple[int, Decimal]] = []
        for line in sale_lines:
            if line.get("is_downpayment") or not line.get("product_id"):
                continue

            quoted_net = as_decimal(line.get("price_subtotal"))
            if quoted_net <= 0:
                continue

            product_type = product_map.get(line["product_id"][0], {}).get("type")
            if product_type == "service":
                continue

            existing_cost = as_decimal(line_cost_map.get(line["id"], {}).get("actual_cost", 0))
            weight = existing_cost if abs(existing_cost) >= TWO_DECIMALS else quoted_net
            if weight > 0:
                targets.append((line["id"], weight))

        return targets

    def _classify_project_cost_entry(self, entry: dict[str, Any]) -> str:
        text = self._normalize_cost_text(entry)

        if any(keyword in text for keyword in MATERIAL_LOGISTICS_KEYWORDS):
            return "material_logistics"
        if any(keyword in text for keyword in SERVICE_OPERATION_KEYWORDS):
            return "service_operations"
        return "unallocated"

    def _normalize_cost_text(self, entry: dict[str, Any]) -> str:
        parts = [
            entry.get("name") or "",
            relation_name(entry.get("product_id")) or "",
            relation_name(entry.get("move_line_id")) or "",
            entry.get("category") or "",
        ]
        return " ".join(parts).lower()

    def _add_line_cost(
        self,
        line_cost_map: dict[int, dict[str, Any]],
        line_id: int,
        cost_amount: Decimal,
        *,
        source: str,
        source_label: str,
        reference: str | None,
    ) -> None:
        if abs(cost_amount) < TWO_DECIMALS:
            return

        entry = line_cost_map.setdefault(
            line_id,
            {
                "actual_cost": Decimal("0"),
                "references": set(),
                "source_labels": [],
                "source_tokens": set(),
            },
        )
        entry["actual_cost"] += cost_amount
        if reference:
            entry["references"].add(reference)
        if source_label not in entry["source_labels"]:
            entry["source_labels"].append(source_label)
        entry["source_tokens"].add(source)

    def _allocate_proportionally(
        self,
        line_cost_map: dict[int, dict[str, Any]],
        targets: list[tuple[int, Decimal]],
        total_amount: Decimal,
        *,
        source: str,
        source_label: str,
        reference: str | None,
    ) -> None:
        if not targets or abs(total_amount) < TWO_DECIMALS:
            return

        total_weight = sum(weight for _, weight in targets)
        if total_weight <= 0:
            return

        remaining = total_amount
        sorted_targets = sorted(targets, key=lambda item: item[1], reverse=True)
        for index, (line_id, weight) in enumerate(sorted_targets):
            if index == len(sorted_targets) - 1:
                share = remaining
            else:
                share = (total_amount * weight / total_weight).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
                remaining -= share

            self._add_line_cost(
                line_cost_map,
                line_id,
                share,
                source=source,
                source_label=source_label,
                reference=reference,
            )

    def _finalize_line_cost_map(self, line_cost_map: dict[int, dict[str, Any]]) -> None:
        for entry in line_cost_map.values():
            entry["reference"] = ", ".join(sorted(entry.pop("references", set())))
            entry["source_label"] = " + ".join(entry.pop("source_labels", []))
            entry["source"] = ",".join(sorted(entry.pop("source_tokens", set())))

    def _build_stock_only_cost_model(
        self,
        raw_lines: list[dict[str, Any]],
        stock_cost_map: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        sale_lines = [line for line in raw_lines if not line.get("display_type")]
        line_cost_map = {
            line_id: {
                "actual_cost": entry["actual_cost"],
                "reference": entry["reference"],
                "source": "stock_valuation",
                "source_label": "Stock valuation",
            }
            for line_id, entry in stock_cost_map.items()
        }

        quoted_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
        )
        actual_cost_total = sum(
            as_decimal(entry["actual_cost"])
            for entry in line_cost_map.values()
        )
        costed_revenue_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
            if line_cost_map.get(line["id"])
        )
        unmapped_revenue_total = sum(
            as_decimal(line.get("price_subtotal"))
            for line in sale_lines
            if not line_cost_map.get(line["id"])
            and not line.get("is_downpayment")
            and as_decimal(line.get("price_subtotal")) > 0
        )
        coverage_percent = Decimal("0")
        if quoted_total:
            coverage_percent = (costed_revenue_total / quoted_total) * Decimal("100")

        return {
            "line_cost_map": line_cost_map,
            "project_cost_entries": [],
            "summary": {
                "cost_model": "stock_valuation_fallback",
                "cost_source_label": "Stock valuation fallback",
                "actual_cost_total": actual_cost_total,
                "allocated_cost_total": actual_cost_total,
                "project_extra_cost_total": Decimal("0"),
                "project_extra_cost_count": 0,
                "costed_revenue_total": costed_revenue_total,
                "unmapped_revenue_total": unmapped_revenue_total,
                "costed_line_count": sum(
                    1
                    for line in sale_lines
                    if line_cost_map.get(line["id"]) and as_decimal(line.get("price_subtotal")) > 0
                ),
                "unmapped_line_count": sum(
                    1
                    for line in sale_lines
                    if not line_cost_map.get(line["id"])
                    and not line.get("is_downpayment")
                    and as_decimal(line.get("price_subtotal")) > 0
                ),
                "cost_coverage_percent": coverage_percent,
            },
        }

    def _get_stock_cost_map(self, raw_lines: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        sale_line_ids = [
            line["id"]
            for line in raw_lines
            if not line.get("display_type")
        ]
        if not sale_line_ids:
            return {}

        moves = self.client.search_read(
            "stock.move",
            [["sale_line_id", "in", sale_line_ids], ["state", "=", "done"]],
            ["id", "sale_line_id", "picking_id", "stock_valuation_layer_ids"],
            limit=500,
        )
        if not moves:
            return {}

        svl_ids = sorted(
            {
                svl_id
                for move in moves
                for svl_id in (move.get("stock_valuation_layer_ids") or [])
            }
        )
        if not svl_ids:
            return {}

        layers = self.client.search_read(
            "stock.valuation.layer",
            [["id", "in", svl_ids]],
            ["id", "stock_move_id", "value", "description"],
            limit=1000,
        )

        moves_by_id = {move["id"]: move for move in moves}
        cost_map: dict[int, dict[str, Any]] = {}

        for layer in layers:
            move_ref = layer.get("stock_move_id")
            if not move_ref:
                continue

            move = moves_by_id.get(move_ref[0])
            sale_line_ref = move.get("sale_line_id") if move else None
            if not sale_line_ref:
                continue

            sale_line_id = sale_line_ref[0]
            entry = cost_map.setdefault(
                sale_line_id,
                {
                    "actual_cost": Decimal("0"),
                    "references": set(),
                },
            )
            entry["actual_cost"] += as_decimal(abs(layer.get("value") or 0))

            if move.get("picking_id"):
                entry["references"].add(move["picking_id"][1])
            elif layer.get("description"):
                entry["references"].add(layer["description"])

        for entry in cost_map.values():
            entry["reference"] = ", ".join(sorted(entry.pop("references")))

        return cost_map

    def _build_line_groups(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Decimal | int | str]] = defaultdict(
            lambda: {
                "quoted_net": Decimal("0"),
                "invoiced_net": Decimal("0"),
                "remaining_net": Decimal("0"),
                "actual_cost": Decimal("0"),
                "gross_profit": Decimal("0"),
                "count": 0,
                "costed_count": 0,
            }
        )

        for line in lines:
            group = buckets[line["kind"]]
            group["quoted_net"] += as_decimal(line["quoted_net"])
            group["invoiced_net"] += as_decimal(line["invoiced_net"])
            group["remaining_net"] += as_decimal(line["remaining_net"])
            group["actual_cost"] += as_decimal(line["actual_cost"])
            group["gross_profit"] += as_decimal(line["gross_profit"])
            group["count"] += 1
            if line["has_actual_cost"]:
                group["costed_count"] += 1

        labels = {
            "service": "Service lines",
            "non_service": "Non-service lines",
            "downpayment": "Downpayments",
        }

        groups = []
        for key in ["service", "non_service", "downpayment"]:
            if key not in buckets:
                continue
            group = buckets[key]
            groups.append(
                {
                    "key": key,
                    "label": labels[key],
                    "count": int(group["count"]),
                    "costed_count": int(group["costed_count"]),
                    "quoted_net": as_money(group["quoted_net"]),
                    "invoiced_net": as_money(group["invoiced_net"]),
                    "remaining_net": as_money(group["remaining_net"]),
                    "actual_cost": as_money(group["actual_cost"]),
                    "gross_profit": as_money(group["gross_profit"]),
                }
            )

        return groups

    def _build_summary(
        self,
        sale_order: dict[str, Any],
        lines: list[dict[str, Any]],
        line_groups: list[dict[str, Any]],
        cost_summary: dict[str, Any],
        profitability_costs: dict[str, Decimal | dict[str, dict[str, Decimal]]],
    ) -> dict[str, Any]:
        quoted_total = sum(as_decimal(line["quoted_net"]) for line in lines)
        invoiced_total = sum(as_decimal(line["invoiced_net"]) for line in lines)
        remaining_total = sum(as_decimal(line["remaining_net"]) for line in lines)
        odoo_remaining_total = sum(as_decimal(line["odoo_remaining_net"]) for line in lines)
        drift_total = sum(as_decimal(line["drift_vs_odoo"]) for line in lines)
        stale_line_count = sum(1 for line in lines if line["is_stale"])
        allocated_cost_total = as_decimal(cost_summary["allocated_cost_total"])
        actual_cost_total = as_decimal(cost_summary["actual_cost_total"])
        posted_actual_total = as_decimal(cost_summary["posted_actual_total"])
        project_extra_cost_total = as_decimal(cost_summary["project_extra_cost_total"])
        draft_bill_commitment_total = as_decimal(cost_summary["draft_bill_commitment_total"])
        po_open_commitment_total = as_decimal(cost_summary["po_open_commitment_total"])
        open_commitment_total = as_decimal(cost_summary["open_commitment_total"])
        final_cost_total = as_decimal(cost_summary["final_cost_total"])
        expected_cost_total = as_decimal(profitability_costs["expected_cost_total"])
        native_billed_cost_total = as_decimal(profitability_costs["billed_cost_total"])
        direct_profit_total = quoted_total - allocated_cost_total
        gross_profit_total = quoted_total - actual_cost_total
        final_profit_total = quoted_total - final_cost_total
        costed_revenue_total = as_decimal(cost_summary["costed_revenue_total"])
        unmapped_revenue_total = as_decimal(cost_summary["unmapped_revenue_total"])
        costed_line_count = int(cost_summary["costed_line_count"])
        unmapped_line_count = int(cost_summary["unmapped_line_count"])
        order_untaxed = as_decimal(sale_order.get("amount_untaxed"))
        order_total = as_decimal(sale_order.get("amount_total"))
        progress = Decimal("0")
        margin_percent = Decimal("0")
        roi_percent = Decimal("0")
        final_margin_percent = Decimal("0")
        final_roi_percent = Decimal("0")
        coverage_percent = as_decimal(cost_summary["cost_coverage_percent"])
        if quoted_total:
            progress = (invoiced_total / quoted_total) * Decimal("100")
            margin_percent = (gross_profit_total / quoted_total) * Decimal("100")
            final_margin_percent = (final_profit_total / quoted_total) * Decimal("100")
        if actual_cost_total:
            roi_percent = (gross_profit_total / actual_cost_total) * Decimal("100")
        if final_cost_total:
            final_roi_percent = (final_profit_total / final_cost_total) * Decimal("100")

        breakdown = {group["key"]: group for group in line_groups}

        return {
            "quoted_total_untaxed": as_money(quoted_total),
            "order_amount_untaxed": as_money(order_untaxed),
            "order_amount_total": as_money(order_total),
            "line_total_delta_vs_order": as_money(quoted_total - order_untaxed),
            "invoiced_total_untaxed": as_money(invoiced_total),
            "remaining_total_untaxed": as_money(remaining_total),
            "odoo_remaining_total_untaxed": as_money(odoo_remaining_total),
            "remaining_delta_vs_odoo": as_money(drift_total),
            "invoice_progress_percent": as_money(progress),
            "actual_cost_total": as_money(actual_cost_total),
            "posted_actual_total": as_money(posted_actual_total),
            "draft_bill_commitment_total": as_money(draft_bill_commitment_total),
            "po_open_commitment_total": as_money(po_open_commitment_total),
            "open_commitment_total": as_money(open_commitment_total),
            "final_cost_total": as_money(final_cost_total),
            "native_expected_cost_total": as_money(expected_cost_total),
            "native_billed_cost_total": as_money(native_billed_cost_total),
            "actual_vs_native_billed_cost_gap": as_money(actual_cost_total - native_billed_cost_total),
            "expected_vs_actual_cost_gap": as_money(expected_cost_total - actual_cost_total),
            "final_vs_native_expected_cost_gap": as_money(final_cost_total - expected_cost_total),
            "allocated_cost_total": as_money(allocated_cost_total),
            "project_extra_cost_total": as_money(project_extra_cost_total),
            "project_extra_cost_count": int(cost_summary["project_extra_cost_count"]),
            "direct_profit_total": as_money(direct_profit_total),
            "gross_profit_total": as_money(gross_profit_total),
            "final_profit_total": as_money(final_profit_total),
            "margin_percent": as_money(margin_percent),
            "roi_percent": as_money(roi_percent),
            "final_margin_percent": as_money(final_margin_percent),
            "final_roi_percent": as_money(final_roi_percent),
            "cost_coverage_percent": as_money(coverage_percent),
            "costed_revenue_total": as_money(costed_revenue_total),
            "unmapped_revenue_total": as_money(unmapped_revenue_total),
            "cost_model": cost_summary["cost_model"],
            "cost_source_label": cost_summary["cost_source_label"],
            "line_count": len(lines),
            "stale_line_count": stale_line_count,
            "costed_line_count": costed_line_count,
            "unmapped_line_count": unmapped_line_count,
            "service_line_count": breakdown.get("service", {}).get("count", 0),
            "service_quoted_total": breakdown.get("service", {}).get("quoted_net", 0),
            "service_invoiced_total": breakdown.get("service", {}).get("invoiced_net", 0),
            "service_remaining_total": breakdown.get("service", {}).get("remaining_net", 0),
            "service_actual_cost": breakdown.get("service", {}).get("actual_cost", 0),
            "non_service_line_count": breakdown.get("non_service", {}).get("count", 0),
            "non_service_quoted_total": breakdown.get("non_service", {}).get("quoted_net", 0),
            "non_service_invoiced_total": breakdown.get("non_service", {}).get("invoiced_net", 0),
            "non_service_remaining_total": breakdown.get("non_service", {}).get("remaining_net", 0),
            "non_service_actual_cost": breakdown.get("non_service", {}).get("actual_cost", 0),
            "downpayment_total": breakdown.get("downpayment", {}).get("quoted_net", 0),
        }

    def _build_alerts(self, project: dict[str, Any], summary: dict[str, Any]) -> list[str]:
        alerts: list[str] = []

        if summary["service_line_count"]:
            alerts.append(
                f"This dashboard includes {summary['service_line_count']} service line(s) from raw Odoo sale.order.line data, totaling {summary['service_quoted_total']:,.2f} untaxed."
            )

        if summary["actual_cost_total"]:
            alerts.append(
                f"Read-only {summary['cost_source_label'].lower()} found {summary['actual_cost_total']:,.2f} total cost. {summary['allocated_cost_total']:,.2f} is allocated directly to BG lines and {summary['project_extra_cost_total']:,.2f} remains as project-level cost."
            )

        if summary["actual_cost_total"] and summary["project_extra_cost_count"] == 0 and summary["unmapped_line_count"] == 0:
            alerts.append(
                "All meaningful revenue lines in this project now have a final cost allocation under the current read-only ruleset."
            )

        if summary["unmapped_line_count"]:
            alerts.append(
                f"{summary['unmapped_line_count']} revenue line(s), totaling {summary['unmapped_revenue_total']:,.2f}, still have no direct line allocation. Their cost, if present, stays in project-level cost until a safe mapping rule exists."
            )

        if summary["project_extra_cost_count"]:
            alerts.append(
                f"{summary['project_extra_cost_count']} project-level cost entries are tracked separately from BG lines so the project total stays accurate without forcing unsafe allocations."
            )

        if summary["stale_line_count"]:
            alerts.append(
                f"Detected {summary['stale_line_count']} line(s) where Odoo remaining revenue differs from the BG line calculation. "
                "This dashboard uses BG line totals as the source of truth."
            )

        if not project.get("allow_timesheets"):
            alerts.append(
                "Project has Allow Timesheets disabled. Native Odoo profitability may hide service revenue, but this dashboard still counts service lines directly from raw Odoo data."
            )

        if abs(summary["line_total_delta_vs_order"]) >= 0.01:
            alerts.append(
                "The sum of BG lines does not exactly match sale order untaxed total. Review manual rounding or custom lines before using this dashboard as the final source."
            )

        return alerts
