from __future__ import annotations

import unittest
from pathlib import Path

class MonthlyShippingChartIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.html_path = self.root_dir / "index.html"
        self.charts_path = self.root_dir / "assets" / "js" / "charts.js"
        self.state_path = self.root_dir / "assets" / "js" / "state.js"
        self.service_path = self.root_dir / "dashboard_service.py"

    def test_index_html_defines_monthly_shipping_chart_canvas(self):
        self.assertTrue(self.html_path.exists(), "index.html does not exist!")
        content = self.html_path.read_text(encoding="utf-8")
        self.assertIn('id="monthlyShippingTrendChart"', content, 
                      "index.html must define the monthlyShippingTrendChart canvas element")
        self.assertIn('Phân tích Xu hướng Chi phí vận chuyển theo tháng', content,
                      "index.html must contain section title for monthly shipping analysis")

    def test_charts_js_defines_monthly_shipping_chart_renderer(self):
        self.assertTrue(self.charts_path.exists(), "charts.js does not exist!")
        content = self.charts_path.read_text(encoding="utf-8")
        self.assertIn("export function renderMonthlyShippingTrendChart", content,
                      "charts.js must export renderMonthlyShippingTrendChart function")

    def test_state_js_tracks_monthly_shipping_chart(self):
        self.assertTrue(self.state_path.exists(), "state.js does not exist!")
        content = self.state_path.read_text(encoding="utf-8")
        self.assertIn("monthlyShippingTrendChart: null", content,
                      "state.js must track monthlyShippingTrendChart in state object")

    def test_dashboard_service_returns_shipping_cost_field(self):
        self.assertTrue(self.service_path.exists(), "dashboard_service.py does not exist!")
        content = self.service_path.read_text(encoding="utf-8")
        self.assertIn('"shipping_cost": shipping_cost', content,
                      "dashboard_service.py must include shipping_cost in project row dictionary")

if __name__ == "__main__":
    unittest.main()
