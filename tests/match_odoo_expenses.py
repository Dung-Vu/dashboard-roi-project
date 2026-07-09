"""Match Odoo profitability 'expenses' bucket exactly for BG-202512-3272."""
import sys
import json
from collections import defaultdict
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_client import OdooAPI

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

ACCOUNT_ID = 1395
PROJECT_ID = 1334

# Get ALL analytic lines for this account, all categories
analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", ACCOUNT_ID]],
    ["id", "amount", "account_id", "move_line_id", "category"],
    limit=100000,
)
print(f"All analytic lines: {len(analytic_lines)}")

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in analytic_lines if relation_id(l.get("move_line_id"))})
mls = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "balance", "parent_state", "move_type", "analytic_distribution", "purchase_line_id", "date"],
        limit=len(chunk),
    ))
ml_map = {ml["id"]: ml for ml in mls}

# Categorize
expense_total = Decimal("0")
expense_lines = []
cogs_lines = []
others_lines = []

EXPENSE_CATS = {"expense", "expenses", "vendor_bill", "vendor_bills", "other"}
COGS_CATS = {"purchase_order", "other_purchase_costs", "cost_of_goods_sold"}

for al in analytic_lines:
    cat = al.get("category") or "?"
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id)
    if not ml:
        continue
    if ml.get("parent_state") != "posted":
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    balance = as_decimal(ml.get("balance"))
    line_info = {
        "ml_id": ml_id,
        "balance": float(balance),
        "category": cat,
        "move_type": ml.get("move_type"),
        "po_line": relation_id(ml.get("purchase_line_id")),
    }
    if cat in EXPENSE_CATS:
        expense_total += balance
        expense_lines.append(line_info)
    elif cat in COGS_CATS:
        cogs_lines.append(line_info)
    else:
        others_lines.append(line_info)

print(f"\nExpenses (categories in {EXPENSE_CATS}):")
print(f"  Total = {expense_total}")
print(f"  Lines: {len(expense_lines)}")

print(f"\nCOGS-ish lines (categories in {COGS_CATS}):")
print(f"  Total = {sum(Decimal(str(l['balance'])) for l in cogs_lines)}")
print(f"  Lines: {len(cogs_lines)}")

print(f"\nOther categories (not expense, not cogs):")
print(f"  Total = {sum(Decimal(str(l['balance'])) for l in others_lines)}")
print(f"  Lines: {len(others_lines)}")
for ln in others_lines[:10]:
    print(f"    - {ln}")

# Now filter to EXACTLY what Odoo's profitability 'expenses' bucket does.
# Odoo uses the analytic distribution total — not the move line balance.
# Verify by category totals matching the panel.
print()
print("=" * 80)
print("Compare to panel breakdown:")
print("=" * 80)
panel = client.call_method("project.project", "get_panel_data", [[PROJECT_ID]])
cost_items = panel.get("profitability_items", {}).get("costs", {}).get("data", [])
for it in cost_items:
    item_id = str(it.get("id", ""))
    billed = -as_decimal(it.get("billed"))
    label = it.get("name") or item_id
    print(f"  {item_id}: billed={billed}")

# Now compute "expenses" by aggregate of analytic_lines per category, joining by analytic
# amount (not move line balance).
print()
print("Aggregate analytic line amounts by category:")
by_cat = defaultdict(lambda: Decimal("0"))
for al in analytic_lines:
    cat = al.get("category") or "?"
    by_cat[cat] += as_decimal(al.get("amount"))
for cat, total in sorted(by_cat.items()):
    print(f"  {cat}: {total}")