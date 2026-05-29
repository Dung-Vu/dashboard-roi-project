// ===== Configuration =====
const API_BASE = '';
const DEFAULT_DATE_FROM = '2026-01-01';

// ===== State =====
let dashboardData = null;
let filteredProjects = [];
let gpChart = null;
let revenueDoughnutChart = null;
let isLoadingState = false;
let currentPage = 1;
const ITEMS_PER_PAGE = 10;

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
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + ' tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + ' tr';
    }
    return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
}

// Full VND formatting for table rows
function formatFullVND(amount) {
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

// ===== API =====
async function fetchDashboard(dateFrom, refresh = false) {
    const params = new URLSearchParams({ date_from: dateFrom });
    if (refresh) params.set('refresh', '1');
    
    const response = await fetch(`${API_BASE}/api/projects-dashboard?${params}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
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
                const {ctx, chartArea} = chart;
                if (!chartArea) return null;
                const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
                gradient.addColorStop(0, themeColor.end);
                gradient.addColorStop(1, themeColor.start);
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

function renderProjectsTable(projects) {
    const tbody = document.getElementById('projectsTable');
    tbody.innerHTML = '';
    
    // Pagination
    const totalPages = Math.max(1, Math.ceil(projects.length / ITEMS_PER_PAGE));
    if (currentPage > totalPages) currentPage = totalPages;
    const startIdx = (currentPage - 1) * ITEMS_PER_PAGE;
    const pageProjects = projects.slice(startIdx, startIdx + ITEMS_PER_PAGE);
    
    const fragment = document.createDocumentFragment();
    
    pageProjects.forEach(p => {
        const gpClass = p.gp_percent !== null && p.gp_percent >= 0 ? 'gp-positive' : 'gp-negative';
        const stateClass = p.order_state === 'Done' ? 'done' : 
                          p.order_state === 'In progress' ? 'progress' : 'pending';
        const stateLabel = {
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
        }[p.order_state] || escapeHTML(p.order_state) || '-';
        
        let healthBadgeHTML = '';
        if (p.gp_percent === null || p.gp_percent === undefined) {
            healthBadgeHTML = '<span style="color: var(--color-text-secondary); opacity: 0.5;">-</span>';
        } else {
            let healthClass = 'health-coral';
            if (p.gp_percent > 40) {
                healthClass = 'health-green';
            } else if (p.gp_percent >= 15) {
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
        tr.innerHTML = `
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
        fragment.appendChild(tr);
    });
    
    tbody.appendChild(fragment);
    
    const start = projects.length > 0 ? startIdx + 1 : 0;
    const end = Math.min(startIdx + ITEMS_PER_PAGE, projects.length);
    document.getElementById('tableInfo').textContent = `Hiển thị ${start}-${end} / ${projects.length} dự án`;
    renderPagination(projects.length);
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
    prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderProjectsTable(filteredProjects); } });
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
        firstBtn.addEventListener('click', () => { currentPage = 1; renderProjectsTable(filteredProjects); });
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
        btn.addEventListener('click', () => { currentPage = i; renderProjectsTable(filteredProjects); });
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
        lastBtn.addEventListener('click', () => { currentPage = totalPages; renderProjectsTable(filteredProjects); });
        container.appendChild(lastBtn);
    }
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn' + (currentPage === totalPages ? ' disabled' : '');
    nextBtn.innerHTML = '&raquo;';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; renderProjectsTable(filteredProjects); } });
    container.appendChild(nextBtn);
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
    
    // Populate state filter
    const stateFilter = document.getElementById('stateFilter');
    const allStates = new Set();
    projects.forEach(p => {
        if (p.order_state) allStates.add(p.order_state);
    });
    
    const stateLabels = {
        'Done': 'Hoàn tất',
        'In progress': 'Đang xử lý',
        'Need process': 'Cần xử lý',
        'ATTENTION!': 'Đã đặt hàng',
        'NVL về/Chưa SX': 'NVL về/Chờ SX',
        'Hàng về/Chờ thi công': 'Hàng về/Chờ TC',
        'Giao hàng xong/Chờ hoàn thành checklist': 'Giao xong/Chờ checklist',
        'Pending': 'Chờ KH',
        'Chờ phản hồi nội bộ': 'Chờ nội bộ',
        'Sx xong gom đi OCP2': 'Chờ OCP2',
        'Gom hàng OCP2 - Đợt 2': 'Chờ OCP2-2',
    };
    
    stateFilter.innerHTML = '<option value="">Tất cả trạng thái</option>';
    Array.from(allStates).sort().forEach(state => {
        const opt = document.createElement('option');
        opt.value = state;
        opt.textContent = stateLabels[state] || state;
        stateFilter.appendChild(opt);
    });
}

// ===== Filter & Search =====
function applyFilters() {
    if (!dashboardData) return;
    
    const searchTerm = document.getElementById('searchInput').value.trim().toLowerCase();
    const tagFilter = document.getElementById('tagFilter').value;
    const stateFilter = document.getElementById('stateFilter').value;
    
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
        
        return true;
    });
    
    currentPage = 1;
    renderProjectsTable(filteredProjects);
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
    
    // Ensure Chart.js renders correctly with correct width when entering the ranks view
    if (hash === '#/ranks' && dashboardData) {
        renderGPChart(dashboardData.tag_gp_ranks);
        renderRevenueDoughnut(dashboardData.tag_buckets);
        renderTagLeaderboard(dashboardData.tag_buckets);
    }
    
    // Update menu indicator position vertical
    updateMenuIndicator();
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
    
    loadingEl.style.display = 'flex';
    errorEl.style.display = 'none';
    mainEl.style.display = 'none';
    
    try {
        const dateFrom = dateFromInput ? dateFromInput.value : '';
        const selectedDateFrom = dateFrom || DEFAULT_DATE_FROM;
        dashboardData = await fetchDashboard(selectedDateFrom, refresh);
        
        renderKPIs(dashboardData.summary);
        renderKPISparklines(dashboardData.projects);
        renderTagAnalysis(dashboardData.tag_buckets, dashboardData.tag_gp_ranks);
        populateFilters(dashboardData.projects);
        
        applyFilters();
        
        document.getElementById('lastUpdated').textContent = formatDateTime(dashboardData.fetched_at);
        
        loadingEl.style.display = 'none';
        mainEl.style.display = 'block';
        
        // Execute routing logic once data is loaded to show the correct section immediately
        handleRouting();
    } catch (err) {
        console.error('Load error:', err);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'flex';
        document.getElementById('errorMessage').textContent = err.message;
    } finally {
        isLoadingState = false;
        if (refreshBtn) refreshBtn.disabled = false;
        if (dateFromInput) dateFromInput.disabled = false;
    }
}

// ===== Event Listeners =====
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    
    // Set up Hash Router
    addEventListener('hashchange', handleRouting);
    
    // Resize listener for sidebar sliding indicator
    addEventListener('resize', updateMenuIndicator);
    
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadDashboard(true);
    });
    
    document.getElementById('dateFrom').addEventListener('change', () => {
        loadDashboard(true);
    });
    
    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.getElementById('tagFilter').addEventListener('change', applyFilters);
    document.getElementById('stateFilter').addEventListener('change', applyFilters);
});
