import { state } from '../state.js';
import { DEFAULT_DATE_FROM } from '../config.js';
import { formatVND, formatPercent } from '../utils.js';

export function renderKPIs(summary) {
    document.getElementById('totalProjects').textContent = summary.total_projects;
    document.getElementById('validProjects').textContent =
        `${summary.valid_project_count} dự án hợp lệ`;
    document.getElementById('totalBG').textContent = formatVND(summary.total_bg_untaxed);
    document.getElementById('totalCost').textContent = formatVND(summary.total_native_expected_cost);
    document.getElementById('totalGP').textContent = formatVND(summary.total_gp_amount);

    const weightedGP = document.getElementById('weightedGP');
    weightedGP.textContent = `${formatPercent(summary.weighted_gp_percent)} weighted`;
    if (summary.weighted_gp_percent === null || summary.weighted_gp_percent === undefined) {
        weightedGP.className = 'kpi-subtitle';
    } else if (summary.weighted_gp_percent >= 0) {
        weightedGP.className = 'kpi-subtitle gp-positive';
    } else {
        weightedGP.className = 'kpi-subtitle gp-negative';
    }
}

export function getDashboardMeta() {
    const projects = state.dashboardData?.projects || [];
    const summary = state.dashboardData?.summary || {};
    const doneCount = Number(summary.total_projects || 0);
    return state.dashboardData?.meta || {
        date_field: 'sale.order.date_order',
        project_scope: 'all_order_states',
        summary_scope: 'done_only',
        counts: {
            list_projects: projects.length,
            done_projects: doneCount,
            valid_done_projects: Number(summary.valid_project_count || 0),
            non_done_projects: Math.max(projects.length - doneCount, 0),
        },
        state_counts: projects.reduce((acc, project) => {
            const key = project.order_state || 'No state';
            acc[key] = (acc[key] || 0) + 1;
            return acc;
        }, {}),
        date_from: state.dashboardData?.date_from || DEFAULT_DATE_FROM,
    };
}

export function renderScopeBar() {
    const meta = getDashboardMeta();
    const counts = meta.counts || {};
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };
    setText('scopeListCount', counts.list_projects ?? (state.dashboardData?.projects || []).length);
    setText('scopeDoneCount', counts.done_projects ?? state.dashboardData?.summary?.total_projects ?? 0);
    setText('scopeValidDoneCount', counts.valid_done_projects ?? state.dashboardData?.summary?.valid_project_count ?? 0);
    setText('scopeDateFrom', meta.date_from || state.dashboardData?.date_from || DEFAULT_DATE_FROM);
}
