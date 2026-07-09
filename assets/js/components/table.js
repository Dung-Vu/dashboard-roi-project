import { ITEMS_PER_PAGE, STATE_LABELS, GP_HEALTH_HIGH, GP_HEALTH_MEDIUM } from '../config.js';
import { escapeHTML, formatPercent, formatFullVND, formatVND, getHealthBucket, scrollToTableTop, isGPInInterval, normalizeText } from '../utils.js';
import { state, saveUIState, applyPendingFilterSelections } from '../state.js';

export function getSortValue(project, columnKey) {
    const val = project[columnKey];
    if (val === null || val === undefined) return '';
    if (typeof val === 'number') return val;
    return String(val).toLowerCase();
}

const _COST_LABEL_MAP = {
    'purchase_order': 'Đơn mua hàng',
    'manufacturing_order': 'Lệnh sản xuất',
    'cost_of_goods_sold': 'Giá vốn hàng bán',
    'employee': 'Nhân công',
    'timesheet': 'Bảng chấm công',
    'timesheets': 'Bảng chấm công',
    'expense': 'Chi phí',
    'expenses': 'Chi phí',
    'vendor_bill': 'Hóa đơn nhà cung cấp',
    'vendor_bills': 'Hóa đơn nhà cung cấp',
    'subcontracting': 'Gia công phụ',
    'other': 'Chi phí khác',
    'billable_fixed': 'Dịch vụ cố định',
    'billable_time': 'Dịch vụ theo giờ',
    'billable_milestones': 'Dịch vụ theo mốc',
    'non_billable': 'Không tính phí',
    'downpayment': 'Tạm ứng',
    'stock_move': 'Xuất kho',
    'shipping_cost': 'Phí vận chuyển (SC Logistics)',
    'other_expense': 'Chi phí khác',
};

export function translateCostLabel(rawLabel) {
    if (!rawLabel) return 'Khác';
    const key = rawLabel.toLowerCase().replace(/\s+/g, '_');
    return _COST_LABEL_MAP[key] || _COST_LABEL_MAP[rawLabel] || rawLabel;
}

export function applySorting(projects) {
    if (!state.sortColumn) return projects;
    const sorted = [...projects];
    sorted.sort((a, b) => {
        const aVal = getSortValue(a, state.sortColumn);
        const bVal = getSortValue(b, state.sortColumn);
        let cmp = 0;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            cmp = aVal - bVal;
        } else {
            cmp = String(aVal).localeCompare(String(bVal), 'vi');
        }
        return state.sortDirection === 'asc' ? cmp : -cmp;
    });
    return sorted;
}

export function toggleSort(columnKey) {
    if (state.sortColumn === columnKey) {
        state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortColumn = columnKey;
        state.sortDirection = 'asc';
    }
    saveUIState();
    renderProjectsTable(state.filteredProjects);
}

export function updateSortIndicators() {
    document.querySelectorAll('th[data-sort]').forEach(th => {
        const key = th.getAttribute('data-sort');
        th.classList.remove('sort-asc', 'sort-desc');
        if (key === state.sortColumn) {
            th.classList.add(state.sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

export function exportCSV() {
    if (!state.filteredProjects || state.filteredProjects.length === 0) return;

    const headers = ['Đơn hàng', 'Khách hàng', 'Tags', 'Trạng thái', 'Doanh thu', 'Chi phí', 'Chi phí gốc', 'GP', 'GP%', 'Giải trình'];
    const rows = applySorting(state.filteredProjects).map(p => [
        p.sale_order_name || '',
        p.customer || '',
        (p.tags || []).join('; '),
        STATE_LABELS[p.order_state] || p.order_state || '',
        p.bg_untaxed,
        p.adjusted_expected_cost ?? p.native_expected_cost,
        p.native_expected_cost,
        p.gp_amount,
        p.gp_percent !== null && p.gp_percent !== undefined ? p.gp_percent.toFixed(1) + '%' : '',
        p.x_studio_giai_trinh || '',
    ]);

    const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\r\n');

    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `du-an-roi-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

export function renderExportButton() {
    const tableInfo = document.getElementById('tableInfo');
    if (!tableInfo) return;
    let exportBtn = document.getElementById('exportCsvBtn');
    if (!exportBtn) {
        exportBtn = document.createElement('button');
        exportBtn.id = 'exportCsvBtn';
        exportBtn.innerHTML = '<i class="fas fa-download" aria-hidden="true"></i><span>Xuất CSV</span>';
        exportBtn.className = 'btn btn-export compact';
        exportBtn.addEventListener('click', exportCSV);
        tableInfo.parentElement.insertBefore(exportBtn, tableInfo.nextSibling);
    }
}

export function updateFilterIndicators() {
    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    const searchTerm = searchInput ? searchInput.value.trim() : '';
    const tagVal = tagFilter ? tagFilter.value : '';
    const stateVal = stateFilter ? stateFilter.value : '';
    const healthVal = healthFilter ? healthFilter.value : '';

    const hasActiveFilters = searchTerm || tagVal || stateVal || healthVal || state.gpRangeFilter || state.revenueTierFilter;

    let clearBtn = document.getElementById('clearFiltersBtn');
    if (!clearBtn) {
        clearBtn = document.createElement('button');
        clearBtn.id = 'clearFiltersBtn';
        clearBtn.className = 'clear-filters-btn';
        clearBtn.addEventListener('click', clearFilters);
        const filterContainer = document.querySelector('.table-filters-box');
        if (filterContainer) {
            filterContainer.appendChild(clearBtn);
        }
    }
    
    if (state.gpRangeFilter && state.revenueTierFilter) {
        clearBtn.innerHTML = `✕ Xóa bộ lọc (${state.gpRangeFilter} & Phân khúc ${state.revenueTierFilter})`;
    } else if (state.gpRangeFilter) {
        clearBtn.innerHTML = `✕ Xóa bộ lọc (${state.gpRangeFilter})`;
    } else if (state.revenueTierFilter) {
        clearBtn.innerHTML = `✕ Xóa bộ lọc (Phân khúc ${state.revenueTierFilter})`;
    } else {
        clearBtn.textContent = '✕ Xóa bộ lọc';
    }
    
    clearBtn.style.display = hasActiveFilters ? 'inline-block' : 'none';
}

export function clearFilters() {
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

    applyFilters();
}

export function renderProjectsTable(projects) {
    const tbody = document.getElementById('projectsTable');
    if (!tbody) return;
    tbody.innerHTML = '';

    const sortedProjects = applySorting(projects);

    if (sortedProjects.length === 0) {
        const emptyTr = document.createElement('tr');
        emptyTr.innerHTML = `
            <td colspan="10" style="text-align:center;padding:5rem 2rem;color:var(--color-text-secondary);">
                <div style="margin-bottom:1.25rem; display:inline-block; position:relative;">
                    <i class="far fa-folder-open" style="font-size:3.5rem;color:var(--color-mint);filter:drop-shadow(0 0 12px var(--color-mint-glow));"></i>
                </div>
                <h3 style="font-family:var(--font-heading);font-weight:700;font-size:1.15rem;color:var(--color-text-primary);margin:0 0 0.5rem 0;">Không tìm thấy dự án nào</h3>
                <p style="font-size:0.875rem;opacity:0.8;margin:0 auto;max-width:320px;line-height:1.5;">Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm để khám phá dữ liệu khác.</p>
            </td>
        `;
        tbody.appendChild(emptyTr);
        const tableInfo = document.getElementById('tableInfo');
        if (tableInfo) tableInfo.textContent = 'Hiển thị 0-0 / 0 dự án';
        renderPagination(0);
        updateSortIndicators();
        return;
    }

    const totalPages = Math.max(1, Math.ceil(sortedProjects.length / ITEMS_PER_PAGE));
    if (state.currentPage > totalPages) state.currentPage = totalPages;
    const startIdx = (state.currentPage - 1) * ITEMS_PER_PAGE;
    const pageProjects = sortedProjects.slice(startIdx, startIdx + ITEMS_PER_PAGE);

    const fragment = document.createDocumentFragment();

    pageProjects.forEach(p => {
        const gpClass = p.gp_percent !== null && p.gp_percent >= 0 ? 'gp-positive' : 'gp-negative';
        const stateClass = p.order_state === 'Done' ? 'done' :
                          p.order_state === 'In progress' ? 'progress' : 'pending';
        const stateLabel = STATE_LABELS[p.order_state] || escapeHTML(p.order_state) || '-';
        const adjustedCost = p.adjusted_expected_cost ?? p.native_expected_cost;
        const hasBreakdown = (p.cost_breakdown || []).length > 0;

        let healthBadgeHTML = '';
        if (p.gp_percent === null || p.gp_percent === undefined || Number.isNaN(Number(p.gp_percent))) {
            healthBadgeHTML = '<span style="color: var(--color-text-secondary); opacity: 0.5;">-</span>';
        } else {
            let healthClass = 'health-coral';
            if (p.gp_percent > GP_HEALTH_HIGH) {
                healthClass = 'health-green';
            } else if (p.gp_percent >= GP_HEALTH_MEDIUM) {
                healthClass = 'health-amber';
            }
            healthBadgeHTML = `
                <span class="health-orb-badge ${healthClass}">
                    <span class="orb-dot"></span>
                    ${formatPercent(p.gp_percent)}
                </span>
            `;
        }

        const odooUrl = state.dashboardData?.meta?.odoo_url;
        let saleOrderHTML = '';
        const parsedId = p.sale_order_id ? Number(p.sale_order_id) : NaN;
        if (!isNaN(parsedId)) {
            if (odooUrl) {
                saleOrderHTML = `<a href="${escapeHTML(odooUrl)}/web#id=${parsedId}&model=sale.order&view_type=form" target="_blank" rel="noopener noreferrer" class="odoo-link">${escapeHTML(p.sale_order_name) || '-'}</a>`;
            } else {
                saleOrderHTML = `<a href="/api/redirect/sale-order/${parsedId}" target="_blank" rel="noopener noreferrer" class="odoo-link">${escapeHTML(p.sale_order_name) || '-'}</a>`;
            }
        } else {
            saleOrderHTML = `<strong style="color: var(--color-emerald); font-family: var(--font-heading); font-size: 0.88rem;">${escapeHTML(p.sale_order_name) || '-'}</strong>`;
        }

        const tr = document.createElement('tr');
        tr.className = 'fade-in-up';
        const indexOnPage = pageProjects.indexOf(p);
        tr.style.animationDelay = `${indexOnPage * 0.025}s`;

        const isSelected = state.selectedProjects.has(p.project_id);
        const expandIcon = hasBreakdown
            ? `<button class="cost-expand-btn" data-project-id="${p.project_id}" style="background:none;border:none;cursor:pointer;color:var(--color-emerald);padding:2px 6px;border-radius:4px;transition:all 0.2s;display:inline-flex;align-items:center;font-size:0.75rem;" title="Xem chi tiết chi phí"><i class="fas fa-chevron-right" style="font-size:0.6rem;transition:transform 0.2s;"></i></button>`
            : '';
        tr.innerHTML = `
            <td style="text-align: center;"><input type="checkbox" class="project-checkbox" data-project-id="${p.project_id}" ${isSelected ? 'checked' : ''}></td>
            <td>${saleOrderHTML}</td>
            <td style="color: var(--color-text-secondary); font-weight: 500; max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHTML(p.customer) || '-'}">${escapeHTML(p.customer) || '-'}</td>
            <td><div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">${(p.tags || []).map(t => `<span class="tag-badge">${escapeHTML(t)}</span>`).join('')}</div></td>
            <td><span class="state-badge ${stateClass}">${stateLabel}</span></td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 700; color: var(--color-text-primary);">${formatFullVND(p.bg_untaxed)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-weight: 600; color: var(--color-text-secondary);">
                <div style="display:flex;align-items:center;justify-content:flex-end;gap:4px;">
                    ${expandIcon}
                    <span>${formatFullVND(adjustedCost)}</span>
                </div>
            </td>
            <td class="text-right ${gpClass}" style="font-family: var(--font-heading); font-weight: 700;">${formatFullVND(p.gp_amount)}</td>
            <td class="text-right" style="font-family: var(--font-heading); font-size: 0.825rem; vertical-align: middle;">${healthBadgeHTML}</td>
            <td class="giai-trinh-cell" data-project-id="${p.project_id}" style="position: relative; padding-right: 36px;" title="${escapeHTML(p.x_studio_giai_trinh) || '-'}">
                <span class="giai-trinh-text" style="font-weight: 500; font-size: 0.85rem; line-height: 1.4; max-width: 75px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; color: var(--color-text-primary);">${escapeHTML(p.x_studio_giai_trinh) || '-'}</span>
                <button class="btn-giai-trinh-edit" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--color-emerald); cursor: pointer; padding: 4px; display: flex; align-items: center; justify-content: center; border-radius: 4px; transition: all 0.2s;" title="Chỉnh sửa giải trình" onmouseover="this.style.background='rgba(16, 120, 80, 0.1)'" onmouseout="this.style.background='none'">
                    <i class="fas fa-pencil-alt" style="font-size: 0.85rem;"></i>
                </button>
            </td>
        `;
        if (isSelected) tr.classList.add('selected-row');
        fragment.appendChild(tr);

        // Cost breakdown detail row (hidden by default)
        if (hasBreakdown) {
            const detailTr = document.createElement('tr');
            detailTr.className = 'cost-breakdown-row';
            detailTr.dataset.breakdownFor = p.project_id;
            detailTr.style.display = 'none';
            const nativeCost = p.native_expected_cost ?? 0;
            let bHTML = `<td colspan="10" style="padding: 0 1rem 1rem 3.5rem; background: rgba(16, 120, 80, 0.03); border-left: 3px solid var(--color-emerald);">
                <div style="padding: 0.75rem 0 0.25rem 0;">
                    <div style="font-size: 0.78rem; font-weight: 700; color: var(--color-emerald); margin-bottom: 0.5rem; font-family: var(--font-heading); display:flex; align-items:center; gap:6px;">
                        <i class="fas fa-layer-group" style="font-size:0.7rem;"></i>
                        Cấu thành chi phí — ${escapeHTML(p.sale_order_name)}
                        <span id="cost-loading-${p.project_id}" style="display:none; font-weight: 400; color: var(--color-text-secondary); font-size: 0.72rem; margin-left: 8px;">
                            <i class="fas fa-spinner fa-spin" style="color: var(--color-emerald); font-size: 0.7rem;"></i> Đang cập nhật...
                        </span>
                        <span id="cost-error-${p.project_id}" style="display:none; font-weight: 400; color: #dc2626; font-size: 0.72rem; margin-left: 8px;">
                            <i class="fas fa-exclamation-triangle"></i> Lỗi kết nối Odoo
                        </span>
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
                        <thead><tr style="border-bottom: 1px solid rgba(16, 120, 80, 0.15);">
                            <th style="text-align:left;padding:6px 8px;font-weight:600;color:var(--color-text-secondary);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px;">Loại chi phí</th>
                            <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--color-text-secondary);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px;">Đã thanh toán</th>
                            <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--color-text-secondary);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px;">Chờ thanh toán</th>
                            <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--color-text-secondary);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px;">Tổng chi phí</th>
                        </tr></thead><tbody id="aggregated-cost-tbody-${p.project_id}">
                            <tr class="cost-placeholder-row">
                                <td colspan="4" style="text-align:center;padding:1.5rem;color:var(--color-text-secondary);">
                                    <i class="fas fa-spinner fa-spin" style="margin-right:8px;color:var(--color-emerald);"></i>Đang tải dữ liệu chi tiết từ Odoo...
                                </td>
                            </tr>
                        </tbody></table>
                    </div></td>`;
            detailTr.innerHTML = bHTML;
            fragment.appendChild(detailTr);
        }
    });

    tbody.appendChild(fragment);

    const start = sortedProjects.length > 0 ? startIdx + 1 : 0;
    const end = Math.min(startIdx + ITEMS_PER_PAGE, sortedProjects.length);
    const tableInfo = document.getElementById('tableInfo');
    if (tableInfo) tableInfo.textContent = `Hiển thị ${start}-${end} / ${sortedProjects.length} dự án`;
    renderPagination(sortedProjects.length);
    renderExportButton();
    updateSortIndicators();
    updateSelectAllState();
}

export function updateSelectAllState() {
    const selectAll = document.getElementById('selectAll');
    if (!selectAll) return;
    const checkboxes = document.querySelectorAll('.project-checkbox');
    const checkedCount = document.querySelectorAll('.project-checkbox:checked').length;
    selectAll.checked = checkboxes.length > 0 && checkedCount === checkboxes.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
}

export function updateMultiSelectPanel() {
    const panel = document.getElementById('multiSelectPanel');
    if (!panel) return;

    if (state.selectedProjects.size === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';

    const allProjects = state.dashboardData?.projects || [];
    const selected = allProjects.filter(p => state.selectedProjects.has(p.project_id));

    let totalBG = 0;
    let totalCost = 0;
    let totalGP = 0;
    let weightedGPSum = 0;
    let weightedGPCount = 0;

    selected.forEach(p => {
        totalBG += p.bg_untaxed || 0;
        totalCost += (p.adjusted_expected_cost ?? p.native_expected_cost) || 0;
        totalGP += p.gp_amount || 0;
        if (p.gp_percent !== null && p.gp_percent !== undefined && (p.bg_untaxed || 0) > 0) {
            weightedGPSum += p.gp_percent * p.bg_untaxed;
            weightedGPCount += p.bg_untaxed;
        }
    });

    const weightedGP = weightedGPCount > 0 ? (weightedGPSum / weightedGPCount).toFixed(1) : '-';

    const selCountEl = document.getElementById('selectedCount');
    const selBGEl = document.getElementById('selectedTotalBG');
    const selCostEl = document.getElementById('selectedTotalCost');
    const selGPEl = document.getElementById('selectedTotalGP');
    const selAvgGPEl = document.getElementById('selectedAvgGP');

    if (selCountEl) selCountEl.textContent = state.selectedProjects.size;
    if (selBGEl) selBGEl.textContent = formatFullVND(totalBG);
    if (selCostEl) selCostEl.textContent = formatFullVND(totalCost);
    if (selGPEl) selGPEl.textContent = formatFullVND(totalGP);
    if (selAvgGPEl) selAvgGPEl.textContent = weightedGP !== '-' ? weightedGP + '%' : '-';
}

export function renderPagination(totalItems) {
    const container = document.getElementById('pagination');
    if (!container) return;
    container.innerHTML = '';

    const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
    if (totalPages <= 1) return;

    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn' + (state.currentPage === 1 ? ' disabled' : '');
    prevBtn.innerHTML = '&laquo;';
    prevBtn.disabled = state.currentPage === 1;
    prevBtn.addEventListener('click', () => { if (state.currentPage > 1) { state.currentPage--; renderProjectsTable(state.filteredProjects); scrollToTableTop(); } });
    container.appendChild(prevBtn);

    const maxVisible = 5;
    let startPage = Math.max(1, state.currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) startPage = Math.max(1, endPage - maxVisible + 1);

    if (startPage > 1) {
        const firstBtn = document.createElement('button');
        firstBtn.className = 'page-btn';
        firstBtn.textContent = '1';
        firstBtn.addEventListener('click', () => { state.currentPage = 1; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
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
        btn.className = 'page-btn' + (i === state.currentPage ? ' active' : '');
        btn.textContent = i;
        btn.addEventListener('click', () => { state.currentPage = i; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
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
        lastBtn.addEventListener('click', () => { state.currentPage = totalPages; renderProjectsTable(state.filteredProjects); scrollToTableTop(); });
        container.appendChild(lastBtn);
    }

    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn' + (state.currentPage === totalPages ? ' disabled' : '');
    nextBtn.innerHTML = '&raquo;';
    nextBtn.disabled = state.currentPage === totalPages;
    nextBtn.addEventListener('click', () => { if (state.currentPage < totalPages) { state.currentPage++; renderProjectsTable(state.filteredProjects); scrollToTableTop(); } });
    container.appendChild(nextBtn);
}

export function populateFilters(projects) {
    const tagFilter = document.getElementById('tagFilter');
    if (!tagFilter) return;
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

    const stateFilter = document.getElementById('stateFilter');
    if (!stateFilter) return;
    const allStates = new Set();
    projects.forEach(p => {
        if (p.order_state) allStates.add(p.order_state);
    });

    stateFilter.innerHTML = '<option value="">Tất cả trạng thái</option>';
    Array.from(allStates).sort().forEach(orderState => {
        const opt = document.createElement('option');
        opt.value = orderState;
        opt.textContent = STATE_LABELS[orderState] || orderState;
        stateFilter.appendChild(opt);
    });
    applyPendingFilterSelections();
}

export function applyFilters() {
    if (!state.dashboardData) return;

    const searchInput = document.getElementById('searchInput');
    const tagFilter = document.getElementById('tagFilter');
    const stateFilter = document.getElementById('stateFilter');
    const healthFilter = document.getElementById('healthFilter');

    const searchTerm = searchInput ? normalizeText(searchInput.value) : '';
    const tagVal = tagFilter ? tagFilter.value : '';
    const stateVal = stateFilter ? stateFilter.value : '';
    const healthVal = healthFilter ? healthFilter.value : '';

    state.filteredProjects = state.dashboardData.projects.filter(p => {
        if (searchTerm) {
            const searchFields = normalizeText([
                p.sale_order_name,
                p.x_studio_giai_trinh,
                p.customer,
            ].filter(Boolean).join(' '));
            if (!searchFields.includes(searchTerm)) return false;
        }

        if (tagVal && !(p.tags || []).includes(tagVal)) return false;
        if (stateVal && p.order_state !== stateVal) return false;
        if (healthVal && getHealthBucket(p) !== healthVal) return false;

        if (state.gpRangeFilter) {
            if (!isGPInInterval(p.gp_percent, state.gpRangeFilter)) return false;
        }

        if (state.revenueTierFilter) {
            const amount = p.bg_untaxed || 0;
            let projectTier = '';
            if (amount < 10000000) projectTier = '<10tr';
            else if (amount < 100000000) projectTier = '10-100tr';
            else if (amount < 200000000) projectTier = '100-200tr';
            else projectTier = '>200tr';

            if (projectTier !== state.revenueTierFilter) return false;
        }

        return true;
    });

    state.currentPage = 1;
    renderProjectsTable(state.filteredProjects);
    updateFilterIndicators();
    saveUIState();
}
