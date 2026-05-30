// ===== Configuration =====
const API_BASE = '';
const DEFAULT_DATE_FROM = '2026-01-01';

// GP Health Thresholds
const GP_HEALTH_HIGH = 40;
const GP_HEALTH_MEDIUM = 15;
const UI_STATE_KEY = 'bonario-roi-dashboard-ui-v2';

// Shared State Label Map
const STATE_LABELS = {
    'Done': 'Hoàn tất',
    'In progress': 'Đang xử lý',
    'Need process': 'Cần xử lý',
    'ATTENTION!': 'Đã đặt hàng',
    'NVL về/Chưa SX': 'NVL về/Chờ SX',
    'Hàng về/Chờ thi công': 'Hàng về/Chờ TC',
    'Giao hàng xong/Chờ hoàn thành checklist': 'Giao xong',
    'Pending': 'Chờ KH',
    'Sx xong gom đi OCP2': 'Chờ OCP2',
    'Gom hàng OCP2 - Đợt 2': 'Chờ OCP2-2',
    'Chờ phản hồi nội bộ': 'Chờ nội bộ',
};

// ===== State =====
let dashboardData = null;
let filteredProjects = [];
let gpChart = null;
let revenueDoughnutChart = null;
let isLoadingState = false;
let currentPage = 1;
const ITEMS_PER_PAGE = 10;
let selectedProjects = new Set();  // Set of project_id
let currentAbortController = null;

// Sort state
let sortColumn = null;
let sortDirection = 'asc';
let pendingUIState = {};

// Sortable columns config
const SORTABLE_COLUMNS = [
    { key: 'sale_order_name', label: 'Đơn hàng' },
    { key: 'project_name', label: 'Dự án' },
    { key: 'customer', label: 'Khách hàng' },
    { key: 'bg_untaxed', label: 'Doanh thu' },
    { key: 'native_expected_cost', label: 'Chi phí' },
    { key: 'gp_amount', label: 'GP' },
    { key: 'gp_percent', label: 'GP%' },
];

// ===== Utility Functions =====
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0 ₫';
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + ' tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + ' tr';
    }
    if (amount >= 1e3) {
        return (amount / 1e3).toFixed(1) + ' k';
    }
    return amount.toFixed(0) + ' ₫';
}

function formatFullVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0 ₫';
    return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
}

function formatPercent(value) {
    if (value === null || value === undefined || isNaN(Number(value))) return '-';
    return Number(value).toFixed(1) + '%';
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('vi-VN');
}

function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function getElementValue(id) {
    return document.getElementById(id)?.value || '';
}

function loadUIState() {
    try {
        return JSON.parse(localStorage.getItem(UI_STATE_KEY) || '{}');
    } catch (err) {
        return {};
    }
}

function saveUIState() {
    const state = {
        dateFrom: getElementValue('dateFrom'),
        search: getElementValue('searchInput'),
        tag: getElementValue('tagFilter'),
        state: getElementValue('stateFilter'),
        health: getElementValue('healthFilter'),
        sortColumn,
        sortDirection,
        route: location.hash || '#/overview',
    };
    pendingUIState = state;
    try {
        localStorage.setItem(UI_STATE_KEY, JSON.stringify(state));
    } catch (err) {
        // Ignore private browsing or storage quota errors.
    }
}

function applySavedUIState() {
    pendingUIState = loadUIState();
    if (pendingUIState.route && !location.hash) {
        location.hash = pendingUIState.route;
    }
    const dateInput = document.getElementById('dateFrom');
    if (dateInput && pendingUIState.dateFrom) {
        dateInput.value = pendingUIState.dateFrom;
    }
    const searchInput = document.getElementById('searchInput');
    if (searchInput && pendingUIState.search) {
        searchInput.value = pendingUIState.search;
    }
    sortColumn = pendingUIState.sortColumn || null;
    sortDirection = pendingUIState.sortDirection === 'desc' ? 'desc' : 'asc';
}

function applyPendingFilterSelections() {
    const filterIds = [
        ['tagFilter', pendingUIState.tag],
        ['stateFilter', pendingUIState.state],
        ['healthFilter', pendingUIState.health],
    ];
    filterIds.forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value && Array.from(el.options).some(option => option.value === value)) {
            el.value = value;
        }
    });
}

function getHealthBucket(project) {
    const gp = project?.gp_percent;
    if (gp === null || gp === undefined || Number.isNaN(Number(gp))) return 'missing';
    if (gp > GP_HEALTH_HIGH) return 'high';
    if (gp >= GP_HEALTH_MEDIUM) return 'medium';
    return 'low';
}

// ===== API =====
async function fetchDashboard(dateFrom, refresh = false) {
    // Cancel previous request if still in flight
    if (currentAbortController) {
        currentAbortController.abort();
    }
    const controller = new AbortController();
    currentAbortController = controller;
    const { signal } = controller;

    const timeoutId = setTimeout(() => {
        controller.abort();
    }, 60000);

    const params = new URLSearchParams({ date_from: dateFrom });
    if (refresh) params.set('refresh', '1');
    
    try {
        const response = await fetch(`${API_BASE}/api/projects-dashboard?${params}`, { signal });
        clearTimeout(timeoutId);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
            throw new Error('Yêu cầu bị hủy hoặc hết thời gian chờ (60s)');
        }
        throw err;
    }
}

// ===== Loading Overlay =====
function showLoadingOverlay() {
    let overlay = document.getElementById('refreshOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'refreshOverlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(255,255,255,0.75);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(2px);';
        overlay.innerHTML = '<div style="text-align:center;"><div style="width:48px;height:48px;border:4px solid #107850;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px;"></div><p style="font-family:var(--font-heading);font-weight:600;color:#0c2317;">Đang tải dữ liệu...</p></div>';
        // Add keyframe animation
        const styleEl = document.createElement('style');
        styleEl.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
        document.head.appendChild(styleEl);
        document.body.appendChild(overlay);
    } else {
        overlay.style.display = 'flex';
    }
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('refreshOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// ===== Render Functions =====
function renderKPISparklines(projects) {
    document.querySelectorAll('.kpi-card').forEach(card => {
        const existing = card.querySelector('.kpi-sparkline');
        if (existing) existing.remove();
    });

    if (!Array.isArray(projects)) return;
    const validProjects = projects
        .filter(p => p && p.gp_percent !== null && p.gp_percent !== undefined)
        .slice(-10);
    if (validProjects.length < 2) return;
    
    const values = validProjects.map(p => p.gp_percent);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const valRange = maxVal - minVal || 1;
    
    const width = 240, height = 45, padding = 4;
    const points = values.map((val, idx) => ({
        x: (idx / (values.length - 1)) * width,
        y: height - padding - ((val - minVal) / valRange) * (height - 2 * padding)
    }));
    
    let pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[i], p1 = points[i + 1];
        const cpX = p0.x + (p1.x - p0.x) / 2;
        pathD += ` C ${cpX} ${p0.y}, ${cpX} ${p1.y}, ${p1.x} ${p1.y}`;
    }
    const fillD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;
    
    document.querySelectorAll('.kpi-card').forEach((card, cardIdx) => {
        const gradId = `sparklineGrad-${cardIdx}-${Math.random().toString(36).substr(2, 9)}`;
        const svgHTML = `
            <svg class="kpi-sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#107850" stop-opacity="0.28" />
                        <stop offset="100%" stop-color="#557361" stop-opacity="0.02" />
                    </linearGradient>
                </defs>
                <path d="${fillD}" fill="url(#${gradId})" />
                <path d="${pathD}" fill="none" stroke="#107850" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
        `;
        card.style.position = 'relative';
        card.style.overflow = 'hidden';
        card.insertAdjacentHTML('beforeend', svgHTML);
    });
}

function renderKPIs(summary) {
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

function getDashboardMeta() {
    const projects = dashboardData?.projects || [];
    const summary = dashboardData?.summary || {};
    const doneCount = Number(summary.total_projects || 0);
    return dashboardData?.meta || {
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
        date_from: dashboardData?.date_from || DEFAULT_DATE_FROM,
    };
}

function renderScopeBar() {
    const meta = getDashboardMeta();
    const counts = meta.counts || {};
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };
    setText('scopeListCount', counts.list_projects ?? (dashboardData?.projects || []).length);
    setText('scopeDoneCount', counts.done_projects ?? dashboardData?.summary?.total_projects ?? 0);
    setText('scopeValidDoneCount', counts.valid_done_projects ?? dashboardData?.summary?.valid_project_count ?? 0);
    setText('scopeDateFrom', meta.date_from || dashboardData?.date_from || DEFAULT_DATE_FROM);
}

function renderStateMixPanel() {
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
    stateCounts.forEach(([state, count]) => {
        const item = document.createElement('div');
        item.className = 'state-mix-item';
        const percent = (count / total) * 100;
        item.innerHTML = `
            <div class="state-mix-row">
                <span>${escapeHTML(STATE_LABELS[state] || state)}</span>
                <strong>${count}</strong>
            </div>
            <div class="state-mix-track"><span style="width:${percent.toFixed(1)}%"></span></div>
        `;
        fragment.appendChild(item);
    });
    container.appendChild(fragment);
}

function renderRiskProjectsPanel() {
    const container = document.getElementById('riskProjectsPanel');
    if (!container) return;
    container.innerHTML = '';
    const riskyProjects = (dashboardData?.projects || [])
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

function renderTagSnapshotPanel() {
    const container = document.getElementById('tagSnapshotPanel');
    if (!container) return;
    container.innerHTML = '';
    const buckets = dashboardData?.tag_buckets || {};
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

function renderOperationalPanels() {
    renderScopeBar();
    renderStateMixPanel();
    renderRiskProjectsPanel();
    renderTagSnapshotPanel();
}

function renderTagAnalysis(tagBuckets, tagGPRanks) {
    const container = document.getElementById('tagAnalysis');
    container.innerHTML = '';
    
    const tags = Object.keys(tagBuckets);
    
    // Calculate grand total revenue across all tags for contribution percentages
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
    
    // Render each tag as a premium biophilic progress bar widget
    tags.forEach(tag => {
        const buckets = tagBuckets[tag];
        const ranks = tagGPRanks[tag] || [];
        const totalBG = tagTotals[tag];
        
        let totalCount = 0;
        Object.values(buckets).forEach(tier => {
            totalCount += tier.count;
        });
        
        // Calculate contribution ratio
        const contributionPercent = grandTotalBG > 0 ? ((totalBG / grandTotalBG) * 100).toFixed(1) : 0;
        
        const card = document.createElement('div');
        card.className = 'tag-insight-item';
        card.innerHTML = `
            <div class="tag-insight-header">
                <span class="tag-insight-title">${escapeHTML(tag)}</span>
                <span class="tag-insight-volume">${totalCount} dự án · ${formatVND(totalBG)}</span>
            </div>
            
            <!-- Custom Aura Forest Biophilic Progress Bar -->
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
                            <span style="font-weight: 600; color: var(--color-text-secondary);">#${r.rank} ${escapeHTML(r.range)}</span>
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

function renderGPChart(tagGPRanks) {
    const ctx = document.getElementById('gpChart').getContext('2d');
    
    if (gpChart) {
        gpChart.destroy();
    }
    
    // Query calculated text colors from DOM computed variables
    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#0c2317';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#557361';
    
    const tags = Object.keys(tagGPRanks);
    
    // Collect all unique ranges
    const allRanges = new Set();
    Object.values(tagGPRanks).forEach(ranks => {
        ranks.forEach(r => allRanges.add(r.range));
    });
    const sortedRanges = Array.from(allRanges).sort((a, b) => {
        const aNum = parseInt(a.split('-')[0]);
        const bNum = parseInt(b.split('-')[0]);
        return aNum - bNum;
    });
    
    // Beautiful Aura Forest green gradients
    const colors = [
        { border: '#107850', start: 'rgba(16, 120, 80, 0.4)', end: 'rgba(16, 120, 80, 0.02)' }, // Rich Emerald
        { border: '#00e699', start: 'rgba(0, 230, 153, 0.4)', end: 'rgba(0, 230, 153, 0.02)' }, // Mint Glow
        { border: '#6b7f73', start: 'rgba(107, 127, 115, 0.4)', end: 'rgba(107, 127, 115, 0.02)' }, // Clay
        { border: '#2e7d32', start: 'rgba(46, 125, 50, 0.4)', end: 'rgba(46, 125, 50, 0.02)' }    // Pine
    ];

    // Pre-create gradients after chart is created (cached per dataset)
    const cachedGradients = {};
    
    const finalDatasets = tags.map((tag, index) => {
        const ranks = tagGPRanks[tag] || [];
        const rankMap = {};
        ranks.forEach(r => { rankMap[r.range] = r.count; });
        const themeColor = colors[index % colors.length];
        
        return {
            label: tag,
            data: sortedRanges.map(range => rankMap[range] || 0),
            backgroundColor: function(context) {
                const chart = context.chart;
                const {ctx: chartCtx, chartArea} = chart;
                if (!chartArea) return themeColor.start;
                const cacheKey = `${index}-${chartArea.bottom}-${chartArea.top}`;
                if (cachedGradients[cacheKey]) return cachedGradients[cacheKey];
                const gradient = chartCtx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
                gradient.addColorStop(0, themeColor.end);
                gradient.addColorStop(1, themeColor.start);
                cachedGradients[cacheKey] = gradient;
                return gradient;
            },
            borderColor: themeColor.border,
            borderWidth: 1.5,
            borderRadius: 5,
            borderSkipped: false,
            hoverBackgroundColor: themeColor.border
        };
    });
    
    gpChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sortedRanges,
            datasets: finalDatasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColorPrimary, // Dynamic Primary text
                        font: {
                            family: "'Outfit', sans-serif",
                            size: 12,
                            weight: '600'
                        },
                        padding: 18,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(12, 35, 23, 0.95)',
                    titleColor: '#f4f7f5',
                    bodyColor: '#a7f3d0',
                    borderColor: 'var(--color-emerald)',
                    borderWidth: 1,
                    padding: 10,
                    boxPadding: 5,
                    titleFont: {
                        family: "'Montserrat', sans-serif",
                        weight: '600'
                    },
                    bodyFont: {
                        family: "'Outfit', sans-serif"
                    }
                }
            },
            scales: {
                x: {
                    ticks: { 
                        color: textColorSecondary, // Dynamic Secondary text
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' }
                    },
                    grid: { color: 'rgba(16, 120, 80, 0.04)' } // Subtle emerald grid
                },
                y: {
                    ticks: { 
                        color: textColorSecondary, // Dynamic Secondary text
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        stepSize: 1
                    },
                    grid: { color: 'rgba(16, 120, 80, 0.04)' },
                    beginAtZero: true
                }
            }
        }
    });
}

function renderRevenueDoughnut(tagBuckets) {
    const canvas = document.getElementById('revenueDoughnutChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (revenueDoughnutChart) {
        revenueDoughnutChart.destroy();
    }
    
    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#0c2317';
    
    const tags = Object.keys(tagBuckets);
    const tagRevenueData = tags.map(tag => {
        let tagBG = 0;
        Object.values(tagBuckets[tag]).forEach(tier => { tagBG += tier.bg_untaxed; });
        return { tag, revenue: tagBG };
    }).sort((a, b) => b.revenue - a.revenue);
    
    const colors = ['#107850', '#00e699', '#6b7f73', '#2e7d32', '#a3b899'];
    
    revenueDoughnutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: tagRevenueData.map(d => d.tag),
            datasets: [{
                data: tagRevenueData.map(d => d.revenue),
                backgroundColor: colors.slice(0, tagRevenueData.length),
                borderColor: '#ffffff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: textColorPrimary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(12, 35, 23, 0.95)',
                    callbacks: {
                        label: function(context) {
                            const value = context.raw;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            return ` ${context.label}: ${formatVND(value)} (${((value/total)*100).toFixed(1)}%)`;
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

function renderTagLeaderboard(tagBuckets) {
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

function updateMenuIndicator() {
    const activeItem = document.querySelector('.sidebar-menu .menu-item.active');
    const indicator = document.getElementById('menuIndicator');
    if (!indicator) return;
    
    if (!activeItem) {
        indicator.style.opacity = '0';
        return;
    }
    
    indicator.style.opacity = '1';
    const menuContainer = document.querySelector('.sidebar-menu');
    const activeRect = activeItem.getBoundingClientRect();
    const menuRect = menuContainer.getBoundingClientRect();
    
    const offsetTop = activeRect.top - menuRect.top;
    const height = activeRect.height;
    
    indicator.style.height = `${height}px`;
    indicator.style.transform = `translate3d(0, ${offsetTop}px, 0)`;
}

// ===== Table Sorting =====
function getSortValue(project, columnKey) {
    const val = project[columnKey];
    if (val === null || val === undefined) return '';
    if (typeof val === 'number') return val;
    return String(val).toLowerCase();
}

function applySorting(projects) {
    if (!sortColumn) return projects;
    const sorted = [...projects];
    sorted.sort((a, b) => {
        const aVal = getSortValue(a, sortColumn);
        const bVal = getSortValue(b, sortColumn);
        let cmp = 0;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            cmp = aVal - bVal;
        } else {
            cmp = String(aVal).localeCompare(String(bVal), 'vi');
        }
        return sortDirection === 'asc' ? cmp : -cmp;
    });
    return sorted;
}

function toggleSort(columnKey) {
    if (sortColumn === columnKey) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = columnKey;
        sortDirection = 'asc';
    }
    saveUIState();
    renderProjectsTable(filteredProjects);
}

function updateSortIndicators() {
    document.querySelectorAll('th[data-sort]').forEach(th => {
        const key = th.getAttribute('data-sort');
        th.classList.remove('sort-asc', 'sort-desc');
        if (key === sortColumn) {
            th.classList.add(sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

// ===== Export CSV =====
function exportCSV() {
    if (!filteredProjects || filteredProjects.length === 0) return;
    
    const headers = ['Đơn hàng', 'Dự án', 'Khách hàng', 'Tags', 'Trạng thái', 'Doanh thu', 'Chi phí', 'GP', 'GP%'];
    const rows = applySorting(filteredProjects).map(p => [
        p.sale_order_name || '',
        p.project_name || '',
        p.customer || '',
        (p.tags || []).join('; '),
        STATE_LABELS[p.order_state] || p.order_state || '',
        p.bg_untaxed,
        p.native_expected_cost,
        p.gp_amount,
        p.gp_percent !== null && p.gp_percent !== undefined ? p.gp_percent.toFixed(1) + '%' : '',
    ]);
    
    const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\r\n');
    
    // BOM for Excel Vietnamese support
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `du-an-roi-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function renderExportButton() {
    const tableInfo = document.getElementById('tableInfo');
    if (!tableInfo) return;
    let exportBtn = document.getElementById('exportCsvBtn');
    if (!exportBtn) {
        exportBtn = document.createElement('button');
        exportBtn.id = 'exportCsvBtn';
        exportBtn.innerHTML = '<i class="fas fa-download" aria-hidden="true"></i><span>Xuất CSV</span>';
        exportBtn.className = 'btn btn-export compact';
        exportBtn.addEventListener('click', exportCSV);
        tableInfo.parentElement.insertBefore(exportBtn, tableInfo.nextSibling);
    }
}

// ===== Filter Indicators =====
function updateFilterIndicators() {
    const searchTerm = document.getElementById('searchInput').value.trim();
    const tagFilter = document.getElementById('tagFilter').value;
    const stateFilter = document.getElementById('stateFilter').value;
    const healthFilter = document.getElementById('healthFilter')?.value || '';
    const hasActiveFilters = searchTerm || tagFilter || stateFilter || healthFilter;
    
    let clearBtn = document.getElementById('clearFiltersBtn');
    if (!clearBtn) {
        clearBtn = document.createElement('button');
        clearBtn.id = 'clearFiltersBtn';
        clearBtn.textContent = '✕ Xóa bộ lọc';
        clearBtn.className = 'clear-filters-btn';
        clearBtn.addEventListener('click', clearFilters);
        // Append near the filter controls
        const filterContainer = document.querySelector('.table-filters-box');
        if (filterContainer) {
            filterContainer.appendChild(clearBtn);
        }
    }
    clearBtn.style.display = hasActiveFilters ? 'inline-block' : 'none';
}

function clearFilters() {
    document.getElementById('searchInput').value = '';
    document.getElementById('tagFilter').value = '';
    document.getElementById('stateFilter').value = '';
    const healthFilter = document.getElementById('healthFilter');
    if (healthFilter) healthFilter.value = '';
    applyFilters();
}

function renderProjectsTable(projects) {
    const tbody = document.getElementById('projectsTable');
    tbody.innerHTML = '';
    
    // Apply sorting
    const sortedProjects = applySorting(projects);
    
    // Empty state
    if (sortedProjects.length === 0) {
        const emptyTr = document.createElement('tr');
        emptyTr.innerHTML = `
            <td colspan="10" style="text-align:center;padding:3rem 1rem;color:var(--color-text-secondary);">
                <div style="font-size:2.5rem;margin-bottom:0.5rem;">📭</div>
                <div style="font-weight:600;font-size:1rem;margin-bottom:0.3rem;">Không tìm thấy dự án nào</div>
                <div style="font-size:0.85rem;opacity:0.7;">Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm</div>
            </td>
        `;
        tbody.appendChild(emptyTr);
        document.getElementById('tableInfo').textContent = 'Hiển thị 0-0 / 0 dự án';
        renderPagination(0);
        updateSortIndicators();
        return;
    }
    
    // Pagination
    const totalPages = Math.max(1, Math.ceil(sortedProjects.length / ITEMS_PER_PAGE));
    if (currentPage > totalPages) currentPage = totalPages;
    const startIdx = (currentPage - 1) * ITEMS_PER_PAGE;
    const pageProjects = sortedProjects.slice(startIdx, startIdx + ITEMS_PER_PAGE);
    
    const fragment = document.createDocumentFragment();
    
    pageProjects.forEach(p => {
        const gpClass = p.gp_percent !== null && p.gp_percent >= 0 ? 'gp-positive' : 'gp-negative';
        const stateClass = p.order_state === 'Done' ? 'done' : 
                          p.order_state === 'In progress' ? 'progress' : 'pending';
        const stateLabel = STATE_LABELS[p.order_state] || escapeHTML(p.order_state) || '-';
        
        let healthBadgeHTML = '';
        if (p.gp_percent === null || p.gp_percent === undefined) {
            healthBadgeHTML = '<span style="color: var(--color-text-secondary); opacity: 0.5;">-</span>';
        } else {
            let healthClass = 'health-coral';
            if (p.gp_percent > GP_HEALTH_HIGH) {
                healthClass = 'health-green';
            } else if (p.gp_percent >= GP_HEALTH_MEDIUM) {
                healthClass = 'health-amber';
            }
            healthBadgeHTML = `
                <span class="health-orb-badge ${healthClass}">
                    <span class="orb-dot"></span>
                    ${formatPercent(p.gp_percent)}
                </span>
            `;
        }
        
        const tr = document.createElement('tr');
        const isSelected = selectedProjects.has(p.project_id);
        tr.innerHTML = `
            <td style="text-align: center;"><input type="checkbox" class="project-checkbox" data-project-id="${p.project_id}" ${isSelected ? 'checked' : ''}></td>
            <td><strong style="color: var(--color-emerald); font-family: var(--font-heading); font-size: 0.88rem;">${escapeHTML(p.sale_order_name) || '-'}</strong></td>
            <td><span style="font-weight: 600; color: var(--color-text-primary);">${escapeHTML(p.project_name) || '-'}</span></td>
            <td style="color: var(--color-text-secondary); font-weight: 500;">${escapeHTML(p.customer) || '-'}</td>
            <td><div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">${(p.tags || []).map(t => `<span class="tag-badge">${escapeHTML(t)}</span>`).join('')}</div></td>
            <td><span class="state-badge ${stateClass}">${stateLabel}</span></td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 700; color: var(--color-text-primary);">${formatFullVND(p.bg_untaxed)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 600; color: var(--color-text-secondary);">${formatFullVND(p.native_expected_cost)}</td>
            <td class="text-right ${gpClass}" style="font-family: var(--font-heading); font-weight: 700;">${formatFullVND(p.gp_amount)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-size: 0.825rem; vertical-align: middle;">${healthBadgeHTML}</td>
        `;
        if (isSelected) tr.classList.add('selected-row');
        fragment.appendChild(tr);
    });
    
    tbody.appendChild(fragment);
    
    const start = sortedProjects.length > 0 ? startIdx + 1 : 0;
    const end = Math.min(startIdx + ITEMS_PER_PAGE, sortedProjects.length);
    document.getElementById('tableInfo').textContent = `Hiển thị ${start}-${end} / ${sortedProjects.length} dự án`;
    renderPagination(sortedProjects.length);
    renderExportButton();
    updateSortIndicators();
    attachCheckboxListeners();
}

function attachCheckboxListeners() {
    // Individual checkboxes
    document.querySelectorAll('.project-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const projectId = parseInt(e.target.dataset.projectId);
            const tr = e.target.closest('tr');
            if (e.target.checked) {
                selectedProjects.add(projectId);
                tr.classList.add('selected-row');
            } else {
                selectedProjects.delete(projectId);
                tr.classList.remove('selected-row');
            }
            updateMultiSelectPanel();
            updateSelectAllState();
        });
    });
    // Select all
    const selectAll = document.getElementById('selectAll');
    if (selectAll) {
        selectAll.addEventListener('change', (e) => {
            const startIdx = (currentPage - 1) * ITEMS_PER_PAGE;
            const endIdx = startIdx + ITEMS_PER_PAGE;
            const sortedProjects = applySorting(filteredProjects);
            const pageProjects = sortedProjects.slice(startIdx, endIdx);
            
            if (e.target.checked) {
                pageProjects.forEach(p => selectedProjects.add(p.project_id));
            } else {
                pageProjects.forEach(p => selectedProjects.delete(p.project_id));
            }
            // Update UI
            document.querySelectorAll('.project-checkbox').forEach(cb => {
                const pid = parseInt(cb.dataset.projectId);
                cb.checked = selectedProjects.has(pid);
                cb.closest('tr').classList.toggle('selected-row', selectedProjects.has(pid));
            });
            updateMultiSelectPanel();
        });
    }
    updateSelectAllState();
}

function updateSelectAllState() {
    const selectAll = document.getElementById('selectAll');
    if (!selectAll) return;
    const checkboxes = document.querySelectorAll('.project-checkbox');
    const checkedCount = document.querySelectorAll('.project-checkbox:checked').length;
    selectAll.checked = checkboxes.length > 0 && checkedCount === checkboxes.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
}

function updateMultiSelectPanel() {
    const panel = document.getElementById('multiSelectPanel');
    if (!panel) return;
    
    if (selectedProjects.size === 0) {
        panel.style.display = 'none';
        return;
    }
    
    panel.style.display = 'block';
    
    // Find selected project data from dashboardData
    const allProjects = dashboardData?.projects || [];
    const selected = allProjects.filter(p => selectedProjects.has(p.project_id));
    
    let totalBG = 0;
    let totalCost = 0;
    let totalGP = 0;
    let weightedGPSum = 0;
    let weightedGPCount = 0;
    
    selected.forEach(p => {
        totalBG += p.bg_untaxed || 0;
        totalCost += p.native_expected_cost || 0;
        totalGP += p.gp_amount || 0;
        if (p.gp_percent !== null && p.gp_percent !== undefined && (p.bg_untaxed || 0) > 0) {
            weightedGPSum += p.gp_percent * p.bg_untaxed;
            weightedGPCount += p.bg_untaxed;
        }
    });
    
    const weightedGP = weightedGPCount > 0 ? (weightedGPSum / weightedGPCount).toFixed(1) : '-';
    
    document.getElementById('selectedCount').textContent = selectedProjects.size;
    document.getElementById('selectedTotalBG').textContent = formatFullVND(totalBG);
    document.getElementById('selectedTotalCost').textContent = formatFullVND(totalCost);
    document.getElementById('selectedTotalGP').textContent = formatFullVND(totalGP);
    document.getElementById('selectedAvgGP').textContent = weightedGP !== '-' ? weightedGP + '%' : '-';
}

function renderPagination(totalItems) {
    const container = document.getElementById('pagination');
    container.innerHTML = '';
    
    const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
    if (totalPages <= 1) return;
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn' + (currentPage === 1 ? ' disabled' : '');
    prevBtn.innerHTML = '&laquo;';
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderProjectsTable(filteredProjects); scrollToTableTop(); } });
    container.appendChild(prevBtn);
    
    // Page numbers
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) startPage = Math.max(1, endPage - maxVisible + 1);
    
    if (startPage > 1) {
        const firstBtn = document.createElement('button');
        firstBtn.className = 'page-btn';
        firstBtn.textContent = '1';
        firstBtn.addEventListener('click', () => { currentPage = 1; renderProjectsTable(filteredProjects); scrollToTableTop(); });
        container.appendChild(firstBtn);
        if (startPage > 2) {
            const dots = document.createElement('span');
            dots.className = 'page-dots';
            dots.textContent = '...';
            container.appendChild(dots);
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        const btn = document.createElement('button');
        btn.className = 'page-btn' + (i === currentPage ? ' active' : '');
        btn.textContent = i;
        btn.addEventListener('click', () => { currentPage = i; renderProjectsTable(filteredProjects); scrollToTableTop(); });
        container.appendChild(btn);
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const dots = document.createElement('span');
            dots.className = 'page-dots';
            dots.textContent = '...';
            container.appendChild(dots);
        }
        const lastBtn = document.createElement('button');
        lastBtn.className = 'page-btn';
        lastBtn.textContent = totalPages;
        lastBtn.addEventListener('click', () => { currentPage = totalPages; renderProjectsTable(filteredProjects); scrollToTableTop(); });
        container.appendChild(lastBtn);
    }
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn' + (currentPage === totalPages ? ' disabled' : '');
    nextBtn.innerHTML = '&raquo;';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; renderProjectsTable(filteredProjects); scrollToTableTop(); } });
    container.appendChild(nextBtn);
}

function scrollToTableTop() {
    const table = document.getElementById('projectsTable');
    if (table) {
        table.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function populateFilters(projects) {
    const tagFilter = document.getElementById('tagFilter');
    const allTags = new Set();
    projects.forEach(p => {
        (p.tags || []).forEach(t => allTags.add(t));
    });
    
    tagFilter.innerHTML = '<option value="">Tất cả tags</option>';
    Array.from(allTags).sort().forEach(tag => {
        const opt = document.createElement('option');
        opt.value = tag;
        opt.textContent = tag;
        tagFilter.appendChild(opt);
    });
    
    // Populate state filter using shared STATE_LABELS
    const stateFilter = document.getElementById('stateFilter');
    const allStates = new Set();
    projects.forEach(p => {
        if (p.order_state) allStates.add(p.order_state);
    });
    
    stateFilter.innerHTML = '<option value="">Tất cả trạng thái</option>';
    Array.from(allStates).sort().forEach(state => {
        const opt = document.createElement('option');
        opt.value = state;
        opt.textContent = STATE_LABELS[state] || state;
        stateFilter.appendChild(opt);
    });
    applyPendingFilterSelections();
}

// ===== Filter & Search =====
function applyFilters() {
    if (!dashboardData) return;
    
    const searchTerm = document.getElementById('searchInput').value.trim().toLowerCase();
    const tagFilter = document.getElementById('tagFilter').value;
    const stateFilter = document.getElementById('stateFilter').value;
    const healthFilter = document.getElementById('healthFilter')?.value || '';
    
    filteredProjects = dashboardData.projects.filter(p => {
        // Search
        if (searchTerm) {
            const searchFields = [
                p.sale_order_name,
                p.project_name,
                p.customer,
            ].filter(Boolean).join(' ').toLowerCase();
            if (!searchFields.includes(searchTerm)) return false;
        }
        
        // Tag filter
        if (tagFilter && !(p.tags || []).includes(tagFilter)) return false;
        
        // State filter
        if (stateFilter && p.order_state !== stateFilter) return false;

        // GP health filter
        if (healthFilter && getHealthBucket(p) !== healthFilter) return false;
        
        return true;
    });
    
    currentPage = 1;
    renderProjectsTable(filteredProjects);
    updateFilterIndicators();
    saveUIState();
}

// ===== SPA Router =====
function handleRouting() {
    const hash = location.hash || '#/overview';
    
    // Map hash to DOM section IDs
    const routeMap = {
        '#/overview': 'overview-route',
        '#/tags': 'tags-route',
        '#/projects': 'projects-route',
        '#/ranks': 'ranks-route'
    };
    
    const activeSectionId = routeMap[hash] || 'overview-route';
    
    // Hide all route views
    document.querySelectorAll('.route-view').forEach(view => {
        view.classList.remove('active');
    });
    
    // Show active route view
    const activeView = document.getElementById(activeSectionId);
    if (activeView) {
        activeView.classList.add('active');
    }
    
    // Update active sidebar menu items
    document.querySelectorAll('.sidebar-menu .menu-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href === hash || (hash === '#/overview' && href === '#/overview')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // Only render charts if not already rendered (avoid re-creating on every route change)
    if (hash === '#/ranks' && dashboardData) {
        if (!gpChart) {
            renderGPChart(dashboardData.tag_gp_ranks);
        } else {
            gpChart.resize();
        }
        if (!revenueDoughnutChart) {
            renderRevenueDoughnut(dashboardData.tag_buckets);
        } else {
            revenueDoughnutChart.resize();
        }
        renderTagLeaderboard(dashboardData.tag_buckets);
    }
    
    // Update menu indicator position vertical
    updateMenuIndicator();
    saveUIState();
}

// ===== Main =====
async function loadDashboard(refresh = false) {
    if (isLoadingState) return;
    isLoadingState = true;
    
    const refreshBtn = document.getElementById('refreshBtn');
    const dateFromInput = document.getElementById('dateFrom');
    if (refreshBtn) refreshBtn.disabled = true;
    if (dateFromInput) dateFromInput.disabled = true;
    
    const loadingEl = document.getElementById('loadingState');
    const errorEl = document.getElementById('errorState');
    const mainEl = document.getElementById('mainContent');
    
    // Use overlay for refresh, full loading state only for initial load
    if (dashboardData) {
        // Refresh mode: show overlay, keep content visible
        showLoadingOverlay();
    } else {
        // Initial load: show loading state, hide main
        loadingEl.style.display = 'flex';
        errorEl.style.display = 'none';
        mainEl.style.display = 'none';
    }
    
    try {
        const dateFrom = dateFromInput ? dateFromInput.value : '';
        const selectedDateFrom = dateFrom || DEFAULT_DATE_FROM;
        dashboardData = await fetchDashboard(selectedDateFrom, refresh);
        if (dateFromInput) dateFromInput.value = dashboardData.date_from || selectedDateFrom;
        if (gpChart) {
            gpChart.destroy();
            gpChart = null;
        }
        if (revenueDoughnutChart) {
            revenueDoughnutChart.destroy();
            revenueDoughnutChart = null;
        }
        
        renderKPIs(dashboardData.summary);
        renderKPISparklines(dashboardData.projects);
        renderOperationalPanels();
        renderTagAnalysis(dashboardData.tag_buckets, dashboardData.tag_gp_ranks);
        populateFilters(dashboardData.projects);
        
        applyFilters();
        
        document.getElementById('lastUpdated').textContent = formatDateTime(dashboardData.fetched_at);
        saveUIState();
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (mainEl) mainEl.style.display = 'block';
        hideLoadingOverlay();
        
        // Execute routing logic once data is loaded to show the correct section immediately
        handleRouting();
    } catch (err) {
        console.error('Load error:', err);
        hideLoadingOverlay();
        if (!dashboardData) {
            // Only show error state if we don't have any data yet
            loadingEl.style.display = 'none';
            errorEl.style.display = 'flex';
            document.getElementById('errorMessage').textContent = err.message;
        }
    } finally {
        isLoadingState = false;
        if (refreshBtn) refreshBtn.disabled = false;
        if (dateFromInput) dateFromInput.disabled = false;
    }
}

// ===== Event Listeners =====
document.addEventListener('DOMContentLoaded', () => {
    applySavedUIState();
    loadDashboard();
    
    // Set up Hash Router
    addEventListener('hashchange', handleRouting);
    
    // Resize listener for sidebar sliding indicator
    addEventListener('resize', updateMenuIndicator);
    
    // Refresh button (JS handler, not inline)
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadDashboard(true);
    });
    
    // Retry button handler
    const retryBtn = document.getElementById('retryBtn');
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            loadDashboard(true);
        });
    }
    
    document.getElementById('dateFrom').addEventListener('change', () => {
        saveUIState();
        loadDashboard(true);
    });
    
    // Search with debounce (300ms)
    const debouncedApplyFilters = debounce(applyFilters, 300);
    document.getElementById('searchInput').addEventListener('input', debouncedApplyFilters);
    document.getElementById('tagFilter').addEventListener('change', applyFilters);
    document.getElementById('stateFilter').addEventListener('change', applyFilters);
    document.getElementById('healthFilter').addEventListener('change', applyFilters);
    
    // Table header sort click handlers
    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            toggleSort(column);
        });
    });
    
    // Multi-select: Clear selection button
    document.getElementById('clearSelection')?.addEventListener('click', () => {
        selectedProjects.clear();
        document.querySelectorAll('.project-checkbox').forEach(cb => {
            cb.checked = false;
            cb.closest('tr').classList.remove('selected-row');
        });
        document.getElementById('selectAll').checked = false;
        updateMultiSelectPanel();
    });
});
