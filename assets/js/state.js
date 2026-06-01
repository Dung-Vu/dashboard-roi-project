import { UI_STATE_KEY } from './config.js';
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
    pendingUIState: {}
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
        sortColumn: state.sortColumn,
        sortDirection: state.sortDirection,
        route: location.hash || '#/overview',
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
    state.sortColumn = state.pendingUIState.sortColumn || null;
    state.sortDirection = state.pendingUIState.sortDirection === 'desc' ? 'desc' : 'asc';
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
