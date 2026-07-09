"""Detailed debug for BG-202512-3272: print raw dist for all BILL lines containing 1519/1518/1522 etc."""
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


# Replicate the full shipping-cost fetch logic in dashboard_service for account 1395
ACCOUNT_ID = 1395
SHIPPING_IDS = {566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}

# Get all non-invoice analytic lines
analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", ACCOUNT_ID], ["category", "!=", "invoice"]],
    ["id", "amount", "account_id", "move_line_id", "category"],
    limit=100000,
)
print(f"Analytic lines (non-invoice): {len(analytic_lines)}")

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in analytic_lines if relation_id(l.get("move_line_id"))})
mls = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "name", "balance", "parent_state", "move_type", "analytic_distribution", "purchase_line_id", "date"],
        limit=len(chunk),
    ))
ml_map = {ml["id"]: ml for ml in mls}

# Process with exact same logic as dashboard_service._fetch_shipping_costs
shipping_total = Decimal("0")
shipping_lines = []
skipped_reasons = defaultdict(int)

processed_ml_per_account = defaultdict(set)

for line in analytic_lines:
    ml_ref = line.get("move_line_id")
    ml_id = relation_id(ml_ref)
    if not ml_id:
        skipped_reasons["no_ml"] += 1
        continue
    ml = ml_map.get(ml_id)
    if not ml:
        skipped_reasons["ml_not_fetched"] += 1
        continue
    if ml.get("parent_state") != "posted":
        skipped_reasons["not_posted"] += 1
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        skipped_reasons["out_move_type"] += 1
        continue
    if ml.get("purchase_line_id"):
        skipped_reasons["has_po"] += 1
        continue
    acc_id = line["account_id"][0]
    if ml_id in processed_ml_per_account[acc_id]:
        skipped_reasons["dup_in_account"] += 1
        continue
    dist = ml.get("analytic_distribution")
    if not dist:
        skipped_reasons["no_dist"] += 1
        continue
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except Exception:
            skipped_reasons["dist_parse_fail"] += 1
            continue
    if not isinstance(dist, dict):
        skipped_reasons["dist_not_dict"] += 1
        continue
    
    is_shipping = False
    for key in dist.keys():
        for part in str(key).split(","):
            part = part.strip()
            try:
                if int(part) in SHIPPING_IDS:
                    is_shipping = True
                    break
            except ValueError:
                pass
        if is_shipping:
            break
    
    if not is_shipping:
        skipped_reasons["not_shipping_dist"] += 1
        continue
    
    processed_ml_per_account[acc_id].add(ml_id)
    balance = float(ml.get("balance") or 0)
    shipping_total += Decimal(str(balance))
    shipping_lines.append({
        "ml_id": ml_id,
        "balance": balance,
        "date": ml.get("date"),
        "move_id": relation_name(ml.get("move_id")),
        "name": ml.get("name"),
        "dist": dist,
        "po_line": relation_id(ml.get("purchase_line_id")),
    })

print(f"\nSkipped reasons: {dict(skipped_reasons)}")
print(f"\nShipping detected: {shipping_total}")
print(f"Lines: {len(shipping_lines)}")
for ln in shipping_lines:
    print(f"  + {ln['ml_id']} | {ln['date']} | {ln['balance']:>15} | {ln['move_id']} | po={ln['po_line']}")
    print(f"      dist = {ln['dist']!r}")
    print(f"      name: {ln['name']}")

# Also dump all 73 lines and which skip reason they hit
print()
print("=" * 80)
print("Lines with 1519 in dist (raw):")
print("=" * 80)
for line in analytic_lines:
    ml_id = relation_id(line.get("move_line_id"))
    ml = ml_map.get(ml_id)
    if not ml:
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
            try: parts.add(int(p.strip()))
            except: pass
    if SHIPPING_IDS & parts:
        # Show with skip reason
        skip_reasons = []
        if ml.get("parent_state") != "posted": skip_reasons.append("not_posted")
        if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}: skip_reasons.append("out_move_type")
        if ml.get("purchase_line_id"): skip_reasons.append(f"has_po({relation_id(ml.get('purchase_line_id'))})")
        marker = " [SKIP:" + ",".join(skip_reasons) + "]" if skip_reasons else " [OK]"
        print(f"  {ml_id} | {ml.get('date')} | {ml.get('move_type'):20} | bal={ml.get('balance'):>15} | state={ml.get('parent_state')} | po={relation_id(ml.get('purchase_line_id'))}{marker}")
        print(f"      name: {ml.get('name')!r}")