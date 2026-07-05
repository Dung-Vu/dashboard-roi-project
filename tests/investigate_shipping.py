"""Investigate shipping cost for O-BG-2606-0330 by multiple methods."""
import sys
import json
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_client import OdooAPI, OdooAPIError

ODOO_URL = "https://bonario-vietnam.odoo.com"
ODOO_DB = "bonario-vietnam"
ODOO_USER_ID = 208
ODOO_API_KEY = "80aa54434e151ac3f2002b9d85bce253853f84fa"

SHIPPING_ACCOUNT_PARTS = {"1519", "1271"}

client = OdooAPI(ODOO_URL, ODOO_DB, ODOO_USER_ID, ODOO_API_KEY)

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

print("=" * 80)
print("STEP 1: Find Sale Order O-BG-2606-0330")
print("=" * 80)
so_records = client.search_read(
    "sale.order",
    [["name", "=", "O-BG-2606-0330"]],
    ["id", "name", "partner_id", "date_order", "amount_untaxed", "amount_total", "user_id", "company_id"],
    limit=5,
)
if not so_records:
    print("NOT FOUND: Sale order O-BG-2606-0330")
    sys.exit(0)
so = so_records[0]
print(json.dumps({k: so.get(k) for k in so}, default=str, indent=2, ensure_ascii=False))
so_id = so["id"]

print()
print("=" * 80)
print("STEP 2: Find Project linked to this Sale Order")
print("=" * 80)
projects = client.call_method(
    "project.project",
    "search_read",
    [[["sale_order_id", "=", so_id]]],
    {
        "fields": ["id", "name", "partner_id", "sale_order_id", "account_id", "company_id", "active", "x_studio_giai_trinh"],
        "context": {"active_test": False},
    },
)
if not projects:
    print("NOT FOUND: Project linked to sale order", so_id)
    sys.exit(0)
for p in projects:
    print(json.dumps({k: p.get(k) for k in p}, default=str, indent=2, ensure_ascii=False))

project = projects[0]
project_id = project["id"]
account_ref = project.get("account_id")
account_id = relation_id(account_ref)
account_name = relation_name(account_ref)
print(f"\nProject ID: {project_id}")
print(f"Analytic Account: {account_name} (id={account_id})")

print()
print("=" * 80)
print("STEP 3: Method A - Current dashboard shipping calc (mimics _fetch_shipping_costs)")
print("=" * 80)
print("Filters: category != invoice, parent_state=posted, NOT out_invoice/refund/receipt,")
print("         SKIP if purchase_line_id present, SKIP if dist missing,")
print("         MUST match '1519' or '1271' in dist keys")

analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", account_id], ["category", "!=", "invoice"]],
    ["id", "amount", "account_id", "move_line_id"],
    limit=100000,
)
print(f"\nAnalytic lines (category != invoice) on account {account_id}: {len(analytic_lines)}")

move_line_ids = sorted({
    relation_id(line.get("move_line_id"))
    for line in analytic_lines
    if relation_id(line.get("move_line_id"))
})
print(f"Distinct move_line_ids to fetch: {len(move_line_ids)}")

if move_line_ids:
    move_lines = []
    chunk_size = 500
    for i in range(0, len(move_line_ids), chunk_size):
        chunk = move_line_ids[i:i+chunk_size]
        chunk_lines = client.search_read(
            "account.move.line",
            [["id", "in", chunk]],
            ["id", "analytic_distribution", "parent_state", "move_type", "balance", "purchase_line_id", "date", "name", "move_id", "product_id"],
            limit=len(chunk),
        )
        move_lines.extend(chunk_lines)
    move_line_map = {ml["id"]: ml for ml in move_lines}
    print(f"Fetched move lines: {len(move_lines)}")

    method_a_total = Decimal("0")
    method_a_lines = []
    skipped_reasons = {"no_ml": 0, "not_posted": 0, "out_move_type": 0, "has_po": 0, "no_dist": 0, "not_shipping_dist": 0}
    for line in analytic_lines:
        ml_ref = line.get("move_line_id")
        ml_id = relation_id(ml_ref)
        if not ml_id:
            skipped_reasons["no_ml"] += 1
            continue
        ml = move_line_map.get(ml_id)
        if not ml:
            skipped_reasons["no_ml"] += 1
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
        dist = ml.get("analytic_distribution")
        if not dist:
            skipped_reasons["no_dist"] += 1
            continue
        if isinstance(dist, str):
            try:
                dist = json.loads(dist)
            except Exception:
                pass
        if not isinstance(dist, dict):
            skipped_reasons["no_dist"] += 1
            continue
        is_shipping = False
        for key in dist.keys():
            parts = [p.strip() for p in key.split(",")]
            if "1519" in parts or "1271" in parts:
                is_shipping = True
                break
        if not is_shipping:
            skipped_reasons["not_shipping_dist"] += 1
            continue
        balance = float(ml.get("balance") or 0)
        method_a_total += Decimal(str(balance))
        method_a_lines.append({
            "ml_id": ml_id,
            "ml_name": ml.get("name"),
            "date": ml.get("date"),
            "balance": balance,
            "move_id": relation_name(ml.get("move_id")),
            "move_type": ml.get("move_type"),
            "parent_state": ml.get("parent_state"),
            "purchase_line_id": relation_id(ml.get("purchase_line_id")),
            "product": relation_name(ml.get("product_id")),
        })

    print(f"\nMethod A total (matches dashboard): {method_a_total}")
    print(f"Method A lines contributing: {len(method_a_lines)}")
    print(f"Skipped reasons: {skipped_reasons}")
    if method_a_lines:
        print("\nDetail of contributing move lines:")
        for ml in method_a_lines:
            print(f"  - id={ml['ml_id']} date={ml['date']} balance={ml['balance']} move={ml['move_id']} type={ml['move_type']} po_line={ml['purchase_line_id']} prod={ml['product']} name={ml['ml_name']}")

print()
print("=" * 80)
print("STEP 4: Method B - Include PO-linked bills (remove purchase_line_id skip)")
print("=" * 80)
method_b_total = Decimal("0")
method_b_lines = []
if move_line_ids:
    for line in analytic_lines:
        ml_id = relation_id(line.get("move_line_id"))
        if not ml_id:
            continue
        ml = move_line_map.get(ml_id)
        if not ml:
            continue
        if ml.get("parent_state") != "posted":
            continue
        if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
            continue
        dist = ml.get("analytic_distribution")
        if not dist:
            continue
        if isinstance(dist, str):
            try:
                dist = json.loads(dist)
            except Exception:
                pass
        if not isinstance(dist, dict):
            continue
        is_shipping = False
        for key in dist.keys():
            parts = [p.strip() for p in key.split(",")]
            if "1519" in parts or "1271" in parts:
                is_shipping = True
                break
        if not is_shipping:
            continue
        balance = float(ml.get("balance") or 0)
        method_b_total += Decimal(str(balance))
        method_b_lines.append({
            "ml_id": ml_id,
            "balance": balance,
            "move_id": relation_name(ml.get("move_id")),
            "po_line": relation_id(ml.get("purchase_line_id")),
            "product": relation_name(ml.get("product_id")),
        })
print(f"Method B total (include PO-linked posted bills): {method_b_total}")
print(f"Method B lines: {len(method_b_lines)}")
only_po_linked = [ml for ml in method_b_lines if ml.get("po_line")]
print(f"  of which PO-linked (the ones A skipped): {len(only_po_linked)}")
for ml in only_po_linked:
    print(f"  + id={ml['ml_id']} balance={ml['balance']} move={ml['move_id']} po_line={ml['po_line']} prod={ml['product']}")

print()
print("=" * 80)
print("STEP 5: Method C - Include draft bills + PO open commitments + posted")
print("=" * 80)
print("Fetching ALL move lines touching the account, regardless of state...")

# Get all analytic lines regardless of category
all_analytic_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "=", account_id]],
    ["id", "amount", "account_id", "move_line_id", "category", "name", "date"],
    limit=100000,
)
print(f"Total analytic lines on account (all categories): {len(all_analytic_lines)}")

all_ml_ids = sorted({
    relation_id(line.get("move_line_id"))
    for line in all_analytic_lines
    if relation_id(line.get("move_line_id"))
})
print(f"Distinct move_line_ids: {len(all_ml_ids)}")

all_move_lines = []
for i in range(0, len(all_ml_ids), 500):
    chunk = all_ml_ids[i:i+500]
    cl = client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "analytic_distribution", "parent_state", "move_type", "balance", "purchase_line_id", "date", "name", "move_id", "product_id"],
        limit=len(chunk),
    )
    all_move_lines.extend(cl)
all_ml_map = {ml["id"]: ml for ml in all_move_lines}

method_c_total = Decimal("0")
method_c_lines = []
for line in all_analytic_lines:
    ml_id = relation_id(line.get("move_line_id"))
    if not ml_id:
        continue
    ml = all_ml_map.get(ml_id)
    if not ml:
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    dist = ml.get("analytic_distribution")
    if not dist:
        continue
    if isinstance(dist, str):
        try:
            dist = json.loads(dist)
        except Exception:
            pass
    if not isinstance(dist, dict):
        continue
    is_shipping = False
    for key in dist.keys():
        parts = [p.strip() for p in key.split(",")]
        if "1519" in parts or "1271" in parts:
            is_shipping = True
            break
    if not is_shipping:
        continue
    balance = float(ml.get("balance") or 0)
    method_c_total += Decimal(str(balance))
    method_c_lines.append({
        "ml_id": ml_id,
        "analytic_category": line.get("category"),
        "parent_state": ml.get("parent_state"),
        "balance": balance,
        "move_id": relation_name(ml.get("move_id")),
        "po_line": relation_id(ml.get("purchase_line_id")),
        "product": relation_name(ml.get("product_id")),
        "name": ml.get("name"),
        "date": ml.get("date"),
    })

print(f"Method C total (any state, any category, PO/no-PO): {method_c_total}")
print(f"Method C lines: {len(method_c_lines)}")
print("\nBreakdown by parent_state:")
from collections import defaultdict
by_state = defaultdict(lambda: {"total": Decimal("0"), "count": 0})
for ml in method_c_lines:
    s = ml["parent_state"]
    by_state[s]["total"] += Decimal(str(ml["balance"]))
    by_state[s]["count"] += 1
for s, info in by_state.items():
    print(f"  {s}: {info['count']} lines, total={info['total']}")

print("\nBreakdown by po_line presence:")
by_po = {"has_po": {"total": Decimal("0"), "count": 0}, "no_po": {"total": Decimal("0"), "count": 0}}
for ml in method_c_lines:
    bucket = "has_po" if ml.get("po_line") else "no_po"
    by_po[bucket]["total"] += Decimal(str(ml["balance"]))
    by_po[bucket]["count"] += 1
for k, info in by_po.items():
    print(f"  {k}: {info['count']} lines, total={info['total']}")

print()
print("=" * 80)
print("STEP 6: Method D - Profitability items (Odoo native, project.project.panel)")
print("=" * 80)
try:
    panel = client.call_method("project.project", "get_panel_data", [[project_id]])
    cost_items = panel.get("profitability_items", {}).get("costs", {}).get("data", [])
    print(f"Total cost items in panel: {len(cost_items)}")
    expense_total = Decimal("0")
    shipping_items = []
    for it in cost_items:
        item_id = str(it.get("id", ""))
        billed = -as_decimal(it.get("billed"))
        to_bill = -as_decimal(it.get("to_bill"))
        expected = billed + to_bill
        label = it.get("name") or it.get("display_name") or it.get("label") or item_id
        if item_id in {"expense", "expenses", "vendor_bill", "vendor_bills", "other"}:
            expense_total += expected
        # Try to detect shipping-related by name
        text = str(label).lower()
        if any(kw in text for kw in ["ship", "vận chuyển", "vanchuyen", "giao", "logistics", "1519", "1271"]):
            shipping_items.append({"id": item_id, "label": label, "billed": billed, "to_bill": to_bill, "expected": expected})
    
    print("\nAll cost items (first 30):")
    for it in cost_items[:30]:
        item_id = str(it.get("id", ""))
        billed = -as_decimal(it.get("billed"))
        to_bill = -as_decimal(it.get("to_bill"))
        expected = billed + to_bill
        label = it.get("name") or it.get("display_name") or it.get("label") or item_id
        print(f"  - id={item_id} label={label!r} billed={billed} to_bill={to_bill} expected={expected}")
    print(f"\nTotal expense (expense/expenses/vendor_bill/other): {expense_total}")
    print(f"\nShipping-keyword-matched items: {len(shipping_items)}")
    for s in shipping_items:
        print(f"  -> id={s['id']} label={s['label']!r} billed={s['billed']} to_bill={s['to_bill']} expected={s['expected']}")
except OdooAPIError as e:
    print(f"Failed to fetch profitability panel: {e}")

print()
print("=" * 80)
print("STEP 7: Method E - All move lines directly (analytic_distribution LIKE account_id)")
print("=" * 80)
# Search for all move lines that mention this account in their distribution
try:
    direct_mls = client.search_read(
        "account.move.line",
        [["analytic_distribution", "ilike", str(account_id)]],
        ["id", "name", "balance", "parent_state", "move_type", "analytic_distribution", "purchase_line_id", "date", "move_id", "product_id"],
        limit=1000,
    )
    print(f"Move lines directly matching account_id {account_id} in dist: {len(direct_mls)}")
    
    # Filter shipping-only and breakdown
    direct_shipping_total = Decimal("0")
    direct_shipping_lines = []
    for ml in direct_mls:
        dist = ml.get("analytic_distribution")
        if isinstance(dist, str):
            try:
                dist = json.loads(dist)
            except Exception:
                pass
        if not isinstance(dist, dict):
            continue
        is_shipping = False
        for key in dist.keys():
            parts = [p.strip() for p in key.split(",")]
            if "1519" in parts or "1271" in parts:
                is_shipping = True
                break
        if not is_shipping:
            continue
        # Also check if account_id is in the dist
        account_match = False
        for key in dist.keys():
            parts = [p.strip() for p in key.split(",")]
            if str(account_id) in parts:
                account_match = True
                break
        if not account_match:
            continue
        if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
            continue
        balance = float(ml.get("balance") or 0)
        direct_shipping_total += Decimal(str(balance))
        direct_shipping_lines.append({
            "id": ml["id"],
            "name": ml.get("name"),
            "parent_state": ml.get("parent_state"),
            "move_type": ml.get("move_type"),
            "balance": balance,
            "po_line": relation_id(ml.get("purchase_line_id")),
            "move_id": relation_name(ml.get("move_id")),
            "date": ml.get("date"),
            "product": relation_name(ml.get("product_id")),
        })
    print(f"Direct move lines matching this account AND shipping codes: {len(direct_shipping_lines)}")
    print(f"Total: {direct_shipping_total}")
    print("\nBreakdown by state:")
    by_state_d = defaultdict(lambda: {"total": Decimal("0"), "count": 0})
    for ml in direct_shipping_lines:
        by_state_d[ml["parent_state"]]["total"] += Decimal(str(ml["balance"]))
        by_state_d[ml["parent_state"]]["count"] += 1
    for s, info in by_state_d.items():
        print(f"  {s}: {info['count']} lines, total={info['total']}")
    print("\nBreakdown by PO presence:")
    by_po_d = {"has_po": {"total": Decimal("0"), "count": 0}, "no_po": {"total": Decimal("0"), "count": 0}}
    for ml in direct_shipping_lines:
        bucket = "has_po" if ml.get("po_line") else "no_po"
        by_po_d[bucket]["total"] += Decimal(str(ml["balance"]))
        by_po_d[bucket]["count"] += 1
    for k, info in by_po_d.items():
        print(f"  {k}: {info['count']} lines, total={info['total']}")
    print("\nAll detail:")
    for ml in direct_shipping_lines:
        print(f"  - id={ml['id']} state={ml['parent_state']} type={ml['move_type']} bal={ml['balance']} po={ml['po_line']} move={ml['move_id']} date={ml['date']} prod={ml['product']} name={ml['name']}")
except Exception as e:
    print(f"Method E failed: {e}")

print()
print("=" * 80)
print("STEP 8: Method F - PO open commitments on shipping codes (project detail page logic)")
print("=" * 80)
try:
    po_lines = client.search_read(
        "purchase.order.line",
        [
            ["order_id.state", "in", ["purchase", "done"]],
            ["analytic_distribution", "ilike", str(account_id)],
        ],
        ["id", "name", "order_id", "product_id", "product_qty", "qty_invoiced", "price_subtotal", "analytic_distribution"],
        limit=1000,
    )
    print(f"PO lines (state in purchase/done) with dist containing account_id {account_id}: {len(po_lines)}")
    
    po_open_total = Decimal("0")
    po_shipping_lines = []
    for line in po_lines:
        dist = line.get("analytic_distribution")
        if isinstance(dist, str):
            try:
                dist = json.loads(dist)
            except Exception:
                pass
        if not isinstance(dist, dict):
            continue
        # Check if account_id is in dist primary
        account_match = False
        shipping_match = False
        for key in dist.keys():
            parts = [p.strip() for p in key.split(",")]
            if str(account_id) in parts:
                account_match = True
            if "1519" in parts or "1271" in parts:
                shipping_match = True
        if not (account_match and shipping_match):
            continue
        product_qty = as_decimal(line.get("product_qty"))
        qty_invoiced = as_decimal(line.get("qty_invoiced"))
        open_qty = product_qty - qty_invoiced
        if product_qty <= 0 or open_qty <= 0:
            continue
        raw_amount = as_decimal(line.get("price_subtotal")) * open_qty / product_qty
        po_open_total += raw_amount
        po_shipping_lines.append({
            "id": line["id"],
            "name": line.get("name"),
            "order": relation_name(line.get("order_id")),
            "product": relation_name(line.get("product_id")),
            "open_qty": open_qty,
            "raw_amount": raw_amount,
        })
    print(f"PO shipping open-commitments on this account: {len(po_shipping_lines)} lines, total={po_open_total}")
    for p in po_shipping_lines:
        print(f"  -> id={p['id']} name={p['name']} order={p['order']} prod={p['product']} open_qty={p['open_qty']} amount={p['raw_amount']}")
except Exception as e:
    print(f"Method F failed: {e}")

print()
print("=" * 80)
print("FINAL SUMMARY")
print("=" * 80)
print(f"Project O-BG-2606-0330 (project_id={project_id}, account={account_name} id={account_id})")
print(f"  Method A (dashboard current - posted, NO PO-linked, dist has 1519/1271): {method_a_total}")
print(f"  Method B (posted, INCLUDING PO-linked bills, dist has 1519/1271):       {method_b_total}")
print(f"  Method C (any state, any category, dist has 1519/1271):                 {method_c_total}")
print(f"  Method D (Odoo native profitability panel - expense-bucket total):       {expense_total if 'expense_total' in dir() else 'N/A'}")
print(f"  Method E (direct move-line search on account + shipping codes):         {direct_shipping_total if 'direct_shipping_total' in dir() else 'N/A'}")
print(f"  Method F (PO open commitments on shipping codes):                       {po_open_total if 'po_open_total' in dir() else 'N/A'}")