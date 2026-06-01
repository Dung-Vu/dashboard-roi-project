// Node.js script to stress test app.js visual components under adversarial scenarios
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// 1. Setup Mock DOM Environment
const createdElements = [];
const mockedElements = {};

function createMockElement(tag) {
    const el = {
        tagName: tag.toUpperCase(),
        style: {},
        classList: {
            list: new Set(),
            add(cls) { this.list.add(cls); },
            remove(cls) { this.list.delete(cls); },
            contains(cls) { return this.list.has(cls); }
        },
        remove: () => {},
        insertAdjacentHTML: (pos, html) => {
            el.insertedHTML = (el.insertedHTML || '') + html;
        },
        appendChild: (child) => {
            el.children = el.children || [];
            if (child.children && Array.isArray(child.children)) {
                el.children.push(...child.children);
            } else {
                el.children.push(child);
            }
        },
        querySelector: (sel) => {
            if (sel === '.kpi-sparkline') return el.sparkline;
            return null;
        },
        getBoundingClientRect: () => ({ top: 100, height: 40 }),
        addEventListener: (event, cb) => {
            el.listeners = el.listeners || {};
            el.listeners[event] = el.listeners[event] || [];
            el.listeners[event].push(cb);
        },
        getAttribute: (attr) => {
            if (attr === 'href') return el._href;
            return null;
        }
    };
    Object.defineProperty(el, 'textContent', {
        get() { return el._textContent; },
        set(val) { el._textContent = val; }
    });
    Object.defineProperty(el, 'innerHTML', {
        get() { return el._innerHTML; },
        set(val) { el._innerHTML = val; }
    });
    Object.defineProperty(el, 'className', {
        get() { return el._className; },
        set(val) { el._className = val; }
    });
    Object.defineProperty(el, 'value', {
        get() { return el._value || ''; },
        set(val) { el._value = val; }
    });
    createdElements.push(el);
    return el;
}

const documentMock = {
    addEventListener: () => {},
    createElement: (tag) => createMockElement(tag),
    createDocumentFragment: () => {
        const frag = {
            children: [],
            appendChild: (child) => {
                frag.children.push(child);
            }
        };
        return frag;
    },
    getElementById: (id) => {
        if (!mockedElements[id]) {
            mockedElements[id] = createMockElement('div');
        }
        return mockedElements[id];
    },
    querySelectorAll: (sel) => {
        if (sel === '.kpi-card') {
            if (!mockedElements.kpiCards) {
                mockedElements.kpiCards = [
                    createMockElement('div'),
                    createMockElement('div')
                ];
                mockedElements.kpiCards.forEach(c => {
                    c.sparkline = createMockElement('div');
                    c.sparkline.remove = () => { c.sparklineRemoved = true; c.sparkline = null; };
                });
            }
            return mockedElements.kpiCards;
        }
        if (sel === '.route-view') {
            return mockedElements.routeViews || [];
        }
        if (sel === '.sidebar-menu .menu-item') {
            return mockedElements.menuItems || [];
        }
        return [];
    }
};

const sandbox = {
    global: {},
    window: {},
    console: console,
    document: documentMock,
    location: { hash: '#/overview' },
    addEventListener: () => {},
    setInterval: () => {},
    setTimeout: () => {},
    Math: Math,
    Date: Date,
    String: String,
    Number: Number,
    Intl: Intl,
    Array: Array,
    Object: Object,
    RegExp: RegExp,
    Error: Error,
    TypeError: TypeError,
    Chart: function() {
        return { destroy: () => {} };
    }
};

// 2. Load all JS modules in dependency resolution order, strip import/export, and concatenate
const modules = [
    'assets/js/config.js',
    'assets/js/utils.js',
    'assets/js/state.js',
    'assets/js/api.js',
    'assets/js/charts.js',
    'assets/js/components/dashboard-kpi.js',
    'assets/js/components/table.js',
    'assets/js/components/ops-panels.js',
    'app.js'
];

let combinedCode = '';
for (const mod of modules) {
    const modPath = path.join(__dirname, '..', mod);
    let modCode = fs.readFileSync(modPath, 'utf8');

    // Strip imports
    modCode = modCode.replace(/import\s+(?:[\w*\s{},]*)\s+from\s+['"].*?['"];?/g, '');

    // Strip exports
    modCode = modCode.replace(/\bexport\s+(const|let|var|function|async\s+function|class)\b/g, '$1');
    modCode = modCode.replace(/\bexport\s+\{\s*[\w\s,]*\s*\};?/g, '');

    combinedCode += '\n// --- MODULE: ' + mod + ' ---\n' + modCode;
}

// Strip out the DOMContentLoaded event listener at the end so it doesn't auto-run loadDashboard() during context execution
combinedCode = combinedCode.replace(/document\.addEventListener\('DOMContentLoaded'[\s\S]*\}\);?\s*$/, '');

// Write to debug file
fs.writeFileSync(path.join(__dirname, 'debug_combined.js'), combinedCode);

vm.createContext(sandbox);
vm.runInContext(combinedCode, sandbox);

// 3. Test Cases
console.log("--- Starting Frontend Adversarial Stress Tests ---");
let testsPassed = 0;
let testsFailed = 0;

function assert(condition, message) {
    if (condition) {
        console.log(`[PASS] ${message}`);
        testsPassed++;
    } else {
        console.error(`[FAIL] ${message}`);
        testsFailed++;
    }
}

// TEST 1: Empty projects array in renderKPISparklines()
try {
    // Reset KPI cards state
    documentMock.querySelectorAll('.kpi-card').forEach(c => {
        c.sparkline = createMockElement('div');
        c.sparkline.remove = () => { c.sparklineRemoved = true; c.sparkline = null; };
        c.sparklineRemoved = false;
    });

    // Execute with empty projects array
    sandbox.renderKPISparklines([]);

    // Verify robustness: did it clear old sparklines?
    const cards = documentMock.querySelectorAll('.kpi-card');
    const firstCardCleared = cards[0].sparklineRemoved;

    // If it returned early without clearing, sparklineRemoved will be false!
    assert(firstCardCleared, "Assert that the sparkline visual is cleared when projects are empty (firstCardCleared is true).");
} catch (err) {
    console.error("[ERROR] renderKPISparklines([]) threw:", err.message);
    testsFailed++;
}

// TEST 2: GP% negative, extremely high, null, undefined in health orb badge formatting
try {
    const tbody = documentMock.getElementById('projectsTable');

    const adversarialProjects = [
        { sale_order_name: "SO001", project_name: "Negative GP", customer: "A", tags: [], order_state: "Done", bg_untaxed: 100, native_expected_cost: 150, gp_amount: -50, gp_percent: -50 },
        { sale_order_name: "SO002", project_name: "Extreme GP", customer: "B", tags: [], order_state: "Done", bg_untaxed: 100, native_expected_cost: 0, gp_amount: 150, gp_percent: 150 },
        { sale_order_name: "SO003", project_name: "Null GP", customer: "C", tags: [], order_state: "Done", bg_untaxed: 0, native_expected_cost: 0, gp_amount: 0, gp_percent: null },
        { sale_order_name: "SO004", project_name: "Undefined GP", customer: "D", tags: [], order_state: "Done", bg_untaxed: 0, native_expected_cost: 0, gp_amount: 0, gp_percent: undefined }
    ];

    tbody.innerHTML = '';
    sandbox.renderProjectsTable(adversarialProjects);

    // Get fragment children appended to tbody
    const children = tbody.children || [];
    assert(children.length === 4, "renderProjectsTable rendered exactly 4 rows.");

    // Row 1: Negative GP (-50) -> should be health-coral
    const row1HTML = children[0].innerHTML;
    assert(row1HTML.includes('health-orb-badge health-coral') && row1HTML.includes('-50.0%'), "Negative GP% (-50.0%) correctly maps to health-coral style.");

    // Row 2: Extreme GP (150) -> should be health-green
    const row2HTML = children[1].innerHTML;
    assert(row2HTML.includes('health-orb-badge health-green') && row2HTML.includes('150.0%'), "Extremely high GP% (150.0%) correctly maps to health-green style.");

    // Row 3 & 4: Null/Undefined GP -> should show hyphen '-'
    const row3HTML = children[2].innerHTML;
    const row4HTML = children[3].innerHTML;
    assert(row3HTML.includes('opacity: 0.5;">-</span>') && row4HTML.includes('opacity: 0.5;">-</span>'), "Null/Undefined GP% correctly falls back to safe hyphen '-' label.");

} catch (err) {
    console.error("[ERROR] renderProjectsTable with adversarial projects threw:", err.stack);
    testsFailed++;
}

// TEST 3: Null and Undefined summary.weighted_gp_percent in renderKPIs()
try {
    const weightedGP = documentMock.getElementById('weightedGP');

    // Test with null
    sandbox.renderKPIs({
        total_projects: 0,
        valid_project_count: 0,
        total_bg_untaxed: 0,
        total_native_expected_cost: 0,
        total_gp_amount: 0,
        weighted_gp_percent: null
    });

    assert(weightedGP.className === 'kpi-subtitle', "Assert that a null weighted GP% styles the subtitle as neutral 'kpi-subtitle'.");

    // Test with undefined
    sandbox.renderKPIs({
        total_projects: 0,
        valid_project_count: 0,
        total_bg_untaxed: 0,
        total_native_expected_cost: 0,
        total_gp_amount: 0,
        weighted_gp_percent: undefined
    });
    assert(weightedGP.className === 'kpi-subtitle', "Assert that an undefined weighted GP% styles the subtitle as neutral 'kpi-subtitle'.");

} catch (err) {
    console.error("[ERROR] renderKPIs with null/undefined GP threw:", err.message);
    testsFailed++;
}

// TEST 4: String input in formatPercent() formatted successfully
try {
    let threwError = false;
    let formattedVal = "";
    try {
        formattedVal = sandbox.formatPercent("45");
    } catch (e) {
        threwError = true;
    }
    assert(!threwError && formattedVal === "45.0%", "Assert that string input '45' is successfully formatted as '45.0%' without throwing an error.");
} catch (err) {
    console.error("[ERROR] formatPercent threw unexpected:", err.message);
    testsFailed++;
}

// TEST 5: renderKPISparklines(null) doesn't throw a TypeError
try {
    let threwError = false;
    try {
        sandbox.renderKPISparklines(null);
    } catch (e) {
        threwError = true;
        console.error("renderKPISparklines(null) threw error:", e);
    }
    assert(!threwError, "Assert that renderKPISparklines(null) handles non-array values gracefully and does not throw a TypeError.");
} catch (err) {
    console.error("[ERROR] renderKPISparklines(null) failed test block:", err.message);
    testsFailed++;
}

// TEST 6: Click-to-Odoo Hardening verification
try {
    const tbody = documentMock.getElementById('projectsTable');

    // Scenario 1: Malicious odooUrl (quote breakout) and valid numeric sale_order_id
    vm.runInContext('state.dashboardData = { meta: { odoo_url: \'https://odoo.com" onclick="alert(1)"\' } };', sandbox);

    const validProject = [
        { sale_order_id: 12345, sale_order_name: "SO_VALID", project_name: "Valid ID", customer: "A", tags: [], order_state: "Done", bg_untaxed: 100, native_expected_cost: 150, gp_amount: -50, gp_percent: -50 }
    ];
    tbody.innerHTML = '';
    tbody.children = []; // Explicitly clear the mock DOM children array
    sandbox.renderProjectsTable(validProject);
    const row1HTML = tbody.children[0].innerHTML;
    assert(row1HTML.includes('&quot; onclick=&quot;alert(1)&quot;'), "odoo_url quote breakout is properly HTML-escaped.");
    assert(row1HTML.includes('id=12345&model=sale.order'), "sale_order_id is parsed and included as a valid number in href.");

    // Scenario 2: Non-numeric sale_order_id
    const invalidIdProject = [
        { sale_order_id: "abc", sale_order_name: "SO_INVALID", project_name: "Invalid ID", customer: "B", tags: [], order_state: "Done", bg_untaxed: 100, native_expected_cost: 150, gp_amount: -50, gp_percent: -50 }
    ];
    tbody.innerHTML = '';
    tbody.children = []; // Explicitly clear the mock DOM children array
    sandbox.renderProjectsTable(invalidIdProject);
    const row2HTML = tbody.children[0].innerHTML;
    assert(row2HTML.includes('SO_INVALID') && !row2HTML.includes('class="odoo-link"'), "Non-numeric sale_order_id defaults to strong text and prevents link rendering.");

} catch (err) {
    console.error("[ERROR] Click-to-Odoo Hardening test threw:", err.stack);
    testsFailed++;
}

console.log("--- Stress Testing Complete ---");
console.log(`Summary: Passed ${testsPassed} assertions, Detected ${testsFailed} vulnerabilities/bugs.`);

process.exit(0);
