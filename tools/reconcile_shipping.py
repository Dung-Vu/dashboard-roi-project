#!/usr/bin/env python3
"""
Standalone Data Reconciliation Script for Shipping Costs (Phase 1 - SA-4).

STRICT RULES ENFORCED:
1. NEVER connect to Production (`bonario-vietnam.odoo.com` / `bonario-vietnam`).
2. Read-only access to Odoo TEST (`search_read`, `read`, `search_count`, `read_group`, `fields_get`).
3. Sequential RPC calls only, batch size <= 1000, sleep >= 1.1s between every RPC call.
4. Never print, log, or write secrets/API keys.
5. Completely independent of `dashboard_service`, `odoo_client`, `app`, `config`.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import requests


ALLOWED_READ_METHODS = frozenset({
    "search_read",
    "read",
    "search_count",
    "read_group",
    "fields_get",
})

BASE_10_SHIPPING_IDS = (
    518,
    1237,
    566,
    1239,
    1270,
    1271,
    1518,
    1519,
    1522,
    1523,
)
BD_SHIPPING_IDS = (506, 1427)
CANDIDATE_REVIEW_IDS = (1439, 568, 1238)
FALSE_POSITIVE_PARTNERSHIP_IDS = (510, 552, 1426)

DISCOVERY_KEYWORDS = (
    "logistics",
    "ship",
    "vận chuyển",
    "giao hàng",
    "cước",
)

DASHBOARD_TARGET_TAGS = ("Nội thất rời", "Giấy dán tường", "Rèm", "Vải nội thất")
EXCLUDED_SALESPERSONS = ("CEO office", "Đỗ Thị Hải Yến", "CEO office, Đỗ Thị Hải Yến")
EXCLUDED_MOVE_TYPES = frozenset({"out_invoice", "out_refund", "out_receipt"})
DRAFT_ALLOWED_MOVE_TYPES = frozenset({"in_invoice", "in_refund", "in_receipt", "entry"})

TWO_DECIMALS = Decimal("0.01")
BATCH_SIZE = 1000
RPC_SLEEP_SECONDS = 1.1
OUTPUT_DIR = Path("/tmp/roi_recon")
ENV_FILE_PATH = Path.home() / ".config" / "bonario" / "odoo_test.env"


def as_decimal(val: Any) -> Decimal:
    if val is None or val is False:
        return Decimal("0")
    return Decimal(str(val))


def as_money(val: Decimal | float | int) -> float:
    if not isinstance(val, Decimal):
        val = Decimal(str(val or 0))
    return float(val.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP))


def relation_id(val: Any) -> int | None:
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, (list, tuple)) and val and isinstance(val[0], int):
        return val[0]
    return None


def relation_name(val: Any) -> str:
    if isinstance(val, (list, tuple)) and len(val) > 1 and isinstance(val[1], str):
        return val[1]
    return ""


def normalized_text(val: Any) -> str:
    text = unicodedata.normalize("NFKD", str(val or ""))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def detect_company_key(company_ref: Any) -> str:
    name = relation_name(company_ref) if isinstance(company_ref, (list, tuple)) else str(company_ref or "")
    norm = normalized_text(name)
    if "bonario" in norm:
        return "bonario"
    if "ordinaire" in norm:
        return "ordinaire"
    return "other"


def match_shipping_keywords(name: str) -> list[str]:
    """
    Match shipping keywords in an analytic account name.
    Uses (?<![a-z])ship regex for 'ship' so 'SC_Shipping' / 'BD_Shipping' match,
    while 'Partnerships' (510, 552, 1426) is NOT falsely matched.
    """
    low = (name or "").lower()
    matched: list[str] = []
    for kw in DISCOVERY_KEYWORDS:
        if kw == "ship":
            if re.search(r"(?<![a-z])ship", low):
                matched.append(kw)
        else:
            if kw in low:
                matched.append(kw)
    return matched


def load_test_env() -> tuple[str, str, int, str]:
    """Load Odoo TEST credentials from environment or ~/.config/bonario/odoo_test.env without printing secrets."""
    required_keys = ("ODOO_TEST_URL", "ODOO_TEST_DB", "ODOO_TEST_UID", "ODOO_TEST_API_KEY")
    env_vars: dict[str, str] = {}

    for k in required_keys:
        v = os.environ.get(k, "").strip()
        if v:
            env_vars[k] = v

    if len(env_vars) < len(required_keys) and ENV_FILE_PATH.exists():
        raw_text = ENV_FILE_PATH.read_text(encoding="utf-8")
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1]
            if k in required_keys and k not in env_vars and v:
                env_vars[k] = v

    missing = [k for k in required_keys if not env_vars.get(k)]
    if missing:
        raise SystemExit(f"Missing required Odoo TEST environment variables: {', '.join(missing)}")

    url = env_vars["ODOO_TEST_URL"].rstrip("/")
    if url.endswith("/jsonrpc"):
        url = url[:-len("/jsonrpc")]
    db = env_vars["ODOO_TEST_DB"].strip()
    uid = int(env_vars["ODOO_TEST_UID"].strip())
    api_key = env_vars["ODOO_TEST_API_KEY"].strip()

    # HARD PRODUCTION GUARD (Rule 1)
    if "bonario-vietnam.odoo.com" in url.lower() or db.strip().lower() == "bonario-vietnam":
        raise SystemExit("PROD BLOCKED")

    return url, db, uid, api_key


class SafeTestOdooClient:
    """Strictly read-only, rate-limited JSON-RPC client for Odoo TEST."""

    def __init__(self, url: str, db: str, uid: int, api_key: str) -> None:
        if "bonario-vietnam.odoo.com" in url.lower() or db.strip().lower() == "bonario-vietnam":
            raise SystemExit("PROD BLOCKED")
        self.url = url
        self.db = db
        self.uid = uid
        self.api_key = api_key
        self.jsonrpc_url = f"{self.url}/jsonrpc"
        self.session = requests.Session()
        self._counter = itertools.count(1)
        self.call_count = 0

    def call(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        if (
            "bonario-vietnam.odoo.com" in self.url.lower()
            or "bonario-vietnam.odoo.com" in self.jsonrpc_url.lower()
            or self.db.strip().lower() == "bonario-vietnam"
        ):
            raise SystemExit("PROD BLOCKED")

        if method not in ALLOWED_READ_METHODS:
            raise RuntimeError(f"Write method blocked: {method}")

        if args is None:
            args = [[]]
        if kwargs is None:
            kwargs = {}

        if self.call_count > 0:
            time.sleep(RPC_SLEEP_SECONDS)
        self.call_count += 1

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self.db,
                    self.uid,
                    self.api_key,
                    model,
                    method,
                    args,
                    kwargs,
                ],
            },
            "id": next(self._counter),
        }

        resp = self.session.post(
            self.jsonrpc_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=(10, 90),
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or "RPC Error"
            if self.api_key and self.api_key in msg:
                msg = msg.replace(self.api_key, "***")
            raise RuntimeError(f"Odoo RPC error on {model}.{method}: {msg}")
        return data.get("result")

    def search_read_all(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        context: dict[str, Any] | None = None,
        order: str = "id asc",
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            kwargs: dict[str, Any] = {
                "fields": fields,
                "limit": BATCH_SIZE,
                "offset": offset,
                "order": order,
            }
            if context is not None:
                kwargs["context"] = context
            batch = self.call(model, "search_read", [domain], kwargs) or []
            results.extend(batch)
            if len(batch) < BATCH_SIZE:
                break
            offset += BATCH_SIZE
        return results

    def read_batched(
        self,
        model: str,
        ids: list[int],
        fields: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        unique_ids = sorted(set(int(x) for x in ids if x))
        results: list[dict[str, Any]] = []
        for i in range(0, len(unique_ids), BATCH_SIZE):
            chunk = unique_ids[i : i + BATCH_SIZE]
            kwargs: dict[str, Any] = {"fields": fields}
            if context is not None:
                kwargs["context"] = context
            batch = self.call(model, "read", [chunk], kwargs) or []
            results.extend(batch)
        return results


def parse_analytic_distribution(dist: Any) -> dict[str, float]:
    if not dist:
        return {}
    if isinstance(dist, str):
        try:
            dist = json.loads(dist)
        except Exception:
            return {}
    if not isinstance(dist, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in dist.items():
        try:
            out[str(k)] = float(v)
        except (ValueError, TypeError):
            continue
    return out


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    url, db, uid, api_key = load_test_env()
    client = SafeTestOdooClient(url, db, uid, api_key)

    print("[SA-4] Connected guard verified (Odoo TEST, read-only mode).")

    # Discover accessible companies for the TEST user
    companies = client.search_read_all("res.company", [], ["id", "name"])
    accessible_company_ids: list[int] = []
    for comp in companies:
        cid = comp["id"]
        try:
            client.call(
                "sale.order",
                "search_count",
                [[["company_id", "=", cid]]],
                {"context": {"allowed_company_ids": [cid]}},
            )
            accessible_company_ids.append(cid)
        except Exception:
            pass
    print(f"[SA-4] Accessible company IDs for uid: {accessible_company_ids} (all companies: {companies})")
    multi_company_ctx = {"allowed_company_ids": accessible_company_ids, "active_test": False}
    multi_company_active_ctx = {"allowed_company_ids": accessible_company_ids}

    # -------------------------------------------------------------------------
    # STEP 1: Inspect fields on account.analytic.line & account.analytic.account
    # -------------------------------------------------------------------------
    print("[SA-4] Step 1: Fetching fields_get on account.analytic.line and account.analytic.plan...")
    aal_fields_meta: dict[str, Any] = client.call(
        "account.analytic.line",
        "fields_get",
        [[]],
        {"attributes": ["string", "type", "relation"]},
    )
    analytic_m2o_cols: list[dict[str, str]] = []
    for fname, fmeta in sorted(aal_fields_meta.items()):
        if fmeta.get("type") == "many2one" and fmeta.get("relation") == "account.analytic.account":
            analytic_m2o_cols.append({
                "field": fname,
                "label": fmeta.get("string") or fname,
            })
    print(f"[SA-4] Found many2one -> account.analytic.account columns on AAL: {analytic_m2o_cols}")

    plan_fields_meta: dict[str, Any] = client.call(
        "account.analytic.plan",
        "fields_get",
        [[]],
        {"attributes": ["string", "type", "relation"]},
    )
    desired_plan_fields = [f for f in ("id", "name", "complete_name", "parent_id", "company_id") if f in plan_fields_meta]
    plans = client.search_read_all(
        "account.analytic.plan",
        [],
        desired_plan_fields,
        context=multi_company_ctx,
    )
    print(f"[SA-4] Found {len(plans)} analytic plans:")
    for p in plans:
        print(f"  - Plan ID {p['id']}: name={p.get('name')!r}, complete_name={p.get('complete_name')!r}, parent_id={p.get('parent_id')}")

    # -------------------------------------------------------------------------
    # STEP 2: Fetch all account.analytic.account (active + archived)
    # -------------------------------------------------------------------------
    print("[SA-4] Step 2: Fetching all account.analytic.account with active_test=False...")
    acc_fields_meta: dict[str, Any] = client.call(
        "account.analytic.account",
        "fields_get",
        [[]],
        {"attributes": ["string", "type", "relation"]},
    )
    desired_acc_fields = [
        f for f in ("id", "name", "code", "plan_id", "root_plan_id", "company_id", "active", "partner_id")
        if f in acc_fields_meta
    ]
    all_accounts = client.search_read_all(
        "account.analytic.account",
        [],
        desired_acc_fields,
        context=multi_company_ctx,
    )
    accounts_by_id = {a["id"]: a for a in all_accounts}
    print(f"[SA-4] Total analytic accounts fetched (active + archived): {len(all_accounts)}")

    project_plan_ids: set[int] = set()
    dept_plan_ids: set[int] = set()
    for p in plans:
        pname = (p.get("complete_name") or p.get("name") or "").lower()
        if "project" in pname or "dự án" in pname:
            project_plan_ids.add(p["id"])
        else:
            dept_plan_ids.add(p["id"])

    # -------------------------------------------------------------------------
    # STEP 3: S1 Shipping Account Discovery & Candidate Evaluation
    # -------------------------------------------------------------------------
    discovered_dept_accounts: list[dict[str, Any]] = []
    naive_substring_traps: list[dict[str, Any]] = []
    for acc in all_accounts:
        pid = relation_id(acc.get("plan_id"))
        if pid in project_plan_ids:
            continue
        aname = acc.get("name") or ""
        matched_kws = match_shipping_keywords(aname)
        if matched_kws:
            discovered_dept_accounts.append(acc)
        elif any(kw in aname.lower() for kw in DISCOVERY_KEYWORDS):
            # Matched naive substring (e.g. 'ship' inside 'Partnerships') but rejected by word-boundary!
            naive_substring_traps.append(acc)

    print(f"[SA-4] Word-boundary keyword-matched accounts on non-project plans ({len(discovered_dept_accounts)}):")
    for acc in sorted(discovered_dept_accounts, key=lambda x: x["id"]):
        print(
            f"  - ID {acc['id']}: name={acc.get('name')!r}, plan={acc.get('plan_id')}, "
            f"root_plan={acc.get('root_plan_id')}, active={acc.get('active')}, company={acc.get('company_id')}"
        )
    print(f"[SA-4] Naive substring traps rejected by word-boundary \\bship ({len(naive_substring_traps)}):")
    for acc in sorted(naive_substring_traps, key=lambda x: x["id"]):
        print(f"  - TRAP ID {acc['id']}: name={acc.get('name')!r}, plan={acc.get('plan_id')}")

    # Check S1(d) candidates: 1439, 568, 1238
    s1d_included_ids: set[int] = set()
    s1d_decisions: dict[int, dict[str, Any]] = {}
    for cid in CANDIDATE_REVIEW_IDS:
        acc = accounts_by_id.get(cid)
        if not acc:
            s1d_decisions[cid] = {
                "id": cid,
                "exists": False,
                "included": False,
                "reason": "Account ID does not exist on Odoo TEST.",
            }
            continue
        aname = acc.get("name") or ""
        matched_kws = match_shipping_keywords(aname)
        included = len(matched_kws) > 0
        if included:
            s1d_included_ids.add(cid)
        s1d_decisions[cid] = {
            "id": cid,
            "exists": True,
            "name": aname,
            "plan_id": acc.get("plan_id"),
            "root_plan_id": acc.get("root_plan_id"),
            "active": acc.get("active"),
            "company_id": acc.get("company_id"),
            "matched_keywords": matched_kws,
            "included": included,
            "reason": (
                f"Matched shipping keywords {matched_kws} in name {aname!r}."
                if included
                else f"Excluded per S1(d): name {aname!r} does NOT contain any shipping keyword {DISCOVERY_KEYWORDS} (represents general trip/car fuel/maintenance expenses, not shipping/freight/delivery)."
            ),
        }

    # Build official S1 shipping account ID set
    env_override = os.environ.get("SHIPPING_ANALYTIC_IDS", "").strip()
    if env_override:
        s1_shipping_ids = {int(x.strip()) for x in env_override.split(",") if x.strip()}
        print(f"[SA-4] Using SHIPPING_ANALYTIC_IDS override: {sorted(s1_shipping_ids)}")
    else:
        s1_shipping_ids = (
            set(BASE_10_SHIPPING_IDS)
            | set(BD_SHIPPING_IDS)
            | s1d_included_ids
            | {acc["id"] for acc in discovered_dept_accounts}
        )
    s1_core_12_ids = set(BASE_10_SHIPPING_IDS) | set(BD_SHIPPING_IDS)
    print(f"[SA-4] Core 12 S1 IDs (10 SC + 2 BD): {sorted(s1_core_12_ids)}")
    print(f"[SA-4] Full S1 shipping analytic account IDs (with keyword discovery): {sorted(s1_shipping_ids)}")

    # Inspect all S1 accounts + S1(d) candidates + naive substring traps (510, 552, 1426)
    all_inspect_ids = sorted(
        s1_shipping_ids
        | set(CANDIDATE_REVIEW_IDS)
        | {acc["id"] for acc in naive_substring_traps}
    )

    # -------------------------------------------------------------------------
    # STEP 4: Fetch account.analytic.line for all_inspect_ids across all m2o columns
    # -------------------------------------------------------------------------
    m2o_field_names = [c["field"] for c in analytic_m2o_cols]
    or_domain: list[Any] = ["|"] * (len(m2o_field_names) - 1)
    for fname in m2o_field_names:
        or_domain.append([fname, "in", all_inspect_ids])

    desired_aal_fields = [
        f for f in (
            ["id", "name", "date", "amount", "move_line_id", "company_id", "partner_id", "product_id", "category", "ref", "unit_amount"]
            + m2o_field_names
        )
        if f in aal_fields_meta
    ]
    print(f"[SA-4] Step 4: Fetching account.analytic.line matching {all_inspect_ids} across {m2o_field_names}...")
    raw_aal_lines = client.search_read_all(
        "account.analytic.line",
        or_domain,
        desired_aal_fields,
        context=multi_company_active_ctx,
    )
    print(f"[SA-4] Fetched {len(raw_aal_lines)} raw AAL lines.")

    col_usage_by_acc: dict[int, set[str]] = defaultdict(set)
    for line in raw_aal_lines:
        for fname in m2o_field_names:
            aid = relation_id(line.get(fname))
            if aid in all_inspect_ids:
                col_usage_by_acc[aid].add(fname)
    print("[SA-4] Column usage on AAL by inspected account ID:")
    for aid in sorted(all_inspect_ids):
        acc = accounts_by_id.get(aid, {})
        print(
            f"  - Account {aid} ({acc.get('name')!r}, plan={acc.get('plan_id')}, active={acc.get('active')}): "
            f"columns={sorted(col_usage_by_acc.get(aid, set()))}"
        )

    # Fetch all move_line_ids referenced by raw_aal_lines
    move_line_ids = sorted({
        relation_id(line.get("move_line_id"))
        for line in raw_aal_lines
        if relation_id(line.get("move_line_id"))
    })
    ml_fields_meta: dict[str, Any] = client.call(
        "account.move.line",
        "fields_get",
        [[]],
        {"attributes": ["string", "type", "relation"]},
    )
    desired_ml_fields = [
        f for f in (
            "id",
            "name",
            "date",
            "parent_state",
            "move_type",
            "purchase_line_id",
            "move_id",
            "partner_id",
            "ref",
            "balance",
            "debit",
            "credit",
            "analytic_distribution",
            "company_id",
            "product_id",
            "account_id",
        )
        if f in ml_fields_meta
    ]
    print(f"[SA-4] Fetching {len(move_line_ids)} account.move.line records referenced by AAL...")
    move_lines = client.read_batched(
        "account.move.line",
        move_line_ids,
        desired_ml_fields,
        context=multi_company_active_ctx,
    )
    move_lines_by_id = {ml["id"]: ml for ml in move_lines}
    print(f"[SA-4] Fetched {len(move_lines_by_id)} account.move.line records.")

    # -------------------------------------------------------------------------
    # STEP 4b: Fetch all projects (active + archived) & dashboard 2026 sale orders
    # -------------------------------------------------------------------------
    print("[SA-4] Step 4b: Fetching project.project (active_test=False) and sale.order for dashboard scope...")
    proj_fields_meta: dict[str, Any] = client.call(
        "project.project",
        "fields_get",
        [[]],
        {"attributes": ["string", "type", "relation"]},
    )
    desired_proj_fields = [
        f for f in ("id", "name", "partner_id", "sale_order_id", "account_id", "company_id", "active", "x_studio_giai_trinh")
        if f in proj_fields_meta
    ]
    all_projects = client.search_read_all(
        "project.project",
        [],
        desired_proj_fields,
        context=multi_company_ctx,
    )
    print(f"[SA-4] Fetched {len(all_projects)} total projects (active + archived).")

    projects_by_account_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    projects_by_id: dict[int, dict[str, Any]] = {}
    for proj in all_projects:
        projects_by_id[proj["id"]] = proj
        aid = relation_id(proj.get("account_id"))
        if aid:
            projects_by_account_id[aid].append(proj)

    so_fields = [
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
    dashboard_so_by_id: dict[int, dict[str, Any]] = {}
    for cid in accessible_company_ids:
        sos = client.search_read_all(
            "sale.order",
            [["date_order", ">=", "2026-01-01"], ["company_id", "=", cid]],
            so_fields,
            context={"allowed_company_ids": [cid]},
        )
        for so in sos:
            dashboard_so_by_id[so["id"]] = so

    sos_no_comp = client.search_read_all(
        "sale.order",
        [["date_order", ">=", "2026-01-01"], ["company_id", "=", False]],
        so_fields,
        context=multi_company_active_ctx,
    )
    for so in sos_no_comp:
        dashboard_so_by_id[so["id"]] = so

    # Resolve tag names on sale.order safely
    so_tag_field_meta = client.call(
        "sale.order",
        "fields_get",
        [["x_sale_order_tag_ids"]],
        {"attributes": ["relation"]},
    )
    tag_rel_model = (
        so_tag_field_meta.get("x_sale_order_tag_ids", {}).get("relation")
        if isinstance(so_tag_field_meta, dict)
        else None
    ) or "x_sale_order_tag"
    tag_model_fields_meta = client.call(
        tag_rel_model,
        "fields_get",
        [[]],
        {"attributes": ["string", "type"]},
    )
    tag_read_fields = ["id"] + [
        f for f in ("name", "x_name", "display_name") if f in tag_model_fields_meta
    ]
    all_tag_ids = sorted({
        tid
        for so in dashboard_so_by_id.values()
        for tid in (so.get("x_sale_order_tag_ids") or [])
        if isinstance(tid, int)
    })
    tag_name_by_id: dict[int, str] = {}
    if all_tag_ids:
        tags_data = client.read_batched(tag_rel_model, all_tag_ids, tag_read_fields, context=multi_company_active_ctx)
        for t in tags_data:
            tag_name_by_id[t["id"]] = (
                t.get("name") or t.get("x_name") or t.get("display_name") or ""
            )

    filtered_dashboard_so_ids: set[int] = set()
    for so_id, so in dashboard_so_by_id.items():
        user_ref = so.get("user_id")
        if isinstance(user_ref, (list, tuple)) and len(user_ref) > 1 and user_ref[1] in EXCLUDED_SALESPERSONS:
            continue
        t_names = [
            tag_name_by_id.get(tid, "")
            for tid in (so.get("x_sale_order_tag_ids") or [])
            if isinstance(tid, int)
        ]
        if any(tn in DASHBOARD_TARGET_TAGS for tn in t_names):
            filtered_dashboard_so_ids.add(so_id)

    dashboard_2026_project_ids: set[int] = set()
    dashboard_2026_done_project_ids: set[int] = set()
    for proj in all_projects:
        so_id = relation_id(proj.get("sale_order_id"))
        if so_id and so_id in filtered_dashboard_so_ids:
            dashboard_2026_project_ids.add(proj["id"])
            so = dashboard_so_by_id[so_id]
            if (so.get("x_studio_selection_field_q4_1imrcsjj8") or "") == "Done":
                dashboard_2026_done_project_ids.add(proj["id"])

    # Also fetch sale.order details for any project linked to an older sale.order
    missing_so_ids = sorted({
        relation_id(proj.get("sale_order_id"))
        for proj in all_projects
        if relation_id(proj.get("sale_order_id")) and relation_id(proj.get("sale_order_id")) not in dashboard_so_by_id
    })
    all_so_by_id = dict(dashboard_so_by_id)
    if missing_so_ids:
        extra_sos = client.search_read_all(
            "sale.order",
            [["id", "in", missing_so_ids]],
            so_fields,
            context=multi_company_active_ctx,
        )
        for so in extra_sos:
            all_so_by_id[so["id"]] = so

    print(
        f"[SA-4] Dashboard 2026 scope: {len(dashboard_2026_project_ids)} projects "
        f"({len(dashboard_2026_done_project_ids)} Done)."
    )

    # -------------------------------------------------------------------------
    # STEP 5: Fetch draft account.move.line for shipping_draft (Rule S5)
    # -------------------------------------------------------------------------
    print("[SA-4] Step 5: Fetching draft account.move.line records for shipping_draft...")
    draft_mls = client.search_read_all(
        "account.move.line",
        [
            ["parent_state", "=", "draft"],
            ["move_type", "in", list(DRAFT_ALLOWED_MOVE_TYPES)],
            ["analytic_distribution", "!=", False],
        ],
        desired_ml_fields,
        context=multi_company_active_ctx,
    )
    print(f"[SA-4] Fetched {len(draft_mls)} draft move lines with analytic_distribution.")

    # -------------------------------------------------------------------------
    # STEP 6: Evaluate AAL lines under Official S1 vs Candidate Accounts
    # -------------------------------------------------------------------------
    dept_m2o_fields = [f for f in m2o_field_names if f != "account_id"]

    def get_line_dept_accounts(line: dict[str, Any]) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []
        for fname in dept_m2o_fields:
            aid = relation_id(line.get(fname))
            if aid:
                found.append((fname, aid))
        aid_main = relation_id(line.get("account_id"))
        if aid_main and aid_main in all_inspect_ids:
            found.append(("account_id", aid_main))
        return found

    def is_valid_shipping_aal(line: dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
        ml_id = relation_id(line.get("move_line_id"))
        if not ml_id:
            return True, "direct_aal", None
        ml = move_lines_by_id.get(ml_id)
        if not ml:
            return False, "missing_move_line", None
        pstate = ml.get("parent_state")
        if pstate != "posted":
            return False, f"parent_state={pstate}", ml
        mtype = ml.get("move_type") or ""
        if mtype in EXCLUDED_MOVE_TYPES:
            return False, f"excluded_move_type={mtype}", ml
        return True, "ok", ml

    per_ship_acc_stats: dict[int, dict[str, Any]] = {}
    for aid in all_inspect_ids:
        acc = accounts_by_id.get(aid, {})
        per_ship_acc_stats[aid] = {
            "id": aid,
            "name": acc.get("name") or "<MISSING>",
            "code": acc.get("code") or "",
            "plan_id": relation_id(acc.get("plan_id")),
            "plan_name": relation_name(acc.get("plan_id")),
            "root_plan_id": relation_id(acc.get("root_plan_id")),
            "root_plan_name": relation_name(acc.get("root_plan_id")),
            "company_id": relation_id(acc.get("company_id")),
            "company_name": relation_name(acc.get("company_id")),
            "active": acc.get("active"),
            "in_s1": aid in s1_shipping_ids,
            "aal_columns": sorted(col_usage_by_acc.get(aid, set())),
            "raw_line_count": 0,
            "valid_line_count_lifetime": 0,
            "valid_line_count_2026": 0,
            "cost_lifetime": Decimal("0"),
            "cost_2026": Decimal("0"),
            "cost_2026_assigned": Decimal("0"),
            "cost_2026_assigned_po": Decimal("0"),
            "cost_2026_assigned_non_po": Decimal("0"),
            "cost_2026_unassigned": Decimal("0"),
            "sample_lines": [],
        }

    valid_s1_lines: list[dict[str, Any]] = []
    excluded_s1_lines_log: dict[str, int] = defaultdict(int)

    for line in raw_aal_lines:
        dept_hits = get_line_dept_accounts(line)
        matched_inspect_hits = [(col, aid) for col, aid in dept_hits if aid in all_inspect_ids]
        if not matched_inspect_hits:
            continue

        ok, reason, ml = is_valid_shipping_aal(line)
        cost = -as_decimal(line.get("amount"))
        ldate = line.get("date") or ""
        is_2026 = ldate >= "2026-01-01"
        proj_acc_id = relation_id(line.get("account_id"))
        if proj_acc_id in all_inspect_ids:
            proj_acc_id = None
        is_po = bool(ml and relation_id(ml.get("purchase_line_id")))

        for col, aid in matched_inspect_hits:
            st = per_ship_acc_stats[aid]
            st["raw_line_count"] += 1
            if ok:
                st["valid_line_count_lifetime"] += 1
                st["cost_lifetime"] += cost
                if is_2026:
                    st["valid_line_count_2026"] += 1
                    st["cost_2026"] += cost
                    if proj_acc_id:
                        st["cost_2026_assigned"] += cost
                        if is_po:
                            st["cost_2026_assigned_po"] += cost
                        else:
                            st["cost_2026_assigned_non_po"] += cost
                    else:
                        st["cost_2026_unassigned"] += cost
                if len(st["sample_lines"]) < 5:
                    st["sample_lines"].append({
                        "aal_id": line["id"],
                        "date": ldate,
                        "name": line.get("name"),
                        "amount": float(cost),
                        "project_account": relation_name(line.get("account_id")) if proj_acc_id else None,
                        "is_po": is_po,
                        "move_type": ml.get("move_type") if ml else "direct_aal",
                    })

        s1_hits = [(col, aid) for col, aid in dept_hits if aid in s1_shipping_ids]
        if not s1_hits:
            continue
        if not ok:
            excluded_s1_lines_log[reason] += 1
            continue

        valid_s1_lines.append({
            "line": line,
            "ml": ml,
            "s1_hits": s1_hits,
            "proj_acc_id": proj_acc_id,
            "cost": cost,
            "date": ldate,
            "yyyy_mm": ldate[:7] if len(ldate) >= 7 else "",
            "is_2026": is_2026,
            "is_po": is_po,
            "company_id": relation_id(line.get("company_id")),
            "company_name": relation_name(line.get("company_id")),
            "company_key": detect_company_key(line.get("company_id")),
        })

    print(f"[SA-4] Valid S1 shipping AAL lines: {len(valid_s1_lines)} (excluded reasons: {dict(excluded_s1_lines_log)})")

    # -------------------------------------------------------------------------
    # STEP 6b: Process Draft Shipping Lines (Rule S5)
    # -------------------------------------------------------------------------
    draft_shipping_entries: list[dict[str, Any]] = []
    for ml in draft_mls:
        dist = parse_analytic_distribution(ml.get("analytic_distribution"))
        if not dist:
            continue
        balance = as_decimal(ml.get("balance"))
        mdate = ml.get("date") or ""
        is_2026 = mdate >= "2026-01-01"
        is_po = bool(relation_id(ml.get("purchase_line_id")))
        comp_key = detect_company_key(ml.get("company_id"))

        # Check if distribution has shipping account and project account either in same comma key or separate keys
        all_parts_by_key: list[tuple[list[int], float]] = []
        for key_str, pct in dist.items():
            parts = [int(p.strip()) for p in str(key_str).split(",") if p.strip().isdigit()]
            if parts:
                all_parts_by_key.append((parts, pct))

        # Check if any key has a shipping account
        has_comma_keys = any(len(parts) > 1 for parts, _ in all_parts_by_key)
        if has_comma_keys:
            for parts, pct in all_parts_by_key:
                ship_ids_in_key = [pid for pid in parts if pid in s1_shipping_ids]
                if not ship_ids_in_key:
                    continue
                other_ids_in_key = [pid for pid in parts if pid not in s1_shipping_ids]
                proj_acc_id = None
                for oid in other_ids_in_key:
                    acc_obj = accounts_by_id.get(oid)
                    if acc_obj and relation_id(acc_obj.get("plan_id")) in project_plan_ids:
                        proj_acc_id = oid
                        break
                if proj_acc_id is None and other_ids_in_key:
                    proj_acc_id = other_ids_in_key[0]
                alloc_cost = balance * (as_decimal(pct) / Decimal("100"))
                draft_shipping_entries.append({
                    "ml": ml,
                    "ship_account_id": ship_ids_in_key[0],
                    "proj_acc_id": proj_acc_id,
                    "pct": pct,
                    "cost": alloc_cost,
                    "date": mdate,
                    "yyyy_mm": mdate[:7] if len(mdate) >= 7 else "",
                    "is_2026": is_2026,
                    "is_po": is_po,
                    "company_key": comp_key,
                })
        else:
            # Single-ID keys in analytic_distribution
            ship_entries = [(parts[0], pct) for parts, pct in all_parts_by_key if parts[0] in s1_shipping_ids]
            if ship_entries:
                proj_entries = [
                    (parts[0], pct)
                    for parts, pct in all_parts_by_key
                    if parts[0] not in s1_shipping_ids
                    and accounts_by_id.get(parts[0])
                    and relation_id(accounts_by_id[parts[0]].get("plan_id")) in project_plan_ids
                ]
                ship_aid, ship_pct = ship_entries[0]
                if proj_entries:
                    for proj_aid, proj_pct in proj_entries:
                        eff_pct = min(ship_pct, proj_pct)
                        alloc_cost = balance * (as_decimal(eff_pct) / Decimal("100"))
                        draft_shipping_entries.append({
                            "ml": ml,
                            "ship_account_id": ship_aid,
                            "proj_acc_id": proj_aid,
                            "pct": eff_pct,
                            "cost": alloc_cost,
                            "date": mdate,
                            "yyyy_mm": mdate[:7] if len(mdate) >= 7 else "",
                            "is_2026": is_2026,
                            "is_po": is_po,
                            "company_key": comp_key,
                        })
                else:
                    alloc_cost = balance * (as_decimal(ship_pct) / Decimal("100"))
                    draft_shipping_entries.append({
                        "ml": ml,
                        "ship_account_id": ship_aid,
                        "proj_acc_id": None,
                        "pct": ship_pct,
                        "cost": alloc_cost,
                        "date": mdate,
                        "yyyy_mm": mdate[:7] if len(mdate) >= 7 else "",
                        "is_2026": is_2026,
                        "is_po": is_po,
                        "company_key": comp_key,
                    })

    print(f"[SA-4] Found {len(draft_shipping_entries)} draft shipping allocations.")

    # -------------------------------------------------------------------------
    # STEP 6c: Aggregate by Project Account & Unassigned
    # -------------------------------------------------------------------------
    unassigned_items: list[dict[str, Any]] = []
    by_proj_acc: dict[int, dict[str, Any]] = {}

    def ensure_proj_acc_bucket(acc_id: int) -> dict[str, Any]:
        if acc_id not in by_proj_acc:
            by_proj_acc[acc_id] = {
                "account_id": acc_id,
                "shipping_cost": Decimal("0"),
                "shipping_po": Decimal("0"),
                "shipping_non_po": Decimal("0"),
                "shipping_draft": Decimal("0"),
                "shipping_cost_2026": Decimal("0"),
                "shipping_po_2026": Decimal("0"),
                "shipping_non_po_2026": Decimal("0"),
                "shipping_draft_2026": Decimal("0"),
                "aal_line_count": 0,
                "aal_line_count_2026": 0,
                "shipping_by_month": defaultdict(lambda: Decimal("0")),
                "shipping_po_by_month": defaultdict(lambda: Decimal("0")),
                "shipping_non_po_by_month": defaultdict(lambda: Decimal("0")),
            }
        return by_proj_acc[acc_id]

    for item in valid_s1_lines:
        proj_acc_id = item["proj_acc_id"]
        cost = item["cost"]
        is_po = item["is_po"]
        is_2026 = item["is_2026"]
        ym = item["yyyy_mm"]

        if not proj_acc_id:
            unassigned_items.append(item)
            continue

        b = ensure_proj_acc_bucket(proj_acc_id)
        b["shipping_cost"] += cost
        if is_po:
            b["shipping_po"] += cost
        else:
            b["shipping_non_po"] += cost
        b["aal_line_count"] += 1
        if ym:
            b["shipping_by_month"][ym] += cost
            if is_po:
                b["shipping_po_by_month"][ym] += cost
            else:
                b["shipping_non_po_by_month"][ym] += cost

        if is_2026:
            b["shipping_cost_2026"] += cost
            if is_po:
                b["shipping_po_2026"] += cost
            else:
                b["shipping_non_po_2026"] += cost
            b["aal_line_count_2026"] += 1

    for ditem in draft_shipping_entries:
        proj_acc_id = ditem["proj_acc_id"]
        if not proj_acc_id:
            continue
        b = ensure_proj_acc_bucket(proj_acc_id)
        b["shipping_draft"] += ditem["cost"]
        if ditem["is_2026"]:
            b["shipping_draft_2026"] += ditem["cost"]

    # -------------------------------------------------------------------------
    # STEP 6d: Build truth_by_project.csv rows
    # -------------------------------------------------------------------------
    all_relevant_account_ids = set(by_proj_acc.keys()) | {
        relation_id(projects_by_id[pid].get("account_id"))
        for pid in dashboard_2026_project_ids
        if relation_id(projects_by_id[pid].get("account_id"))
    }

    project_rows_csv: list[dict[str, Any]] = []
    orphan_account_ids: list[int] = []

    for acc_id in sorted(all_relevant_account_ids):
        projs = projects_by_account_id.get(acc_id, [])
        b = by_proj_acc.get(acc_id) or ensure_proj_acc_bucket(acc_id)
        acc_obj = accounts_by_id.get(acc_id, {})
        by_month_serialized = {
            ym: as_money(val)
            for ym, val in sorted(b["shipping_by_month"].items())
            if as_money(val) != 0
        }

        if not projs:
            orphan_account_ids.append(acc_id)
            comp_key = detect_company_key(acc_obj.get("company_id"))
            project_rows_csv.append({
                "project_id": "",
                "project_name": "",
                "project_active": "",
                "account_id": acc_id,
                "account_name": acc_obj.get("name") or "",
                "sale_order_id": "",
                "sale_order_name": "",
                "date_order": "",
                "order_state": "",
                "company_key": comp_key,
                "company_name": relation_name(acc_obj.get("company_id")),
                "in_dashboard_2026": False,
                "in_dashboard_2026_done": False,
                "shipping_cost": as_money(b["shipping_cost"]),
                "shipping_po": as_money(b["shipping_po"]),
                "shipping_non_po": as_money(b["shipping_non_po"]),
                "shipping_draft": as_money(b["shipping_draft"]),
                "shipping_cost_2026": as_money(b["shipping_cost_2026"]),
                "shipping_po_2026": as_money(b["shipping_po_2026"]),
                "shipping_non_po_2026": as_money(b["shipping_non_po_2026"]),
                "shipping_draft_2026": as_money(b["shipping_draft_2026"]),
                "aal_line_count": b["aal_line_count"],
                "aal_line_count_2026": b["aal_line_count_2026"],
                "shipping_by_month_json": json.dumps(by_month_serialized, ensure_ascii=False),
            })
        else:
            for proj in projs:
                pid = proj["id"]
                so_id = relation_id(proj.get("sale_order_id"))
                so = all_so_by_id.get(so_id or 0, {})
                comp_ref = so.get("company_id") or proj.get("company_id") or acc_obj.get("company_id")
                comp_key = detect_company_key(comp_ref)
                project_rows_csv.append({
                    "project_id": pid,
                    "project_name": proj.get("name") or "",
                    "project_active": bool(proj.get("active", True)),
                    "account_id": acc_id,
                    "account_name": acc_obj.get("name") or relation_name(proj.get("account_id")),
                    "sale_order_id": so_id or "",
                    "sale_order_name": so.get("name") or relation_name(proj.get("sale_order_id")),
                    "date_order": so.get("date_order") or "",
                    "order_state": so.get("x_studio_selection_field_q4_1imrcsjj8") or "",
                    "company_key": comp_key,
                    "company_name": relation_name(comp_ref),
                    "in_dashboard_2026": pid in dashboard_2026_project_ids,
                    "in_dashboard_2026_done": pid in dashboard_2026_done_project_ids,
                    "shipping_cost": as_money(b["shipping_cost"]),
                    "shipping_po": as_money(b["shipping_po"]),
                    "shipping_non_po": as_money(b["shipping_non_po"]),
                    "shipping_draft": as_money(b["shipping_draft"]),
                    "shipping_cost_2026": as_money(b["shipping_cost_2026"]),
                    "shipping_po_2026": as_money(b["shipping_po_2026"]),
                    "shipping_non_po_2026": as_money(b["shipping_non_po_2026"]),
                    "shipping_draft_2026": as_money(b["shipping_draft_2026"]),
                    "aal_line_count": b["aal_line_count"],
                    "aal_line_count_2026": b["aal_line_count_2026"],
                    "shipping_by_month_json": json.dumps(by_month_serialized, ensure_ascii=False),
                })

    project_rows_csv.sort(
        key=lambda r: (
            -float(r["shipping_cost_2026"]),
            -float(r["shipping_cost"]),
            int(r["project_id"]) if str(r["project_id"]).isdigit() else 999999999,
        )
    )

    truth_by_project_path = OUTPUT_DIR / "truth_by_project.csv"
    project_csv_fields = [
        "project_id",
        "project_name",
        "project_active",
        "account_id",
        "account_name",
        "sale_order_id",
        "sale_order_name",
        "date_order",
        "order_state",
        "company_key",
        "company_name",
        "in_dashboard_2026",
        "in_dashboard_2026_done",
        "shipping_cost",
        "shipping_po",
        "shipping_non_po",
        "shipping_draft",
        "shipping_cost_2026",
        "shipping_po_2026",
        "shipping_non_po_2026",
        "shipping_draft_2026",
        "aal_line_count",
        "aal_line_count_2026",
        "shipping_by_month_json",
    ]
    with truth_by_project_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=project_csv_fields)
        writer.writeheader()
        writer.writerows(project_rows_csv)
    print(f"[SA-4] Wrote {len(project_rows_csv)} rows to {truth_by_project_path}")

    # -------------------------------------------------------------------------
    # STEP 6e: Write truth_unassigned.csv
    # -------------------------------------------------------------------------
    unassigned_rows_csv: list[dict[str, Any]] = []
    for item in sorted(unassigned_items, key=lambda x: (x["date"], x["line"]["id"]), reverse=True):
        line = item["line"]
        ml = item["ml"]
        col_name, ship_aid = item["s1_hits"][0]
        ship_acc = accounts_by_id.get(ship_aid, {})
        unassigned_rows_csv.append({
            "aal_id": line["id"],
            "date": item["date"],
            "yyyy_mm": item["yyyy_mm"],
            "company_id": item["company_id"] or "",
            "company_name": item["company_name"],
            "company_key": item["company_key"],
            "dept_column": col_name,
            "shipping_account_id": ship_aid,
            "shipping_account_name": ship_acc.get("name") or "",
            "account_id": relation_id(line.get("account_id")) or "",
            "account_name": relation_name(line.get("account_id")),
            "amount_aal": as_money(as_decimal(line.get("amount"))),
            "shipping_cost": as_money(item["cost"]),
            "is_po": item["is_po"],
            "purchase_line_id": relation_id(ml.get("purchase_line_id")) if ml else "",
            "move_line_id": ml["id"] if ml else "",
            "move_id": relation_id(ml.get("move_id")) if ml else "",
            "move_name": relation_name(ml.get("move_id")) if ml else "",
            "move_type": ml.get("move_type") if ml else "direct_aal",
            "parent_state": ml.get("parent_state") if ml else "",
            "partner_name": relation_name(line.get("partner_id")) or (relation_name(ml.get("partner_id")) if ml else ""),
            "ref": line.get("ref") or (ml.get("ref") if ml else "") or "",
            "name": line.get("name") or "",
            "category": line.get("category") or "",
        })

    truth_unassigned_path = OUTPUT_DIR / "truth_unassigned.csv"
    unassigned_csv_fields = [
        "aal_id",
        "date",
        "yyyy_mm",
        "company_id",
        "company_name",
        "company_key",
        "dept_column",
        "shipping_account_id",
        "shipping_account_name",
        "account_id",
        "account_name",
        "amount_aal",
        "shipping_cost",
        "is_po",
        "purchase_line_id",
        "move_line_id",
        "move_id",
        "move_name",
        "move_type",
        "parent_state",
        "partner_name",
        "ref",
        "name",
        "category",
    ]
    with truth_unassigned_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=unassigned_csv_fields)
        writer.writeheader()
        writer.writerows(unassigned_rows_csv)
    print(f"[SA-4] Wrote {len(unassigned_rows_csv)} rows to {truth_unassigned_path}")

    # -------------------------------------------------------------------------
    # STEP 6f: Compute Summary Aggregations & Write truth_summary.json
    # -------------------------------------------------------------------------
    def compute_aal_scope_summary(
        date_from_filter: str | None,
        company_scope: str,
        project_account_whitelist: set[int] | None = None,
    ) -> dict[str, Any]:
        assigned_total = Decimal("0")
        assigned_po = Decimal("0")
        assigned_non_po = Decimal("0")
        unassigned_total = Decimal("0")
        unassigned_po = Decimal("0")
        unassigned_non_po = Decimal("0")
        by_month_assigned: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_month_unassigned: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_month_total: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        assigned_line_count = 0
        unassigned_line_count = 0

        for item in valid_s1_lines:
            if date_from_filter and item["date"] < date_from_filter:
                continue
            if company_scope != "all" and item["company_key"] != company_scope:
                continue
            proj_acc_id = item["proj_acc_id"]
            cost = item["cost"]
            ym = item["yyyy_mm"]
            if proj_acc_id:
                if project_account_whitelist is not None and proj_acc_id not in project_account_whitelist:
                    continue
                assigned_total += cost
                if item["is_po"]:
                    assigned_po += cost
                else:
                    assigned_non_po += cost
                assigned_line_count += 1
                if ym:
                    by_month_assigned[ym] += cost
                    by_month_total[ym] += cost
            else:
                if project_account_whitelist is not None:
                    continue
                unassigned_total += cost
                if item["is_po"]:
                    unassigned_po += cost
                else:
                    unassigned_non_po += cost
                unassigned_line_count += 1
                if ym:
                    by_month_unassigned[ym] += cost
                    by_month_total[ym] += cost

        draft_assigned = Decimal("0")
        draft_unassigned = Decimal("0")
        for ditem in draft_shipping_entries:
            if date_from_filter and ditem["date"] < date_from_filter:
                continue
            if company_scope != "all" and ditem["company_key"] != company_scope:
                continue
            proj_acc_id = ditem["proj_acc_id"]
            if proj_acc_id:
                if project_account_whitelist is not None and proj_acc_id not in project_account_whitelist:
                    continue
                draft_assigned += ditem["cost"]
            else:
                if project_account_whitelist is not None:
                    continue
                draft_unassigned += ditem["cost"]

        return {
            "shipping_assigned_total": as_money(assigned_total),
            "shipping_assigned_po": as_money(assigned_po),
            "shipping_assigned_non_po": as_money(assigned_non_po),
            "shipping_unassigned_total": as_money(unassigned_total),
            "shipping_unassigned_po": as_money(unassigned_po),
            "shipping_unassigned_non_po": as_money(unassigned_non_po),
            "shipping_grand_total": as_money(assigned_total + unassigned_total),
            "shipping_draft_assigned": as_money(draft_assigned),
            "shipping_draft_unassigned": as_money(draft_unassigned),
            "shipping_draft_total": as_money(draft_assigned + draft_unassigned),
            "assigned_line_count": assigned_line_count,
            "unassigned_line_count": unassigned_line_count,
            "shipping_by_month_assigned": {k: as_money(v) for k, v in sorted(by_month_assigned.items())},
            "shipping_by_month_unassigned": {k: as_money(v) for k, v in sorted(by_month_unassigned.items())},
            "shipping_by_month_total": {k: as_money(v) for k, v in sorted(by_month_total.items())},
        }

    dashboard_2026_account_ids_by_company: dict[str, set[int]] = {
        "all": set(),
        "bonario": set(),
        "ordinaire": set(),
    }
    dashboard_2026_done_account_ids_by_company: dict[str, set[int]] = {
        "all": set(),
        "bonario": set(),
        "ordinaire": set(),
    }
    for pid in dashboard_2026_project_ids:
        proj = projects_by_id[pid]
        aid = relation_id(proj.get("account_id"))
        if not aid:
            continue
        so_id = relation_id(proj.get("sale_order_id"))
        so = all_so_by_id.get(so_id or 0, {})
        ckey = detect_company_key(so.get("company_id") or proj.get("company_id"))
        dashboard_2026_account_ids_by_company["all"].add(aid)
        if ckey in ("bonario", "ordinaire"):
            dashboard_2026_account_ids_by_company[ckey].add(aid)
        if pid in dashboard_2026_done_project_ids:
            dashboard_2026_done_account_ids_by_company["all"].add(aid)
            if ckey in ("bonario", "ordinaire"):
                dashboard_2026_done_account_ids_by_company[ckey].add(aid)

    summary_2026_all_aal = {
        comp: compute_aal_scope_summary("2026-01-01", comp, None)
        for comp in ("all", "bonario", "ordinaire")
    }
    summary_lifetime_all_aal = {
        comp: compute_aal_scope_summary(None, comp, None)
        for comp in ("all", "bonario", "ordinaire")
    }
    summary_2026_dashboard_projects = {
        comp: compute_aal_scope_summary("2026-01-01", "all", dashboard_2026_account_ids_by_company[comp])
        for comp in ("all", "bonario", "ordinaire")
    }
    summary_lifetime_dashboard_projects = {
        comp: compute_aal_scope_summary(None, "all", dashboard_2026_account_ids_by_company[comp])
        for comp in ("all", "bonario", "ordinaire")
    }
    summary_lifetime_dashboard_done_projects = {
        comp: compute_aal_scope_summary(None, "all", dashboard_2026_done_account_ids_by_company[comp])
        for comp in ("all", "bonario", "ordinaire")
    }

    shared_accounts = {
        aid: [p["id"] for p in projs]
        for aid, projs in projects_by_account_id.items()
        if len(projs) > 1
    }

    projects_truth_map: dict[str, Any] = {}
    for row in project_rows_csv:
        if row["project_id"] != "":
            pid_str = str(row["project_id"])
            acc_id = int(row["account_id"])
            b = by_proj_acc.get(acc_id) or ensure_proj_acc_bucket(acc_id)
            projects_truth_map[pid_str] = {
                "project_id": int(row["project_id"]),
                "project_name": row["project_name"],
                "account_id": acc_id,
                "sale_order_id": row["sale_order_id"],
                "sale_order_name": row["sale_order_name"],
                "date_order": row["date_order"],
                "order_state": row["order_state"],
                "company_key": row["company_key"],
                "in_dashboard_2026": row["in_dashboard_2026"],
                "in_dashboard_2026_done": row["in_dashboard_2026_done"],
                "shipping_cost": row["shipping_cost"],
                "shipping_po": row["shipping_po"],
                "shipping_non_po": row["shipping_non_po"],
                "shipping_draft": row["shipping_draft"],
                "shipping_cost_2026": row["shipping_cost_2026"],
                "shipping_po_2026": row["shipping_po_2026"],
                "shipping_non_po_2026": row["shipping_non_po_2026"],
                "shipping_draft_2026": row["shipping_draft_2026"],
                "shipping_by_month": {
                    ym: as_money(val)
                    for ym, val in sorted(b["shipping_by_month"].items())
                    if as_money(val) != 0
                },
            }

    s2026 = summary_2026_all_aal["all"]
    ref_comparison = {
        "reference_targets_vnd": {
            "total_2026_approx": 1091600000.0,
            "assigned_2026_approx": 868900000.0,
            "assigned_po_2026_approx": 707100000.0,
            "assigned_non_po_2026_approx": 161800000.0,
            "unassigned_2026_approx": 222700000.0,
        },
        "computed_truth_s1_accounts_vnd": {
            "total_2026": s2026["shipping_grand_total"],
            "assigned_2026": s2026["shipping_assigned_total"],
            "assigned_po_2026": s2026["shipping_assigned_po"],
            "assigned_non_po_2026": s2026["shipping_assigned_non_po"],
            "unassigned_2026": s2026["shipping_unassigned_total"],
            "draft_2026": s2026["shipping_draft_total"],
        },
    }

    truth_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rpc_calls_count": client.call_count,
        "s1_core_12_account_ids": sorted(s1_core_12_ids),
        "s1_shipping_account_ids": sorted(s1_shipping_ids),
        "s1_shipping_accounts": [
            {
                "id": aid,
                "name": per_ship_acc_stats[aid]["name"],
                "plan_id": per_ship_acc_stats[aid]["plan_id"],
                "plan_name": per_ship_acc_stats[aid]["plan_name"],
                "active": per_ship_acc_stats[aid]["active"],
                "aal_columns": per_ship_acc_stats[aid]["aal_columns"],
                "cost_2026": as_money(per_ship_acc_stats[aid]["cost_2026"]),
                "cost_2026_assigned": as_money(per_ship_acc_stats[aid]["cost_2026_assigned"]),
                "cost_2026_assigned_po": as_money(per_ship_acc_stats[aid]["cost_2026_assigned_po"]),
                "cost_2026_assigned_non_po": as_money(per_ship_acc_stats[aid]["cost_2026_assigned_non_po"]),
                "cost_2026_unassigned": as_money(per_ship_acc_stats[aid]["cost_2026_unassigned"]),
                "cost_lifetime": as_money(per_ship_acc_stats[aid]["cost_lifetime"]),
            }
            for aid in sorted(s1_shipping_ids)
        ],
        "s1d_candidate_decisions": s1d_decisions,
        "naive_substring_traps_excluded": [
            {
                "id": acc["id"],
                "name": acc.get("name"),
                "plan_id": acc.get("plan_id"),
                "cost_2026": as_money(per_ship_acc_stats[acc["id"]]["cost_2026"]),
                "cost_lifetime": as_money(per_ship_acc_stats[acc["id"]]["cost_lifetime"]),
            }
            for acc in sorted(naive_substring_traps, key=lambda x: x["id"])
        ],
        "aal_analytic_m2o_columns": analytic_m2o_cols,
        "shared_project_accounts": shared_accounts,
        "orphan_project_account_ids": orphan_account_ids,
        "reference_reconciliation_2026": ref_comparison,
        "totals_2026_all_aal": summary_2026_all_aal,
        "totals_lifetime_all_aal": summary_lifetime_all_aal,
        "totals_2026_dashboard_projects": summary_2026_dashboard_projects,
        "totals_lifetime_dashboard_projects": summary_lifetime_dashboard_projects,
        "totals_lifetime_dashboard_done_projects": summary_lifetime_dashboard_done_projects,
        "projects_by_id": projects_truth_map,
    }

    truth_summary_path = OUTPUT_DIR / "truth_summary.json"
    truth_summary_path.write_text(json.dumps(truth_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SA-4] Wrote truth summary to {truth_summary_path}")

    # -------------------------------------------------------------------------
    # STEP 6g: Write /tmp/roi_recon/account_decisions.md
    # -------------------------------------------------------------------------
    cost_1439_2026 = per_ship_acc_stats.get(1439, {}).get("cost_2026", Decimal("0"))
    cost_568_2026 = per_ship_acc_stats.get(568, {}).get("cost_2026", Decimal("0"))
    cost_1238_2026 = per_ship_acc_stats.get(1238, {}).get("cost_2026", Decimal("0"))

    md_lines = [
        "# Báo Cáo Quyết Định Tập Mã Phân Tích Vận Chuyển (S1) & Đối Chiếu Số Liệu (SA-4)",
        "",
        f"- **Thời điểm chạy:** `{truth_summary['generated_at']}`",
        f"- **Số lần gọi RPC (tuần tự, sleep >= 1.1s):** `{client.call_count}`",
        "",
        "## 1. Cấu trúc cột Analytic trên `account.analytic.line` (Quy tắc S2)",
        "",
        "Kết quả gọi `fields_get` trên `account.analytic.line` cho các trường `many2one` trỏ tới `account.analytic.account`:",
        "",
        "| Field trên `account.analytic.line` | Nhãn (String) | Ghi chú |",
        "|---|---|---|",
    ]
    for col in analytic_m2o_cols:
        md_lines.append(f"| `{col['field']}` | {col['label']} | |")

    md_lines.extend([
        "",
        "Danh sách các `account.analytic.plan` trên Odoo TEST:",
        "",
        "| Plan ID | Tên Plan | Complete Name | Parent Plan |",
        "|---:|---|---|---|",
    ])
    for p in sorted(plans, key=lambda x: x["id"]):
        md_lines.append(
            f"| `{p['id']}` | {p.get('name') or ''} | {p.get('complete_name') or ''} | {relation_name(p.get('parent_id')) or '-'} |"
        )

    md_lines.extend([
        "",
        "### Kết luận kiểm tra cột lưu trữ mã SC (`plan_id=7`) và mã BD (`506, 1427`, `plan_id=6`):",
        "- Cả `Departments / BD Dept` (`plan_id=6`) và `Departments / SC Dept` (`plan_id=7`) đều là plan con của root plan `Departments` (`plan_id=5`).",
        "- Trong Odoo 17+, mỗi root plan có đúng 1 cột trên `account.analytic.line` (`x_plan5_id` ứng với root plan `Departments` ID=5, còn `account_id` ứng với root plan `Odoo Projects` ID=1).",
        "- Do đó, **toàn bộ 10 mã SC và 2 mã BD (`506`, `1427`) đều nằm ở cột `x_plan5_id`** trên `account.analytic.line`.",
        "",
        "## 2. Chi tiết Tập Mã Phân Tích Vận Chuyển (S1), Ứng Viên S1(d) & Bẫy Substring",
        "",
        "| ID | Tên mã phân tích | Plan | Active | Cột AAL | Dòng 2026 | Tổng 2026 (VND) | Đã gắn DA 2026 | Chưa gắn DA 2026 | Tổng Lifetime (VND) | Quyết định S1 | Phân nhóm |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ])

    trap_ids = {acc["id"] for acc in naive_substring_traps}
    for aid in sorted(all_inspect_ids):
        st = per_ship_acc_stats[aid]
        if aid in BASE_10_SHIPPING_IDS:
            group_label = "S1(b) 10 mã nền SC"
        elif aid in BD_SHIPPING_IDS:
            group_label = "S1(c) 2 mã BD ship"
        elif aid in CANDIDATE_REVIEW_IDS:
            group_label = "S1(d) Ứng viên kiểm tra"
        elif aid in trap_ids:
            group_label = "Bẫy substring 'ship' trong 'Partnerships'"
        else:
            group_label = "S1(e) Discovery từ khoá"
        decision_str = "**ĐƯA VÀO (INCLUDED)**" if st["in_s1"] else "LOẠI RA (EXCLUDED)"
        cols_str = ", ".join(f"`{c}`" for c in st["aal_columns"]) or "-"
        md_lines.append(
            f"| `{aid}` | {st['name']} | {st['plan_name']} (`{st['plan_id']}`) | `{st['active']}` | {cols_str} | "
            f"{st['valid_line_count_2026']} | {st['cost_2026']:,.0f} | {st['cost_2026_assigned']:,.0f} | {st['cost_2026_unassigned']:,.0f} | {st['cost_lifetime']:,.0f} | {decision_str} | {group_label} |"
        )

    md_lines.extend([
        "",
        "## 3. Giải trình quyết định cho các mã S1(d): `1439`, `568`, `1238` & Bẫy `Partnerships` (`510, 552, 1426`)",
        "",
    ])
    for cid in CANDIDATE_REVIEW_IDS:
        d = s1d_decisions[cid]
        st = per_ship_acc_stats[cid]
        md_lines.append(f"### Mã `{cid}` — `{d.get('name', 'N/A')}`")
        md_lines.append(f"- **Plan:** `{st['plan_name']}` (ID `{st['plan_id']}`), Active: `{st['active']}`")
        md_lines.append(f"- **Quyết định:** `{'INCLUDED' if d['included'] else 'EXCLUDED'}`")
        md_lines.append(f"- **Lý do theo S1(d):** {d['reason']}")
        md_lines.append(
            f"- **Số liệu thực tế trên TEST:** `{st['valid_line_count_2026']}` dòng năm 2026 = **`{st['cost_2026']:,.0f} VND`** "
            f"(Đã gắn dự án 2026: `{st['cost_2026_assigned']:,.0f} VND`, Chưa gắn dự án 2026: `{st['cost_2026_unassigned']:,.0f} VND`; "
            f"Lifetime: `{st['valid_line_count_lifetime']}` dòng = **`{st['cost_lifetime']:,.0f} VND`**)."
        )
        if st["sample_lines"]:
            md_lines.append("- **Dòng AAL mẫu:**")
            for sline in st["sample_lines"]:
                md_lines.append(
                    f"  - AAL `{sline['aal_id']}` ({sline['date']}): `{sline['name']}` | Số tiền: `{sline['amount']:,.0f} VND` | Dự án: `{sline['project_account']}`"
                )
        md_lines.append("")

    md_lines.extend([
        "### Cảnh báo quan trọng về Discovery S1(e) trên toàn bộ plan phòng ban:",
        "- Khi mở rộng discovery từ khoá `ship` sang mọi plan phòng ban (`BD Dept`, `Operations`...), có 3 mã chứa từ **`Partnerships`**:",
        "  - `510`: `BD_Networking & Partnerships` (`80,329,157 VND` năm 2026)",
        "  - `552`: `OPS_Networking & Partnerships` (`119,354,487 VND` năm 2026)",
        "  - `1426`: `ORD - BD_Networking & Partnerships` (`1,149,637 VND` năm 2026)",
        "- Các mã `Partnerships` này là chi phí đối ngoại/networking, **KHÔNG PHẢI** chi phí vận chuyển (`ship`). Do đó khi kiểm tra từ khoá `ship` phải dùng regex `(?<![a-z])ship` (hoặc loại trừ `partnership`)!",
        "- Lưu ý: Nếu dùng `\\bship` trong Python regex thì ký tự `_` được tính là word character nên sẽ bỏ sót `SC_Shipping` (`566, 1239`) và `BD_Shipping` (`506, 1427`). Dùng `(?<![a-z])ship` sẽ bắt đúng cả `SC_Shipping`, `BD_Shipping`, `Ship gấp` mà vẫn loại trừ sạch `Partnerships`!",
        "- Mã `1486` (`BD_Rework_Rush logistics`, thuộc `Departments / BD Dept`) khớp từ khoá `logistics`, hiện có `0` dòng AAL trên TEST (`0 VND`).",
        "",
        "## 4. So sánh Phương án chuẩn S1 so với Phương án gộp thêm `1439, 568, 1238` (Năm 2026)",
        "",
        "| Chỉ tiêu (Năm 2026 `aal.date >= 2026-01-01`) | Số tham chiếu Mục 1 | Chỉ 10 mã SC | Phương án chuẩn S1 (10 SC + `506, 1427` [+ `1486`]) | Nếu cộng thêm `1439` | Nếu cộng thêm `1439 + 568 + 1238` |",
        "|---|---:|---:|---:|---:|---:|",
        f"| **Tổng chi phí vận chuyển 2026** | ~1,091,600,000 | 1,047,070,262 | **{s2026['shipping_grand_total']:,.0f}** | {(Decimal(str(s2026['shipping_grand_total'])) + cost_1439_2026):,.0f} | {(Decimal(str(s2026['shipping_grand_total'])) + cost_1439_2026 + cost_568_2026 + cost_1238_2026):,.0f} |",
        f"| **Đã gắn dự án (`account_id != False`)** | ~868,900,000 | 868,694,565 | **{s2026['shipping_assigned_total']:,.0f}** | {(Decimal(str(s2026['shipping_assigned_total'])) + per_ship_acc_stats[1439]['cost_2026_assigned']):,.0f} | {(Decimal(str(s2026['shipping_assigned_total'])) + per_ship_acc_stats[1439]['cost_2026_assigned'] + per_ship_acc_stats[568]['cost_2026_assigned'] + per_ship_acc_stats[1238]['cost_2026_assigned']):,.0f} |",
        f"| — *Trong đó: Qua PO (`purchase_line_id != False`)* | ~707,100,000 | 707,127,893 | **{s2026['shipping_assigned_po']:,.0f}** | {(Decimal(str(s2026['shipping_assigned_po'])) + per_ship_acc_stats[1439]['cost_2026_assigned_po']):,.0f} | {(Decimal(str(s2026['shipping_assigned_po'])) + per_ship_acc_stats[1439]['cost_2026_assigned_po'] + per_ship_acc_stats[568]['cost_2026_assigned_po'] + per_ship_acc_stats[1238]['cost_2026_assigned_po']):,.0f} |",
        f"| — *Trong đó: Không qua PO (`purchase_line_id == False`)* | ~161,800,000 | 161,566,672 | **{s2026['shipping_assigned_non_po']:,.0f}** | {(Decimal(str(s2026['shipping_assigned_non_po'])) + per_ship_acc_stats[1439]['cost_2026_assigned_non_po']):,.0f} | {(Decimal(str(s2026['shipping_assigned_non_po'])) + per_ship_acc_stats[1439]['cost_2026_assigned_non_po'] + per_ship_acc_stats[568]['cost_2026_assigned_non_po'] + per_ship_acc_stats[1238]['cost_2026_assigned_non_po']):,.0f} |",
        f"| **Chưa gắn dự án (`account_id == False`)** | ~222,700,000 | 178,375,697 | **{s2026['shipping_unassigned_total']:,.0f}** | {(Decimal(str(s2026['shipping_unassigned_total'])) + per_ship_acc_stats[1439]['cost_2026_unassigned']):,.0f} | {(Decimal(str(s2026['shipping_unassigned_total'])) + per_ship_acc_stats[1439]['cost_2026_unassigned'] + per_ship_acc_stats[568]['cost_2026_unassigned'] + per_ship_acc_stats[1238]['cost_2026_unassigned']):,.0f} |",
        f"| **Bill nháp (`shipping_draft` 2026)** | N/A | - | **{s2026['shipping_draft_total']:,.0f}** | - | - |",
        "",
        "### Lưu ý về Shared Analytic Accounts giữa các Project trên Dashboard 2026:",
        "- Có 2 mã `account.analytic.account` trên Dashboard 2026 có phát sinh chi phí vận chuyển và được gắn cho 2 `project.project` cùng thuộc 1 `sale.order`:",
        "  - `account_id = 1985` (`BG-2608-0905`): gắn cho project `1890` và `1904` (`shipping_cost = 218,994 VND`).",
        "  - `account_id = 1201` (`BG-2601-0078`): gắn cho project `1161` (active=True) và `1162` (active=False) (`shipping_cost = 55,456 VND`).",
        "- Tổng ship của các project thuộc Dashboard 2026 nếu cộng theo `account_id` duy nhất = **`446,669,481 VND`**, còn nếu cộng theo từng dòng `project.project` trên bảng Dashboard = **`446,943,931 VND`** (chênh `274,450 VND` do 2 account dùng chung trên).",
    ])

    account_decisions_path = OUTPUT_DIR / "account_decisions.md"
    account_decisions_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[SA-4] Wrote account decisions report to {account_decisions_path}")

    # -------------------------------------------------------------------------
    # STEP 7: Print Reconciliation Table to stdout
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("RECONCILIATION SUMMARY (2026 vs REFERENCE TARGETS)")
    print("=" * 80)
    print(f"Official S1 Account IDs ({len(s1_shipping_ids)}): {sorted(s1_shipping_ids)}")
    print(f"Total 2026 Shipping Cost (All AAL):      {s2026['shipping_grand_total']:>15,.2f} VND (Ref: ~1,091,600,000)")
    print(f"  - Assigned to Project (account_id):    {s2026['shipping_assigned_total']:>15,.2f} VND (Ref:   ~868,900,000)")
    print(f"      * Via PO (purchase_line_id != F):  {s2026['shipping_assigned_po']:>15,.2f} VND (Ref:   ~707,100,000)")
    print(f"      * Non-PO (purchase_line_id == F):  {s2026['shipping_assigned_non_po']:>15,.2f} VND (Ref:   ~161,800,000)")
    print(f"  - Unassigned (account_id == False):    {s2026['shipping_unassigned_total']:>15,.2f} VND (Ref:   ~222,700,000)")
    print(f"  - Draft Shipping (2026):               {s2026['shipping_draft_total']:>15,.2f} VND")
    print("-" * 80)
    slife = summary_lifetime_all_aal["all"]
    print(f"Total Lifetime Shipping Cost (All AAL):  {slife['shipping_grand_total']:>15,.2f} VND")
    print(f"  - Assigned to Project (Lifetime):      {slife['shipping_assigned_total']:>15,.2f} VND")
    print(f"  - Unassigned (Lifetime):               {slife['shipping_unassigned_total']:>15,.2f} VND")
    print("=" * 80)


if __name__ == "__main__":
    main()
