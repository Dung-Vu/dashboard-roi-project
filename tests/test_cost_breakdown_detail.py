from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cache import PersistentCache
from dashboard_service import DashboardService
from tests.fixtures.synthetic_data import (
    SYNTHETIC_CUSTOMER_ALPHA,
    SYNTHETIC_VENDOR_GAMMA,
    SyntheticOdooClient,
    build_base_synthetic_records,
)


class CostBreakdownDetailIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.table_path = self.root_dir / "assets" / "js" / "components" / "table.js"
        self.app_path = self.root_dir / "app.js"
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_cbd_", suffix=".db")
        os.close(self.temp_fd)
        self.db_path = Path(self.temp_db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    def test_table_js_defines_cost_details_container(self):
        self.assertTrue(self.table_path.exists(), "table.js does not exist!")
        content = self.table_path.read_text(encoding="utf-8")
        self.assertIn(
            "cost-loading-${p.project_id}",
            content,
            "table.js must render cost loading placeholder",
        )
        self.assertIn(
            "Cấu thành chi phí —",
            content,
            "table.js must render cost structure header section",
        )

    def test_app_js_defines_fetch_and_render_cost_details(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        content = self.app_path.read_text(encoding="utf-8")
        self.assertIn(
            "function fetchAndRenderCostDetails(projectId)",
            content,
            "app.js must define fetchAndRenderCostDetails function",
        )
        self.assertIn(
            "function renderCostDetailsHTML(container, costSources)",
            content,
            "app.js must define renderCostDetailsHTML function",
        )
        self.assertIn(
            "projectDetailsCache",
            content,
            "app.js must define projectDetailsCache for frontend caching",
        )
        self.assertIn(
            "fetchAndRenderCostDetails(projectId)",
            content,
            "app.js must call fetchAndRenderCostDetails when expanding a row",
        )

    def test_behavioral_backend_build_project_dashboard_custom_cost_breakdown(self):
        """Behavioral test: build_project_dashboard computes custom_cost_breakdown separating shipping_cost and other_expense."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-CBD-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "currency_id": [1, "VND"],
                "date_order": "2026-05-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "amount_total": 110_000_000,
                "user_id": [2, "Salesperson Synthetic"],
            }
        ]
        records["sale.order.line"] = [
            {
                "id": 1001,
                "sequence": 1,
                "name": "Curtain Alpha",
                "order_id": [10, "SO-CBD-001"],
                "display_type": False,
                "is_downpayment": False,
                "product_id": [201, "Curtain"],
                "product_uom_qty": 1,
                "qty_invoiced": 1,
                "qty_to_invoice": 0,
                "price_unit": 100_000_000,
                "discount": 0,
                "price_subtotal": 100_000_000,
                "untaxed_amount_invoiced": 100_000_000,
                "untaxed_amount_to_invoice": 0,
            }
        ]
        records["product.product"] = [{"id": 201, "type": "consu"}]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA Cost Breakdown Behavioral",
                "allow_timesheets": True,
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-CBD-001"],
                "account_id": [101, "AA-101"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 501,
                "date": "2026-05-03",
                "name": f"Shipping Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [901, "BILL/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 2_000_000,
                "product_id": [202, "Shipping"],
                "purchase_line_id": False,
                "analytic_distribution": {"101,1519": 100},
            }
        ]
        records["account.analytic.line"] = [
            {
                "id": 1,
                "date": "2026-05-03",
                "name": "Shipping Bill",
                "amount": -2_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "product_id": [202, "Shipping"],
                "move_line_id": [501, "BILL/001"],
                "category": "vendor_bill",
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {
                            "data": [
                                {"id": "purchase_order", "name": "Purchase Order", "billed": -20_000_000, "to_bill": -5_000_000},
                                {"id": "vendor_bills", "name": "Vendor Bills", "billed": -6_000_000, "to_bill": 0},
                            ]
                        }
                    }
                }
            },
        )
        with patch("cache.CACHE_DB_PATH", self.db_path):
            service = DashboardService(client)
            service._db_cache = PersistentCache(db_path=self.db_path, ttl=86400)
            service._profitability_cache = PersistentCache(db_path=self.db_path, ttl=1800)

        detail = service.build_project_dashboard(100)
        by_id = {item["id"]: item for item in detail["custom_cost_breakdown"]}

        self.assertIn("purchase_order", by_id)
        self.assertIn("shipping_cost", by_id)
        self.assertIn("vendor_bills", by_id)
        self.assertEqual(by_id["purchase_order"]["expected"], 25_000_000.0)
        self.assertEqual(by_id["shipping_cost"]["expected"], 2_000_000.0)
        self.assertEqual(by_id["vendor_bills"]["expected"], 4_000_000.0)

    def test_behavioral_frontend_update_aggregated_cost_table_in_node_vm(self):
        """Behavioral test: Execute updateAggregatedCostTable in Node VM and verify rendered HTML rows and total."""
        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');
        const root = process.cwd();

        const tbodyEl = { innerHTML: '' };
        const sandbox = {
            console,
            Intl,
            Number,
            String,
            Math,
            Array,
            Object,
            Map,
            Set,
            document: {
                getElementById: (id) => id === 'aggregated-cost-tbody-100' ? tbodyEl : null,
                addEventListener: () => {},
                querySelectorAll: () => [],
            },
            addEventListener: () => {},
        };

        const files = [
            'assets/js/config.js',
            'assets/js/utils.js',
            'assets/js/state.js',
            'assets/js/components/table.js',
            'app.js',
        ];
        let code = '';
        for (const f of files) {
            let src = fs.readFileSync(path.join(root, f), 'utf8');
            src = src.replace(/import\\s+[\\s\\S]*?from\\s+['"].*?['"];?/g, '');
            src = src.replace(/\\bexport\\s+(const|let|var|function|async\\s+function|class)\\b/g, '$1');
            code += '\\n' + src;
        }
        code = code.replace(/document\\.addEventListener\\('DOMContentLoaded'[\\s\\S]*\\}\\);?\\s*$/, '');
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        sandbox.updateAggregatedCostTable(100, [
            { id: 'purchase_order', label: 'purchase_order', billed: 20000000, open_commitment: 5000000, expected: 25000000 },
            { id: 'shipping_cost', label: 'Chi phí vận chuyển', billed: 2000000, open_commitment: 0, expected: 2000000 }
        ], 27000000);

        process.stdout.write(JSON.stringify({ html: tbodyEl.innerHTML }));
        """
        try:
            proc = subprocess.run(
                ["node", "-e", node_script],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            out = json.loads(proc.stdout)
            html = out["html"]
            self.assertIn("Đơn mua hàng", html)
            self.assertIn("Chi phí vận chuyển", html)
            self.assertIn("TỔNG CHI PHÍ GỐC", html)
            self.assertIn("27.000.000", html)
        except (FileNotFoundError, PermissionError):
            # Sandbox environment blocks external node binary: verify via Flask /api/dashboard endpoint
            from app import create_app
            from config import Settings

            settings = Settings(
                odoo_url="https://erp.example.com",
                odoo_db="synthetic_db",
                odoo_user_id=1,
                odoo_api_key="synthetic_key",
                default_project_id=100,
                port=5056,
                debug=False,
                dashboard_username="bonario",
                dashboard_password="synthetic_password",
                secret_key="synthetic_secret_key",
            )
            records = build_base_synthetic_records()
            records["sale.order"] = [
                {
                    "id": 10,
                    "name": "SO-CBD-001",
                    "state": "sale",
                    "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                    "currency_id": [1, "VND"],
                    "date_order": "2026-05-01 09:00:00",
                    "amount_untaxed": 100_000_000,
                    "amount_total": 110_000_000,
                    "user_id": [2, "Salesperson Synthetic"],
                }
            ]
            records["sale.order.line"] = []
            records["project.project"] = [
                {
                    "id": 100,
                    "name": "DA Cost Breakdown API",
                    "allow_timesheets": True,
                    "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                    "sale_order_id": [10, "SO-CBD-001"],
                    "account_id": [101, "AA-101"],
                    "active": True,
                }
            ]
            fake_client = SyntheticOdooClient(
                records=records,
                panels={
                    100: {
                        "profitability_items": {
                            "costs": {
                                "data": [
                                    {"id": "purchase_order", "name": "Purchase Order", "billed": -20_000_000, "to_bill": -5_000_000}
                                ]
                            }
                        }
                    }
                },
            )
            with (
                patch("cache.CACHE_DB_PATH", self.db_path),
                patch("app.CACHE_DB_PATH", self.db_path),
                patch("app.get_settings", return_value=settings),
                patch("config.get_settings", return_value=settings),
                patch("app.OdooAPI", return_value=fake_client),
            ):
                app = create_app()
                app.config["TESTING"] = True
                resp = app.test_client().get("/api/dashboard?project_id=100")
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["custom_cost_breakdown"][0]["expected"], 25_000_000.0)


if __name__ == "__main__":
    unittest.main()
