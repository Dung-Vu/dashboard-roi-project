"""Survey shipping-related data in Odoo:
1. All products whose internal reference / name suggests shipping
2. All analytic accounts whose code/name suggests shipping
3. Sample move lines across recent projects to detect shipping product codes used
"""
import sys
import json
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odoo_client import OdooAPI

client = OdooAPI("https://bonario-vietnam.odoo.com", "bonario-vietnam", 208, "80aa54434e151ac3f2002b9d85bce253853f84fa")

SHIPPING_KEYWORDS = ["ship", "vận chuyển", "vanchuyen", "phí vc", "phí vận", "phi vc", "phi van", "lalamove", "grab", "logistics", "giao hàng", "giao hang", "freight", "transport"]

def relation_name(v):
    if isinstance(v, (list, tuple)) and len(v) > 1:
        return v[1]
    return None

def relation_id(v):
    if isinstance(v, (list, tuple)) and v:
        return v[0]
    return None

print("=" * 80)
print("STEP 1: Survey analytic accounts related to shipping")
print("=" * 80)
# Search by name / code / parent path
all_accounts = client.search_read(
    "account.analytic.account",
    [],
    ["id", "name", "code", "plan_id", "company_id"],
    limit=0,  # 0 = no limit
)
print(f"Total analytic accounts: {len(all_accounts)}")
shipping_accounts = []
for acc in all_accounts:
    name = (acc.get("name") or "").lower()
    code = (acc.get("code") or "").lower()
    text = f"{name} {code}"
    if any(kw in text for kw in SHIPPING_KEYWORDS):
        shipping_accounts.append(acc)

print(f"\nShipping-related analytic accounts: {len(shipping_accounts)}")
# Count by code
code_counter = Counter()
for acc in shipping_accounts:
    code_counter[acc.get("code") or "(no code)"] += 1
print("\nDistribution by code (top 30):")
for code, cnt in code_counter.most_common(30):
    print(f"  code={code!r:30s} count={cnt}")

print("\nFirst 50 shipping accounts detail:")
for acc in shipping_accounts[:50]:
    print(f"  id={acc['id']:6d} code={acc.get('code')!r:12s} name={acc.get('name')!r:80s} plan={relation_name(acc.get('plan_id'))}")

# Save full list to file for inspection
out_path = Path("C:\\Users\\Admin\\AppData\\Local\\Temp\\opencode\\shipping_accounts.json")
out_path.write_text(json.dumps(shipping_accounts, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nFull list written to: {out_path}")

print()
print("=" * 80)
print("STEP 2: Survey products related to shipping")
print("=" * 80)
all_products = client.search_read(
    "product.product",
    [],
    ["id", "name", "default_code", "type", "categ_id"],
    limit=0,
)
print(f"Total products: {len(all_products)}")
shipping_products = []
for p in all_products:
    name = (p.get("name") or "").lower()
    code = (p.get("default_code") or "").lower()
    text = f"{name} {code}"
    if any(kw in text for kw in SHIPPING_KEYWORDS):
        shipping_products.append(p)

print(f"\nShipping-related products: {len(shipping_products)}")
print("\nAll shipping products detail:")
for p in shipping_products:
    print(f"  id={p['id']:6d} code={(p.get('default_code') or '')!r:25s} name={p.get('name')!r:75s} type={p.get('type')}")

out_path2 = Path("C:\\Users\\Admin\\AppData\\Local\\Temp\\opencode\\shipping_products.json")
out_path2.write_text(json.dumps(shipping_products, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nFull list written to: {out_path2}")

print()
print("=" * 80)
print("STEP 3: Aggregate product codes used in 'other' category analytic lines across recent 200 projects")
print("=" * 80)
# Get recent projects
recent_projects = client.call_method(
    "project.project",
    "search_read",
    [[[]]],
    {
        "fields": ["id", "name", "account_id"],
        "context": {"active_test": False},
        "limit": 200,
    },
)
print(f"Recent projects: {len(recent_projects)}")

account_ids = sorted({
    relation_id(p.get("account_id"))
    for p in recent_projects
    if relation_id(p.get("account_id"))
})
print(f"Distinct account_ids: {len(account_ids)}")

# Fetch all analytic lines on those accounts, category != invoice
all_lines = client.search_read(
    "account.analytic.line",
    [["account_id", "in", account_ids], ["category", "!=", "invoice"]],
    ["id", "amount", "account_id", "move_line_id", "category", "product_id", "name"],
    limit=100000,
)
print(f"ANalytic lines on these accounts (non-invoice): {len(all_lines)}")

ml_ids = sorted({relation_id(l.get("move_line_id")) for l in all_lines if relation_id(l.get("move_line_id"))})
print(f"Move lines to fetch: {len(ml_ids)}")
mls = []
for i in range(0, len(ml_ids), 500):
    chunk = ml_ids[i:i+500]
    mls.extend(client.search_read(
        "account.move.line",
        [["id", "in", chunk]],
        ["id", "analytic_distribution", "parent_state", "move_type", "balance", "purchase_line_id", "product_id", "name"],
        limit=len(chunk),
    ))
ml_map = {ml["id"]: ml for ml in mls}

# Stats: products that appear in move lines where dist contains 1519/1271/1522/1518/etc
product_dist_counter = defaultdict(lambda: {"count": 0, "total_balance": 0.0, "dist_codes": Counter()})
for line in all_lines:
    ml_id = relation_id(line.get("move_line_id"))
    ml = ml_map.get(ml_id)
    if not ml:
        continue
    if ml.get("parent_state") != "posted":
        continue
    if ml.get("move_type") in {"out_invoice", "out_refund", "out_receipt"}:
        continue
    dist = ml.get("analytic_distribution")
    if isinstance(dist, str):
        try: dist = json.loads(dist)
        except: pass
    if not isinstance(dist, dict):
        continue
    
    all_parts = set()
    for k in dist.keys():
        for p in k.split(","):
            all_parts.add(p.strip())
    
    # Check shipping codes (known + any code that matches shipping keywords)
    is_shipping_dist = any(code in {"1519", "1271", "1522", "1518", "313"} for code in all_parts)
    
    prod_ref = ml.get("product_id") or line.get("product_id")
    prod_name = relation_name(prod_ref) or "(no product)"
    prod_id = relation_id(prod_ref)
    
    entry = product_dist_counter[prod_name]
    entry["count"] += 1
    entry["total_balance"] += float(ml.get("balance") or 0)
    for code in all_parts:
        entry["dist_codes"][code] += 1

# Show top products by frequency
print("\nTop 30 products by frequency in posted non-out move lines:")
sorted_prods = sorted(product_dist_counter.items(), key=lambda x: -x[1]["count"])
for name, info in sorted_prods[:30]:
    top_codes = info["dist_codes"].most_common(5)
    is_ship_prod = any(kw in name.lower() for kw in SHIPPING_KEYWORDS)
    marker = " [SHIP-NAME]" if is_ship_prod else ""
    print(f"  count={info['count']:4d} total={info['total_balance']:>15.0f} prod={name!r}{marker}")
    print(f"     top dist codes: {top_codes}")