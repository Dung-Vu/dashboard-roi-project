import { API_BASE } from './config.js';
import { state } from './state.js';

export async function fetchDashboard(dateFrom, refresh = false) {
    if (state.currentAbortController) {
        state.currentAbortController.abort();
    }
    const controller = new AbortController();
    state.currentAbortController = controller;
    const { signal } = controller;

    const timeoutId = setTimeout(() => {
        controller.abort();
    }, 60000);

    const params = new URLSearchParams({ date_from: dateFrom });
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
            throw new Error('Yêu cầu bị hủy hoặc hết thời gian chờ (60s)');
        }
        throw err;
    }
}
