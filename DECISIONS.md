# Tài Liệu Quyết Định Nghiệp Vụ & Kỹ Thuật (`DECISIONS.md`)

Tài liệu này ghi nhận toàn bộ các quyết định nghiệp vụ và kỹ thuật đã áp dụng trong đợt kiểm toán & sửa lỗi `dashboard-roi-project` (nhánh `fix/audit-shipping-20261014`).

---

## 1. Quy tắc Chi phí vận chuyển (`S1–S11`) & Quyết định Mã phân tích trên Odoo TEST

### 1.1. Tập mã phân tích vận chuyển (`S1`) — Chỉ tính plan `Departments / SC Dept`
1. **Quyết định của Owner (chốt ngày 14/10/2026)**:
   - **Chỉ tính các mã vận chuyển thuộc plan `Departments / SC Dept` (`plan_id=7`)**.
   - **Không tính các mã thuộc plan `Departments / BD Dept` (`plan_id=6`)**:
     - `506`: `BD_Shipping (CLT, demo...)` (năm 2026 trên TEST: `10,744,753 VND`, trong đó đã gắn dự án `168,736 VND`, chưa gắn dự án `10,576,017 VND`).
     - `1427`: `ORD - BD_Shipping (CLT, demo...)` (năm 2026 trên TEST: `3,526,000 VND`, chưa gắn dự án).
     - `1486`: `BD_Rework_Rush logistics` (năm 2026 trên TEST: `0 VND`).
     - **Lý do nghiệp vụ**: Đây là chi phí gửi mẫu/demo/bán hàng của bộ phận BD (Business Development), không tính vào chỉ tiêu Chi phí vận chuyển chuỗi cung ứng (`SC Dept`).
2. **Discovery bao gồm cả mã đã lưu trữ (`active=False`) trong phạm vi `Departments / SC Dept`**:
   - Mọi truy vấn `account.analytic.account` phục vụ nhận diện mã vận chuyển bắt buộc truyền `context={'active_test': False}` và giới hạn trong plan `Departments / SC Dept` để lấy đủ cả các mã đã lưu trữ có phát sinh bút toán lịch sử (`518`: `SC_Shipping Cost to Customers`, `1237`: `[ORD] SC_Shipping Cost to Customers`) mà không kéo nhầm mã của `BD Dept`.
3. **Danh sách 10 mã vận chuyển `SC Dept` chuẩn (`SHIPPING_ANALYTIC_ACCOUNT_IDS_FALLBACK`)**:
   - **10 mã `SC Dept`**: `{518, 1237, 566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}`.
   - **Số liệu thực tế năm 2026 trên Odoo TEST cho 10 mã `SC Dept`**:
     - **Tổng chi phí vận chuyển năm 2026 (`shipping_company_total`)**: **`1,047,070,262 VND`**
     - **Đã gắn dự án (`shipping_total`)**: **`868,694,565 VND`** (trong đó qua PO: `707,127,893 VND`, ngoài PO: `161,566,672 VND`)
     - **Chưa gắn dự án (`shipping_unassigned_total`)**: **`178,375,697 VND`**
4. **Quyết định đối với các mã `1439`, `568`, `1238` (theo S1d)**:
   - Qua khảo sát thực tế trên Odoo TEST (`tools/reconcile_shipping.py` / `/tmp/roi_recon/account_decisions.md`):
     - `1439`: `SC_Trips in processing SO` (plan `Departments / SC Dept`, cột `x_plan5_id`) — Tên mã không chứa từ khóa vận chuyển/giao hàng/logistics/ship/cước; nội dung chứng từ là chi phí đi công tác/khảo sát khi xử lý đơn hàng. Số tiền năm 2026 trên TEST: **`43,321,335 VND`** (đã gắn dự án: `196,000 VND`, chưa gắn dự án: `43,125,335 VND`). **Quyết định: Loại khỏi tập S1 mặc định**.
     - `568`: `SC_Car related (fuel, maintainnance...)` (plan `Departments / SC Dept`, cột `x_plan5_id`) — Tên mã không chứa từ khóa vận chuyển; nội dung là chi phí xăng xe, phí cầu đường VETC, bảo dưỡng xe nội bộ. Số tiền năm 2026 trên TEST: **`10,261,877 VND`** (100% chưa gắn dự án). **Quyết định: Loại khỏi tập S1 mặc định**.
     - `1238`: `[ORD] SC_Car related` (`active=False`, plan `Departments / SC Dept`) — Số tiền năm 2026 trên TEST: **`0 VND`**. **Quyết định: Loại khỏi tập S1 mặc định**.
   - Nếu cần thay đổi tập mã vận chuyển theo yêu cầu quản trị trong tương lai, có thể cấu hình qua biến môi trường `SHIPPING_ANALYTIC_IDS`.

### 1.2. Nguồn số liệu, Phân bổ, PO, Loại chứng từ & Gán tháng (`S2–S11`)
- **S2 (Nguồn số liệu & Tỷ lệ phân bổ)**:
  - Tính từ `account.analytic.line` (`AAL`) với số tiền `cost = -aal.amount` (Odoo đã nhân sẵn tỷ lệ `%` phân bổ cho từng dự án `account_id` và gắn mã phòng ban ở cột `x_plan5_id`).
  - Đối với nhánh fallback `account.move.line` (chứng từ cũ chỉ gắn mã ship trong `analytic_distribution`), bắt buộc nhân tỷ lệ `share = pct / 100.0` của dự án, tuyệt đối không cộng 100% `move_line.balance`.
- **S3 (Tính cả vận chuyển đặt qua PO)**:
  - Không loại bỏ dòng có `purchase_line_id`. Tách bạch thành `shipping_cost_po` (có `purchase_line_id`) và `shipping_cost_non_po` (không có `purchase_line_id`), đảm bảo `shipping_cost = shipping_cost_po + shipping_cost_non_po`.
- **S4 & S5 (Loại chứng từ & Trạng thái)**:
  - Chỉ tính vào KPI `shipping_cost` các chứng từ đã ghi sổ (`parent_state == 'posted'`) thuộc loại chi phí (`in_invoice`, `in_refund` giảm trừ, `in_receipt`, `entry`). Loại trừ hoàn toàn hóa đơn bán hàng (`out_invoice`, `out_refund`, `out_receipt`).
  - Các hóa đơn mua hàng nháp (`parent_state == 'draft'`) có gắn mã vận chuyển được tách riêng vào trường tham khảo `shipping_draft` và phần `open_commitment` của mục `Chi phí vận chuyển` ở màn chi tiết, không cộng vào KPI `shipping_cost` đã ghi sổ.
- **S6 & S7 (Gán tháng theo `aal.date` & Chi phí vận chuyển chưa gắn dự án)**:
  - Gán tháng theo ngày hạch toán `aal.date` (`YYYY-MM`), không cắt theo `sale.order.date_order`.
  - Các dòng AAL thuộc tập S1 nhưng `account_id = False` được tổng hợp vào `summary["shipping_unassigned_total"]`, `summary["shipping_by_month"][month]["unassigned"]`, và truy xuất chi tiết qua endpoint `GET /api/shipping/unassigned?date_from=&company=&format=csv`.
  - Bất biến cấp công ty: `shipping_total + shipping_unassigned_total == shipping_company_total`.
- **S9 (Bất biến cấu thành chi phí ở màn chi tiết `build_project_dashboard`)**:
  - Khấu trừ từng phần chi phí vận chuyển (`po`, `vendor_bill`, `expense`, `other`) đúng vào mục gốc tương ứng trên panel lợi nhuận của Odoo (`purchase_order`, `other_purchase_costs`/`vendor_bills`, `expenses`, `other`) nơi khoản đó được Odoo gom vào.
  - Giới hạn mức khấu trừ tối đa bằng số dư của từng mục gốc không âm để không sinh ra mục `"Chi phí khác"` bị âm giả tạo (như khi panel dùng `untaxed_amount` cho `hr.expense` còn AAL dùng `total_amount` có VAT), đồng thời bảo toàn dấu âm thực sự của các khoản giảm trừ/hoàn tiền và đảm bảo bất biến:
    `sum(item["expected"] - item.get("panel_gap", 0) for item in custom_cost_breakdown) == profitability_costs["expected_cost_total"]`.
  - Dòng "Chi phí vận chuyển" luôn hiển thị đủ số ghi sổ (bằng màn tổng quan). Phần ship không trừ được khỏi nhóm nào trong panel (ví dụ 1685: hr.expense 400.000 có VAT 8%, panel tính trước thuế 370.370, chênh 29.630) được ghi ở `panel_gap`, không cộng vào tổng chi phí gốc; UI hiện dòng ghi chú.

---

## 2. Các Quyết định Nghiệp vụ Doanh thu, Chi phí, GP & Đồng bộ (`A, B, C, E, F, SEC`)

1. **A-02 (Biên ngày `date_from` theo giờ Việt Nam UTC+7)**:
   - Quy đổi `date_from` (`YYYY-MM-DD 00:00:00` giờ `Asia/Ho_Chi_Minh`) sang UTC trước khi lọc `sale.order.date_order` để không mất đơn hàng phát sinh từ `00:00–06:59` sáng giờ VN.
2. **A-03 (Khử trùng doanh thu khi 1 SO gắn nhiều Project)**:
   - Đánh dấu `shared_so = True` trên từng dòng project dùng chung `sale_order_id`.
   - Trong `_build_projects_dashboard_summary`, khử trùng `bg_untaxed` theo `sale_order_id` để không nhân bản doanh thu công ty.
3. **A-04 (Lọc công ty nghiêm ngặt)**:
   - Dự án có `company_key == ""` chỉ hiển thị khi chọn `company="all"`, không lọt vào bộ lọc riêng của `bonario` hoặc `ordinaire`.
4. **B-01 (Trạng thái Đơn bán hàng & Credit Note `out_refund`)**:
   - Chỉ lấy SO có `state` hợp lệ (cấu hình qua `ALLOWED_SO_STATES`, mặc định `sale,done`), loại bỏ `cancel` và `draft`.
   - Tổng hợp giá trị Credit Note (`out_refund` đã posted) vào `summary["refund_total"]` để hiển thị minh bạch mà không tự ý trừ trực tiếp vào `total_bg_untaxed`.
5. **B-02 & B-03 (Tiền cọc Downpayment & Quy đổi đa tiền tệ)**:
   - `downpayment_total` lấy từ giá trị đã xuất hóa đơn của các dòng cọc (`invoiced_net`) và loại bỏ dòng cọc khỏi phép kiểm tra lệch `quoted_net - invoiced_net` để không báo `is_stale = True` giả.
   - Quy đổi ngoại tệ sang tiền tệ công ty theo ngày chứng từ; nếu thiếu tỷ giá hoặc lỗi RPC thì `raise OdooAPIError` thay vì trả về `0`.
6. **C-01..C-07 (Pipeline Chi phí & Điều chỉnh chéo)**:
   - Nhân đúng tỷ lệ `%` trong `analytic_distribution` ở cả `_get_posted_actual_costs`, `_get_draft_bill_commitments`, và `_get_po_open_commitments`.
   - Khấu trừ phần tiền đang nằm trên Draft Bill (`draft_commitments_by_po_line`) ra khỏi cam kết PO mở (`_get_po_open_commitments`) để không tính trùng khi PO vừa có bill nháp vừa chưa tăng `qty_invoiced`.
   - Không ghi đè `actual_cost_total` về `0` khi dùng `stock_valuation_fallback`; giữ nguyên dấu của `stock.valuation.layer.value` (`-value`) để phiếu trả hàng làm giảm giá vốn kho; giữ bút toán COGS (`display_type == 'cogs'`) trên `out_invoice`.
   - Trong điều chỉnh chi phí chéo (`_find_foreign_analytic_account_sources`, `_apply_foreign_invoice_cost_adjustments`): parse đủ multi-plan key `"1265,1581"`, giữ dấu của bút toán đảo (`amount > 0`), và chia đều/gán đích danh khi có nhiều `foreign_order_ids` để đảm bảo bất biến `sum(foreign_cost_added) == sum(foreign_cost_removed)`.
7. **E-01..E-03 (Cộng đủ chi phí dự án doanh thu 0đ & Phân dải GP% âm nhỏ)**:
   - `_build_projects_dashboard_summary` cộng chi phí của mọi dự án `Done` (kể cả dự án bảo hành/mẫu có `bg_untaxed == 0`) và đếm `zero_revenue_projects`.
   - Mọi dự án có `gp_percent < 0` (ví dụ `-0.5%`) đều thuộc dải `<0%` ở cả backend và frontend.
8. **F-01..F-05 (Cache, Chống đầu độc số 0 khi HTTP 429 & Delta Sync)**:
   - Xóa `profitability:*` trước khi fetch khi `refresh=True` và giữ lại dữ liệu mới sau khi fetch.
   - Khi gặp `OdooAPIError` (như HTTP 429), không ghi đè số `0` vào cache mà trả về bản cache hợp lệ gần nhất kèm cờ `summary["data_stale"] = True`.
   - `get_delta_updates` kiểm tra thêm `account.analytic.line` mới/sửa, áp dụng đầy đủ bộ lọc SO, và bảo toàn `tag_buckets` liên công ty.
   - `PersistentCache` lưu cột `expires_at` dạng `float` theo từng key, dùng chung lock theo `db_path`, tự phục hồi khi JSON/SQLite lỗi, và kiểm tra `owner_id` khi giải phóng `warmer_lock`.
9. **SEC-01 & SEC-02 (Bảo mật & Quản lý Khóa API)**:
   - **Trạng thái khóa API cũ**: **Key cũ đã bị thu hồi trên prod ngày 14/10/2026**. Toàn bộ các script trong `tests/` chỉ đọc thông tin kết nối từ biến môi trường, tuyệt đối không hardcode key hoặc URL production.
   - Guard chặn kết nối production (`ProdBlockedError`) mặc định tắt ở runtime (`ODOO_BLOCK_PROD=0`) để không ảnh hưởng container production, và chỉ bật tự động trong `tests/conftest.py` và `tools/reconcile_shipping.py` (`ODOO_BLOCK_PROD=1`).

