import { state, applySavedUIState, saveUIState } from './assets/js/state.js';
import { debounce } from './assets/js/utils.js';
import { fetchDashboard } from './assets/js/api.js';
import { renderKPISparklines, renderGPChart, renderRevenueDoughnut } from './assets/js/charts.js';
import { renderKPIs, getDashboardMeta, renderScopeBar } from './assets/js/components/dashboard-kpi.js';
import { renderOperationalPanels, renderTagAnalysis, renderTagLeaderboard } from './assets/js/components/ops-panels.js';
import {
    renderProjectsTable,
    populateFilters,
    applyFilters,
    toggleSort,
    updateMultiSelectPanel,
    updateSelectAllState,
    applySorting
} from './assets/js/components/table.js';
import { DEFAULT_COMPANY, DEFAULT_DATE_FROM, ITEMS_PER_PAGE } from './assets/js/config.js';

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

    const offsetTop = activeRect.top - menuRect.top;
    const height = activeRect.height;

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
document.addEventListener('DOMContentLoaded', () => {
    applySavedUIState();
    loadDashboard();

    addEventListener('hashchange', handleRouting);
    addEventListener('resize', updateMenuIndicator);

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

    document.getElementById('companySelector')?.addEventListener('change', (event) => {
        state.company = event.target.value || DEFAULT_COMPANY;
        state.currentPage = 1;
        state.selectedProjects.clear();
        saveUIState();
        loadDashboard(false);
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
});
