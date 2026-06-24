import { state } from './state.js';
import { formatVND, formatPercent } from './utils.js';
import { applyFilters } from './components/table.js';

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

    // Filter projects that have valid metrics
    const validProjects = projects.filter(p => p && p.bg_untaxed !== null && p.bg_untaxed !== undefined).slice(-10);
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
                            return ` ${context.label}: ${formatVND(value)} (${((value/total)*100).toFixed(1)}%)`;
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
                    if (event.native && event.native.target) {
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
 * Renders the full-width stacked revenue segment chart.
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

    const datasets = targetTags.map(tag => {
        const themeColor = TAG_COLORS[tag] || DEFAULT_COLOR;
        const data = tiers.map(tier => {
            const bucket = tagBuckets[tag]?.[tier];
            return bucket ? bucket.bg_untaxed : 0;
        });

        return {
            label: tag,
            data: data,
            stack: 'revenue',
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
                if (event.native && event.native.target) {
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
                            const value = context.raw;
                            
                            // Calculate percentage contribution inside this segment
                            const chart = context.chart;
                            const dataIndex = context.dataIndex;
                            let total = 0;
                            chart.data.datasets.forEach(ds => {
                                total += ds.data[dataIndex] || 0;
                            });
                            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return ` ${dataset.label}: ${formatVND(value)} (${pct}%)`;
                        },
                        footer: function(tooltipItems) {
                            let total = 0;
                            if (tooltipItems.length > 0) {
                                const chart = tooltipItems[0].chart;
                                const dataIndex = tooltipItems[0].dataIndex;
                                chart.data.datasets.forEach(ds => {
                                    total += ds.data[dataIndex] || 0;
                                });
                            }
                            return `Tổng doanh thu phân khúc: ${formatVND(total)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    stacked: true,
                    ticks: {
                        color: textColorSecondary,
                        font: { family: "'Outfit', sans-serif", size: 11, weight: '600' }
                    },
                    grid: { color: 'rgba(43, 108, 176, 0.04)' }
                },
                y: {
                    stacked: true,
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

