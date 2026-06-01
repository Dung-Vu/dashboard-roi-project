
// --- MODULE: assets/js/config.js ---
const API_BASE = '';
const DEFAULT_DATE_FROM = '2026-01-01';
const DEFAULT_COMPANY = 'all';
const COMPANY_OPTIONS = [
    { key: 'all', label: 'Tất cả công ty' },
    { key: 'bonario', label: 'Bonario' },
    { key: 'ordinaire', label: 'Ordinaire' },
];
const GP_HEALTH_HIGH = 40;
const GP_HEALTH_MEDIUM = 15;
const UI_STATE_KEY = 'bonario-roi-dashboard-ui-v2';
const ITEMS_PER_PAGE = 10;

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

const SORTABLE_COLUMNS = [
    { key: 'sale_order_name', label: 'Đơn hàng' },
    { key: 'project_name', label: 'Dự án' },
    { key: 'customer', label: 'Khách hàng' },
    { key: 'bg_untaxed', label: 'Doanh thu' },
    { key: 'adjusted_expected_cost', label: 'Chi phí' },
    { key: 'gp_amount', label: 'GP' },
    { key: 'gp_percent', label: 'GP%' },
];

// --- MODULE: assets/js/utils.js ---


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
    if (amount === null || amount === undefined || isNaN(amount)) return '0\u00a0₫';
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + '\u00a0tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + '\u00a0tr';
    }
    if (amount >= 1e3) {
        return (amount / 1e3).toFixed(1) + '\u00a0k';
    }
    return amount.toFixed(0) + '\u00a0₫';
}

function formatFullVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0\u00a0₫';
    return new Intl.NumberFormat('vi-VN').format(amount) + '\u00a0₫';
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

function getHealthBucket(project) {
    const gp = project?.gp_percent;
    if (gp === null || gp === undefined || Number.isNaN(Number(gp))) return 'missing';
    if (gp > GP_HEALTH_HIGH) return 'high';
    if (gp >= GP_HEALTH_MEDIUM) return 'medium';
    return 'low';
}

function showLoadingOverlay() {
    let overlay = document.getElementById('refreshOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'refreshOverlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = '<div class="spinner"></div><p class="loading-text">Đang tải dữ liệu...</p>';
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

function scrollToTableTop() {
    const table = document.getElementById('projectsTable');
    if (table) {
        table.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function isGPInInterval(gp_percent, intervalLabel) {
    if (gp_percent === null || gp_percent === undefined) return false;
    
    // Sử dụng Math.trunc để tương thích với logic int() của Python
    const valTrunc = Math.trunc(gp_percent);

    if (intervalLabel === "<0%") {
        return valTrunc < 0;
    }
    if (intervalLabel === "0-20%") {
        return valTrunc >= 0 && valTrunc <= 20;
    }
    if (intervalLabel === "21-40%") {
        return valTrunc >= 21 && valTrunc <= 40;
    }
    
    // So khớp dải dạng "X-Y%"
    const match = intervalLabel.match(/^(\d+)-(\d+)%$/);
    if (match) {
        const start = parseInt(match[1], 10);
        const end = parseInt(match[2], 10);
        return valTrunc >= start && valTrunc <= end;
    }
    return false;
}


// --- MODULE: assets/js/state.js ---



const state = {
    dashboardData: null,
    filteredProjects: [],
    gpChart: null,
    revenueDoughnutChart: null,
    isLoadingState: false,
    currentPage: 1,
    selectedProjects: new Set(),
    currentAbortController: null,
    sortColumn: null,
    sortDirection: 'asc',
    company: DEFAULT_COMPANY,
    pendingUIState: {},
    gpRangeFilter: null
};

function loadUIState() {
    try {
        return JSON.parse(localStorage.getItem(UI_STATE_KEY) || '{}');
    } catch (err) {
        return {};
    }
}

function saveUIState() {
    const saved = {
        dateFrom: getElementValue('dateFrom'),
        search: getElementValue('searchInput'),
        tag: getElementValue('tagFilter'),
        state: getElementValue('stateFilter'),
        health: getElementValue('healthFilter'),
        company: getElementValue('companySelector') || state.company,
        sortColumn: state.sortColumn,
        sortDirection: state.sortDirection,
        route: location.hash || '#/overview',
        gpRangeFilter: state.gpRangeFilter,
    };
    state.pendingUIState = saved;
    try {
        localStorage.setItem(UI_STATE_KEY, JSON.stringify(saved));
    } catch (err) {
        // Ignore private browsing or storage quota errors.
    }
}

function applySavedUIState() {
    state.pendingUIState = loadUIState();
    if (state.pendingUIState.route && !location.hash) {
        location.hash = state.pendingUIState.route;
    }
    const dateInput = document.getElementById('dateFrom');
    if (dateInput && state.pendingUIState.dateFrom) {
        dateInput.value = state.pendingUIState.dateFrom;
    }
    const searchInput = document.getElementById('searchInput');
    if (searchInput && state.pendingUIState.search) {
        searchInput.value = state.pendingUIState.search;
    }
    const companySelector = document.getElementById('companySelector');
    state.company = state.pendingUIState.company || DEFAULT_COMPANY;
    if (companySelector) {
        companySelector.value = state.company;
    }
    state.sortColumn = state.pendingUIState.sortColumn || null;
    state.sortDirection = state.pendingUIState.sortDirection === 'desc' ? 'desc' : 'asc';
    state.gpRangeFilter = state.pendingUIState.gpRangeFilter || null;
}

function applyPendingFilterSelections() {
    const filterIds = [
        ['tagFilter', state.pendingUIState.tag],
        ['stateFilter', state.pendingUIState.state],
        ['healthFilter', state.pendingUIState.health],
    ];
    filterIds.forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value && Array.from(el.options).some(option => option.value === value)) {
            el.value = value;
        }
    });
}

// --- MODULE: assets/js/api.js ---



async function fetchDashboard(dateFrom, company = 'bonario', refresh = false) {
    if (state.currentAbortController) {
        state.currentAbortController.abort();
    }
    const controller = new AbortController();
    state.currentAbortController = controller;
    const { signal } = controller;

    const timeoutId = setTimeout(() => {
        controller.abort();
    }, 180000);

    const params = new URLSearchParams({ date_from: dateFrom, company });
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
            throw new Error('Yêu cầu bị hủy hoặc hết thời gian chờ (180s)');
        }
        throw err;
    }
}

// --- MODULE: assets/js/charts.js ---




const TAG_COLORS = {
    "Nội thất rời": { border: '#2b6cb0', start: 'rgba(43, 108, 176, 0.4)', end: 'rgba(43, 108, 176, 0.02)' },
    "Giấy dán tường": { border: '#f6ad55', start: 'rgba(246, 173, 85, 0.4)', end: 'rgba(246, 173, 85, 0.02)' },
    "Rèm": { border: '#319795', start: 'rgba(49, 151, 149, 0.4)', end: 'rgba(49, 151, 149, 0.02)' },
    "Vải nội thất": { border: '#9f7aea', start: 'rgba(159, 122, 234, 0.4)', end: 'rgba(159, 122, 234, 0.02)' }
};

const DEFAULT_COLOR = { border: '#cbd5e0', start: 'rgba(203, 213, 224, 0.4)', end: 'rgba(203, 213, 224, 0.02)' };

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
                        <stop offset="0%" stop-color="var(--color-emerald, #2b6cb0)" stop-opacity="0.28" />
                        <stop offset="100%" stop-color="var(--color-text-secondary, #64748b)" stop-opacity="0.02" />
                    </linearGradient>
                </defs>
                <path d="${fillD}" fill="url(#${gradId})" />
                <path d="${pathD}" fill="none" stroke="var(--color-emerald, #2b6cb0)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
        `;
        card.style.position = 'relative';
        card.style.overflow = 'hidden';
        card.insertAdjacentHTML('beforeend', svgHTML);
    });
}

function renderGPChart(tagGPRanks) {
    const canvas = document.getElementById('gpChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (state.gpChart) {
        state.gpChart.destroy();
    }

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#0c2317';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#557361';
    const colorMint = style.getPropertyValue('--color-mint').trim() || '#60a5fa';
    const colorEmerald = style.getPropertyValue('--color-emerald').trim() || '#2b6cb0';

    const tags = Object.keys(tagGPRanks);
    const allRanges = new Set();
    Object.values(tagGPRanks).forEach(ranks => {
        ranks.forEach(r => allRanges.add(r.range));
    });
    const sortedRanges = Array.from(allRanges).sort((a, b) => {
        const aMatch = a.match(/(-?\d+)/);
        const bMatch = b.match(/(-?\d+)/);
        const aNum = aMatch ? parseInt(aMatch[0], 10) : 0;
        const bNum = bMatch ? parseInt(bMatch[0], 10) : 0;
        return aNum - bNum;
    });

    const cachedGradients = {};

    const finalDatasets = tags.map((tag, index) => {
        const ranks = tagGPRanks[tag] || [];
        const rankMap = {};
        ranks.forEach(r => { rankMap[r.range] = r.count; });
        const themeColor = TAG_COLORS[tag] || DEFAULT_COLOR;

        return {
            label: tag,
            data: sortedRanges.map(range => rankMap[range] ? rankMap[range] : null),
            skipNull: true,
            categoryPercentage: 0.85,
            barPercentage: 0.8,
            maxBarThickness: 28,
            minBarLength: 10,
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
            borderWidth: 2,
            borderRadius: 2,
            borderSkipped: false,
            hoverBackgroundColor: themeColor.border
        };
    });

    state.gpChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sortedRanges,
            datasets: finalDatasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (evt, elements, chart) => {
                if (elements && elements.length > 0) {
                    const activeElement = elements[0];
                    const datasetIndex = activeElement.datasetIndex;
                    const index = activeElement.index;

                    const dataset = chart.data.datasets[datasetIndex];
                    const tag = dataset.label;
                    const range = chart.data.labels[index];

                    const tagFilter = document.getElementById('tagFilter');
                    if (tagFilter) {
                        tagFilter.value = tag;
                    }
                    const stateFilter = document.getElementById('stateFilter');
                    if (stateFilter) {
                        stateFilter.value = 'Done';
                    }
                    state.pendingUIState.tag = tag;
                    state.pendingUIState.order_state = 'Done';
                    state.gpRangeFilter = range;

                    applyFilters();

                    location.hash = '#/projects';
                }
            },
            onHover: (event, chartElement) => {
                if (event.native && event.native.target) {
                    event.native.target.style.cursor = chartElement.length ? 'pointer' : 'default';
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColorPrimary,
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
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    titleColor: '#f4f7f5',
                    bodyColor: colorMint,
                    borderColor: colorEmerald,
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
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' }
                    },
                    grid: { color: 'rgba(16, 120, 80, 0.04)' }
                },
                y: {
                    ticks: {
                        color: textColorSecondary,
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
    if (state.revenueDoughnutChart) {
        state.revenueDoughnutChart.destroy();
    }

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#0c2317';

    const tags = Object.keys(tagBuckets);
    const tagRevenueData = tags.map(tag => {
        let tagBG = 0;
        Object.values(tagBuckets[tag]).forEach(tier => { tagBG += tier.bg_untaxed; });
        return { tag, revenue: tagBG };
    }).sort((a, b) => b.revenue - a.revenue);

    state.revenueDoughnutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: tagRevenueData.map(d => d.tag),
            datasets: [{
                data: tagRevenueData.map(d => d.revenue),
                backgroundColor: tagRevenueData.map(d => (TAG_COLORS[d.tag] || DEFAULT_COLOR).border),
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
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
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

// --- MODULE: assets/js/components/dashboard-kpi.js ---




function renderKPIs(summary) {
    document.getElementById('totalProjects').textContent = summary.total_projects;
    document.getElementById('validProjects').textContent =
        `${summary.valid_project_count} dự án hợp lệ`;
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
}

function getDashboardMeta() {
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

function renderScopeBar() {
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

// --- MODULE: assets/js/components/table.js ---




function getSortValue(project, columnKey) {
    const val = project[columnKey];
    if (val === null || val === undefined) return '';
    if (typeof val === 'number') return val;
    return String(val).toLowerCase();
}

function applySorting(projects) {
    if (!state.sortColumn) return projects;
    const sorted = [...projects];
    sorted.sort((a, b) => {
        const aVal = getSortValue(a, state.sortColumn);
        const bVal = getSortValue(b, state.sortColumn);
        let cmp = 0;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            cmp = aVal - bVal;
        } else {
            cmp = String(aVal).localeCompare(String(bVal), 'vi');
        }
        return state.sortDirection === 'asc' ? cmp : -cmp;
    });
    return sorted;
}

function toggleSort(columnKey) {
    if (state.sortColumn === columnKey) {
        state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortColumn = columnKey;
        state.sortDirection = 'asc';
    }
    saveUIState();
    renderProjectsTable(state.filteredProjects);
}

function updateSortIndicators() {
    document.querySelectorAll('th[data-sort]').forEach(th => {
        const key = th.getAttribute('data-sort');
        th.classList.remove('sort-asc', 'sort-desc');
        if (key === state.sortColumn) {
            th.classList.add(state.sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

function exportCSV() {
    if (!state.filteredProjects || state.filteredProjects.length === 0) return;

    const headers = ['Đơn hàng', 'Dự án', 'Khách hàng', 'Tags', 'Trạng thái', 'Doanh thu', 'Chi phí', 'Chi phí gốc', 'GP', 'GP%'];
    const rows = applySorting(state.filteredProjects).map(p => [
        p.sale_order_name || '',
        p.project_name || '',
        p.customer || '',
        (p.tags || []).join('; '),
        STATE_LABELS[p.order_state] || p.order_state || '',
        p.bg_untaxed,
        p.adjusted_expected_cost ?? p.native_expected_cost,
        p.native_expected_cost,
        p.gp_amount,
        p.gp_percent !== null && p.gp_percent !== undefined ? p.gp_percent.toFixed(1) + '%' : '',
    ]);

    const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\r\n');

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

function updateFilterIndicators() {
    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    const searchTerm = searchInput ? searchInput.value.trim() : '';
    const tagVal = tagFilter ? tagFilter.value : '';
    const stateVal = stateFilter ? stateFilter.value : '';
    const healthVal = healthFilter ? healthFilter.value : '';

    const hasActiveFilters = searchTerm || tagVal || stateVal || healthVal || state.gpRangeFilter;

    let clearBtn = document.getElementById('clearFiltersBtn');
    if (!clearBtn) {
        clearBtn = document.createElement('button');
        clearBtn.id = 'clearFiltersBtn';
        clearBtn.className = 'clear-filters-btn';
        clearBtn.addEventListener('click', clearFilters);
        const filterContainer = document.querySelector('.table-filters-box');
        if (filterContainer) {
            filterContainer.appendChild(clearBtn);
        }
    }
    
    if (state.gpRangeFilter) {
        clearBtn.innerHTML = `✕ Xóa bộ lọc (${state.gpRangeFilter})`;
    } else {
        clearBtn.textContent = '✕ Xóa bộ lọc';
    }
    
    clearBtn.style.display = hasActiveFilters ? 'inline-block' : 'none';
}

function clearFilters() {
    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    if (searchInput) searchInput.value = '';
    if (tagFilter) tagFilter.value = '';
    if (stateFilter) stateFilter.value = '';
    if (healthFilter) healthFilter.value = '';

    state.gpRangeFilter = null;

    applyFilters();
}

function renderProjectsTable(projects) {
    const tbody = document.getElementById('projectsTable');
    if (!tbody) return;
    tbody.innerHTML = '';

    const sortedProjects = applySorting(projects);

    if (sortedProjects.length === 0) {
        const emptyTr = document.createElement('tr');
        emptyTr.innerHTML = `
            <td colspan="10" style="text-align:center;padding:5rem 2rem;color:var(--color-text-secondary);">
                <div style="margin-bottom:1.25rem; display:inline-block; position:relative;">
                    <i class="far fa-folder-open" style="font-size:3.5rem;color:var(--color-mint);filter:drop-shadow(0 0 12px var(--color-mint-glow));"></i>
                </div>
                <h3 style="font-family:var(--font-heading);font-weight:700;font-size:1.15rem;color:var(--color-text-primary);margin:0 0 0.5rem 0;">Không tìm thấy dự án nào</h3>
                <p style="font-size:0.875rem;opacity:0.8;margin:0 auto;max-width:320px;line-height:1.5;">Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm để khám phá dữ liệu khác.</p>
            </td>
        `;
        tbody.appendChild(emptyTr);
        const tableInfo = document.getElementById('tableInfo');
        if (tableInfo) tableInfo.textContent = 'Hiển thị 0-0 / 0 dự án';
        renderPagination(0);
        updateSortIndicators();
        return;
    }

    const totalPages = Math.max(1, Math.ceil(sortedProjects.length / ITEMS_PER_PAGE));
    if (state.currentPage > totalPages) state.currentPage = totalPages;
    const startIdx = (state.currentPage - 1) * ITEMS_PER_PAGE;
    const pageProjects = sortedProjects.slice(startIdx, startIdx + ITEMS_PER_PAGE);

    const fragment = document.createDocumentFragment();

    pageProjects.forEach(p => {
        const gpClass = p.gp_percent !== null && p.gp_percent >= 0 ? 'gp-positive' : 'gp-negative';
        const stateClass = p.order_state === 'Done' ? 'done' :
                          p.order_state === 'In progress' ? 'progress' : 'pending';
        const stateLabel = STATE_LABELS[p.order_state] || escapeHTML(p.order_state) || '-';
        const adjustedCost = p.adjusted_expected_cost ?? p.native_expected_cost;

        let healthBadgeHTML = '';
        if (p.gp_percent === null || p.gp_percent === undefined || Number.isNaN(Number(p.gp_percent))) {
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

        const odooUrl = state.dashboardData?.meta?.odoo_url;
        let saleOrderHTML = '';
        const parsedId = p.sale_order_id ? Number(p.sale_order_id) : NaN;
        if (odooUrl && !isNaN(parsedId)) {
            saleOrderHTML = `<a href="${escapeHTML(odooUrl)}/web#id=${parsedId}&model=sale.order&view_type=form" target="_blank" rel="noopener noreferrer" class="odoo-link">${escapeHTML(p.sale_order_name) || '-'}</a>`;
        } else {
            saleOrderHTML = `<strong style="color: var(--color-emerald); font-family: var(--font-heading); font-size: 0.88rem;">${escapeHTML(p.sale_order_name) || '-'}</strong>`;
        }

        const tr = document.createElement('tr');
        tr.className = 'fade-in-up';
        const indexOnPage = pageProjects.indexOf(p);
        tr.style.animationDelay = `${indexOnPage * 0.025}s`;

        const isSelected = state.selectedProjects.has(p.project_id);
        tr.innerHTML = `
            <td style="text-align: center;"><input type="checkbox" class="project-checkbox" data-project-id="${p.project_id}" ${isSelected ? 'checked' : ''}></td>
            <td>${saleOrderHTML}</td>
            <td><span style="font-weight: 600; color: var(--color-text-primary);">${escapeHTML(p.project_name) || '-'}</span></td>
            <td style="color: var(--color-text-secondary); font-weight: 500;">${escapeHTML(p.customer) || '-'}</td>
            <td><div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">${(p.tags || []).map(t => `<span class="tag-badge">${escapeHTML(t)}</span>`).join('')}</div></td>
            <td><span class="state-badge ${stateClass}">${stateLabel}</span></td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 700; color: var(--color-text-primary);">${formatFullVND(p.bg_untaxed)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 600; color: var(--color-text-secondary);">${formatFullVND(adjustedCost)}</td>
            <td class="text-right ${gpClass}" style="font-family: var(--font-heading); font-weight: 700;">${formatFullVND(p.gp_amount)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-size: 0.825rem; vertical-align: middle;">${healthBadgeHTML}</td>
        `;
        if (isSelected) tr.classList.add('selected-row');
        fragment.appendChild(tr);
    });

    tbody.appendChild(fragment);

    const start = sortedProjects.length > 0 ? startIdx + 1 : 0;
    const end = Math.min(startIdx + ITEMS_PER_PAGE, sortedProjects.length);
    const tableInfo = document.getElementById('tableInfo');
    if (tableInfo) tableInfo.textContent = `Hiển thị ${start}-${end} / ${sortedProjects.length} dự án`;
    renderPagination(sortedProjects.length);
    renderExportButton();
    updateSortIndicators();
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

    if (state.selectedProjects.size === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';

    const allProjects = state.dashboardData?.projects || [];
    const selected = allProjects.filter(p => state.selectedProjects.has(p.project_id));

    let totalBG = 0;
    let totalCost = 0;
    let totalGP = 0;
    let weightedGPSum = 0;
    let weightedGPCount = 0;

    selected.forEach(p => {
        totalBG += p.bg_untaxed || 0;
        totalCost += (p.adjusted_expected_cost ?? p.native_expected_cost) || 0;
        totalGP += p.gp_amount || 0;
        if (p.gp_percent !== null && p.gp_percent !== undefined && (p.bg_untaxed || 0) > 0) {
            weightedGPSum += p.gp_percent * p.bg_untaxed;
            weightedGPCount += p.bg_untaxed;
        }
    });

    const weightedGP = weightedGPCount > 0 ? (weightedGPSum / weightedGPCount).toFixed(1) : '-';

    const selCountEl = document.getElementById('selectedCount');
    const selBGEl = document.getElementById('selectedTotalBG');
    const selCostEl = document.getElementById('selectedTotalCost');
    const selGPEl = document.getElementById('selectedTotalGP');
    const selAvgGPEl = document.getElementById('selectedAvgGP');

    if (selCountEl) selCountEl.textContent = state.selectedProjects.size;
    if (selBGEl) selBGEl.textContent = formatFullVND(totalBG);
    if (selCostEl) selCostEl.textContent = formatFullVND(totalCost);
    if (selGPEl) selGPEl.textContent = formatFullVND(totalGP);
    if (selAvgGPEl) selAvgGPEl.textContent = weightedGP !== '-' ? weightedGP + '%' : '-';
}

function renderPagination(totalItems) {
    const container = document.getElementById('pagination');
    if (!container) return;
    container.innerHTML = '';

    const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
    if (totalPages <= 1) return;

    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn' + (state.currentPage === 1 ? ' disabled' : '');
    prevBtn.innerHTML = '&laquo;';
    prevBtn.disabled = state.currentPage === 1;
    prevBtn.addEventListener('click', () => { if (state.currentPage > 1) { state.currentPage--; renderProjectsTable(state.filteredProjects); scrollToTableTop(); } });
    container.appendChild(prevBtn);

    const maxVisible = 5;
    let startPage = Math.max(1, state.currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) startPage = Math.max(1, endPage - maxVisible + 1);

    if (startPage > 1) {
        const firstBtn = document.createElement('button');
        firstBtn.className = 'page-btn';
        firstBtn.textContent = '1';
        firstBtn.addEventListener('click', () => { state.currentPage = 1; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
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
        btn.className = 'page-btn' + (i === state.currentPage ? ' active' : '');
        btn.textContent = i;
        btn.addEventListener('click', () => { state.currentPage = i; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
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
        lastBtn.addEventListener('click', () => { state.currentPage = totalPages; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
        container.appendChild(lastBtn);
    }

    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn' + (state.currentPage === totalPages ? ' disabled' : '');
    nextBtn.innerHTML = '&raquo;';
    nextBtn.disabled = state.currentPage === totalPages;
    nextBtn.addEventListener('click', () => { if (state.currentPage < totalPages) { state.currentPage++; renderProjectsTable(state.filteredProjects); scrollToTableTop(); } });
    container.appendChild(nextBtn);
}

function populateFilters(projects) {
    const tagFilter = document.getElementById('tagFilter');
    if (!tagFilter) return;
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

    const stateFilter = document.getElementById('stateFilter');
    if (!stateFilter) return;
    const allStates = new Set();
    projects.forEach(p => {
        if (p.order_state) allStates.add(p.order_state);
    });

    stateFilter.innerHTML = '<option value="">Tất cả trạng thái</option>';
    Array.from(allStates).sort().forEach(orderState => {
        const opt = document.createElement('option');
        opt.value = orderState;
        opt.textContent = STATE_LABELS[orderState] || orderState;
        stateFilter.appendChild(opt);
    });
    applyPendingFilterSelections();
}

function applyFilters() {
    if (!state.dashboardData) return;

    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    const searchTerm = searchInput ? searchInput.value.trim().toLowerCase() : '';
    const tagVal = tagFilter ? tagFilter.value : '';
    const stateVal = stateFilter ? stateFilter.value : '';
    const healthVal = healthFilter ? healthFilter.value : '';

    state.filteredProjects = state.dashboardData.projects.filter(p => {
        if (searchTerm) {
            const searchFields = [
                p.sale_order_name,
                p.project_name,
                p.customer,
            ].filter(Boolean).join(' ').toLowerCase();
            if (!searchFields.includes(searchTerm)) return false;
        }

        if (tagVal && !(p.tags || []).includes(tagVal)) return false;
        if (stateVal && p.order_state !== stateVal) return false;
        if (healthVal && getHealthBucket(p) !== healthVal) return false;

        if (state.gpRangeFilter) {
            if (!isGPInInterval(p.gp_percent, state.gpRangeFilter)) return false;
        }

        return true;
    });

    state.currentPage = 1;
    renderProjectsTable(state.filteredProjects);
    updateFilterIndicators();
    saveUIState();
}

// --- MODULE: assets/js/components/ops-panels.js ---






function renderOperationalPanels() {
    renderScopeBar();
    renderStateMixPanel();
    renderRiskProjectsPanel();
    renderTagSnapshotPanel();
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

function renderRiskProjectsPanel() {
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

function renderTagSnapshotPanel() {
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

function renderTagAnalysis(tagBuckets, tagGPRanks) {
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

// --- MODULE: app.js ---









// ===== SPA Router =====
function handleRouting() {
    const hash = location.hash || '#/overview';
    const routeMap = {
        '#/overview': 'overview-route',
        '#/tags': 'tags-route',
        '#/projects': 'projects-route',
        '#/ranks': 'ranks-route'
    };

    const activeSectionId = routeMap[hash] || 'overview-route';

    document.querySelectorAll('.route-view').forEach(view => {
        view.classList.remove('active');
    });

    const activeView = document.getElementById(activeSectionId);
    if (activeView) {
        activeView.classList.add('active');
    }

    document.querySelectorAll('.sidebar-menu .menu-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href === hash || (hash === '#/overview' && href === '#/overview')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    if (hash !== '#/ranks') {
        if (state.gpChart) {
            state.gpChart.destroy();
            state.gpChart = null;
        }
        if (state.revenueDoughnutChart) {
            state.revenueDoughnutChart.destroy();
            state.revenueDoughnutChart = null;
        }
    }

    if (hash === '#/ranks' && state.dashboardData) {
        if (!state.gpChart) {
            renderGPChart(state.dashboardData.tag_gp_ranks);
        } else {
            state.gpChart.resize();
        }
        if (!state.revenueDoughnutChart) {
            renderRevenueDoughnut(state.dashboardData.tag_buckets);
        } else {
            state.revenueDoughnutChart.resize();
        }
        renderTagLeaderboard(state.dashboardData.tag_buckets);
    }

    updateMenuIndicator();
    saveUIState();
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

    // Get the zoom factor from CSS variable --zoom-factor (default is 1.0 if not present)
    const zoomFactor = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--zoom-factor')) || 1.0;

    const offsetTop = (activeRect.top - menuRect.top) / zoomFactor;
    const height = activeRect.height / zoomFactor;

    indicator.style.height = `${height}px`;
    indicator.style.transform = `translate3d(0, ${offsetTop}px, 0)`;
}

// ===== Main Boot / Data Loading =====
async function loadDashboard(refresh = false) {
    if (state.isLoadingState) return;
    state.isLoadingState = true;

    const refreshBtn = document.getElementById('refreshBtn');
    const dateFromInput = document.getElementById('dateFrom');
    if (refreshBtn) refreshBtn.disabled = true;
    if (dateFromInput) dateFromInput.disabled = true;

    const loadingEl = document.getElementById('loadingState');
    const errorEl = document.getElementById('errorState');
    const mainEl = document.getElementById('mainContent');

    if (state.dashboardData) {
        let overlay = document.getElementById('refreshOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'refreshOverlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = '<div class="spinner"></div><p class="loading-text">Đang tải dữ liệu...</p>';
            document.body.appendChild(overlay);
        } else {
            overlay.style.display = 'flex';
        }
    } else {
        if (loadingEl) loadingEl.style.display = 'flex';
        if (errorEl) errorEl.style.display = 'none';
        if (mainEl) mainEl.style.display = 'none';
    }

    try {
        const dateFrom = dateFromInput ? dateFromInput.value : '';
        const selectedDateFrom = dateFrom || DEFAULT_DATE_FROM;
        const companySelector = document.getElementById('companySelector');
        const selectedCompany = companySelector ? companySelector.value : (state.company || DEFAULT_COMPANY);
        state.company = selectedCompany;
        state.dashboardData = await fetchDashboard(selectedDateFrom, selectedCompany, refresh);
        if (dateFromInput) dateFromInput.value = state.dashboardData.date_from || selectedDateFrom;
        if (state.gpChart) {
            state.gpChart.destroy();
            state.gpChart = null;
        }
        if (state.revenueDoughnutChart) {
            state.revenueDoughnutChart.destroy();
            state.revenueDoughnutChart = null;
        }

        renderKPIs(state.dashboardData.summary);
        renderKPISparklines(state.dashboardData.projects);
        renderOperationalPanels();
        renderTagAnalysis(state.dashboardData.tag_buckets, state.dashboardData.tag_gp_ranks);
        populateFilters(state.dashboardData.projects);

        applyFilters();

        const lastUpdatedEl = document.getElementById('lastUpdated');
        if (lastUpdatedEl && state.dashboardData.fetched_at) {
            const date = new Date(state.dashboardData.fetched_at);
            lastUpdatedEl.textContent = date.toLocaleString('vi-VN');
        }
        saveUIState();

        if (loadingEl) loadingEl.style.display = 'none';
        if (mainEl) mainEl.style.display = 'block';

        const overlay = document.getElementById('refreshOverlay');
        if (overlay) overlay.style.display = 'none';

        handleRouting();
    } catch (err) {
        console.error('Load error:', err);
        const overlay = document.getElementById('refreshOverlay');
        if (overlay) overlay.style.display = 'none';
        if (!state.dashboardData) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (errorEl) errorEl.style.display = 'flex';
            const errorMsgEl = document.getElementById('errorMessage');
            if (errorMsgEl) errorMsgEl.textContent = err.message;
        }
    } finally {
        state.isLoadingState = false;
        if (refreshBtn) refreshBtn.disabled = false;
        if (dateFromInput) dateFromInput.disabled = false;
    }
}

// ===== Event Listeners =====
