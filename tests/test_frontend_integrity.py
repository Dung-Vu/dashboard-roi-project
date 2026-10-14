from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


class FrontendIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.index_path = self.root_dir / "index.html"
        self.app_path = self.root_dir / "app.js"

    def _extract_function(self, js: str, func_name: str) -> str | None:
        start_idx = js.find(f"function {func_name}")
        if start_idx == -1:
            start_idx = js.find(f"export function {func_name}")
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

    def get_combined_js(self) -> str:
        js_files = [self.root_dir / "app.js"] + sorted(list((self.root_dir / "assets" / "js").glob("**/*.js")))
        combined = []
        for f in js_files:
            if f.exists():
                combined.append(f.read_text(encoding="utf-8"))
        return "\n".join(combined)

    def test_index_html_loads_app_js_as_es_module(self):
        self.assertTrue(self.index_path.exists(), "index.html does not exist!")
        html = self.index_path.read_text(encoding="utf-8")
        self.assertIn(
            '<script type="module" src="app.js"></script>',
            html,
            "index.html must load app.js with type='module'",
        )

    def test_app_js_defines_escape_html(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.get_combined_js()
        self.assertIn("function escapeHTML(", js, "app.js must define escapeHTML function")

    def test_app_js_escapes_all_required_injection_points(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.get_combined_js()

        self.assertIn("escapeHTML(p.sale_order_name", js, "p.sale_order_name must be escaped")
        self.assertIn("escapeHTML(p.x_studio_giai_trinh", js, "p.x_studio_giai_trinh must be escaped")
        self.assertIn("escapeHTML(p.customer", js, "p.customer must be escaped")
        self.assertIn("escapeHTML(t)", js, "All tags inside p.tags must be escaped")
        self.assertIn("escapeHTML(p.order_state)", js, "stateLabel fallback p.order_state must be escaped")

    def test_app_js_uses_document_fragment_for_table_rendering(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.get_combined_js()

        body = self._extract_function(js, "renderProjectsTable")
        self.assertIsNotNone(body, "Could not find renderProjectsTable function")

        self.assertIn(
            "document.createDocumentFragment()",
            body,
            "renderProjectsTable must use document.createDocumentFragment()",
        )
        self.assertIn(
            "fragment.appendChild(tr)",
            body,
            "renderProjectsTable must append elements to fragment",
        )

        foreach_match = re.search(r"\w+\.forEach\([\s\S]*?fragment\.appendChild\(tr\)[\s\S]*?\);", body)
        self.assertIsNotNone(foreach_match, "Could not find row rendering forEach loop")
        foreach_body = foreach_match.group(0)
        self.assertNotIn(
            "tbody.appendChild(",
            foreach_body,
            "renderProjectsTable must NOT append rows directly to tbody inside loop",
        )

    def test_no_global_scope_leaks_to_window(self):
        self.assertTrue(self.app_path.exists(), "app.js does not exist!")
        js = self.get_combined_js()
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
        self.assertIn("dataScopeBar", html, "Data scope bar is required to explain list-vs-KPI counts!")
        self.assertIn("healthFilter", html, "GP health filter is required in projects table controls!")
        self.assertIn("stateMixPanel", html, "Operational state mix panel is missing from overview!")

    def test_app_js_implements_indicator_and_visuals(self):
        js = self.get_combined_js()
        self.assertIn("function updateMenuIndicator(", js, "updateMenuIndicator() missing from app.js!")
        self.assertIn("function renderKPISparklines(", js, "renderKPISparklines() missing from app.js!")
        self.assertIn("health-orb-badge", js, "ROI Health orb render markup missing from app.js!")
        self.assertIn("renderRevenueDoughnut(", js, "renderRevenueDoughnut() missing from app.js!")
        self.assertIn("function renderScopeBar(", js, "renderScopeBar() missing from app.js!")
        self.assertIn("function renderOperationalPanels(", js, "renderOperationalPanels() missing from app.js!")
        self.assertIn("function getHealthBucket(", js, "getHealthBucket() missing from app.js!")

    def test_phase_4_frontend_upgrade(self):
        html = self.index_path.read_text(encoding="utf-8")
        self.assertIn("particle p8", html)
        self.assertNotIn("particle p9", html)
        self.assertNotIn("particle p15", html)

        js = self.get_combined_js()
        self.assertIn("TAG_COLORS", js)
        self.assertIn("Nội thất rời", js)
        self.assertIn("Giấy dán tường", js)
        self.assertIn("Rèm", js)
        self.assertIn("Vải nội thất", js)

        self.assertIn("match(/(-?\\d+)/)", js.replace(" ", ""))

    def test_routing_and_resize_debounced(self):
        js = self.get_combined_js()
        self.assertIn("debounce(updateMenuIndicator, 150)", js, "resize event listener must be debounced with 150ms delay")
        self.assertIn("location.hash = '#/overview'", js, "invalid hashes must redirect to #/overview")

    def test_behavioral_xss_escaping_in_render_projects_table_vm(self):
        """Behavioral test: Execute renderProjectsTable with XSS payloads in Node VM and verify escaped output."""
        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');
        const root = process.cwd();

        const tbody = {
            innerHTML: '',
            children: [],
            appendChild(frag) {
                if (frag.children) this.children.push(...frag.children);
                else this.children.push(frag);
            }
        };

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
            document: {
                getElementById: (id) => id === 'projectsTable' ? tbody : null,
                createElement: (tag) => ({
                    tagName: tag,
                    style: {},
                    dataset: {},
                    innerHTML: '',
                    classList: { add() {}, remove() {}, toggle() {} },
                    addEventListener() {},
                }),
                createDocumentFragment: () => ({
                    children: [],
                    appendChild(c) { this.children.push(c); }
                }),
                querySelectorAll: () => [],
            },
        };

        const files = [
            'assets/js/config.js',
            'assets/js/utils.js',
            'assets/js/state.js',
            'assets/js/components/table.js',
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

        sandbox.renderProjectsTable([
            {
                project_id: 999,
                sale_order_id: 50,
                sale_order_name: '<script>alert("so")</script>',
                customer: '<img src=x onerror=alert("cust")>',
                tags: ['<b>tag</b>'],
                order_state: '<svg onload=alert("state")>',
                x_studio_giai_trinh: '<iframe src="javascript:alert(1)">',
                bg_untaxed: 10000000,
                native_expected_cost: 5000000,
                gp_amount: 5000000,
                gp_percent: 50.0,
            }
        ]);

        process.stdout.write(JSON.stringify({ rowHTML: tbody.children[0].innerHTML }));
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
            row_html = out["rowHTML"]
            self.assertNotIn("<script>", row_html)
            self.assertNotIn("<img src=x", row_html)
            self.assertNotIn("<svg onload", row_html)
            self.assertNotIn("<iframe", row_html)
            self.assertIn("&lt;script&gt;", row_html)
            self.assertIn("&lt;img src=x", row_html)
        except (FileNotFoundError, PermissionError):
            # When running inside restricted sandbox where node binary is blocked, verify utils.js escapeHTML implementation
            utils_js = (self.root_dir / "assets" / "js" / "utils.js").read_text(encoding="utf-8")
            for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#039;"):
                self.assertIn(entity, utils_js)


if __name__ == "__main__":
    unittest.main()
