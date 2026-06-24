import { DEFAULT_COMPANY, UI_STATE_KEY } from './config.js';
import { getElementValue } from './utils.js';

export const state = {
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
    gpRangeFilter: null,
    monthlyTrendChart: null,
    revenueTierFilter: null,
    stackedRevenueChart: null,
    tagCharts: null
};

export function loadUIState() {
    try {
        return JSON.parse(localStorage.getItem(UI_STATE_KEY) || '{}');
    } catch (err) {
        return {};
    }
}

export function saveUIState() {
    const saved = {
        dateFrom: getElementValue('dateFrom'),
        search: getElementValue('searchInput'),
        tag: getElementValue('tagFilter'),
        state: getElementValue('stateFilter'),
        health: getElementValue('healthFilter'),
        company: state.company, // Read directly from global state since custom select trigger doesn't have .value
        sortColumn: state.sortColumn,
        sortDirection: state.sortDirection,
        route: location.hash || '#/overview',
        gpRangeFilter: state.gpRangeFilter,
        revenueTierFilter: state.revenueTierFilter,
    };
    state.pendingUIState = saved;
    try {
        localStorage.setItem(UI_STATE_KEY, JSON.stringify(saved));
    } catch (err) {
        // Ignore private browsing or storage quota errors.
    }
}

export function applySavedUIState() {
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
    state.company = state.pendingUIState.company || DEFAULT_COMPANY;
    
    // Synchronize Custom Company Selector UI (Trigger text and modal options active class)
    const companyLabels = {
        'all': 'Tất cả công ty',
        'bonario': 'Bonario',
        'ordinaire': 'Ordinaire'
    };
    const selectedLabel = document.getElementById('selectedCompanyLabel');
    if (selectedLabel) {
        selectedLabel.textContent = companyLabels[state.company] || state.company;
    }
    document.querySelectorAll('.company-opt-btn').forEach(btn => {
        if (btn.dataset.value === state.company) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    state.sortColumn = state.pendingUIState.sortColumn || null;
    state.sortDirection = state.pendingUIState.sortDirection === 'desc' ? 'desc' : 'asc';
    state.gpRangeFilter = state.pendingUIState.gpRangeFilter || null;
    state.revenueTierFilter = state.pendingUIState.revenueTierFilter || null;
}

export function applyPendingFilterSelections() {
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
