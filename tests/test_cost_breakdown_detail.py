from __future__ import annotations

import unittest
from pathlib import Path

class CostBreakdownDetailIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.table_path = self.root_dir / "assets" / "js" / "components" / "table.js"
        self.app_path = self.root_dir / "app.js"

    def test_table_js_defines_cost_details_container(self):
        self.assertTrue(self.table_path.exists(), "table.js does not exist!")
        content = self.table_path.read_text(encoding="utf-8")
        self.assertIn('cost-loading-${p.project_id}', content, 
                      "table.js must render cost loading placeholder")
        self.assertIn('Cấu thành chi phí —', content,
                      "table.js must render cost structure header section")

    def test_app_js_defines_fetch_and_render_cost_details(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        content = self.app_path.read_text(encoding="utf-8")
        self.assertIn("function fetchAndRenderCostDetails(projectId)", content,
                      "app.js must define fetchAndRenderCostDetails function")
        self.assertIn("function renderCostDetailsHTML(container, costSources)", content,
                      "app.js must define renderCostDetailsHTML function")
        self.assertIn("projectDetailsCache", content,
                      "app.js must define projectDetailsCache for frontend caching")
        self.assertIn("fetchAndRenderCostDetails(projectId)", content,
                      "app.js must call fetchAndRenderCostDetails when expanding a row")

if __name__ == "__main__":
    unittest.main()
