"""Drill into the 4 skipped 'not_shipping_dist' move lines to see what costs they are."""
import sys
import json
from decimal import Decimal
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_client import OdooAPI

client = OdooAPI("https://bonario-vietnam.odoo.com", "bonario-vietnam", 208, "80aa54434e151ac3f2002b9d85bce253853f84fa")
ACCOUNT_ID = 1781
PROJECT_ID = 1685
SHIPPING_PARTS = {"1519", "1271"}

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

# Get all analytic lines for this account
analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", ACCOUNT_ID]],
    ["id", "amount", "account_id", "move_line_id", "category", "name", "date", "product_id", "partner_id"],
    limit=1000,
)
print(f"Total analytic lines on account {ACCOUNT_ID}: {len(analytic_lines)}")

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in analytic_lines if relation_id(l.get("move_line_id"))})
print(f"Move lines to fetch: {len(ml_ids)}")

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
print("FULL DETAIL OF ALL ANALYTIC-LINKED MOVE LINES")
print("=" * 80)
for al in analytic_lines:
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id, {})
    dist = ml.get("analytic_distribution")
    if isinstance(dist, str):
        try:
            dist = json.loads(dist)
        except Exception:
            pass
    dist_keys = list(dist.keys()) if isinstance(dist, dict) else []
    # Parse parts
    all_parts = set()
    for k in dist_keys:
        for p in k.split(","):
            all_parts.add(p.strip())
    is_shipping = bool(SHIPPING_PARTS & all_parts)
    includes_project = str(ACCOUNT_ID) in all_parts
    
    print(f"\n[AL id={al['id']}] category={al.get('category')!r} amount={al.get('amount')} date={al.get('date')}")
    print(f"  analytic line name: {al.get('name')!r}")
    print(f"  product: {relation_name(al.get('product_id'))}")
    print(f"  [ML id={ml_id}] state={ml.get('parent_state')} type={ml.get('move_type')} balance={ml.get('balance')}")
    print(f"  ML name: {ml.get('name')!r}")
    print(f"  ML move: {relation_name(ml.get('move_id'))}")
    print(f"  ML partner: {relation_name(ml.get('partner_id'))}")
    print(f"  ML product: {relation_name(ml.get('product_id'))}")
    print(f"  ML purchase_line_id: {relation_id(ml.get('purchase_line_id'))}")
    print(f"  dist keys: {dist_keys}")
    print(f"  all parts: {sorted(all_parts)}")
    print(f"  is_shipping (contains 1519/1271): {is_shipping}")
    print(f"  includes_project_account ({ACCOUNT_ID}): {includes_project}")

# Sum totals by category
print()
print("=" * 80)
print("TOTALS BY CATEGORY & SHIPPING-FLAG")
print("=" * 80)
buckets = defaultdict(lambda: {"total": Decimal("0"), "count": 0})
for al in analytic_lines:
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id, {})
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    dist = ml.get("analytic_distribution")
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except: pass
    parts = set()
    if isinstance(dist, dict):
        for k in dist.keys():
            for p in k.split(","):
                parts.add(p.strip())
    is_ship = bool(SHIPPING_PARTS & parts)
    cat = al.get("category") or "no_cat"
    key = f"{cat}|{'ship' if is_ship else 'nonship'}|{ml.get('parent_state','?')}"
    buckets[key]["total"] += as_decimal(ml.get("balance"))
    buckets[key]["count"] += 1

for k in sorted(buckets.keys()):
    v = buckets[k]
    print(f"  {k}: {v['count']} lines, total balance = {v['total']}")

# Total of all non-invoice expenses regardless of shipping dist
print()
total_expense = Decimal("0")
for al in analytic_lines:
    if al.get("category") == "invoice":
        continue
    ml_id = relation_id(al.get("move_line_id"))
    ml = ml_map.get(ml_id, {})
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    total_expense += as_decimal(ml.get("balance"))
print(f"TOTAL non-invoice balance (all expense, posted+draft): {total_expense}")

# Look up PO lines for this project to see if shipping was ordered via PO
print()
print("=" * 80)
print("PURCHASE ORDER LINES FOR THIS PROJECT (any dist containing 1781)")
print("=" * 80)
po_lines = client.search_read(
    "purchase.order.line",
    [["analytic_distribution", "ilike", str(ACCOUNT_ID)]],
    ["id", "name", "order_id", "product_id", "product_qty", "qty_invoiced", "price_subtotal", "analytic_distribution", "order_state"],
    limit=500,
)
print(f"Found {len(po_lines)} PO lines touching account {ACCOUNT_ID}")
for pl in po_lines:
    dist = pl.get("analytic_distribution")
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except: pass
    parts = set()
    if isinstance(dist, dict):
        for k in dist.keys():
            for p in k.split(","):
                parts.add(p.strip())
    is_ship = bool(SHIPPING_PARTS & parts)
    qty = as_decimal(pl.get("product_qty"))
    qinv = as_decimal(pl.get("qty_invoiced"))
    open_qty = qty - qinv
    raw_amount = as_decimal(pl.get("price_subtotal")) * open_qty / qty if qty > 0 else Decimal("0")
    print(f"  - id={pl['id']} order={relation_name(pl.get('order_id'))} prod={relation_name(pl.get('product_id'))} qty={qty} qinv={qinv} open={open_qty} price_sub={pl.get('price_subtotal')} open_amount={raw_amount} is_ship={is_ship} name={pl.get('name')!r}")
    print(f"    dist parts: {sorted(parts)}")