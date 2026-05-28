# ROI Project Dashboard

Standalone dashboard lấy dữ liệu trực tiếp từ Odoo để tính GP project. Màn hình chính hiện là multi-project dashboard từ `2026-01-01`, dùng `sale.order.amount_untaxed` và Native Expected Cost từ `project.project.get_panel_data()`.

Mục tiêu chính của repo này là: vẫn dùng Odoo làm nguồn raw data, nhưng toàn bộ logic cộng line, nhận diện service line, và tính số đúng cho dashboard sẽ do repo này xử lý.

## Mục tiêu

- Lấy toàn bộ BG line từ sale order gắn với project.
- Giữ đủ cả các line có `product type = service`, kể cả khi Odoo native profitability có thể bỏ sót chúng.
- Tự tính `quoted`, `invoiced`, `remaining` dựa trên BG line.
- Tự tính `actual cost`, `gross profit`, `margin`, `ROI` từ dữ liệu Odoo đọc-only.
- So sánh với `untaxed_amount_to_invoice` của Odoo để phát hiện drift.
- Màn hình chính tự load toàn bộ project có BG từ `2026-01-01`; endpoint single-project cũ vẫn được giữ ở `/api/dashboard`.
- Ưu tiên accuracy cho một project bằng cost pipeline 2 tầng: `analytic account` làm nguồn tổng cost chính, `stock valuation` chỉ làm fallback cho direct line allocation.
- Rule allocate final cho project đầu tiên hiện gồm:
    - exact `product_id` match từ `account.analytic.line` sang `sale.order.line`
    - chi phí thi công / công tác / vé xe allocate vào service fee line chính
    - chi phí ship vật tư allocate tỷ trọng vào các material lines
    - chỉ fallback sang `stock.move` + `stock.valuation.layer` nếu analytic account không đủ dữ liệu

## Cách chạy

1. Tạo virtualenv và cài dependencies:

    ```powershell
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

2. Điền `.env` theo `.env.example`.

3. Chạy app:

    ```powershell
    python app.py
    ```

4. Mở trình duyệt ở `http://localhost:5056`.

## Multi-project dashboard

Endpoint chính:

```text
GET /api/projects-dashboard?date_from=2026-01-01
GET /api/projects-dashboard?date_from=2026-01-01&refresh=1
```

Payload gồm `projects`, `summary`, `tag_buckets`, `tag_gp_ranks`, `date_from`, `fetched_at`.

Rule chính:

- `GP% = (BG Untaxed - Native Expected Cost) / BG Untaxed * 100`.
- `Weighted GP% = (sum(BG Untaxed) - sum(Native Expected Cost)) / sum(BG Untaxed) * 100`.
- Project có `BG Untaxed <= 0` vẫn hiện trong list nhưng không tham gia summary average, bucket, rank.
- Chỉ bucket/rank 3 tag: `Nội thất rời`, `Giấy dán tường`, `Rèm`.
- Payload multi-project được cache in-memory 10 phút theo `date_from`; `refresh=1` bỏ cache.

## Single-project API cũ

Màn hình chính chỉ giữ 4 KPI cần quyết định:

- `Tổng giá BG`: `quoted_total_untaxed`
- `Chi phí final`: `actual_cost_total + open_commitment_total`
- `Lợi nhuận final`: `quoted_total_untaxed - final_cost_total`
- `Tỷ suất lợi nhuận / BG`: `final_margin_percent`

`actual_cost_total` vẫn được giữ trong API như chi phí đã posted trên analytic account. Phần `open_commitment_total` lấy read-only từ native profitability `to_bill` để dashboard final không bỏ sót bill draft hoặc chi phí đã cam kết nhưng chưa post.

Ngay dưới đó là một block `Cost Breakdown` nhỏ gọn:

- `Allocated line cost`: cost đã map an toàn trực tiếp vào BG line
- `Project-level extra cost`: cost xác nhận ở cấp project nhưng chưa cần ép vào line
- `Cost coverage %`: tỷ lệ revenue đã có cost allocation
- `Service Included`: số service line vẫn được tính vào doanh thu

Toàn bộ `cost journal` và `line audit` được chuyển xuống phần `Kiểm tra chi tiết dữ liệu` và ẩn mặc định.

## Ghi chú

- Endpoint single-project vẫn giữ cost pipeline riêng; dashboard multi-project dùng `project.project.get_panel_data()` để lấy Native Expected Cost đúng theo công thức GP mới.
- Khi `Allow Timesheets = False`, Odoo native profitability có thể ẩn service revenue. App này vẫn giữ đủ line BG vì đọc trực tiếp từ sale order.
- Phân loại `service` hiện đang đọc từ `product.product.type` trên instance Odoo hiện tại.
- Cost hiện đọc hoàn toàn read-only theo kiến trúc này:
    - `account.analytic.line` của `project.account_id` làm nguồn tổng cost chính
    - direct line allocation bằng exact product match trên analytic entries
    - rule-based allocation cho `service operations` và `material logistics`
    - `stock.move` + `stock.valuation.layer` chỉ dùng làm fallback khi analytic không allocate được line nào
- Nếu một cost entry thuộc project nhưng chưa có rule an toàn để allocate vào BG line, app giữ nó ở `Project Cost Journal` thay vì ghi hay sửa dữ liệu ngược vào Odoo.
- Nếu `Delta vs Odoo` khác 0, line đó nhiều khả năng bị stale do discount đã đổi nhưng `untaxed_amount_to_invoice` chưa recompute.
