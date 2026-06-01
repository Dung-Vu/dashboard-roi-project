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
