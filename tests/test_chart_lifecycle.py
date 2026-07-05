from __future__ import annotations

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
            "state.tagCharts"
        ]

        for chart in charts_to_check:
            if chart == "state.tagCharts":
                # Check for loop destruction
                self.assertIn("state.tagCharts[tag].destroy()", routing_body, "Tag charts must be destroyed in a loop.")
                self.assertIn("state.tagCharts = null", routing_body, "state.tagCharts reference must be nullified.")
            else:
                # Check that .destroy() is called on the chart reference
                destroy_pattern = f"{chart}.destroy()"
                self.assertIn(destroy_pattern, routing_body, f"Chart '{chart}' must be destroyed on routing changes via .destroy().")

                # Check that the reference is set to null
                null_pattern = f"{chart} = null"
                self.assertIn(null_pattern, routing_body, f"Chart '{chart}' reference must be set to null on routing changes.")


if __name__ == "__main__":
    unittest.main()
