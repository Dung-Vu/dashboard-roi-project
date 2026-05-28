// ===== Configuration =====
const API_BASE = '';
const DEFAULT_DATE_FROM = '2026-01-01';

// ===== State =====
let dashboardData = null;
let filteredProjects = [];
let gpChart = null;

// ===== Utility Functions =====
function formatVND(amount) {
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + ' tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + ' tr';
    }
    return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
}

function formatFullVND(amount) {
    return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
}

function formatPercent(value) {
    if (value === null || value === undefined) return '-';
    return value.toFixed(1) + '%';
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
function renderKPIs(summary) {
    document.getElementById('totalProjects').textContent = summary.total_projects;
    document.getElementById('validProjects').textContent = 
        `${summary.valid_project_count} dự án hợp lệ`;
    document.getElementById('totalBG').textContent = formatVND(summary.total_bg_untaxed);
    document.getElementById('totalCost').textContent = formatVND(summary.total_native_expected_cost);
    document.getElementById('totalGP').textContent = formatVND(summary.total_gp_amount);
    document.getElementById('weightedGP').textContent = 
        `${formatPercent(summary.weighted_gp_percent)} weighted`;
}

function renderTagAnalysis(tagBuckets, tagGPRanks) {
    const container = document.getElementById('tagAnalysis');
    container.innerHTML = '';
    
    const tags = Object.keys(tagBuckets);
    tags.forEach(tag => {
        const buckets = tagBuckets[tag];
        const ranks = tagGPRanks[tag] || [];
        
        // Calculate totals
        let totalCount = 0;
        let totalBG = 0;
        Object.values(buckets).forEach(tier => {
            totalCount += tier.count;
            totalBG += tier.bg_untaxed;
        });
        
        const card = document.createElement('div');
        card.className = 'tag-card';
        card.innerHTML = `
            <div class="tag-card-header">
                <span class="tag-name">${tag}</span>
                <span class="tag-total">${totalCount} dự án · ${formatVND(totalBG)}</span>
            </div>
            <div class="tier-grid">
                ${renderTiers(buckets)}
            </div>
            ${ranks.length > 0 ? `
                <div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border);">
                    <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem;">
                        GP% phổ biến nhất
                    </div>
                    ${ranks.map(r => `
                        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.25rem;">
                            <span style="color: var(--text-secondary);">#${r.rank} ${r.range}</span>
                            <span style="color: var(--success);">${r.count} dự án</span>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        `;
        container.appendChild(card);
    });
}

function renderTiers(buckets) {
    const tierOrder = ['<10tr', '10-100tr', '100-200tr', '>200tr'];
    return tierOrder.map(tierName => {
        const tier = buckets[tierName] || { count: 0, bg_untaxed: 0, weighted_gp_percent: null };
        return `
            <div class="tier-item">
                <div class="tier-label">${tierName}</div>
                <div class="tier-value">${tier.count} dự án</div>
                <div class="tier-gp">${formatVND(tier.bg_untaxed)}</div>
                ${tier.weighted_gp_percent !== null 
                    ? `<div class="tier-gp">GP: ${formatPercent(tier.weighted_gp_percent)}</div>` 
                    : ''}
            </div>
        `;
    }).join('');
}

function renderGPChart(tagGPRanks) {
    const ctx = document.getElementById('gpChart').getContext('2d');
    
    if (gpChart) {
        gpChart.destroy();
    }
    
    const tags = Object.keys(tagGPRanks);
    const datasets = tags.map((tag, index) => {
        const ranks = tagGPRanks[tag] || [];
        const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'];
        return {
            label: tag,
            data: ranks.map(r => ({ x: r.range, y: r.count })),
            backgroundColor: colors[index % colors.length] + '80',
            borderColor: colors[index % colors.length],
            borderWidth: 2,
        };
    });
    
    // Collect all ranges
    const allRanges = new Set();
    Object.values(tagGPRanks).forEach(ranks => {
        ranks.forEach(r => allRanges.add(r.range));
    });
    const sortedRanges = Array.from(allRanges).sort((a, b) => {
        const aNum = parseInt(a.split('-')[0]);
        const bNum = parseInt(b.split('-')[0]);
        return aNum - bNum;
    });
    
    // Rebuild datasets with all ranges
    const finalDatasets = tags.map((tag, index) => {
        const ranks = tagGPRanks[tag] || [];
        const rankMap = {};
        ranks.forEach(r => { rankMap[r.range] = r.count; });
        const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'];
        return {
            label: tag,
            data: sortedRanges.map(range => rankMap[range] || 0),
            backgroundColor: colors[index % colors.length] + '80',
            borderColor: colors[index % colors.length],
            borderWidth: 2,
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
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: '#334155' }
                },
                y: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: '#334155' },
                    beginAtZero: true
                }
            }
        }
    });
}

function renderProjectsTable(projects) {
    const tbody = document.getElementById('projectsTable');
    tbody.innerHTML = '';
    
    projects.forEach(p => {
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
        }[p.order_state] || p.order_state || '-';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${p.sale_order_name || '-'}</strong></td>
            <td>${p.project_name || '-'}</td>
            <td>${p.customer || '-'}</td>
            <td>${(p.tags || []).map(t => `<span class="tag-badge">${t}</span>`).join('')}</td>
            <td><span class="state-badge ${stateClass}">${stateLabel}</span></td>
            <td class="text-right">${formatFullVND(p.bg_untaxed)}</td>
            <td class="text-right">${formatFullVND(p.native_expected_cost)}</td>
            <td class="text-right ${gpClass}">${formatFullVND(p.gp_amount)}</td>
            <td class="text-right ${gpClass}">${formatPercent(p.gp_percent)}</td>
        `;
        tbody.appendChild(tr);
    });
    
    document.getElementById('tableInfo').textContent = `Hiển thị ${projects.length} dự án`;
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
    
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
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
    
    renderProjectsTable(filteredProjects);
}

// ===== Main =====
async function loadDashboard(refresh = false) {
    const loadingEl = document.getElementById('loadingState');
    const errorEl = document.getElementById('errorState');
    const mainEl = document.getElementById('mainContent');
    
    loadingEl.style.display = 'flex';
    errorEl.style.display = 'none';
    mainEl.style.display = 'none';
    
    try {
        const dateFrom = document.getElementById('dateFrom').value || DEFAULT_DATE_FROM;
        dashboardData = await fetchDashboard(dateFrom, refresh);
        
        renderKPIs(dashboardData.summary);
        renderTagAnalysis(dashboardData.tag_buckets, dashboardData.tag_gp_ranks);
        renderGPChart(dashboardData.tag_gp_ranks);
        populateFilters(dashboardData.projects);
        
        filteredProjects = dashboardData.projects;
        renderProjectsTable(filteredProjects);
        
        document.getElementById('lastUpdated').textContent = formatDateTime(dashboardData.fetched_at);
        
        loadingEl.style.display = 'none';
        mainEl.style.display = 'block';
    } catch (err) {
        console.error('Load error:', err);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'flex';
        document.getElementById('errorMessage').textContent = err.message;
    }
}

// ===== Event Listeners =====
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    
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
