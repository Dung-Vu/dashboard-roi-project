"""Compute the 'expenses' bucket exact logic: vendor_bill category WITHOUT purchase_line_id."""
import sys
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

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

analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", ACCOUNT_ID]],
    ["id", "amount", "account_id", "move_line_id", "category", "name"],
    limit=100000,
)

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in analytic_lines if relation_id(l.get("move_line_id"))})
mls = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "balance", "parent_state", "move_type", "purchase_line_id", "date", "name"],
        limit=len(chunk),
    ))
ml_map = {ml["id"]: ml for ml in mls}

# Categories used by Odoo profitability
EXPENSE_CATS = {"expense", "expenses", "vendor_bill", "vendor_bills", "other"}

# Compute: expense bucket = sum of analytic.amount for vendor_bill|expense|other category
# EXCLUDING move lines with purchase_line_id (those go to purchase_order)
expense_no_po_total = Decimal("0")
expense_no_po_lines = []
expense_with_po_total = Decimal("0")
expense_with_po_lines = []

for al in analytic_lines:
    if al.get("category") not in EXPENSE_CATS:
        continue
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id)
    if not ml:
        continue
    if ml.get("parent_state") != "posted":
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    
    amount = as_decimal(al.get("amount"))  # analytic line amount (signed)
    po_line = relation_id(ml.get("purchase_line_id"))
    line_info = {
        "al_id": al["id"],
        "ml_id": ml_id,
        "analytic_amount": float(amount),
        "category": al.get("category"),
        "po_line": po_line,
        "name": al.get("name"),
        "ml_name": ml.get("name"),
    }
    if po_line:
        expense_with_po_total += -amount  # expense positive display
        expense_with_po_lines.append(line_info)
    else:
        expense_no_po_total += -amount
        expense_no_po_lines.append(line_info)

print("=" * 80)
print("Odoo panel 'expenses' bucket logic verification")
print("=" * 80)
print(f"Odoo panel reports expenses = 7,217,753")
print()
print(f"Sum of expense category analytic_amount, NO PO-linked:    {-expense_no_po_total}")
print(f"  Lines: {len(expense_no_po_lines)}")
print()
print(f"Sum of expense category analytic_amount, PO-linked:      {-expense_with_po_total}")
print(f"  Lines: {len(expense_with_po_lines)}")
print()

# Now show details of expense_no_po_lines that DON'T go through shipping dist
# (these would be the ones dashboard misses)
print("=" * 80)
print("Expense (no-PO) lines breakdown by shipping dist:")
print("=" * 80)
# We need to also fetch move lines' analytic_distribution
mls2 = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls2.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "analytic_distribution"],
        limit=len(chunk),
    ))
ml_dist_map = {ml["id"]: ml.get("analytic_distribution") for ml in mls2}

SHIPPING_IDS = {566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}

ship_in_dist_total = Decimal("0")
ship_in_dist_lines = []
ship_not_in_dist_total = Decimal("0")
ship_not_in_dist_lines = []

for ln in expense_no_po_lines:
    dist = ml_dist_map.get(ln["ml_id"])
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except: dist = None
    parts = set()
    if isinstance(dist, dict):
        for k in dist.keys():
            for p in k.split(","):
                try: parts.add(int(p.strip()))
                except: pass
    is_ship = bool(SHIPPING_IDS & parts)
    if is_ship:
        ship_in_dist_total += Decimal(str(ln["analytic_amount"]))
        ship_in_dist_lines.append(ln)
    else:
        ship_not_in_dist_total += Decimal(str(ln["analytic_amount"]))
        ship_not_in_dist_lines.append(ln)

print(f"\nLines WITH shipping account in dist: {-ship_in_dist_total}, count={len(ship_in_dist_lines)}")
for ln in ship_in_dist_lines:
    print(f"  - {ln['ml_id']} | {ln['analytic_amount']} | cat={ln['category']} | {ln['ml_name']}")

print(f"\nLines WITHOUT shipping account in dist: {-ship_not_in_dist_total}, count={len(ship_not_in_dist_lines)}")
for ln in ship_not_in_dist_lines:
    print(f"  - {ln['ml_id']} | {ln['analytic_amount']} | cat={ln['category']} | {ln['ml_name']}")