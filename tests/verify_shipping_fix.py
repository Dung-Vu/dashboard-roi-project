"""Verify shipping fix by running the patched _fetch_shipping_costs against account 1781 (O-BG-2606-0330)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_client import OdooAPI
from dashboard_service import DashboardService

client = OdooAPI("https://bonario-vietnam.odoo.com", "bonario-vietnam", 208, "80aa54434e151ac3f2002b9d85bce253853f84fa")
service = DashboardService(client)

ACCOUNT_ID = 1781  # O-BG-2606-0330

print("Discovered shipping account IDs:", sorted(service._get_shipping_account_ids()))

costs_by_acc, costs_by_month = service._fetch_shipping_costs([ACCOUNT_ID])

print()
print("Result of patched _fetch_shipping_costs:")
print(f"  Total shipping_cost for account {ACCOUNT_ID}: {costs_by_acc.get(ACCOUNT_ID, 0.0)}")
print(f"  By month: {costs_by_month.get(ACCOUNT_ID, {})}")

# Compare with project detail page shipping calc
print()
print("=" * 80)
print("Project detail page (build_project_dashboard) shipping calc:")
print("=" * 80)
detail = service.build_project_dashboard(1685)
breakdown = detail.get("custom_cost_breakdown", [])
for it in breakdown:
    if it.get("id") == "shipping_cost":
        print(f"  shipping_cost item: billed={it['billed']}, open_commitment={it['open_commitment']}, expected={it['expected']}")
        break
else:
    print("  No shipping_cost item in breakdown (expected = 0)?")

# Also dump all breakdown items
print("\nFull custom_cost_breakdown:")
for it in breakdown:
    print(f"  - id={it['id']!r:20s} label={it['label']!r:40s} billed={it['billed']} open_commit={it['open_commitment']} expected={it['expected']}")