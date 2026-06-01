import { GP_HEALTH_HIGH, GP_HEALTH_MEDIUM } from './config.js';

export function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

export function formatVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0 ₫';
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + ' tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + ' tr';
    }
    if (amount >= 1e3) {
        return (amount / 1e3).toFixed(1) + ' k';
    }
    return amount.toFixed(0) + ' ₫';
}

export function formatFullVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0 ₫';
    return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
}

export function formatPercent(value) {
    if (value === null || value === undefined || isNaN(Number(value))) return '-';
    return Number(value).toFixed(1) + '%';
}

export function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('vi-VN');
}

export function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

export function getElementValue(id) {
    return document.getElementById(id)?.value || '';
}

export function getHealthBucket(project) {
    const gp = project?.gp_percent;
    if (gp === null || gp === undefined || Number.isNaN(Number(gp))) return 'missing';
    if (gp > GP_HEALTH_HIGH) return 'high';
    if (gp >= GP_HEALTH_MEDIUM) return 'medium';
    return 'low';
}

export function showLoadingOverlay() {
    let overlay = document.getElementById('refreshOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'refreshOverlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(255,255,255,0.75);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(2px);';
        overlay.innerHTML = '<div style="text-align:center;"><div style="width:48px;height:48px;border:4px solid #107850;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px;"></div><p style="font-family:var(--font-heading);font-weight:600;color:#0c2317;">Đang tải dữ liệu...</p></div>';
        const styleEl = document.createElement('style');
        styleEl.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
        document.head.appendChild(styleEl);
        document.body.appendChild(overlay);
    } else {
        overlay.style.display = 'flex';
    }
}

export function hideLoadingOverlay() {
    const overlay = document.getElementById('refreshOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

export function scrollToTableTop() {
    const table = document.getElementById('projectsTable');
    if (table) {
        table.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}
