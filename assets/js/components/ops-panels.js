import { state } from '../state.js';
import { STATE_LABELS } from '../config.js';
import { escapeHTML, formatPercent, formatVND, getHealthBucket } from '../utils.js';
import { getDashboardMeta, renderScopeBar } from './dashboard-kpi.js';
import { applyFilters } from './table.js';

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
                <small>${escapeHTML(project.customer || project.project_name || '-')}</small>
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
        let totalBG = 0, totalCount = 0, weightedGPSum = 0;
        Object.values(tagBuckets[tag]).forEach(tier => {
            totalBG += tier.bg_untaxed;
            totalCount += tier.count;
            if (tier.weighted_gp_percent !== null) weightedGPSum += tier.weighted_gp_percent * tier.count;
        });
        return { tag, totalBG, totalCount, avgGP: totalCount > 0 ? (weightedGPSum / totalCount) : 0 };
    }).sort((a, b) => b.avgGP - a.avgGP);

    const fragment = document.createDocumentFragment();
    items.forEach((item, index) => {
        const rank = index + 1;
        const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-standard';
        const div = document.createElement('div');
        div.className = `leaderboard-item ${rankClass}`;
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
        fragment.appendChild(div);
    });
    container.appendChild(fragment);
}

export function renderTagAnalysis(tagBuckets, tagGPRanks) {
    const container = document.getElementById('tagAnalysis');
    if (!container) return;
    container.innerHTML = '';

    const tags = Object.keys(tagBuckets);
    let grandTotalBG = 0;
    const tagTotals = {};

    tags.forEach(tag => {
        const buckets = tagBuckets[tag];
        let tagBG = 0;
        Object.values(buckets).forEach(tier => {
            tagBG += tier.bg_untaxed;
        });
        tagTotals[tag] = tagBG;
        grandTotalBG += tagBG;
    });

    const fragment = document.createDocumentFragment();

    tags.forEach(tag => {
        const buckets = tagBuckets[tag];
        const ranks = tagGPRanks[tag] || [];
        const totalBG = tagTotals[tag];

        let totalCount = 0;
        Object.values(buckets).forEach(tier => {
            totalCount += tier.count;
        });

        const contributionPercent = grandTotalBG > 0 ? ((totalBG / grandTotalBG) * 100).toFixed(1) : 0;

        const card = document.createElement('div');
        card.className = 'tag-insight-item';
        card.innerHTML = `
            <div class="tag-insight-header">
                <span class="tag-insight-title">${escapeHTML(tag)}</span>
                <span class="tag-insight-volume">${totalCount} dự án · ${formatVND(totalBG)}</span>
            </div>

            <div class="progress-bar-container" title="Chiếm ${contributionPercent}% doanh thu các nhóm">
                <div class="progress-bar-fill" style="width: ${contributionPercent}%;"></div>
            </div>

            <div class="progress-tiers-grid">
                ${renderTiers(buckets)}
            </div>

            ${ranks.length > 0 ? `
                <div class="tag-insight-footer">
                    <div class="tag-ranks-label">GP% phổ biến nhất</div>
                    ${ranks.map(r => `
                        <div class="tag-rank-row">
                            <span style="font-weight: 600; color: var(--color-text-secondary); font-size: 0.825rem;">#${r.rank} ${escapeHTML(r.range)}</span>
                            <span class="gp-positive" style="font-weight: 700;">${r.count} dự án</span>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        `;
        fragment.appendChild(card);
    });

    container.appendChild(fragment);
}

function renderTiers(buckets) {
    const tierOrder = ['<10tr', '10-100tr', '100-200tr', '>200tr'];
    return tierOrder.map(tierName => {
        const tier = buckets[tierName] || { count: 0, bg_untaxed: 0, weighted_gp_percent: null };
        const gpVal = tier.weighted_gp_percent !== null ? tier.weighted_gp_percent : 0;
        const gpClass = gpVal >= 0 ? 'gp-positive' : 'gp-negative';

        return `
            <div class="progress-tier-box">
                <div class="progress-tier-name">${tierName}</div>
                <div class="progress-tier-count">${tier.count} DA</div>
                ${tier.weighted_gp_percent !== null
                    ? `<div class="progress-tier-margin ${gpClass}">${formatPercent(tier.weighted_gp_percent)}</div>`
                    : '<div class="progress-tier-margin" style="color: var(--color-text-secondary); opacity: 0.5;">-</div>'}
            </div>
        `;
    }).join('');
}
