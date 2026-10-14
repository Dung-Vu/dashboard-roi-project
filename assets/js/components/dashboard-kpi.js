import { state } from '../state.js';
import { DEFAULT_DATE_FROM } from '../config.js';
import { formatVND, formatFullVND, formatPercent } from '../utils.js';

export function renderKPIs(summary) {
    if (!summary) return;
    document.getElementById('totalProjects').textContent = summary.total_projects;
    const zeroRevCount = Number(summary.zero_revenue_projects || 0);
    document.getElementById('validProjects').textContent = zeroRevCount > 0
        ? `${summary.valid_project_count} dự án hợp lệ (${zeroRevCount} DA 0đ)`
        : `${summary.valid_project_count} dự án hợp lệ`;
    document.getElementById('totalBG').textContent = formatVND(summary.total_bg_untaxed);
    document.getElementById('totalCost').textContent = formatVND(summary.total_adjusted_expected_cost ?? summary.total_native_expected_cost);
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

    // Hiển thị các trường mới theo Hợp đồng dữ liệu Mục 3
    const shippingAssigned = Number(summary.shipping_total ?? 0);
    const shippingUnassigned = Number(summary.shipping_unassigned_total ?? 0);
    const shippingCompany = Number(summary.shipping_company_total ?? (shippingAssigned + shippingUnassigned));

    const shipCompanyEl = document.getElementById('shippingCompanyTotal');
    if (shipCompanyEl) {
        shipCompanyEl.textContent = formatVND(shippingCompany);
        shipCompanyEl.title = `Tổng vận chuyển công ty: ${formatFullVND(shippingCompany)} (Đã gắn dự án: ${formatFullVND(shippingAssigned)} | Chưa gắn dự án: ${formatFullVND(shippingUnassigned)})`;
    }
    const shipBreakdownEl = document.getElementById('shippingBreakdownText');
    if (shipBreakdownEl) {
        shipBreakdownEl.textContent = `Đã gắn dự án: ${formatVND(shippingAssigned)} · Chưa gắn dự án: ${formatVND(shippingUnassigned)}`;
    }
    const zeroRevEl = document.getElementById('zeroRevenueProjects');
    if (zeroRevEl) {
        zeroRevEl.textContent = `${zeroRevCount} dự án`;
    }
    const refundEl = document.getElementById('refundTotal');
    if (refundEl) {
        const refundVal = Number(summary.refund_total ?? 0);
        refundEl.textContent = formatVND(refundVal);
        refundEl.title = formatFullVND(refundVal);
    }
    const staleWarnEl = document.getElementById('staleDataWarning');
    if (staleWarnEl) {
        const isStale = Boolean(summary.data_stale || state.dashboardData?.data_stale || state.dashboardData?.meta?.data_stale);
        staleWarnEl.style.display = isStale ? 'inline-flex' : 'none';
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
    
    const listCount = counts.list_projects ?? (state.dashboardData?.projects || []).length ?? 0;
    const doneCount = counts.done_projects ?? state.dashboardData?.summary?.total_projects ?? 0;
    const validCount = counts.valid_done_projects ?? state.dashboardData?.summary?.valid_project_count ?? 0;
    
    setText('scopeListCount', listCount);
    setText('scopeDoneCount', doneCount);
    setText('scopeValidDoneCount', validCount);
    
    const dateFromStr = meta.date_from || state.dashboardData?.date_from || DEFAULT_DATE_FROM;
    setText('scopeDateFrom', dateFromStr);

    // 1. Tính % KPI Hoàn tất
    const doneBadge = document.getElementById('scopeDoneBadge');
    if (doneBadge) {
        const percent = listCount > 0 ? ((doneCount / listCount) * 100).toFixed(1) : '0.0';
        doneBadge.textContent = `${percent}%`;
    }

    // 2. Tính % Valid BG > 0
    const validBadge = document.getElementById('scopeValidBadge');
    if (validBadge) {
        const percent = doneCount > 0 ? ((validCount / doneCount) * 100).toFixed(1) : '0.0';
        validBadge.textContent = `${percent}%`;
    }

    // 3. Tính số ngày từ ngày báo giá đã chọn đến hôm nay
    const daysBadge = document.getElementById('scopeDaysBadge');
    if (daysBadge) {
        try {
            const startDate = new Date(dateFromStr);
            const today = new Date();
            startDate.setHours(0,0,0,0);
            today.setHours(0,0,0,0);
            const diffTime = Math.max(0, today - startDate);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            daysBadge.textContent = `${diffDays} ngày qua`;
        } catch (e) {
            daysBadge.textContent = '- ngày qua';
        }
    }
}
