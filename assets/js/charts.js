import { state } from './state.js';
import { formatVND, formatPercent, escapeHTML, formatFullVND } from './utils.js';
import { applyFilters } from './components/table.js';
import { STATE_LABELS } from './config.js';

const TAG_COLORS = {
    "Nội thất rời": { border: '#2b6cb0', start: 'rgba(43, 108, 176, 0.4)', end: 'rgba(43, 108, 176, 0.02)' },
    "Giấy dán tường": { border: '#f6ad55', start: 'rgba(246, 173, 85, 0.4)', end: 'rgba(246, 173, 85, 0.02)' },
    "Rèm": { border: '#319795', start: 'rgba(49, 151, 149, 0.4)', end: 'rgba(49, 151, 149, 0.02)' },
    "Vải nội thất": { border: '#9f7aea', start: 'rgba(159, 122, 234, 0.4)', end: 'rgba(159, 122, 234, 0.02)' }
};

const DEFAULT_COLOR = { border: '#cbd5e0', start: 'rgba(203, 213, 224, 0.4)', end: 'rgba(203, 213, 224, 0.02)' };

export function renderKPISparklines(projects) {
    document.querySelectorAll('.kpi-card').forEach(card => {
        const existing = card.querySelector('.kpi-sparkline');
        if (existing) existing.remove();
    });

    if (!Array.isArray(projects) || projects.length < 2) return;

    // Lọc dự án theo công ty đang chọn, trạng thái Done & bg_untaxed > 0, khử trùng shared_so, lấy 10 dự án mới nhất
    const selectedCompany = state.currentCompany || state.company || 'all';
    const seenSO = new Set();
    const validProjects = projects
        .filter(p => {
            if (!p || p.order_state !== 'Done' || !(p.bg_untaxed > 0)) return false;
            if (selectedCompany !== 'all' && p.company_key && p.company_key !== selectedCompany) return false;
            if (p.shared_so && p.sale_order_id) {
                if (seenSO.has(p.sale_order_id)) return false;
                seenSO.add(p.sale_order_id);
            }
            return true;
        })
        .slice(0, 10)
        .reverse();
    if (validProjects.length < 2) return;

    document.querySelectorAll('.kpi-grid > .kpi-card').forEach((card, cardIdx) => {
        let values = [];
        let strokeColor = 'var(--color-emerald, #2b6cb0)';
        
        if (card.querySelector('#totalProjects')) {
            // Card 1: Project Count - trend of GP%
            values = validProjects.map(p => p.gp_percent ?? 0);
            strokeColor = '#3182ce'; // Blue
        } else if (card.querySelector('#totalBG')) {
            // Card 2: Doanh thu - trend of bg_untaxed
            values = validProjects.map(p => p.bg_untaxed || 0);
            strokeColor = '#38a169'; // Green
        } else if (card.querySelector('#totalCost')) {
            // Card 3: Chi phí - trend of adjusted expected cost
            values = validProjects.map(p => p.adjusted_expected_cost ?? p.native_expected_cost ?? 0);
            strokeColor = '#dd6b20'; // Orange
        } else if (card.querySelector('#weightedGP') || card.querySelector('#totalGP')) {
            // Card 4: Lợi nhuận gộp - trend of gp_percent
            values = validProjects.map(p => p.gp_percent ?? 0);
            strokeColor = '#805ad5'; // Purple
        } else {
            return;
        }

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

        const gradId = `sparklineGrad-${cardIdx}-${Math.random().toString(36).substr(2, 9)}`;
        const svgHTML = `
            <svg class="kpi-sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.22" />
                        <stop offset="100%" stop-color="var(--color-bg-base, #1a202c)" stop-opacity="0.01" />
                    </linearGradient>
                </defs>
                <path d="${fillD}" fill="url(#${gradId})" />
                <path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
        `;
        card.style.position = 'relative';
        card.style.overflow = 'hidden';
        card.insertAdjacentHTML('beforeend', svgHTML);
    });
}

export function renderGPChart(tagGPRanks) {
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
        if (a === '<0%') return -1;
        if (b === '<0%') return 1;
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
            skipNull: false,
            categoryPercentage: 0.85,
            barPercentage: 0.8,
            maxBarThickness: 16,
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
                    state.pendingUIState.state = 'Done';
                    state.pendingUIState.order_state = 'Done';
                    state.gpRangeFilter = range;
                    state.revenueTierFilter = null;

                    applyFilters();

                    location.hash = '#/projects';
                }
            },
            onHover: (event, chartElement) => {
                if (event && event.native && event.native.target) {
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

export function renderRevenueDoughnut(tagBuckets) {
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
                            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
                            return ` ${context.label}: ${formatVND(value)} (${pct}%)`;
                        },
                        footer: function() {
                            return 'Một đơn hàng có thể gắn nhiều Tag (tổng các Tag có thể lớn hơn tổng doanh thu công ty đã khử trùng)';
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

export function renderMonthlyTrendChart(projects) {
    const canvas = document.getElementById('monthlyTrendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (state.monthlyTrendChart) {
        state.monthlyTrendChart.destroy();
        state.monthlyTrendChart = null;
    }
    
    const doneProjects = (projects || []).filter(p => p.order_state === 'Done' && p.bg_untaxed > 0 && p.date_order);
    const monthlyData = {};
    doneProjects.forEach(p => {
        const date = new Date(p.date_order);
        if (isNaN(date.getTime())) return;
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const key = `${year}-${month}`;
        if (!monthlyData[key]) {
            monthlyData[key] = {
                label: `Tháng ${month}/${year}`,
                totalBG: 0,
                totalGP: 0
            };
        }
        monthlyData[key].totalBG += p.bg_untaxed || 0;
        monthlyData[key].totalGP += p.gp_amount || 0;
    });
    
    const sortedKeys = Object.keys(monthlyData).sort();
    const labels = sortedKeys.map(k => monthlyData[k].label);
    const bgData = sortedKeys.map(k => monthlyData[k].totalBG);
    const gpPercentData = sortedKeys.map(k => {
        const d = monthlyData[k];
        return d.totalBG > 0 ? (d.totalGP / d.totalBG) * 100 : 0;
    });

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#1e293b';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#64748b';

    state.monthlyTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Doanh thu (BG)',
                    data: bgData,
                    borderColor: '#2b6cb0',
                    backgroundColor: 'rgba(43, 108, 176, 0.05)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'y'
                },
                {
                    label: 'Weighted GP%',
                    data: gpPercentData,
                    borderColor: '#d97706',
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    pointBackgroundColor: '#d97706',
                    tension: 0.3,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColorPrimary,
                        font: { family: "'Outfit', sans-serif", size: 12, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(12, 35, 23, 0.95)',
                    titleColor: '#f4f7f5',
                    bodyColor: '#a7f3d0',
                    borderColor: '#2b6cb0',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: function(context) {
                            const value = context.raw;
                            if (context.datasetIndex === 0) {
                                return ` ${context.dataset.label}: ${formatVND(value)}`;
                            } else {
                                return ` ${context.dataset.label}: ${value.toFixed(1)}%`;
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' }
                    },
                    grid: { color: 'rgba(43, 108, 176, 0.04)' }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        callback: function(value) {
                            return formatVND(value);
                        }
                    },
                    grid: { color: 'rgba(43, 108, 176, 0.04)' },
                    title: {
                        display: true,
                        text: 'Doanh thu',
                        color: textColorPrimary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '700' }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        callback: function(value) {
                            return value.toFixed(0) + '%';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Weighted GP%',
                        color: textColorPrimary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '700' }
                    }
                }
            }
        }
    });
}

/**
 * Renders 4 independent GP% distribution charts for the core tags.
 */
export function renderTagGPCharts(tagGPRanks) {
    const targetTags = ["Nội thất rời", "Giấy dán tường", "Rèm", "Vải nội thất"];
    const canvasIds = {
        "Nội thất rời": "gpTagNoiThatRoi",
        "Giấy dán tường": "gpTagGiayDanTuong",
        "Rèm": "gpTagRem",
        "Vải nội thất": "gpTagVaiNoiThat"
    };

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#1e293b';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#64748b';
    const colorMint = style.getPropertyValue('--color-mint').trim() || '#60a5fa';
    const colorEmerald = style.getPropertyValue('--color-emerald').trim() || '#2b6cb0';

    // Store chart instances on state.tagCharts to manage lifecycle
    if (!state.tagCharts) {
        state.tagCharts = {};
    }

    // Get uniform set of sorted ranges for all GP charts to make them visually comparable
    const allRanges = new Set();
    Object.values(tagGPRanks).forEach(ranks => {
        ranks.forEach(r => allRanges.add(r.range));
    });
    const sortedRanges = Array.from(allRanges).sort((a, b) => {
        if (a === '<0%') return -1;
        if (b === '<0%') return 1;
        const aMatch = a.match(/(-?\d+)/);
        const bMatch = b.match(/(-?\d+)/);
        const aNum = aMatch ? parseInt(aMatch[0], 10) : 0;
        const bNum = bMatch ? parseInt(bMatch[0], 10) : 0;
        return aNum - bNum;
    });

    targetTags.forEach(tag => {
        const canvasId = canvasIds[tag];
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        // Destroy previous instance to prevent overlays
        if (state.tagCharts[tag]) {
            state.tagCharts[tag].destroy();
        }

        const ctx = canvas.getContext('2d');
        const ranks = tagGPRanks[tag] || [];
        const themeColor = TAG_COLORS[tag] || DEFAULT_COLOR;

        const rankMap = {};
        ranks.forEach(r => { rankMap[r.range] = r.count; });
        const chartData = sortedRanges.map(range => rankMap[range] || 0);

        let gradientCache = null;

        state.tagCharts[tag] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: sortedRanges,
                datasets: [{
                    label: tag,
                    data: chartData,
                    skipNull: true,
                    categoryPercentage: 0.8,
                    barPercentage: 0.8,
                    backgroundColor: function(context) {
                        const chart = context.chart;
                        const {ctx: chartCtx, chartArea} = chart;
                        if (!chartArea) return themeColor.start;
                        if (gradientCache) return gradientCache;
                        const gradient = chartCtx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
                        gradient.addColorStop(0, themeColor.end);
                        gradient.addColorStop(1, themeColor.start);
                        gradientCache = gradient;
                        return gradient;
                    },
                    borderColor: themeColor.border,
                    borderWidth: 2,
                    borderRadius: 4,
                    borderSkipped: false,
                    hoverBackgroundColor: themeColor.border
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onClick: (evt, elements, chart) => {
                    if (elements && elements.length > 0) {
                        const activeElement = elements[0];
                        const index = activeElement.index;
                        const range = chart.data.labels[index];

                        // Redirect to projects filtering by Tag & GP segment
                        const tagFilter = document.getElementById('tagFilter');
                        if (tagFilter) tagFilter.value = tag;
                        const stateFilter = document.getElementById('stateFilter');
                        if (stateFilter) stateFilter.value = 'Done';

                        state.pendingUIState.tag = tag;
                        state.pendingUIState.state = 'Done';
                        state.pendingUIState.order_state = 'Done';
                        state.gpRangeFilter = range;
                        state.revenueTierFilter = null; // Clear tier filter

                        applyFilters();
                        location.hash = '#/projects';
                    }
                },
                onHover: (event, chartElement) => {
                    if (event && event.native && event.native.target) {
                        event.native.target.style.cursor = chartElement.length ? 'pointer' : 'default';
                    }
                },
                plugins: {
                    legend: { display: false }, // Tag name is in the card header
                    tooltip: {
                        backgroundColor: 'rgba(30, 41, 59, 0.95)',
                        titleColor: '#f4f7f5',
                        bodyColor: colorMint,
                        borderColor: colorEmerald,
                        borderWidth: 1,
                        padding: 10,
                        titleFont: { family: "'Montserrat', sans-serif", weight: '600' },
                        bodyFont: { family: "'Outfit', sans-serif" },
                        callbacks: {
                            label: function(context) {
                                return ` Số lượng dự án: ${context.raw} DA`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: textColorSecondary,
                            font: { family: "'Outfit', sans-serif", size: 10, weight: '600' }
                        },
                        grid: { color: 'rgba(43, 108, 176, 0.04)' }
                    },
                    y: {
                        ticks: {
                            color: textColorSecondary,
                            font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                            stepSize: 1
                        },
                        grid: { color: 'rgba(43, 108, 176, 0.04)' },
                        beginAtZero: true
                    }
                }
            }
        });
    });
}

/**
 * Renders the full-width grouped revenue segment chart (stacked: false to avoid multi-tag double counting).
 */
export function renderStackedRevenueChart(tagBuckets) {
    const canvas = document.getElementById('stackedRevenueChart');
    if (!canvas) return;

    if (state.stackedRevenueChart) {
        state.stackedRevenueChart.destroy();
    }

    const ctx = canvas.getContext('2d');
    const tiers = ['<10tr', '10-100tr', '100-200tr', '>200tr'];
    const targetTags = ["Nội thất rời", "Giấy dán tường", "Rèm", "Vải nội thất"];

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#1e293b';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#64748b';
    const colorMint = style.getPropertyValue('--color-mint').trim() || '#60a5fa';
    const colorEmerald = style.getPropertyValue('--color-emerald').trim() || '#2b6cb0';

    // Tính tổng doanh thu phân khúc đã khử trùng theo SO từ danh sách dự án Done có bg_untaxed > 0
    const allProjects = state.dashboardData?.projects || [];
    const hasProjectsData = Array.isArray(allProjects) && allProjects.length > 0;
    const segmentDedupTotals = { '<10tr': 0, '10-100tr': 0, '100-200tr': 0, '>200tr': 0 };
    if (hasProjectsData) {
        const seenSO = new Set();
        allProjects.forEach(p => {
            if (!p || p.order_state !== 'Done' || !(p.bg_untaxed > 0)) return;
            const soKey = p.sale_order_id ? `so:${p.sale_order_id}` : (p.sale_order_name ? `name:${p.sale_order_name}` : `proj:${p.project_id}`);
            if (p.shared_so || p.sale_order_id) {
                if (seenSO.has(soKey)) return;
                seenSO.add(soKey);
            }
            const amount = p.bg_untaxed || 0;
            let tier = '';
            if (amount > 0 && amount < 10000000) tier = '<10tr';
            else if (amount < 100000000) tier = '10-100tr';
            else if (amount < 200000000) tier = '100-200tr';
            else tier = '>200tr';
            if (tier && segmentDedupTotals[tier] !== undefined) {
                segmentDedupTotals[tier] += amount;
            }
        });
    }

    const datasets = targetTags.map(tag => {
        const themeColor = TAG_COLORS[tag] || DEFAULT_COLOR;
        const data = tiers.map(tier => {
            const bucket = tagBuckets[tag]?.[tier];
            return bucket ? bucket.bg_untaxed : 0;
        });

        return {
            label: tag,
            data: data,
            backgroundColor: themeColor.border,
            borderColor: '#ffffff',
            borderWidth: 1.5,
            borderRadius: 4,
            hoverBackgroundColor: themeColor.border
        };
    });

    state.stackedRevenueChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tiers,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (evt, elements, chart) => {
                if (elements && elements.length > 0) {
                    const activeElement = elements[0];
                    const datasetIndex = activeElement.datasetIndex;
                    const index = activeElement.index;

                    const tag = chart.data.datasets[datasetIndex].label;
                    const tier = chart.data.labels[index];

                    // Redirect to projects filtering by Tag & Revenue segment
                    const tagFilter = document.getElementById('tagFilter');
                    if (tagFilter) tagFilter.value = tag;
                    const stateFilter = document.getElementById('stateFilter');
                    if (stateFilter) stateFilter.value = 'Done';

                    state.pendingUIState.tag = tag;
                    state.pendingUIState.state = 'Done';
                    state.pendingUIState.order_state = 'Done';
                    state.revenueTierFilter = tier;
                    state.gpRangeFilter = null; // Clear GP range filter

                    applyFilters();
                    location.hash = '#/projects';
                }
            },
            onHover: (event, chartElement) => {
                if (event && event.native && event.native.target) {
                    event.native.target.style.cursor = chartElement.length ? 'pointer' : 'default';
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColorPrimary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 15
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    titleColor: '#f4f7f5',
                    bodyColor: '#ffffff',
                    borderColor: colorEmerald,
                    borderWidth: 1,
                    padding: 10,
                    titleFont: { family: "'Montserrat', sans-serif", weight: '600' },
                    bodyFont: { family: "'Outfit', sans-serif" },
                    callbacks: {
                        label: function(context) {
                            const dataset = context.dataset;
                            const value = context.raw || 0;
                            const dataIndex = context.dataIndex;
                            const tier = tiers[dataIndex];
                            let total = hasProjectsData ? (segmentDedupTotals[tier] || 0) : 0;
                            if (!total) {
                                context.chart.data.datasets.forEach(ds => {
                                    total += ds.data[dataIndex] || 0;
                                });
                            }
                            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
                            return ` ${dataset.label}: ${formatVND(value)} (${pct}%)`;
                        },
                        footer: function(tooltipItems) {
                            let total = 0;
                            if (tooltipItems.length > 0) {
                                const dataIndex = tooltipItems[0].dataIndex;
                                const tier = tiers[dataIndex];
                                if (hasProjectsData) {
                                    total = segmentDedupTotals[tier] || 0;
                                } else {
                                    const chart = tooltipItems[0].chart;
                                    chart.data.datasets.forEach(ds => {
                                        total += ds.data[dataIndex] || 0;
                                    });
                                }
                            }
                            return [
                                `Tổng doanh thu phân khúc (khử trùng SO): ${formatVND(total)}`,
                                'Lưu ý: Một đơn hàng có thể thuộc nhiều hạng mục (Tag)'
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    stacked: false,
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '600' }
                    },
                    grid: { color: 'rgba(43, 108, 176, 0.04)' }
                },
                y: {
                    stacked: false,
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        callback: function(value) {
                            return formatVND(value);
                        }
                    },
                    grid: { color: 'rgba(43, 108, 176, 0.04)' }
                }
            }
        }
    });
}

/**
 * Helper duy nhất lấy phân bổ chi phí vận chuyển theo tháng cho 1 dự án (S11).
 * Ưu tiên p.shipping_cost_by_month; chỉ fallback sang p.date_order nếu payload cũ hoàn toàn không có trường shipping_cost_by_month.
 */
export function getProjectShippingByMonth(p) {
    if (!p) return {};
    if (p.shipping_cost_by_month !== undefined && p.shipping_cost_by_month !== null) {
        return p.shipping_cost_by_month;
    }
    if (p.date_order && p.shipping_cost) {
        const date = new Date(p.date_order);
        if (!isNaN(date.getTime())) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            return { [`${year}-${month}`]: p.shipping_cost };
        }
    }
    return {};
}

export function renderMonthlyShippingTrendChart(projects) {
    const canvas = document.getElementById('monthlyShippingTrendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (state.monthlyShippingTrendChart) {
        state.monthlyShippingTrendChart.destroy();
        state.monthlyShippingTrendChart = null;
    }
    
    const activeProjects = (projects || []);
    const summaryByMonth = state.dashboardData?.summary?.shipping_by_month || {};
    const monthlyData = {};

    const ensureMonthEntry = (key) => {
        const parts = String(key).split('-');
        if (parts.length !== 2) return null;
        const year = parts[0];
        const month = parts[1];
        if (!monthlyData[key]) {
            monthlyData[key] = {
                label: `Tháng ${month}/${year}`,
                assignedShipping: 0,
                unassignedShipping: 0,
                projectsInMonth: new Set()
            };
        }
        return monthlyData[key];
    };

    // Tổng hợp phần "Đã gắn dự án" từ activeProjects qua helper chung getProjectShippingByMonth(p)
    activeProjects.forEach(p => {
        const costByMonth = getProjectShippingByMonth(p);
        Object.entries(costByMonth).forEach(([key, rawCost]) => {
            const cost = Number(rawCost) || 0;
            if (cost === 0) return;
            const entry = ensureMonthEntry(key);
            if (!entry) return;
            entry.assignedShipping += cost;
            entry.projectsInMonth.add(p.project_id);
        });
    });

    // Kết hợp với summary.shipping_by_month từ backend (đặc biệt cho phần "Chưa gắn dự án")
    Object.entries(summaryByMonth).forEach(([key, info]) => {
        if (!info) return;
        const unassigned = Number(info.unassigned) || 0;
        const assignedFromSummary = Number(info.assigned) || 0;
        if (unassigned === 0 && assignedFromSummary === 0 && !monthlyData[key]) return;
        const entry = ensureMonthEntry(key);
        if (!entry) return;
        if (activeProjects.length === 0 && info.assigned !== undefined) {
            entry.assignedShipping = assignedFromSummary;
        }
        entry.unassignedShipping = unassigned;
        if (Array.isArray(info.projects) && entry.projectsInMonth.size === 0) {
            info.projects.forEach(proj => {
                const pid = (proj && typeof proj === 'object') ? proj.project_id : proj;
                if (pid !== undefined && pid !== null) entry.projectsInMonth.add(pid);
            });
        }
    });
    
    const sortedKeys = Object.keys(monthlyData).sort();
    const labels = sortedKeys.map(k => monthlyData[k].label);
    const assignedData = sortedKeys.map(k => monthlyData[k].assignedShipping);
    const unassignedData = sortedKeys.map(k => monthlyData[k].unassignedShipping);
    const countData = sortedKeys.map(k => monthlyData[k].projectsInMonth.size);

    const style = getComputedStyle(document.documentElement);
    const textColorPrimary = style.getPropertyValue('--color-text-primary').trim() || '#1e293b';
    const textColorSecondary = style.getPropertyValue('--color-text-secondary').trim() || '#64748b';
    const colorEmerald = style.getPropertyValue('--color-emerald').trim() || '#10b981';

    state.monthlyShippingTrendChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Đã gắn dự án',
                    data: assignedData,
                    backgroundColor: 'rgba(239, 68, 68, 0.75)',
                    borderColor: '#ef4444',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    order: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'Số lượng dự án phát sinh',
                    data: countData,
                    type: 'line',
                    borderColor: colorEmerald,
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 3,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    fill: false,
                    tension: 0.3,
                    order: 1,
                    yAxisID: 'y1'
                },
                {
                    label: 'Chưa gắn dự án',
                    data: unassignedData,
                    backgroundColor: 'rgba(245, 158, 11, 0.75)',
                    borderColor: '#f59e0b',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    order: 2,
                    yAxisID: 'y'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (event, elements) => {
                if (elements && elements.length > 0) {
                    const index = elements[0].index;
                    const monthKey = sortedKeys[index];
                    showMonthlyShippingDetailModal(monthKey, activeProjects);
                }
            },
            onHover: (event, chartElement) => {
                if (event && event.native && event.native.target) {
                    event.native.target.style.cursor = (chartElement && chartElement[0]) ? 'pointer' : 'default';
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { 
                        color: textColorPrimary, 
                        font: { family: "'Outfit', sans-serif", size: 12, weight: '500' } 
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    titleColor: '#f4f7f5',
                    bodyColor: '#ffffff',
                    padding: 10,
                    titleFont: { family: "'Outfit', sans-serif", weight: '600' },
                    bodyFont: { family: "'Outfit', sans-serif" },
                    callbacks: {
                        label: function(context) {
                            const val = context.raw || 0;
                            if (context.dataset.yAxisID === 'y1') {
                                return ` ${context.dataset.label}: ${val} dự án`;
                            }
                            return ` ${context.dataset.label}: ${formatFullVND(val)}`;
                        },
                        footer: function(tooltipItems) {
                            if (!tooltipItems || tooltipItems.length === 0) return '';
                            const idx = tooltipItems[0].dataIndex;
                            const assigned = assignedData[idx] || 0;
                            const unassigned = unassignedData[idx] || 0;
                            const total = assigned + unassigned;
                            return [
                                `Đã gắn dự án: ${formatFullVND(assigned)}`,
                                `Chưa gắn dự án: ${formatFullVND(unassigned)}`,
                                `Tổng chi phí vận chuyển tháng: ${formatFullVND(total)}`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { 
                        color: textColorSecondary, 
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '600' } 
                    },
                    grid: { color: 'rgba(148,163,184,0.06)' }
                },
                y: {
                    position: 'left',
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        callback: function(value) {
                            const num = Number(value) || 0;
                            const abs = Math.abs(num);
                            const sign = num < 0 ? '-' : '';
                            if (abs >= 1e9) return sign + (abs / 1e9).toFixed(1) + ' tỷ';
                            if (abs >= 1e6) return sign + (abs / 1e6).toFixed(1) + ' tr';
                            if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + ' k';
                            return num;
                        }
                    },
                    grid: { color: 'rgba(148,163,184,0.06)' }
                },
                y1: {
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 10, weight: '600' },
                        stepSize: 1,
                        callback: function(value) {
                            return value + ' DA';
                        }
                    }
                }
            }
        }
    });
}

export function showMonthlyShippingDetailModal(monthKey, activeProjects) {
    const modal = document.getElementById('shippingDetailModal');
    if (!modal) return;
    
    // Parse monthKey like "2026-06" to show "Tháng 06/2026"
    const parts = String(monthKey).split('-');
    const monthTitle = parts.length === 2 ? `Tháng ${parts[1]}/${parts[0]}` : monthKey;
    
    const titleEl = document.getElementById('shippingModalTitle');
    if (titleEl) {
        titleEl.textContent = `Chi tiết chi phí vận chuyển - ${monthTitle}`;
    }
    
    // Filter and collect projects contributing to this month (cùng helper getProjectShippingByMonth và giữ cả số âm cost !== 0)
    const contributors = [];
    let totalAssignedCost = 0;
    
    (activeProjects || []).forEach(p => {
        const costByMonth = getProjectShippingByMonth(p);
        const cost = Number(costByMonth[monthKey]) || 0;
        
        if (cost !== 0) {
            contributors.push({
                project_id: p.project_id,
                project_name: p.project_name || '',
                sale_order_name: p.sale_order_name || '',
                customer: p.customer || '',
                order_state: p.order_state || 'No state',
                bg_untaxed: p.bg_untaxed || 0,
                costInMonth: cost,
                totalProjectShipping: p.shipping_cost || 0,
                shipping_cost_po: p.shipping_cost_po || 0,
                shipping_cost_non_po: p.shipping_cost_non_po || 0,
                shipping_draft: p.shipping_draft || 0
            });
            totalAssignedCost += cost;
        }
    });
    
    // Sort contributors descending by shipping cost in this month
    contributors.sort((a, b) => b.costInMonth - a.costInMonth);

    const unassignedCost = Number(state.dashboardData?.summary?.shipping_by_month?.[monthKey]?.unassigned) || 0;
    const totalCost = totalAssignedCost + unassignedCost;
    
    // Set summary cards
    const totalCostEl = document.getElementById('shippingModalTotalCost');
    if (totalCostEl) {
        totalCostEl.textContent = formatFullVND(totalCost);
    }
    
    const totalProjectsEl = document.getElementById('shippingModalTotalProjects');
    if (totalProjectsEl) {
        totalProjectsEl.textContent = unassignedCost !== 0
            ? `${contributors.length} dự án (+ Chưa gắn DA)`
            : `${contributors.length} dự án`;
    }
    
    // Populate table body
    const tbody = document.getElementById('shippingModalTableBody');
    if (tbody) {
        tbody.innerHTML = '';
        if (contributors.length === 0 && unassignedCost === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="padding: 24px; text-align: center; color: var(--color-text-secondary);">
                        Không có dữ liệu chi phí vận chuyển trong tháng này.
                    </td>
                </tr>
            `;
        } else {
            contributors.forEach(c => {
                const tr = document.createElement('tr');
                tr.style.borderBottom = '1px solid rgba(43, 108, 176, 0.06)';
                tr.style.transition = 'background-color 0.2s';
                tr.addEventListener('mouseenter', () => {
                    tr.style.backgroundColor = 'rgba(43, 108, 176, 0.02)';
                });
                tr.addEventListener('mouseleave', () => {
                    tr.style.backgroundColor = 'transparent';
                });
                
                const projectLink = `#/project/${c.project_id}`;
                const stateClass = c.order_state === 'Done' ? 'done' :
                                  c.order_state === 'In progress' ? 'progress' : 'pending';
                const stateLabel = STATE_LABELS[c.order_state] || escapeHTML(c.order_state) || '-';
                const shipBreakdownTooltip = `Qua PO: ${formatFullVND(c.shipping_cost_po)} | Ngoài PO: ${formatFullVND(c.shipping_cost_non_po)}${c.shipping_draft > 0 ? ' | Bill nháp: ' + formatFullVND(c.shipping_draft) : ''}`;
                const monthCostColor = c.costInMonth < 0 ? 'var(--color-emerald)' : '#ef4444';
                
                tr.innerHTML = `
                    <td style="padding: 12px 16px;">
                        <a href="${projectLink}" style="font-weight: 600; color: var(--color-link); text-decoration: none; display: block; margin-bottom: 2px;">
                            ${escapeHTML(c.project_name || c.sale_order_name)}
                        </a>
                        <span style="font-size: 0.75rem; color: var(--color-text-secondary); display: flex; align-items: center; gap: 4px;">
                            <i class="far fa-user" style="font-size: 0.7rem;"></i> Khách hàng: ${escapeHTML(c.customer || 'N/A')}
                        </span>
                    </td>
                    <td style="padding: 12px 16px; text-align: center;">
                        <span class="state-badge ${stateClass}">
                            ${stateLabel}
                        </span>
                    </td>
                    <td style="padding: 12px 16px; text-align: right; font-weight: 500; font-family: var(--font-heading);">
                        ${formatFullVND(c.bg_untaxed)}
                    </td>
                    <td style="padding: 12px 16px; text-align: right; font-weight: 700; color: ${monthCostColor}; background: rgba(239, 68, 68, 0.01); font-family: var(--font-heading);" title="${escapeHTML(shipBreakdownTooltip)}">
                        ${formatFullVND(c.costInMonth)}
                    </td>
                    <td style="padding: 12px 16px; text-align: right; font-weight: 600; color: var(--color-text-primary); font-family: var(--font-heading);" title="${escapeHTML(shipBreakdownTooltip)}">
                        ${formatFullVND(c.totalProjectShipping)}
                    </td>
                `;
                tbody.appendChild(tr);
            });

            if (unassignedCost !== 0) {
                const dateFrom = document.getElementById('dateFrom')?.value || state.dashboardData?.date_from || '2026-01-01';
                const company = state.company || 'all';
                const csvUrl = `/api/shipping/unassigned?date_from=${encodeURIComponent(dateFrom)}&company=${encodeURIComponent(company)}&format=csv`;
                const jsonUrl = `/api/shipping/unassigned?date_from=${encodeURIComponent(dateFrom)}&company=${encodeURIComponent(company)}`;
                const totalUnassignedAllMonths = state.dashboardData?.summary?.shipping_unassigned_total ?? unassignedCost;

                const unassignedTr = document.createElement('tr');
                unassignedTr.style.borderTop = '2px dashed rgba(245, 158, 11, 0.35)';
                unassignedTr.style.backgroundColor = 'rgba(245, 158, 11, 0.05)';
                unassignedTr.innerHTML = `
                    <td style="padding: 12px 16px;">
                        <div style="font-weight: 700; color: #b45309; margin-bottom: 4px;">
                            <i class="fas fa-box-open" style="margin-right: 4px;"></i> Chi phí vận chuyển chưa gắn dự án
                        </div>
                        <div style="display: flex; gap: 10px; font-size: 0.75rem;">
                            <a href="${escapeHTML(csvUrl)}" target="_blank" rel="noopener noreferrer" style="color: var(--color-emerald); font-weight: 600; text-decoration: none;">
                                <i class="fas fa-download"></i> Tải CSV chi tiết
                            </a>
                            <a href="${escapeHTML(jsonUrl)}" target="_blank" rel="noopener noreferrer" style="color: var(--color-text-secondary); font-weight: 500; text-decoration: none;">
                                <i class="fas fa-external-link-alt"></i> Xem JSON
                            </a>
                        </div>
                    </td>
                    <td style="padding: 12px 16px; text-align: center;">
                        <span class="state-badge pending">Chưa gắn DA</span>
                    </td>
                    <td style="padding: 12px 16px; text-align: right; color: var(--color-text-secondary);">-</td>
                    <td style="padding: 12px 16px; text-align: right; font-weight: 700; color: #d97706; font-family: var(--font-heading);">
                        ${formatFullVND(unassignedCost)}
                    </td>
                    <td style="padding: 12px 16px; text-align: right; font-weight: 600; color: var(--color-text-primary); font-family: var(--font-heading);">
                        ${formatFullVND(totalUnassignedAllMonths)}
                    </td>
                `;
                tbody.appendChild(unassignedTr);
            }
        }
    }
    
    // Show modal
    modal.style.display = 'flex';
}
