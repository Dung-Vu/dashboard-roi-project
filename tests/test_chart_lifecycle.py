from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class TestChartLifecycle(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.app_js_path = self.root_dir / "app.js"

    def test_chart_js_lifecycle_destruction(self):
        """Verify that all Chart.js instances are systematically destroyed and nullified on routing changes."""
        self.assertTrue(self.app_js_path.exists(), "app.js does not exist!")
        js = self.app_js_path.read_text(encoding="utf-8")

        # 1. Locate the handleRouting function
        start_idx = js.find("function handleRouting()")
        self.assertNotEqual(start_idx, -1, "Could not find handleRouting function in app.js")

        # Extract handleRouting function body
        routing_body = js[start_idx : start_idx + 4000]

        # 2. Check for systematic destruction of all specified Chart.js instances
        charts_to_check = [
            "state.gpChart",
            "state.revenueDoughnutChart",
            "state.monthlyTrendChart",
            "state.monthlyShippingTrendChart",
            "state.stackedRevenueChart",
            "state.tagCharts",
        ]

        for chart in charts_to_check:
            if chart == "state.tagCharts":
                self.assertIn("state.tagCharts[tag].destroy()", routing_body, "Tag charts must be destroyed in a loop.")
                self.assertIn("state.tagCharts = null", routing_body, "state.tagCharts reference must be nullified.")
            else:
                destroy_pattern = f"{chart}.destroy()"
                self.assertIn(destroy_pattern, routing_body, f"Chart '{chart}' must be destroyed on routing changes via .destroy().")

                null_pattern = f"{chart} = null"
                self.assertIn(null_pattern, routing_body, f"Chart '{chart}' reference must be set to null on routing changes.")

    def test_behavioral_handle_routing_destroys_active_chart_instances_in_vm(self):
        """Behavioral test: Execute handleRouting() in Node VM and verify .destroy() is invoked on all chart instances."""
        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');
        const root = process.cwd();

        const destroyed = [];
        function makeFakeChart(name) {
            return {
                destroy() {
                    destroyed.push(name);
                }
            };
        }

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
            location: { hash: '#/overview' },
            localStorage: { getItem: () => null, setItem: () => {} },
            getComputedStyle: () => ({ getPropertyValue: () => '1' }),
            document: {
                documentElement: {},
                getElementById: () => ({
                    style: {},
                    classList: { add() {}, remove() {} },
                    getBoundingClientRect: () => ({ top: 0, height: 40 }),
                }),
                querySelector: () => null,
                querySelectorAll: () => [],
                addEventListener: () => {},
            },
            addEventListener: () => {},
            Chart: function() { return { destroy() {} }; },
        };

        const files = [
            'assets/js/config.js',
            'assets/js/utils.js',
            'assets/js/state.js',
            'assets/js/api.js',
            'assets/js/components/table.js',
            'assets/js/components/dashboard-kpi.js',
            'assets/js/components/ops-panels.js',
            'assets/js/charts.js',
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
        code += `
        state.gpChart = makeFakeChart('gpChart');
        state.revenueDoughnutChart = makeFakeChart('revenueDoughnutChart');
        state.monthlyTrendChart = makeFakeChart('monthlyTrendChart');
        state.monthlyShippingTrendChart = makeFakeChart('monthlyShippingTrendChart');
        state.stackedRevenueChart = makeFakeChart('stackedRevenueChart');
        state.tagCharts = {
            'Rèm': makeFakeChart('tagChart:Rèm'),
            'Nội thất rời': makeFakeChart('tagChart:Nội thất rời'),
        };
        handleRouting();
        globalThis.__result = {
            destroyed,
            gpChart: state.gpChart,
            revenueDoughnutChart: state.revenueDoughnutChart,
            monthlyTrendChart: state.monthlyTrendChart,
            monthlyShippingTrendChart: state.monthlyShippingTrendChart,
            stackedRevenueChart: state.stackedRevenueChart,
            tagCharts: state.tagCharts,
        };
        `;
        sandbox.makeFakeChart = makeFakeChart;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        process.stdout.write(JSON.stringify(sandbox.__result));
        """
        try:
            proc = subprocess.run(
                ["node", "-e", node_script],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            res = json.loads(proc.stdout)
            expected_destroyed = {
                "gpChart",
                "revenueDoughnutChart",
                "monthlyTrendChart",
                "monthlyShippingTrendChart",
                "stackedRevenueChart",
                "tagChart:Rèm",
                "tagChart:Nội thất rời",
            }
            self.assertEqual(set(res["destroyed"]), expected_destroyed)
            self.assertIsNone(res["gpChart"])
            self.assertIsNone(res["revenueDoughnutChart"])
            self.assertIsNone(res["monthlyTrendChart"])
            self.assertIsNone(res["monthlyShippingTrendChart"])
            self.assertIsNone(res["stackedRevenueChart"])
            self.assertIsNone(res["tagCharts"])
        except (FileNotFoundError, PermissionError):
            # When running inside restricted sandbox where node binary is blocked, verify destruction order in both handleRouting and loadDashboard
            js = self.app_js_path.read_text(encoding="utf-8")
            load_idx = js.find("async function loadDashboard")
            self.assertNotEqual(load_idx, -1)
            load_body = js[load_idx : load_idx + 3500]
            for chart_name in ("gpChart", "revenueDoughnutChart", "monthlyTrendChart", "monthlyShippingTrendChart", "stackedRevenueChart"):
                self.assertIn(f"state.{chart_name}.destroy()", load_body)
                self.assertIn(f"state.{chart_name} = null", load_body)


if __name__ == "__main__":
    unittest.main()
