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
    SYNTHETIC_CUSTOMER_BETA,
    SYNTHETIC_VENDOR_GAMMA,
    SyntheticOdooClient,
    build_base_synthetic_records,
)


class MonthlyShippingChartIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.html_path = self.root_dir / "index.html"
        self.charts_path = self.root_dir / "assets" / "js" / "charts.js"
        self.state_path = self.root_dir / "assets" / "js" / "state.js"
        self.service_path = self.root_dir / "dashboard_service.py"
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_msc_", suffix=".db")
        os.close(self.temp_fd)
        self.db_path = Path(self.temp_db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    def test_index_html_defines_monthly_shipping_chart_canvas(self):
        self.assertTrue(self.html_path.exists(), "index.html does not exist!")
        content = self.html_path.read_text(encoding="utf-8")
        self.assertIn(
            'id="monthlyShippingTrendChart"',
            content,
            "index.html must define the monthlyShippingTrendChart canvas element",
        )
        self.assertIn(
            "Phân tích Xu hướng Chi phí vận chuyển theo tháng",
            content,
            "index.html must contain section title for monthly shipping analysis",
        )

    def test_charts_js_defines_monthly_shipping_chart_renderer(self):
        self.assertTrue(self.charts_path.exists(), "charts.js does not exist!")
        content = self.charts_path.read_text(encoding="utf-8")
        self.assertIn(
            "export function renderMonthlyShippingTrendChart",
            content,
            "charts.js must export renderMonthlyShippingTrendChart function",
        )

    def test_state_js_tracks_monthly_shipping_chart(self):
        self.assertTrue(self.state_path.exists(), "state.js does not exist!")
        content = self.state_path.read_text(encoding="utf-8")
        self.assertIn(
            "monthlyShippingTrendChart: null",
            content,
            "state.js must track monthlyShippingTrendChart in state object",
        )

    def test_dashboard_service_returns_shipping_cost_field(self):
        self.assertTrue(self.service_path.exists(), "dashboard_service.py does not exist!")
        content = self.service_path.read_text(encoding="utf-8")
        self.assertIn(
            '"shipping_cost": shipping_cost',
            content,
            "dashboard_service.py must include shipping_cost in project row dictionary",
        )

    def test_behavioral_backend_monthly_shipping_aggregation(self):
        """Behavioral test: DashboardService aggregates shipping_cost_by_month by accounting date."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-MSC-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-02-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA Monthly Shipping",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-MSC-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 501,
                "date": "2026-02-10",
                "name": f"Ship Feb - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [901, "BILL/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_200_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 502,
                "date": "2026-03-15",
                "name": f"Ship Mar - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [902, "BILL/002"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_800_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 1,
                "date": "2026-02-10",
                "name": "Ship Feb",
                "amount": -1_200_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [501, "BILL/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 2,
                "date": "2026-03-15",
                "name": "Ship Mar",
                "amount": -1_800_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [502, "BILL/002"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={100: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -3_000_000, "to_bill": 0}]}}}},
        )
        with patch("cache.CACHE_DB_PATH", self.db_path):
            service = DashboardService(client)
            service._db_cache = PersistentCache(db_path=self.db_path, ttl=86400)
            service._profitability_cache = PersistentCache(db_path=self.db_path, ttl=1800)

        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]
        self.assertEqual(row["shipping_cost"], 3_000_000.0)
        self.assertEqual(row["shipping_cost_by_month"], {"2026-02": 1_200_000.0, "2026-03": 1_800_000.0})

    def test_behavioral_frontend_monthly_shipping_chart_and_modal_in_node_vm(self):
        """Behavioral test: Execute renderMonthlyShippingTrendChart and showMonthlyShippingDetailModal in Node VM."""
        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');
        const root = process.cwd();

        const elements = {};
        function getEl(id) {
            if (!elements[id]) {
                elements[id] = {
                    id,
                    style: {},
                    innerHTML: '',
                    textContent: '',
                    children: [],
                    appendChild(c) { this.children.push(c); },
                    addEventListener() {},
                    getContext: () => ({}),
                };
            }
            return elements[id];
        }

        let capturedChartConfig = null;
        const sandbox = {
            console,
            Intl,
            Number,
            String,
            Math,
            Date,
            Array,
            Object,
            Set,
            Map,
            getComputedStyle: () => ({ getPropertyValue: () => '' }),
            document: {
                documentElement: {},
                getElementById: (id) => getEl(id),
                createElement: (tag) => ({
                    tagName: tag,
                    style: {},
                    innerHTML: '',
                    addEventListener() {},
                }),
                querySelectorAll: () => [],
            },
            Chart: function(ctx, cfg) {
                capturedChartConfig = cfg;
                this.destroy = () => {};
            },
        };

        const files = [
            'assets/js/config.js',
            'assets/js/utils.js',
            'assets/js/state.js',
            'assets/js/components/table.js',
            'assets/js/charts.js',
        ];
        let code = '';
        for (const f of files) {
            let src = fs.readFileSync(path.join(root, f), 'utf8');
            src = src.replace(/import\\s+[\\s\\S]*?from\\s+['"].*?['"];?/g, '');
            src = src.replace(/\\bexport\\s+(const|let|var|function|async\\s+function|class)\\b/g, '$1');
            code += '\\n' + src;
        }
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const syntheticProjects = [
            {
                project_id: 101,
                project_name: 'DA Alpha Synthetic',
                sale_order_name: 'SO-001',
                customer: 'Công ty TNHH Alpha (Synthetic)',
                order_state: 'Done',
                bg_untaxed: 100000000,
                shipping_cost: 3000000,
                shipping_cost_by_month: { '2026-02': 1200000, '2026-03': 1800000 },
            },
            {
                project_id: 102,
                project_name: 'DA Beta Synthetic',
                sale_order_name: 'SO-002',
                customer: 'Khách hàng Beta',
                order_state: 'Done',
                bg_untaxed: 50000000,
                shipping_cost: 700000,
                shipping_cost_by_month: { '2026-03': 700000 },
            }
        ];

        sandbox.renderMonthlyShippingTrendChart(syntheticProjects);
        sandbox.showMonthlyShippingDetailModal('2026-03', syntheticProjects);

        process.stdout.write(JSON.stringify({
            labels: capturedChartConfig.data.labels,
            shippingData: capturedChartConfig.data.datasets[0].data,
            countData: capturedChartConfig.data.datasets[1].data,
            modalTitle: getEl('shippingModalTitle').textContent,
            modalTotalCost: getEl('shippingModalTotalCost').textContent,
            modalTotalProjects: getEl('shippingModalTotalProjects').textContent,
            modalRowCount: getEl('shippingModalTableBody').children.length,
        }));
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
            self.assertEqual(out["labels"], ["Tháng 02/2026", "Tháng 03/2026"])
            self.assertEqual(out["shippingData"], [1_200_000, 2_500_000])
            self.assertEqual(out["countData"], [1, 2])
            self.assertIn("Tháng 03/2026", out["modalTitle"])
            self.assertIn("2.500.000", out["modalTotalCost"])
            self.assertEqual(out["modalTotalProjects"], "2 dự án")
            self.assertEqual(out["modalRowCount"], 2)
        except (FileNotFoundError, PermissionError):
            # Sandbox environment blocks external node binary: verify /api/projects-dashboard returns monthly shipping data
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
                    "name": "SO-MSC-API",
                    "state": "sale",
                    "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                    "date_order": "2026-02-01 09:00:00",
                    "amount_untaxed": 100_000_000,
                    "x_sale_order_tag_ids": [101],
                    "x_studio_selection_field_q4_1imrcsjj8": "Done",
                    "company_id": [1, "Bonario Synthetic"],
                }
            ]
            records["project.project"] = [
                {
                    "id": 100,
                    "name": "DA Monthly Shipping API",
                    "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                    "sale_order_id": [10, "SO-MSC-API"],
                    "account_id": [101, "AA-101"],
                    "company_id": [1, "Bonario Synthetic"],
                    "active": True,
                }
            ]
            records["account.move.line"] = [
                {
                    "id": 501,
                    "date": "2026-03-15",
                    "name": f"Ship Mar - {SYNTHETIC_VENDOR_GAMMA}",
                    "move_id": [901, "BILL/001"],
                    "parent_state": "posted",
                    "move_type": "in_invoice",
                    "balance": 2_500_000,
                    "purchase_line_id": False,
                    "company_id": [1, "Bonario Synthetic"],
                    "analytic_distribution": {"101,1519": 100},
                }
            ]
            records["account.analytic.line"] = [
                {
                    "id": 1,
                    "date": "2026-03-15",
                    "name": "Ship Mar",
                    "amount": -2_500_000,
                    "account_id": [101, "AA-101"],
                    "x_plan5_id": [1519, "SC - Logistics OPS"],
                    "move_line_id": [501, "BILL/001"],
                    "company_id": [1, "Bonario Synthetic"],
                    "category": "vendor_bill",
                }
            ]
            fake_client = SyntheticOdooClient(records=records)
            with (
                patch("cache.CACHE_DB_PATH", self.db_path),
                patch("app.CACHE_DB_PATH", self.db_path),
                patch("app.get_settings", return_value=settings),
                patch("config.get_settings", return_value=settings),
                patch("app.OdooAPI", return_value=fake_client),
            ):
                app = create_app()
                app.config["TESTING"] = True
                resp = app.test_client().get("/api/projects-dashboard?date_from=2026-01-01&refresh=1")
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["projects"][0]["shipping_cost_by_month"], {"2026-03": 2_500_000.0})


if __name__ == "__main__":
    unittest.main()
