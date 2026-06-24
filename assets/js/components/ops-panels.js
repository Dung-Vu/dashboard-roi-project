import { state } from '../state.js';
import { STATE_LABELS } from '../config.js';
import { escapeHTML, formatPercent, formatVND, getHealthBucket } from '../utils.js';
import { getDashboardMeta, renderScopeBar } from './dashboard-kpi.js';
import { applyFilters } from './table.js';
import { renderStackedRevenueChart, renderTagGPCharts } from '../charts.js';

export function renderOperationalPanels() {
    renderScopeBar();
    renderStateMixPanel();
    renderRiskProjectsPanel();
    renderTagSnapshotPanel();
}

export function renderStateMixPanel() {
    const container = document.getElementById('stateMixPanel');
    if (!container) return;
    container.innerHTML = '';
    const meta = getDashboardMeta();
    const stateCounts = Object.entries(meta.state_counts || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6);
    const total = Math.max(Number(meta.counts?.list_projects || 0), 1);
    if (!stateCounts.length) {
        container.innerHTML = '<div class="ops-empty">Chưa có project trong phạm vi này.</div>';
        return;
    }
    const fragment = document.createDocumentFragment();
    stateCounts.forEach(([orderState, count]) => {
        const item = document.createElement('div');
        item.className = 'state-mix-item';
        const percent = (count / total) * 100;
        item.innerHTML = `
            <div class="state-mix-row">
                <span>${escapeHTML(STATE_LABELS[orderState] || orderState)}</span>
                <strong>${count}</strong>
            </div>
            <div class="state-mix-track"><span style="width:${percent.toFixed(1)}%"></span></div>
        `;
        fragment.appendChild(item);
    });
    container.appendChild(fragment);
}

export function renderRiskProjectsPanel() {
    const container = document.getElementById('riskProjectsPanel');
    if (!container) return;
    container.innerHTML = '';
    const riskyProjects = (state.dashboardData?.projects || [])
        .filter(project => project.gp_percent !== null && project.gp_percent !== undefined)
        .sort((a, b) => Number(a.gp_percent) - Number(b.gp_percent))
        .slice(0, 5);
    if (!riskyProjects.length) {
        container.innerHTML = '<div class="ops-empty">Chưa có GP% để đánh giá.</div>';
        return;
    }
    const fragment = document.createDocumentFragment();
    riskyProjects.forEach(project => {
        const item = document.createElement('a');
        item.className = `risk-item risk-${getHealthBucket(project)}`;
        item.href = '#/projects';
        item.innerHTML = `
            <span>
                <strong>${escapeHTML(project.sale_order_name || '-')}</strong>
                <small>${escapeHTML(project.customer || project.x_studio_giai_trinh || '-')}</small>
            </span>
            <b>${formatPercent(project.gp_percent)}</b>
        `;
        item.addEventListener('click', () => {
            const searchInput = document.getElementById('searchInput');
            if (searchInput) searchInput.value = project.sale_order_name || '';
            applyFilters();
        });
        fragment.appendChild(item);
    });
    container.appendChild(fragment);
}

export function renderTagSnapshotPanel() {
    const container = document.getElementById('tagSnapshotPanel');
    if (!container) return;
    container.innerHTML = '';
    const buckets = state.dashboardData?.tag_buckets || {};
    const tags = Object.keys(buckets)
        .map(tag => {
            const totals = Object.values(buckets[tag]).reduce((acc, bucket) => {
                acc.count += bucket.count || 0;
                acc.bg += bucket.bg_untaxed || 0;
                acc.gp += bucket.gp_amount || 0;
                return acc;
            }, { count: 0, bg: 0, gp: 0 });
            return {
                tag,
                ...totals,
                gpPercent: totals.bg > 0 ? (totals.gp / totals.bg) * 100 : null,
            };
        })
        .sort((a, b) => b.bg - a.bg)
        .slice(0, 4);
    if (!tags.length) {
        container.innerHTML = '<div class="ops-empty">Chưa có tag Done trong phạm vi này.</div>';
        return;
    }
    const fragment = document.createDocumentFragment();
    tags.forEach(tag => {
        const item = document.createElement('div');
        item.className = 'tag-snapshot-item';
        item.innerHTML = `
            <span>
                <strong>${escapeHTML(tag.tag)}</strong>
                <small>${tag.count} dự án Done · ${formatVND(tag.bg)}</small>
            </span>
            <b>${formatPercent(tag.gpPercent)}</b>
        `;
        fragment.appendChild(item);
    });
    container.appendChild(fragment);
}

export function renderTagLeaderboard(tagBuckets) {
    const container = document.getElementById('tagLeaderboard');
    if (!container) return;
    container.innerHTML = '';

    const items = Object.keys(tagBuckets).map(tag => {
        let totalBG = 0, totalGP = 0, totalCount = 0;
        Object.values(tagBuckets[tag]).forEach(tier => {
            totalBG += tier.bg_untaxed || 0;
            totalGP += tier.gp_amount || 0;
            totalCount += tier.count || 0;
        });
        const avgGP = totalBG > 0 ? (totalGP / totalBG) * 100 : 0;
        return { tag, totalBG, totalCount, avgGP };
    }).sort((a, b) => b.avgGP - a.avgGP);

    const fragment = document.createDocumentFragment();
    items.forEach((item, index) => {
        const rank = index + 1;
        const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-standard';
        const div = document.createElement('div');
        div.className = `leaderboard-item ${rankClass}`;
        div.style.cursor = 'pointer';
        div.innerHTML = `
            <div class="leaderboard-rank">${rank}</div>
            <div class="leaderboard-info">
                <div class="leaderboard-name">${escapeHTML(item.tag)}</div>
                <div class="leaderboard-stats">${item.totalCount} dự án · Doanh thu: ${formatVND(item.totalBG)}</div>
            </div>
            <div class="leaderboard-kpi">
                <div class="leaderboard-kpi-val ${item.avgGP >= 0 ? 'gp-positive' : 'gp-negative'}">${formatPercent(item.avgGP)}</div>
                <div class="leaderboard-kpi-sub">Weighted GP</div>
            </div>
        `;
        
        div.addEventListener('click', () => {
            const tagFilter = document.getElementById('tagFilter');
            if (tagFilter) {
                tagFilter.value = item.tag;
            }
            state.pendingUIState.tag = item.tag;
            state.gpRangeFilter = null;

            applyFilters();

            location.hash = '#/projects';
        });

        fragment.appendChild(div);
    });
    container.appendChild(fragment);
}

export function renderTagAnalysis(tagBuckets, tagGPRanks) {
    // Safe check: only render if tags canvases exist
    const hasCanvases = document.getElementById('stackedRevenueChart') && document.getElementById('gpTagNoiThatRoi');
    if (!hasCanvases) return;

    // Delegate rendering to new Chart.js visualizers
    renderStackedRevenueChart(tagBuckets);
    renderTagGPCharts(tagGPRanks);

}
