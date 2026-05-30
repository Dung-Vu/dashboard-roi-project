from __future__ import annotations

import unittest
import re
from pathlib import Path

class FrontendIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.index_path = self.root_dir / "index.html"
        self.app_path = self.root_dir / "app.js"

    def _extract_function(self, js: str, func_name: str) -> str | None:
        start_idx = js.find(f"function {func_name}")
        if start_idx == -1:
            return None
        
        open_brace_idx = js.find("{", start_idx)
        if open_brace_idx == -1:
            return None
            
        brace_count = 1
        current_idx = open_brace_idx + 1
        while brace_count > 0 and current_idx < len(js):
            char = js[current_idx]
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
            current_idx += 1
            
        if brace_count == 0:
            return js[start_idx:current_idx]
        return None

    def test_index_html_loads_app_js_as_es_module(self):
        self.assertTrue(self.index_path.exists(), "index.html does not exist!")
        html = self.index_path.read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="app.js"></script>', html, 
                      "index.html must load app.js with type='module'")

    def test_app_js_defines_escape_html(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.app_path.read_text(encoding="utf-8")
        self.assertIn("function escapeHTML(", js, "app.js must define escapeHTML function")

    def test_app_js_escapes_all_required_injection_points(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.app_path.read_text(encoding="utf-8")
        
        # Verify required escapeHTML injections
        self.assertIn("escapeHTML(p.sale_order_name", js, "p.sale_order_name must be escaped")
        self.assertIn("escapeHTML(p.project_name", js, "p.project_name must be escaped")
        self.assertIn("escapeHTML(p.customer", js, "p.customer must be escaped")
        self.assertIn("escapeHTML(t)", js, "All tags inside p.tags must be escaped")
        self.assertIn("escapeHTML(p.order_state)", js, "stateLabel fallback p.order_state must be escaped")
        self.assertIn("escapeHTML(tag)", js, "tag group name inside renderTagAnalysis must be escaped")
        self.assertIn("escapeHTML(r.range)", js, "r.range inside renderTagAnalysis must be escaped")

    def test_app_js_uses_document_fragment_for_table_rendering(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.app_path.read_text(encoding="utf-8")
        
        # Extract renderProjectsTable body
        body = self._extract_function(js, "renderProjectsTable")
        self.assertIsNotNone(body, "Could not find renderProjectsTable function")
        
        self.assertIn("document.createDocumentFragment()", body, 
                      "renderProjectsTable must use document.createDocumentFragment()")
        self.assertIn("fragment.appendChild(tr)", body, 
                      "renderProjectsTable must append elements to fragment")
        
        # Ensure no tbody.appendChild(tr) inside the row rendering loop
        foreach_match = re.search(r"\w+\.forEach\([\s\S]*?fragment\.appendChild\(tr\)[\s\S]*?\}\);", body)
        self.assertIsNotNone(foreach_match, "Could not find row rendering forEach loop")
        foreach_body = foreach_match.group(0)
        self.assertNotIn("tbody.appendChild(", foreach_body, 
                         "renderProjectsTable must NOT append rows directly to tbody inside loop")

    def test_app_js_uses_document_fragment_for_tag_analysis_rendering(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.app_path.read_text(encoding="utf-8")
        
        # Extract renderTagAnalysis body
        body = self._extract_function(js, "renderTagAnalysis")
        self.assertIsNotNone(body, "Could not find renderTagAnalysis function")
        
        self.assertIn("document.createDocumentFragment()", body, 
                      "renderTagAnalysis must use document.createDocumentFragment()")
        self.assertIn("fragment.appendChild(card)", body, 
                      "renderTagAnalysis must append elements to fragment")
        
        # Ensure no container.appendChild(card) inside the loop
        foreach_match = re.search(r"tags\.forEach\([\s\S]*?\}\);", body)
        self.assertIsNotNone(foreach_match, "Could not find tags.forEach loop")
        foreach_body = foreach_match.group(0)
        self.assertNotIn("container.appendChild(", foreach_body, 
                         "renderTagAnalysis must NOT append cards directly to container inside loop")

    def test_no_global_scope_leaks_to_window(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.app_path.read_text(encoding="utf-8")
        self.assertNotIn("window.", js, "Do not assign top-level variables to window object")

    def test_phase_2_orbs_and_particles_exist(self):
        html = self.index_path.read_text(encoding="utf-8")
        for orb in ["orb-1", "orb-2", "orb-3", "orb-4"]:
            self.assertIn(orb, html, f"{orb} is missing from background layer!")
        self.assertIn("particles-container", html, "Particles container is missing!")

    def test_kpi_cards_and_menu_indicator_html(self):
        html = self.index_path.read_text(encoding="utf-8")
        self.assertIn("menu-indicator", html, "Menu indicator element missing from sidebar-menu!")
        self.assertIn("revenueDoughnutChart", html, "Doughnut chart canvas element missing from rankings view!")
        self.assertIn("tagLeaderboard", html, "Leaderboard container element missing from rankings view!")
        self.assertIn("dataScopeBar", html, "Data scope bar is required to explain list-vs-KPI counts!")
        self.assertIn("healthFilter", html, "GP health filter is required in projects table controls!")
        self.assertIn("stateMixPanel", html, "Operational state mix panel is missing from overview!")

    def test_app_js_implements_indicator_and_visuals(self):
        js = self.app_path.read_text(encoding="utf-8")
        self.assertIn("function updateMenuIndicator(", js, "updateMenuIndicator() missing from app.js!")
        self.assertIn("function renderKPISparklines(", js, "renderKPISparklines() missing from app.js!")
        self.assertIn("health-orb-badge", js, "ROI Health orb render markup missing from app.js!")
        self.assertIn("renderRevenueDoughnut(", js, "renderRevenueDoughnut() missing from app.js!")
        self.assertIn("function renderScopeBar(", js, "renderScopeBar() missing from app.js!")
        self.assertIn("function renderOperationalPanels(", js, "renderOperationalPanels() missing from app.js!")
        self.assertIn("function getHealthBucket(", js, "getHealthBucket() missing from app.js!")

if __name__ == "__main__":
    unittest.main()
