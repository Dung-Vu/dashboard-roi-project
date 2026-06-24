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
    if (amount === null || amount === undefined || isNaN(amount)) return '0\u00a0₫';
    if (amount >= 1e9) {
        return (amount / 1e9).toFixed(1) + '\u00a0tỷ';
    }
    if (amount >= 1e6) {
        return (amount / 1e6).toFixed(1) + '\u00a0tr';
    }
    if (amount >= 1e3) {
        return (amount / 1e3).toFixed(1) + '\u00a0k';
    }
    return amount.toFixed(0) + '\u00a0₫';
}

export function formatFullVND(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '0\u00a0₫';
    return new Intl.NumberFormat('vi-VN').format(amount) + '\u00a0₫';
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
        overlay.className = 'loading-overlay';
        overlay.innerHTML = '<div class="spinner"></div><p class="loading-text">Đang tải dữ liệu...</p>';
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

export function isGPInInterval(gp_percent, intervalLabel) {
    if (gp_percent === null || gp_percent === undefined) return false;
    
    // Sử dụng Math.trunc để tương thích với logic int() của Python
    const valTrunc = Math.trunc(gp_percent);

    if (intervalLabel === "<0%") {
        return valTrunc < 0;
    }
    if (intervalLabel === "0-20%") {
        return valTrunc >= 0 && valTrunc <= 20;
    }
    if (intervalLabel === "21-40%") {
        return valTrunc >= 21 && valTrunc <= 40;
    }
    
    // So khớp dải dạng "X-Y%"
    const match = intervalLabel.match(/^(\d+)-(\d+)%$/);
    if (match) {
        const start = parseInt(match[1], 10);
        const end = parseInt(match[2], 10);
        return valTrunc >= start && valTrunc <= end;
    }
    return false;
}

export function showToast(message, type = 'success') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.style.cssText = 'position: fixed; bottom: 24px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; pointer-events: none;';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = 'padding: 12px 20px; border-radius: 8px; color: white; font-weight: 500; font-size: 0.88rem; box-shadow: 0 4px 12px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 8px; transform: translateY(20px); opacity: 0; transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: auto; backdrop-filter: blur(8px);';
    
    let icon = '<i class="fas fa-check-circle"></i>';
    let bg = 'rgba(16, 120, 80, 0.95)'; // var(--color-emerald)
    if (type === 'error') {
        icon = '<i class="fas fa-exclamation-circle"></i>';
        bg = 'rgba(234, 88, 12, 0.95)'; // Terracotta
    } else if (type === 'info') {
        icon = '<i class="fas fa-info-circle"></i>';
        bg = 'rgba(2, 132, 199, 0.95)'; // Slate Blue
    }
    
    toast.style.backgroundColor = bg;
    toast.innerHTML = `${icon}<span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
    }, 10);
    
    setTimeout(() => {
        toast.style.transform = 'translateY(-20px)';
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.remove();
            if (container.children.length === 0) {
                container.remove();
            }
        }, 300);
    }, 3500);
}

