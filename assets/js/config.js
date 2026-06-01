export const API_BASE = '';
export const DEFAULT_DATE_FROM = '2026-01-01';
export const GP_HEALTH_HIGH = 40;
export const GP_HEALTH_MEDIUM = 15;
export const UI_STATE_KEY = 'bonario-roi-dashboard-ui-v2';
export const ITEMS_PER_PAGE = 10;

export const STATE_LABELS = {
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
    'Chờ phản hồi nội bộ': 'Chờ nội bộ',
};

export const SORTABLE_COLUMNS = [
    { key: 'sale_order_name', label: 'Đơn hàng' },
    { key: 'project_name', label: 'Dự án' },
    { key: 'customer', label: 'Khách hàng' },
    { key: 'bg_untaxed', label: 'Doanh thu' },
    { key: 'native_expected_cost', label: 'Chi phí' },
    { key: 'gp_amount', label: 'GP' },
    { key: 'gp_percent', label: 'GP%' },
];
