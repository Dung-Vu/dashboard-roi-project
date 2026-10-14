"""Synthetic Odoo client and synthetic dataset builders for offline testing.

Strictly enforces the production guard and never uses real customer names
or makes network requests.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from odoo_client import OdooAPIError, PROD_DB, PROD_HOST, ProdBlockedError

PROD_BLOCKED_HOST = PROD_HOST

SYNTHETIC_CUSTOMER_ALPHA = "Công ty TNHH Alpha (Synthetic)"
SYNTHETIC_CUSTOMER_BETA = "Khách hàng Beta"
SYNTHETIC_VENDOR_GAMMA = "Nhà vận chuyển Gamma"

FIXED_SHIPPING_IDS = (518, 1237, 566, 1239, 1270, 1271, 1518, 1519, 1522, 1523)
BD_SHIPPING_IDS = (506, 1427)


def assert_not_prod_url(url: str | None) -> None:
    """Hard guard: block any attempt to target production Odoo."""
    if url and PROD_BLOCKED_HOST in str(url).lower():
        raise ProdBlockedError("PROD BLOCKED")


class SyntheticOdooClient:
    """In-memory Odoo client supporting domain evaluation, active_test, field projection, and error injection."""

    def __init__(
        self,
        records: dict[str, list[dict[str, Any]]] | None = None,
        conversions: dict[int, Decimal | float | Exception] | None = None,
        panels: dict[int, dict[str, Any] | Exception] | None = None,
        field_relations: dict[tuple[str, str], str] | None = None,
        url: str = "http://localhost:8069",
        db: str = "synthetic_test_db",
        error_on_models: dict[str, Exception] | None = None,
        error_on_methods: dict[tuple[str, str], Exception] | None = None,
    ) -> None:
        assert_not_prod_url(url)
        if db == PROD_DB:
            raise ProdBlockedError("PROD BLOCKED")
        self.records: dict[str, list[dict[str, Any]]] = records or {}
        self.conversions: dict[int, Decimal | float | Exception] = conversions or {}
        self.panels: dict[int, dict[str, Any] | Exception] = panels or {}
        self.field_relations: dict[tuple[str, str], str] = field_relations or {
            ("sale.order", "x_sale_order_tag_ids"): "crm.tag",
        }
        self.url = url
        self.db = db
        self.uid = 1
        self.api_key = "synthetic_api_key_do_not_use"
        self.error_on_models: dict[str, Exception] = error_on_models or {}
        self.error_on_methods: dict[tuple[str, str], Exception] = error_on_methods or {}
        self.calls: list[tuple[Any, ...]] = []

    def simulate_429(self, model: str | None = None, method: str = "search_read") -> None:
        """Configure the client to raise HTTP 429 OdooAPIError on the specified model/method."""
        err = OdooAPIError("HTTP 429 Too Many Requests", model=model or "", method=method)
        if model and method:
            self.error_on_methods[(model, method)] = err
        elif model:
            self.error_on_models[model] = err
        else:
            self.error_on_models["*"] = err

    def clear_errors(self) -> None:
        self.error_on_models.clear()
        self.error_on_methods.clear()

    def _check_injected_error(self, model: str, method: str) -> None:
        assert_not_prod_url(self.url)
        if "*" in self.error_on_models:
            raise self.error_on_models["*"]
        if (model, method) in self.error_on_methods:
            raise self.error_on_methods[(model, method)]
        if model in self.error_on_models:
            raise self.error_on_models[model]

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str] | None = None,
        limit: int = 0,
        offset: int = 0,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(("search_read", model, domain, fields, context))
        self._check_injected_error(model, "search_read")

        active_test = True
        if isinstance(context, dict) and context.get("active_test") is False:
            active_test = False

        raw_records = [dict(r) for r in self.records.get(model, [])]
        if active_test:
            raw_records = [r for r in raw_records if r.get("active", True) is not False]

        matches = [r for r in raw_records if self._matches(r, domain, model=model)]
        if offset:
            matches = matches[offset:]
        if limit:
            matches = matches[:limit]

        if fields is not None:
            allowed = {"id"} | set(fields)
            matches = [{k: v for k, v in r.items() if k in allowed} for r in matches]

        return matches

    def call_method(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        kwargs = kwargs or {}
        context = kwargs.get("context")
        self.calls.append(("call_method", model, method, args, kwargs))
        self._check_injected_error(model, method)

        if method == "search_read":
            domain = args[0] if args else []
            fields = kwargs.get("fields")
            limit = kwargs.get("limit", 0)
            offset = kwargs.get("offset", 0)
            return self.search_read(
                model,
                domain,
                fields=fields,
                limit=limit,
                offset=offset,
                context=context,
            )

        if model == "res.currency" and method == "_convert":
            currency_id = args[0][0] if args and isinstance(args[0], (list, tuple)) else args[0]
            amount = Decimal(str(args[1]))
            conv = self.conversions.get(currency_id, amount)
            if isinstance(conv, Exception):
                raise conv
            if callable(conv):
                return conv(amount, args)
            return conv

        if model == "project.project" and method == "get_panel_data":
            project_id = args[0][0]
            panel = self.panels.get(project_id, {})
            if isinstance(panel, Exception):
                raise panel
            return panel

        if method == "fields_get":
            field_names = args[0] if args else []
            return {
                field: {"relation": self.field_relations.get((model, field))}
                for field in field_names
                if self.field_relations.get((model, field))
            }

        if method == "write":
            ids = args[0] if args else []
            vals = args[1] if args and len(args) > 1 else {}
            for rec in self.records.get(model, []):
                if rec.get("id") in ids:
                    rec.update(vals)
            return True

        return {}

    def test_connection(self) -> dict[str, Any]:
        assert_not_prod_url(self.url)
        return {"ok": True, "user": {"id": self.uid, "name": "Synthetic Tester", "login": "tester"}}

    def _matches(self, record: dict[str, Any], domain: list[Any], model: str = "") -> bool:
        if not domain:
            return True

        stack: list[bool] = []
        for token in reversed(domain):
            if token == "!":
                operand = stack.pop() if stack else True
                stack.append(not operand)
            elif token == "|":
                left = stack.pop() if stack else False
                right = stack.pop() if stack else False
                stack.append(left or right)
            elif token == "&":
                left = stack.pop() if stack else True
                right = stack.pop() if stack else True
                stack.append(left and right)
            elif isinstance(token, (list, tuple)) and len(token) == 3:
                stack.append(self._eval_leaf(record, token, model=model))
            else:
                stack.append(True)

        return all(stack)

    def _eval_leaf(self, record: dict[str, Any], condition: list[Any] | tuple[Any, ...], model: str = "") -> bool:
        field, operator, value = condition
        actual = self._get_field(record, field, model=model)
        comparable = self._comparable_value(actual)

        if operator == "=":
            if value is False or value is None:
                return actual is False or actual is None or actual == []
            return comparable == value

        if operator == "!=":
            if value is False or value is None:
                return not (actual is False or actual is None or actual == [])
            return comparable != value

        if operator == "in":
            return self._matches_in(actual, value)

        if operator == "not in":
            return not self._matches_in(actual, value)

        if operator in (">=", "<=", ">", "<"):
            if comparable is None or comparable is False:
                return False
            if isinstance(comparable, (int, float, Decimal)) and isinstance(value, (int, float, Decimal)):
                c_num = Decimal(str(comparable))
                v_num = Decimal(str(value))
                if operator == ">=":
                    return c_num >= v_num
                if operator == "<=":
                    return c_num <= v_num
                if operator == ">":
                    return c_num > v_num
                if operator == "<":
                    return c_num < v_num
            c_str = str(comparable)
            v_str = str(value)
            if operator == ">=":
                return c_str >= v_str
            if operator == "<=":
                return c_str <= v_str
            if operator == ">":
                return c_str > v_str
            if operator == "<":
                return c_str < v_str

        if operator in ("ilike", "like", "=ilike"):
            needle = str(value or "").lower()
            if isinstance(actual, dict):
                haystack = json.dumps(actual).lower()
            elif isinstance(actual, (list, tuple)) and len(actual) > 1 and isinstance(actual[1], str):
                haystack = f"{actual[0]} {actual[1]}".lower()
            else:
                haystack = str(actual or "").lower()
            return needle in haystack

        return True

    def _matches_in(self, actual: Any, values: list[Any] | set[Any] | tuple[Any, ...]) -> bool:
        if not isinstance(values, (list, tuple, set, frozenset)):
            values = [values]
        normalized_values = set()
        for v in values:
            if v is False or v is None:
                normalized_values.add(False)
                normalized_values.add(None)
            else:
                normalized_values.add(v)

        if actual is False or actual is None:
            return False in normalized_values or None in normalized_values

        comparable = self._comparable_value(actual)
        if isinstance(comparable, list):
            if not comparable:
                return False in normalized_values
            return any(item in normalized_values for item in comparable)
        return comparable in normalized_values

    def _comparable_value(self, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
                return value[0]
            if value and all(isinstance(x, (list, tuple)) and x and isinstance(x[0], int) for x in value):
                return [x[0] for x in value]
        return value

    def _get_field(self, record: dict[str, Any], field: str, model: str = "") -> Any:
        if field in record:
            return record[field]
        if "." not in field:
            return record.get(field)

        parts = field.split(".")
        current: Any = record
        for idx, part in enumerate(parts):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, (list, tuple)) and len(current) >= 2 and isinstance(current[0], int):
                if part == "id":
                    current = current[0]
                elif part == "name":
                    current = current[1]
                else:
                    rel_id = current[0]
                    rel_field_name = parts[idx - 1]
                    rel_model = self._guess_relation_model(model, rel_field_name)
                    rel_rec = self._find_record_by_id(rel_model, rel_id) if rel_model else None
                    current = rel_rec.get(part) if rel_rec else None
            else:
                return None
        return current

    def _guess_relation_model(self, model: str, field_name: str) -> str | None:
        if (model, field_name) in self.field_relations:
            return self.field_relations[(model, field_name)]
        mapping = {
            "order_id": "purchase.order" if "purchase" in model else "sale.order",
            "sale_order_id": "sale.order",
            "move_id": "account.move",
            "move_line_id": "account.move.line",
            "plan_id": "account.analytic.plan",
            "company_id": "res.company",
            "account_id": "account.analytic.account",
            "purchase_line_id": "purchase.order.line",
        }
        return mapping.get(field_name)

    def _find_record_by_id(self, model: str, rec_id: int) -> dict[str, Any] | None:
        for r in self.records.get(model, []):
            if r.get("id") == rec_id:
                return r
        return None


def build_base_synthetic_records() -> dict[str, list[dict[str, Any]]]:
    """Return a clean baseline synthetic dataset for companies, tags, and shipping accounts."""
    return {
        "res.company": [
            {"id": 1, "name": "Bonario Synthetic", "currency_id": [1, "VND"], "active": True},
            {"id": 2, "name": "Ordinaire Synthetic", "currency_id": [1, "VND"], "active": True},
        ],
        "crm.tag": [
            {"id": 101, "name": "Nội thất rời"},
            {"id": 102, "name": "Rèm"},
            {"id": 103, "name": "Giấy dán tường"},
            {"id": 104, "name": "Vải nội thất"},
        ],
        "account.analytic.account": [
            {"id": 518, "name": "2-SC_Logistics", "plan_id": [7, "Departments / SC Dept"], "active": False},
            {"id": 1237, "name": "[ORD] 2-SC_Logistics", "plan_id": [7, "Departments / SC Dept"], "active": False},
            {"id": 506, "name": "BD_Shipping (CLT, demo...)", "plan_id": [6, "Departments / BD Dept"], "active": True},
            {"id": 1427, "name": "ORD - BD_Shipping (CLT, demo...)", "plan_id": [6, "Departments / BD Dept"], "active": True},
            {"id": 1486, "name": "BD_Rework_Rush logistics", "plan_id": [6, "Departments / BD Dept"], "active": True},
            {"id": 1439, "name": "SC_Trips in processing SO", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 568, "name": "SC_Car related (fuel, maintainnance...)", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1519, "name": "SC - Logistics OPS", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1518, "name": "SC - Logistics SO", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1271, "name": "SC - Rush logistics - Ship gấp", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 566, "name": "SC_Shipping (CLT, demo...)", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1522, "name": "[ORD] SC - Logistics OPS", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1523, "name": "[ORD] SC - Logistics SO", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1270, "name": "[ORD] SC - Rush logistics - Ship gấp", "plan_id": [7, "Departments / SC Dept"], "active": True},
            {"id": 1239, "name": "[ORD] SC_Shipping (CLT, demo...)", "plan_id": [7, "Departments / SC Dept"], "active": True},
        ],
    }
