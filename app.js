import { state, applySavedUIState, saveUIState } from './assets/js/state.js';
import { debounce, showToast, escapeHTML, formatFullVND } from './assets/js/utils.js';
import { fetchDashboard } from './assets/js/api.js';
import { renderKPISparklines, renderGPChart, renderRevenueDoughnut, renderMonthlyTrendChart, renderMonthlyShippingTrendChart } from './assets/js/charts.js';
import { renderKPIs } from './assets/js/components/dashboard-kpi.js';
import { renderOperationalPanels, renderTagAnalysis, renderTagLeaderboard } from './assets/js/components/ops-panels.js';
import {
    renderProjectsTable,
    populateFilters,
    applyFilters,
    toggleSort,
    updateMultiSelectPanel,
    updateSelectAllState,
    applySorting,
    translateCostLabel
} from './assets/js/components/table.js';

import { DEFAULT_COMPANY, DEFAULT_DATE_FROM, ITEMS_PER_PAGE, UI_STATE_KEY } from './assets/js/config.js';

// ===== SPA Router =====
function focusProjectInTable(projectId) {
    const projIdNum = parseInt(projectId, 10);
    if (isNaN(projIdNum)) return;

    // 1. Close the shipping detail modal if open
    const shippingDetailModal = document.getElementById('shippingDetailModal');
    if (shippingDetailModal) {
        shippingDetailModal.style.display = 'none';
    }

    // 2. Reset filters to make sure the project is visible
    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    if (searchInput) searchInput.value = '';
    if (tagFilter) tagFilter.value = '';
    if (stateFilter) stateFilter.value = '';
    if (healthFilter) healthFilter.value = '';

    state.gpRangeFilter = null;
    state.revenueTierFilter = null;
    document.querySelectorAll('.gp-filter-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tier-filter-btn').forEach(btn => btn.classList.remove('active'));

    // 3. Re-apply filters to refresh state.filteredProjects
    applyFilters();

    // 4. Find the project in the filtered list
    const index = state.filteredProjects.findIndex(p => p.project_id === projIdNum);
    if (index !== -1) {
        // Go to the correct page
        const page = Math.floor(index / ITEMS_PER_PAGE) + 1;
        state.currentPage = page;
        renderProjectsTable(state.filteredProjects);

        // 5. Highlight and expand row
        setTimeout(() => {
            const row = document.querySelector(`.cost-expand-btn[data-project-id="${projIdNum}"]`)?.closest('tr');
            if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.style.transition = 'background-color 0.5s';
                row.style.backgroundColor = 'rgba(16, 120, 80, 0.15)';
                setTimeout(() => {
                    row.style.backgroundColor = '';
                }, 3000);

                const breakdownRow = document.querySelector(`tr[data-breakdown-for="${projIdNum}"]`);
                const expandBtn = row.querySelector('.cost-expand-btn');
                if (breakdownRow && expandBtn) {
                    const isVisible = breakdownRow.style.display !== 'none';
                    if (!isVisible) {
                        breakdownRow.style.display = 'table-row';
                        const icon = expandBtn.querySelector('i');
                        if (icon) icon.style.transform = 'rotate(90deg)';
                        expandBtn.style.background = 'rgba(16, 120, 80, 0.1)';
                        fetchAndRenderCostDetails(projIdNum);
                    }
                }
            }
        }, 150);
    }
}

function handleRouting() {
    const hash = location.hash || '#/overview';
    const routeMap = {
        '#/overview': 'overview-route',
        '#/tags': 'tags-route',
        '#/projects': 'projects-route',
        '#/ranks': 'ranks-route'
    };

    let matchedRoute = routeMap[hash];
    let projectId = null;

    if (!matchedRoute && hash.startsWith('#/project/')) {
        projectId = parseInt(hash.replace('#/project/', ''), 10);
        if (!isNaN(projectId)) {
            matchedRoute = 'projects-route';
        }
    }

    if (location.hash && !matchedRoute) {
        location.hash = '#/overview';
        return;
    }

    const activeSectionId = matchedRoute || 'overview-route';

    document.querySelectorAll('.route-view').forEach(view => {
        view.classList.remove('active');
    });

    const activeView = document.getElementById(activeSectionId);
    if (activeView) {
        activeView.classList.add('active');
    }

    document.querySelectorAll('.sidebar-menu .menu-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href === hash || (hash === '#/overview' && href === '#/overview') || (projectId && href === '#/projects')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Systematically destroy all Chart.js instances on any hash routing change
    if (state.gpChart) {
        state.gpChart.destroy();
        state.gpChart = null;
    }
    if (state.revenueDoughnutChart) {
        state.revenueDoughnutChart.destroy();
        state.revenueDoughnutChart = null;
    }
    if (state.monthlyTrendChart) {
        state.monthlyTrendChart.destroy();
        state.monthlyTrendChart = null;
    }
    if (state.monthlyShippingTrendChart) {
        state.monthlyShippingTrendChart.destroy();
        state.monthlyShippingTrendChart = null;
    }
    if (state.stackedRevenueChart) {
        state.stackedRevenueChart.destroy();
        state.stackedRevenueChart = null;
    }
    if (state.tagCharts) {
        Object.keys(state.tagCharts).forEach(tag => {
            if (state.tagCharts[tag]) {
                state.tagCharts[tag].destroy();
            }
        });
        state.tagCharts = null;
    }

    if (hash === '#/tags' && state.dashboardData) {
        renderTagAnalysis(state.dashboardData.tag_buckets, state.dashboardData.tag_gp_ranks);
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
        if (!state.monthlyTrendChart) {
            renderMonthlyTrendChart(state.dashboardData.projects);
        } else {
            state.monthlyTrendChart.resize();
        }
        if (!state.monthlyShippingTrendChart) {
            renderMonthlyShippingTrendChart(state.dashboardData.projects);
        } else {
            state.monthlyShippingTrendChart.resize();
        }
        renderTagLeaderboard(state.dashboardData.tag_buckets);
    }

    if (projectId && state.dashboardData) {
        focusProjectInTable(projectId);
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
    if (state.currentAbortController) {
        state.currentAbortController.abort();
    }
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
        const selectedCompany = state.company || DEFAULT_COMPANY;
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
        if (state.monthlyTrendChart) {
            state.monthlyTrendChart.destroy();
            state.monthlyTrendChart = null;
        }
        if (state.monthlyShippingTrendChart) {
            state.monthlyShippingTrendChart.destroy();
            state.monthlyShippingTrendChart = null;
        }
        if (state.stackedRevenueChart) {
            state.stackedRevenueChart.destroy();
            state.stackedRevenueChart = null;
        }
        if (state.tagCharts) {
            Object.keys(state.tagCharts).forEach(tag => {
                if (state.tagCharts[tag]) {
                    state.tagCharts[tag].destroy();
                }
            });
            state.tagCharts = null;
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
        state.lastSyncTime = state.dashboardData.fetched_at;

        if (loadingEl) loadingEl.style.display = 'none';
        if (mainEl) mainEl.style.display = 'block';

        const overlay = document.getElementById('refreshOverlay');
        if (overlay) overlay.style.display = 'none';

        handleRouting();
    } catch (err) {
        console.error('Load error:', err);
        const overlay = document.getElementById('refreshOverlay');
        if (overlay) overlay.style.display = 'none';
        if (err.message && err.message.includes('HTTP 401')) {
            showLogin();
            return;
        }
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

let syncFailures = 0;
let incrementalSyncTimer = null;
let lastUserActivityTime = Date.now();
let currentSyncInterval = 10000;
const INACTIVE_TIMEOUT = 180000;
const ACTIVE_INTERVAL = 10000;
const IDLE_INTERVAL = 60000;

async function runIncrementalSync() {
    if (!state.dashboardData || !state.lastSyncTime || state.isLoadingState) return;
    if (document.querySelector('#projectsTable .inline-edit-input')) return;

    try {
        const lastSync = state.lastSyncTime;
        const company = state.company || DEFAULT_COMPANY;
        const dateFrom = document.getElementById('dateFrom')?.value || DEFAULT_DATE_FROM;

        const res = await fetch(`/api/projects-dashboard/delta?last_sync=${encodeURIComponent(lastSync)}&company=${encodeURIComponent(company)}&date_from=${encodeURIComponent(dateFrom)}`);
        if (res.status === 401) {
            console.warn("Session expired. Redirecting to login.");
            showLogin();
            return;
        }
        const data = await res.json();

        // Reset failures and hide warning on success
        syncFailures = 0;
        const indicator = document.getElementById('syncStatusIndicator');
        if (indicator) indicator.style.display = 'none';

        if (data.ok && data.updated_projects && data.updated_projects.length > 0) {

            
            let hasChanges = false;
            data.updated_projects.forEach(updatedProj => {
                const idx = state.dashboardData.projects.findIndex(p => p.project_id === updatedProj.project_id);
                if (idx !== -1) {
                    const existing = state.dashboardData.projects[idx];
                    if (
                        existing.x_studio_giai_trinh !== updatedProj.x_studio_giai_trinh ||
                        existing.order_state !== updatedProj.order_state ||
                        JSON.stringify(existing.tags) !== JSON.stringify(updatedProj.tags) ||
                        existing.bg_untaxed !== updatedProj.bg_untaxed ||
                        existing.adjusted_expected_cost !== updatedProj.adjusted_expected_cost
                    ) {
                        state.dashboardData.projects[idx] = updatedProj;
                        hasChanges = true;
                    }
                } else {
                    state.dashboardData.projects.push(updatedProj);
                    hasChanges = true;
                }
            });

            if (hasChanges) {
                if (data.summary && Object.keys(data.summary).length > 0) state.dashboardData.summary = data.summary;
                if (data.tag_buckets && Object.keys(data.tag_buckets).length > 0) state.dashboardData.tag_buckets = data.tag_buckets;
                if (data.tag_gp_ranks && Object.keys(data.tag_gp_ranks).length > 0) state.dashboardData.tag_gp_ranks = data.tag_gp_ranks;
                if (data.meta && Object.keys(data.meta).length > 0) state.dashboardData.meta = data.meta;

                renderKPIs(state.dashboardData.summary);
                renderKPISparklines(state.dashboardData.projects);
                renderOperationalPanels();
                renderTagAnalysis(state.dashboardData.tag_buckets, state.dashboardData.tag_gp_ranks);

                const hash = location.hash || '#/overview';
                if (hash === '#/ranks') {
                    if (state.gpChart) state.gpChart.destroy();
                    if (state.revenueDoughnutChart) state.revenueDoughnutChart.destroy();
                    if (state.monthlyTrendChart) state.monthlyTrendChart.destroy();
                    if (state.monthlyShippingTrendChart) state.monthlyShippingTrendChart.destroy();
                    
                    renderGPChart(state.dashboardData.tag_gp_ranks);
                    renderRevenueDoughnut(state.dashboardData.tag_buckets);
                    renderMonthlyTrendChart(state.dashboardData.projects);
                    renderMonthlyShippingTrendChart(state.dashboardData.projects);
                    renderTagLeaderboard(state.dashboardData.tag_buckets);
                } else if (hash === '#/tags') {
                    if (state.stackedRevenueChart) {
                        state.stackedRevenueChart.destroy();
                        state.stackedRevenueChart = null;
                    }
                    if (state.tagCharts) {
                        Object.keys(state.tagCharts).forEach(tag => {
                            if (state.tagCharts[tag]) {
                                state.tagCharts[tag].destroy();
                            }
                        });
                        state.tagCharts = null;
                    }
                    renderTagAnalysis(state.dashboardData.tag_buckets, state.dashboardData.tag_gp_ranks);
                }

                applyFilters();


                showToast(`Đã đồng bộ thời gian thực ${data.updated_projects.length} dự án thay đổi từ Odoo`);
            }
        }

        if (data.sync_time) {
            state.lastSyncTime = data.sync_time;
        }
    } catch (err) {
        syncFailures++;
        console.error(`Failed to run incremental sync (attempt ${syncFailures}):`, err);
        if (syncFailures >= 3) {
            const indicator = document.getElementById('syncStatusIndicator');
            if (indicator) indicator.style.display = 'inline-flex';
        }
    }
}

function scheduleNextSync() {
    if (incrementalSyncTimer) {
        clearTimeout(incrementalSyncTimer);
    }

    const timeSinceLastActivity = Date.now() - lastUserActivityTime;
    const isTabHidden = document.hidden;
    const isIdle = timeSinceLastActivity > INACTIVE_TIMEOUT || isTabHidden;

    currentSyncInterval = isIdle ? IDLE_INTERVAL : ACTIVE_INTERVAL;

    incrementalSyncTimer = setTimeout(async () => {
        await runIncrementalSync();
        scheduleNextSync();
    }, currentSyncInterval);
}

function recordUserActivity() {
    const wasIdle = currentSyncInterval === IDLE_INTERVAL;
    lastUserActivityTime = Date.now();
    if (wasIdle) {

        scheduleNextSync();
    }
}

function startIncrementalSync() {
    ['mousemove', 'keydown', 'click', 'scroll'].forEach(evt => {
        document.removeEventListener(evt, recordUserActivity);
        document.addEventListener(evt, recordUserActivity, { passive: true });
    });

    document.removeEventListener('visibilitychange', scheduleNextSync);
    document.addEventListener('visibilitychange', scheduleNextSync);

    scheduleNextSync();
}

function showLogin() {
    const loginContainer = document.getElementById('loginContainer');
    const appLayout = document.querySelector('.app-layout');
    if (loginContainer) loginContainer.style.display = 'flex';
    if (appLayout) appLayout.style.display = 'none';
}

function initApp() {
    const loginContainer = document.getElementById('loginContainer');
    const appLayout = document.querySelector('.app-layout');
    if (loginContainer) loginContainer.style.display = 'none';
    if (appLayout) appLayout.style.display = 'flex';
    loadDashboard();
    startIncrementalSync();
}

// Cache for detailed project cost details
const projectDetailsCache = new Map();

async function fetchAndRenderCostDetails(projectId) {
    const projIdNum = parseInt(projectId, 10);
    if (isNaN(projIdNum)) return;

    const loadingEl = document.getElementById(`cost-loading-${projIdNum}`);
    const errorEl = document.getElementById(`cost-error-${projIdNum}`);
    const tbody = document.getElementById(`aggregated-cost-tbody-${projIdNum}`);

    // Check frontend cache
    if (projectDetailsCache.has(projIdNum)) {
        const cached = projectDetailsCache.get(projIdNum);
        const project = (state.dashboardData?.projects || []).find(p => p.project_id === projIdNum);
        const nativeCost = project ? (project.native_expected_cost ?? 0) : 0;
        updateAggregatedCostTable(projIdNum, cached.customCostBreakdown || [], nativeCost);
        return;
    }

    if (loadingEl) loadingEl.style.display = 'inline';
    if (errorEl) errorEl.style.display = 'none';

    if (tbody) {
        tbody.innerHTML = `<tr class="cost-placeholder-row">
            <td colspan="4" style="text-align:center;padding:1.5rem;color:var(--color-text-secondary);">
                <i class="fas fa-spinner fa-spin" style="margin-right:8px;color:var(--color-emerald);"></i>Đang tải dữ liệu chi tiết từ Odoo...
            </td>
        </tr>`;
    }

    try {
        const response = await fetch(`/api/dashboard?project_id=${projIdNum}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();
        const costSources = data.cost_sources || [];

        // Save in cache
        projectDetailsCache.set(projIdNum, {
            costSources: costSources,
            customCostBreakdown: data.custom_cost_breakdown || []
        });

        const project = (state.dashboardData?.projects || []).find(p => p.project_id === projIdNum);
        const nativeCost = project ? (project.native_expected_cost ?? 0) : 0;
        updateAggregatedCostTable(projIdNum, data.custom_cost_breakdown || [], nativeCost);
        if (loadingEl) loadingEl.style.display = 'none';
    } catch (err) {
        console.error('Lỗi khi tải chi tiết chi phí:', err);
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'inline';
        if (tbody) {
            tbody.innerHTML = `<tr class="cost-error-row">
                <td colspan="4" style="text-align:center;padding:1.5rem;color:#dc2626;">
                    <i class="fas fa-exclamation-triangle" style="margin-right:8px;"></i>Lỗi khi tải dữ liệu từ Odoo. Vui lòng bấm thử lại.
                </td>
            </tr>`;
        }
    }
}

function renderCostDetailsHTML(container, costSources) {
    // Stub function to maintain compatibility with integrity tests
}

function updateAggregatedCostTable(projectId, customCostBreakdown, nativeCost) {
    const tbody = document.getElementById(`aggregated-cost-tbody-${projectId}`);
    if (!tbody) return;

    if (!customCostBreakdown || customCostBreakdown.length === 0) {
        tbody.innerHTML = `<tr class="cost-empty-row">
            <td colspan="4" style="text-align:center;padding:1.5rem;color:var(--color-text-secondary);">
                Không có chi phí phát sinh cho dự án này.
            </td>
        </tr>`;
        return;
    }

    let html = '';
    let tBilled = 0, tCommit = 0, tExpected = 0;

    customCostBreakdown.forEach(item => {
        const b = item.billed ?? 0, c = item.open_commitment ?? 0, e = item.expected ?? 0;
        tBilled += b; tCommit += c; tExpected += e;
        const pct = nativeCost > 0 ? ((e / nativeCost) * 100).toFixed(1) : '0';
        const label = translateCostLabel(item.label || item.id);

        html += `<tr style="border-bottom:1px solid rgba(16,120,80,0.08);">
            <td style="padding:5px 8px;color:var(--color-text-primary);font-weight:500;"><div style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--color-emerald);opacity:0.6;"></span>${escapeHTML(label)}<span style="font-size:0.7rem;color:var(--color-text-secondary);font-weight:400;">(${pct}%)</span></div></td>
            <td style="text-align:right;padding:5px 8px;font-family:var(--font-heading);color:var(--color-text-secondary);">${formatFullVND(b)}</td>
            <td style="text-align:right;padding:5px 8px;font-family:var(--font-heading);color:${c > 0 ? '#d97706' : 'var(--color-text-secondary)'};">${formatFullVND(c)}</td>
            <td style="text-align:right;padding:5px 8px;font-family:var(--font-heading);font-weight:600;color:var(--color-text-primary);">${formatFullVND(e)}</td>
        </tr>`;
    });

    html += `<tr style="border-top:2px solid rgba(16,120,80,0.2);font-weight:700;">
        <td style="padding:6px 8px;color:var(--color-emerald);font-family:var(--font-heading);"><i class="fas fa-equals" style="font-size:0.65rem;margin-right:4px;"></i> TỔNG CHI PHÍ GỐC</td>
        <td style="text-align:right;padding:6px 8px;font-family:var(--font-heading);color:var(--color-text-primary);">${formatFullVND(tBilled)}</td>
        <td style="text-align:right;padding:6px 8px;font-family:var(--font-heading);color:${tCommit > 0 ? '#d97706' : 'var(--color-text-primary)'};">${formatFullVND(tCommit)}</td>
        <td style="text-align:right;padding:6px 8px;font-family:var(--font-heading);color:var(--color-emerald);font-size:0.95rem;">${formatFullVND(tExpected)}</td>
    </tr>`;

    tbody.innerHTML = html;
}

// ===== Event Listeners =====
document.addEventListener('DOMContentLoaded', async () => {
    applySavedUIState();

    
    // Check authentication status first
    try {
        const res = await fetch('/api/auth-status');
        const data = await res.json();
        if (data.authenticated) {
            initApp();
        } else {
            showLogin();
        }
    } catch (err) {
        console.error('Lỗi khi kiểm tra xác thực:', err);
        showLogin();
    }

    addEventListener('hashchange', handleRouting);
    addEventListener('resize', debounce(updateMenuIndicator, 150));

    document.getElementById('refreshBtn')?.addEventListener('click', () => {
        loadDashboard(true);
    });

    document.getElementById('retryBtn')?.addEventListener('click', () => {
        loadDashboard(true);
    });

    document.getElementById('dateFrom')?.addEventListener('change', () => {
        saveUIState();
        loadDashboard(true);
    });

    // Custom Company Selector Modal Controllers
    const companyModal = document.getElementById('companyModal');
    const companySelectTrigger = document.getElementById('companySelectTrigger');
    const closeCompanyModal = document.getElementById('closeCompanyModal');

    // Shipping Detail Modal Controllers
    const shippingDetailModal = document.getElementById('shippingDetailModal');
    const closeShippingDetailModal = document.getElementById('closeShippingDetailModal');

    closeShippingDetailModal?.addEventListener('click', () => {
        if (shippingDetailModal) {
            shippingDetailModal.style.display = 'none';
        }
    });

    shippingDetailModal?.addEventListener('click', (event) => {
        if (event.target === shippingDetailModal) {
            shippingDetailModal.style.display = 'none';
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            if (companyModal) companyModal.style.display = 'none';
            if (shippingDetailModal) shippingDetailModal.style.display = 'none';
        }
    });

    // 1. Open the Company Selection Modal
    companySelectTrigger?.addEventListener('click', () => {
        if (companyModal) {
            companyModal.style.display = 'flex';
        }
    });

    // 2. Close the Modal via Close button
    closeCompanyModal?.addEventListener('click', () => {
        if (companyModal) {
            companyModal.style.display = 'none';
        }
    });

    // 3. Close the Modal when clicking on the outside dark overlay background
    companyModal?.addEventListener('click', (event) => {
        if (event.target === companyModal) {
            companyModal.style.display = 'none';
        }
    });

    // 4. Handle clicking a Company option button inside the Modal
    document.querySelectorAll('.company-opt-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const value = btn.dataset.value || 'all';
            
            // Update global state company
            state.company = value;
            
            // Reset pagination and active selections
            state.currentPage = 1;
            state.selectedProjects.clear();

            // Sync the trigger button label and modal active button classes
            const companyLabels = {
                'all': 'Tất cả công ty',
                'bonario': 'Bonario',
                'ordinaire': 'Ordinaire'
            };
            const selectedLabel = document.getElementById('selectedCompanyLabel');
            if (selectedLabel) {
                selectedLabel.textContent = companyLabels[value] || value;
            }
            document.querySelectorAll('.company-opt-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.value === value);
            });

            // Close the modal
            if (companyModal) {
                companyModal.style.display = 'none';
            }

            // Save UI state and trigger dashboard reload
            saveUIState();
            loadDashboard(false);
        });
    });

    const debouncedApplyFilters = debounce(applyFilters, 300);
    document.getElementById('searchInput')?.addEventListener('input', debouncedApplyFilters);
    document.getElementById('tagFilter')?.addEventListener('change', applyFilters);
    document.getElementById('stateFilter')?.addEventListener('change', applyFilters);
    document.getElementById('healthFilter')?.addEventListener('change', applyFilters);

    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            if (column) toggleSort(column);
        });
    });

    // R3 Event Delegation for Checkbox changes inside projectsTable
    document.getElementById('projectsTable')?.addEventListener('change', (e) => {
        if (e.target && e.target.matches('input.project-checkbox')) {
            const projectId = parseInt(e.target.dataset.projectId);
            const tr = e.target.closest('tr');
            if (e.target.checked) {
                state.selectedProjects.add(projectId);
                tr?.classList.add('selected-row');
            } else {
                state.selectedProjects.delete(projectId);
                tr?.classList.remove('selected-row');
            }
            updateMultiSelectPanel();
            updateSelectAllState();
        }
    });

    // Select all checkbox handler
    document.getElementById('selectAll')?.addEventListener('change', (e) => {
        const startIdx = (state.currentPage - 1) * ITEMS_PER_PAGE;
        const endIdx = startIdx + ITEMS_PER_PAGE;
        const sortedProjects = applySorting(state.filteredProjects);
        const pageProjects = sortedProjects.slice(startIdx, endIdx);

        if (e.target.checked) {
            pageProjects.forEach(p => state.selectedProjects.add(p.project_id));
        } else {
            pageProjects.forEach(p => state.selectedProjects.delete(p.project_id));
        }
        document.querySelectorAll('.project-checkbox').forEach(cb => {
            const pid = parseInt(cb.dataset.projectId);
            cb.checked = state.selectedProjects.has(pid);
            cb.closest('tr')?.classList.toggle('selected-row', state.selectedProjects.has(pid));
        });
        updateMultiSelectPanel();
    });

    document.getElementById('clearSelection')?.addEventListener('click', () => {
        state.selectedProjects.clear();
        document.querySelectorAll('.project-checkbox').forEach(cb => {
            cb.checked = false;
            cb.closest('tr')?.classList.remove('selected-row');
        });
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        updateMultiSelectPanel();
    });

    // Inline Edit helper for Explanation (x_studio_giai_trinh) in projectsTable
    function triggerInlineEdit(cell) {
        if (!cell || cell.querySelector('.inline-edit-container')) return;

        const projectId = parseInt(cell.dataset.projectId);
        const project = (state.dashboardData?.projects || []).find(p => p.project_id === projectId);
        const currentVal = project ? (project.x_studio_giai_trinh || '') : '';

        const originalHTML = `
            <span class="giai-trinh-text" style="font-weight: 500; font-size: 0.85rem; line-height: 1.4; max-width: 75px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; color: var(--color-text-primary);">${escapeHTML(currentVal) || '-'}</span>
            <button class="btn-giai-trinh-edit" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--color-emerald); cursor: pointer; padding: 4px; display: flex; align-items: center; justify-content: center; border-radius: 4px; transition: all 0.2s;" title="Chỉnh sửa giải trình" onmouseover="this.style.background='rgba(16, 120, 80, 0.1)'" onmouseout="this.style.background='none'">
                <i class="fas fa-pencil-alt" style="font-size: 0.85rem;"></i>
            </button>
        `;

        cell.title = currentVal || '-';
        cell.innerHTML = `
            <div class="inline-edit-container" style="display: flex; flex-direction: column; gap: 0.5rem; width: 100%; min-width: 220px;" onclick="evt => evt.stopPropagation();">
                <textarea class="inline-edit-input" style="width: 100%; min-height: 80px; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--color-emerald); font-size: 0.85rem; background: rgba(255, 255, 255, 0.95); color: #1e293b; font-family: inherit; resize: vertical; line-height: 1.4;" placeholder="Nhập giải trình...">${escapeHTML(currentVal)}</textarea>
                <div class="inline-edit-actions" style="display: flex; gap: 0.5rem; justify-content: flex-end;">
                    <button class="btn-edit-cancel" style="padding: 4px 10px; font-size: 0.75rem; border-radius: 4px; background: #e2e8f0; color: #475569; border: none; cursor: pointer; font-weight: 500;">Hủy</button>
                    <button class="btn-edit-save" style="padding: 4px 10px; font-size: 0.75rem; border-radius: 4px; background: var(--color-emerald); color: white; border: none; cursor: pointer; font-weight: 500; display: flex; align-items: center; gap: 0.25rem;">Lưu</button>
                </div>
            </div>
        `;

        const textarea = cell.querySelector('.inline-edit-input');
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);

        textarea.addEventListener('dblclick', (evt) => evt.stopPropagation());
        textarea.addEventListener('click', (evt) => evt.stopPropagation());

        const cancelBtn = cell.querySelector('.btn-edit-cancel');
        const saveBtn = cell.querySelector('.btn-edit-save');

        cancelBtn.addEventListener('click', (evt) => {
            evt.stopPropagation();
            cell.innerHTML = originalHTML;
        });

        saveBtn.addEventListener('click', (evt) => {
            evt.stopPropagation();
            const newVal = textarea.value.trim();

            textarea.disabled = true;
            cancelBtn.disabled = true;
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span> Lưu</span>';

            fetch('/api/projects-dashboard/update-giai-trinh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: projectId, x_studio_giai_trinh: newVal })
            })
            .then(res => res.json())
            .then(data => {
                if (data.ok) {
                    if (project) {
                        project.x_studio_giai_trinh = newVal;
                    }
                    showToast("Cập nhật giải trình lên Odoo thành công");
                    cell.title = newVal || '-';
                    cell.innerHTML = `
                        <span class="giai-trinh-text" style="font-weight: 500; font-size: 0.85rem; line-height: 1.4; max-width: 75px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; color: var(--color-text-primary);">${escapeHTML(newVal) || '-'}</span>
                        <button class="btn-giai-trinh-edit" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--color-emerald); cursor: pointer; padding: 4px; display: flex; align-items: center; justify-content: center; border-radius: 4px; transition: all 0.2s;" title="Chỉnh sửa giải trình" onmouseover="this.style.background='rgba(16, 120, 80, 0.1)'" onmouseout="this.style.background='none'">
                            <i class="fas fa-pencil-alt" style="font-size: 0.85rem;"></i>
                        </button>
                    `;
                } else {
                    throw new Error("Không thể cập nhật");
                }
            })
            .catch(err => {
                showToast("Lỗi: " + err.message, "error");
                cell.innerHTML = originalHTML;
            });
        });
    }

    // Trigger edit via click on the Edit button
    document.getElementById('projectsTable')?.addEventListener('click', (e) => {
        // Cost breakdown expand/collapse
        const expandBtn = e.target.closest('.cost-expand-btn');
        if (expandBtn) {
            e.stopPropagation();
            const projectId = expandBtn.dataset.projectId;
            const breakdownRow = document.querySelector(`tr[data-breakdown-for="${projectId}"]`);
            const icon = expandBtn.querySelector('i');
            if (breakdownRow) {
                const isVisible = breakdownRow.style.display !== 'none';
                breakdownRow.style.display = isVisible ? 'none' : 'table-row';
                if (icon) icon.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(90deg)';
                expandBtn.style.background = isVisible ? 'none' : 'rgba(16, 120, 80, 0.1)';
                
                if (!isVisible) {
                    fetchAndRenderCostDetails(projectId);
                }
            }
            return;
        }
        // Edit giai trinh button
        const editBtn = e.target.closest('.btn-giai-trinh-edit');
        if (editBtn) {
            e.stopPropagation();
            const cell = editBtn.closest('td.giai-trinh-cell');
            triggerInlineEdit(cell);
        }
    });

    // Trigger edit via double-click on the cell container
    document.getElementById('projectsTable')?.addEventListener('dblclick', (e) => {
        const cell = e.target.closest('td.giai-trinh-cell');
        if (cell) {
            e.stopPropagation();
            triggerInlineEdit(cell);
        }
    });

    // Login Form Submit Handler
    document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const usernameInput = document.getElementById('loginUsername');
        const passwordInput = document.getElementById('loginPassword');
        const errorMsg = document.getElementById('loginErrorMessage');
        const submitBtn = e.target.querySelector('button[type="submit"]');

        if (!usernameInput || !passwordInput) return;

        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        if (errorMsg) errorMsg.style.display = 'none';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang đăng nhập...';
        }

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok && data.ok) {
                initApp();
            } else {
                if (errorMsg) {
                    errorMsg.querySelector('span').textContent = data.error || 'Sai tên đăng nhập hoặc mật khẩu';
                    errorMsg.style.display = 'flex';
                }
                passwordInput.value = '';
            }
        } catch (err) {
            if (errorMsg) {
                errorMsg.querySelector('span').textContent = 'Lỗi kết nối đến máy chủ';
                errorMsg.style.display = 'flex';
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Đăng nhập';
            }
        }
    });

    // Logout Button Click Handler
    document.getElementById('logoutBtn')?.addEventListener('click', async () => {
        try {
            await fetch('/api/logout', { method: 'POST' });
            state.dashboardData = null;
            state.selectedProjects.clear();
            localStorage.removeItem(UI_STATE_KEY);
            location.reload();
        } catch (err) {
            console.error('Lỗi khi đăng xuất:', err);
            location.reload();
        }
    });
});
