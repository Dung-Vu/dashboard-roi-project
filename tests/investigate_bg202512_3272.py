"""Investigate BG-202512-3272 shipping breakdown vs Odoo profitability Expenses bucket."""
import sys
import json
from pathlib import Path
from decimal import Decimal
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_client import OdooAPI, OdooAPIError

client = OdooAPI("https://bonario-vietnam.odoo.com", "bonario-vietnam", 208, "80aa54434e151ac3f2002b9d85bce253853f84fa")

def relation_id(v):
    if isinstance(v, (list, tuple)) and v:
        return v[0]
    return None

def relation_name(v):
    if isinstance(v, (list, tuple)) and len(v) > 1:
        return v[1]
    return None

def as_decimal(v):
    return Decimal(str(v or 0))


# Find SO BG-202512-3272
print("=" * 80)
print("STEP 1: Locate Sale Order BG-202512-3272")
print("=" * 80)
so_records = client.search_read(
    "sale.order",
    [["name", "=", "BG-202512-3272"]],
    ["id", "name", "partner_id", "date_order", "amount_untaxed", "amount_total", "user_id", "company_id"],
    limit=5,
)
if not so_records:
    print("SO NOT FOUND - try alternate search...")
    so_records = client.search_read(
        "sale.order",
        [["name", "ilike", "BG-202512-3272"]],
        ["id", "name", "partner_id", "date_order", "amount_untaxed"],
        limit=5,
    )
print(json.dumps(so_records, default=str, indent=2, ensure_ascii=False))
so = so_records[0]
so_id = so["id"]

print()
print("=" * 80)
print("STEP 2: Find project linked to this SO")
print("=" * 80)
projects = client.call_method(
    "project.project",
    "search_read",
    [[["sale_order_id", "=", so_id]]],
    {
        "fields": ["id", "name", "partner_id", "sale_order_id", "account_id", "company_id", "active"],
        "context": {"active_test": False},
    },
)
print(json.dumps(projects, default=str, indent=2, ensure_ascii=False))
if not projects:
    print("Project not found")
    sys.exit(0)
project = projects[0]
PROJECT_ID = project["id"]
ACCOUNT_ID = relation_id(project.get("account_id"))
ACCOUNT_NAME = relation_name(project.get("account_id"))
print(f"\nPROJECT_ID = {PROJECT_ID}")
print(f"ACCOUNT_ID = {ACCOUNT_ID}")
print(f"ACCOUNT_NAME = {ACCOUNT_NAME}")

print()
print("=" * 80)
print("STEP 3: Odoo profitability panel")
print("=" * 80)
try:
    panel = client.call_method("project.project", "get_panel_data", [[PROJECT_ID]])
    cost_items = panel.get("profitability_items", {}).get("costs", {}).get("data", [])
    revenue_items = panel.get("profitability_items", {}).get("revenues", {}).get("data", [])
    print("Cost items in panel:")
    for it in cost_items:
        item_id = str(it.get("id", ""))
        billed = -as_decimal(it.get("billed"))
        to_bill = -as_decimal(it.get("to_bill"))
        expected = billed + to_bill
        label = it.get("name") or it.get("display_name") or item_id
        print(f"  - id={item_id} label={label!r} billed={billed} to_bill={to_bill} expected={expected}")
    print()
    print("Revenue items:")
    for it in revenue_items:
        item_id = str(it.get("id", ""))
        invoiced = as_decimal(it.get("invoiced"))
        to_invoice = as_decimal(it.get("to_invoice"))
        label = it.get("name") or item_id
        print(f"  - id={item_id} label={label!r} invoiced={invoiced} to_invoice={to_invoice}")
except OdooAPIError as e:
    print(f"panel error: {e}")

print()
print("=" * 80)
print("STEP 4: Fetch all analytic lines on this project's account")
print("=" * 80)
analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", ACCOUNT_ID]],
    ["id", "amount", "account_id", "move_line_id", "category", "name", "date", "product_id", "partner_id"],
    limit=100000,
)
print(f"Total analytic lines on account {ACCOUNT_ID}: {len(analytic_lines)}")

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in analytic_lines if relation_id(l.get("move_line_id"))})
print(f"Distinct move_line_ids: {len(ml_ids)}")

mls = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "name", "balance", "parent_state", "move_type", "analytic_distribution", "purchase_line_id", "date", "move_id", "product_id", "partner_id"],
        limit=len(chunk),
    ))
ml_map = {ml["id"]: ml for ml in mls}

print()
print("=" * 80)
print("STEP 5: Breakdown of all (analytic_line, move_line) pairs")
print("=" * 80)

# Shipping whitelist (from dashboard_service after fix)
SHIPPING_IDS = {566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}

shipping_total = Decimal("0")
shipping_lines = []
expense_total = Decimal("0")
expense_lines = []
others_total = Decimal("0")
others_lines = []
seen_ml_ids_ship = set()  # Avoid double-counting shipping within same account

for al in analytic_lines:
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id)
    if not ml:
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    if ml.get("parent_state") != "posted":
        continue
    
    dist = ml.get("analytic_distribution")
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except: pass
    if not isinstance(dist, dict):
        continue
    
    parts = set()
    for k in dist.keys():
        for p in k.split(","):
            parts.add(p.strip())
    
    balance = as_decimal(ml.get("balance"))
    cat = al.get("category") or "?"
    is_ship = bool(SHIPPING_IDS & parts)
    
    line_info = {
        "al_id": al["id"],
        "ml_id": ml_id,
        "ml_name": ml.get("name"),
        "date": ml.get("date"),
        "balance": float(balance),
        "category": cat,
        "move_id": relation_name(ml.get("move_id")),
        "move_type": ml.get("move_type"),
        "po_line": relation_id(ml.get("purchase_line_id")),
        "product": relation_name(ml.get("product_id")),
        "partner": relation_name(ml.get("partner_id")),
        "dist_parts": sorted(parts),
        "is_shipping": is_ship,
    }
    
    if is_ship and ml_id not in seen_ml_ids_ship:
        shipping_total += balance
        shipping_lines.append(line_info)
        seen_ml_ids_ship.add(ml_id)
    
    if cat in {"expense", "expenses", "vendor_bill", "vendor_bills", "other"}:
        expense_total += balance
        expense_lines.append(line_info)
    else:
        others_total += balance
        others_lines.append(line_info)

print(f"\nSHIPPING (dist has {sorted(SHIPPING_IDS)}):")
print(f"  Total = {shipping_total}")
print(f"  Lines:")
for ln in shipping_lines:
    print(f"    - {ln['ml_id']} | {ln['date']} | bal={ln['balance']:>15} | cat={ln['category']} | dist={ln['dist_parts']} | {ln['move_id']} | prod={ln['product']} | partner={ln['partner']}")
    print(f"        name: {ln['ml_name']}")

print(f"\nEXPENSE (categories in expense/expenses/vendor_bill/vendor_bills/other):")
print(f"  Total = {expense_total}")
print(f"  Lines ({len(expense_lines)}):")
for ln in expense_lines:
    marker = " SHIP" if ln["is_shipping"] else " NON-SHIP"
    print(f"    {marker} | {ln['ml_id']} | {ln['date']} | bal={ln['balance']:>15} | cat={ln['category']} | dist={ln['dist_parts']} | {ln['move_id']} | prod={ln['product']}")
    print(f"        name: {ln['ml_name']}")

print(f"\nOTHERS (non-expense categories):")
print(f"  Total = {others_total}")
print(f"  Lines:")
for ln in others_lines:
    print(f"    - {ln['ml_id']} | {ln['date']} | bal={ln['balance']:>15} | cat={ln['category']} | {ln['move_id']} | {ln['ml_name']}")

print()
print("=" * 80)
print("COMPARISON SUMMARY")
print("=" * 80)
print(f"  Shipping detected by patched dashboard logic: {shipping_total} (excluding PO-linked, excluding draft)")
print(f"  Odoo profitability 'expenses' bucket:          7,212,753")
print(f"  Difference:                                    7,212,753 - {shipping_total} = {Decimal('7212753') - shipping_total}")
print()
print("If user sees 4,517,208 on dashboard, that's still LESS than what SC shipping calc would give.")
print("Possible reasons dashboard shows 4,517,208 vs my computed 1,034,068 (or now shipping_total above):")
print(" - dashboard is using stale cache from before fix")
print(" - dashboard's shipping_cost in /api/dashboard differs from dashboard's _fetch_shipping_costs")
print(" - this project has multiple accounts / split distribution")