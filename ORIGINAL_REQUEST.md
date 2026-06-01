# Original User Request

## Initial Request — 2026-05-28T22:21:19+07:00

Dự án triển khai Pha 1 nâng cấp Front-End cho Bonario ROI Dashboard, tập trung vào việc ngăn chặn rủi ro XSS, tối ưu hóa hiệu năng render bảng dữ liệu bằng DocumentFragment và cấu trúc lại mã nguồn theo dạng mô-đun ESM nhằm cô lập trạng thái ứng dụng.

Working directory: d:\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Ngăn chặn triệt để lỗ hổng XSS (Security Sanitization)
Cải tiến logic chèn dữ liệu trong `app.js` để đảm bảo mọi chuỗi ký tự động được nạp từ API Odoo (ví dụ: tên dự án, khách hàng) phải được lọc sạch (sanitize) trước khi ghi vào DOM. Viết một hàm helper xử lý escape HTML an toàn hoặc sử dụng giải pháp chuẩn để mã hóa các ký tự đặc biệt (như `<`, `>`, `&`, `"`, `'`) nhằm loại bỏ hoàn toàn khả năng chèn thẻ `<script>` độc hại.

### R2. Tối ưu Rendering bằng DocumentFragment (Performance Optimization)
Tái cấu trúc các hàm render động gồm `renderProjectsTable()` và `renderTagAnalysis()` trong `app.js`. Thay vì cộng chuỗi HTML thủ công và ghi đè trực tiếp `.innerHTML` cho từng dòng dữ liệu (gây reflow liên tục), hãy sử dụng cơ chế `document.createElement()` kết hợp tạo một `DocumentFragment` làm bộ nhớ đệm trung gian. Toàn bộ danh sách dòng dự án hoặc khối tags chỉ được chèn vào DOM thực tế đúng một lần duy nhất khi fragment đã dựng xong.

### R3. Mô-đun hóa và Cô lập Trạng thái (ESM Module Integration)
Chuyển đổi tệp `app.js` sang mô hình ES6 Module (ESM) để cô lập hoàn toàn các biến trạng thái toàn cục (`dashboardData`, `filteredProjects`, `gpChart`) ra khỏi namespace chung của trình duyệt, tránh xung đột biến và tăng tính bảo mật dữ liệu. Khai báo thuộc tính `type="module"` tương ứng cho thẻ `<script>` trong `index.html`.

## Acceptance Criteria

### Tính Bảo mật (Security)
- [ ] Mọi trường dữ liệu văn bản từ API hiển thị trên bảng và tags đều được escape HTML chính xác trước khi chèn vào trang web.
- [ ] Thử nghiệm chèn thử một dự án giả lập có chứa thẻ `<script>alert('XSS')</script>` từ Odoo. Xác minh chuỗi script này hiển thị nguyên dạng văn bản (text content) trên giao diện thay vì bị thực thi.

### Tính Hiệu năng (Performance)
- [ ] Không còn bất kỳ thao tác cộng chuỗi `.innerHTML +=` thủ công nào được sử dụng bên trong các vòng lặp render bảng dự án chi tiết và tags.
- [ ] Bảng dữ liệu dự án chi tiết và tags được render mượt mà thông qua `DocumentFragment` và `appendChild` duy nhất một lần cho mỗi lần nạp lại.

## Follow-up — 2026-05-28T22:54:20+07:00

Dự án triển khai Big Update giao diện trực quan Aura Forest Theme 2.0 cho Bonario ROI Dashboard. Bao gồm nâng cấp 4 orbs nền động, hạt sương sinh học mờ ảo, biểu đồ Sparklines trong thẻ KPI, hạt ngọc phát sáng cảnh báo tài chính trong bảng, biểu đồ tròn tỷ trọng tag, bảng xếp hạng Leaderboard, và thanh trượt menu Sidebar mượt mà.

Working directory: d:\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Hệ thống Nền sinh thái Động (Dynamic Ambient Background)
Nâng cấp từ 2 orbs phát sáng tĩnh lên **4 orbs ánh sáng động** (`Emerald`, `Mint`, `Sage`, `Warm Gold`) di chuyển tự do đan xen nhau ở nền qua CSS Keyframes chuyển động quỹ đạo tự do. Tích hợp hiệu ứng **hạt sương sinh học bay nhẹ** (Biophilic Floating Particles) ở góc màn hình, hoạt động mượt mà 60 FPS tối ưu hóa GPU.

### R2. Sparklines xu hướng trong KPI Cards
Nhúng trực tiếp một biểu đồ **Sparkline mini vẽ bằng đường SVG mềm mại** (Moss to Emerald gradient) vào góc dưới của cả 4 thẻ KPI tài chính để biểu diễn xu hướng biên lợi nhuận gộp của 10 dự án gần nhất.

### R3. Hạt ngọc Phát sáng Cảnh báo Sức khỏe Tài chính trong Bảng
Bổ sung cột "Sức khỏe ROI" ở bảng dữ liệu chi tiết, hiển thị các hạt ngọc kính mờ phát sáng ảo diệu (`Lục Bảo phát sáng` cho biên lợi nhuận >40%, `Hổ Phách phát sáng` cho 15%-40%, `San Hô phát sáng` cho <15%). Các hạt ngọc này có hiệu ứng nhấp nháy thở nhẹ (pulsing glow).

### R4. Đa dạng hóa Biểu đồ & Xếp hạng tại trang Ranks (`#/ranks`)
Phân tách trang `#/ranks` thành bố cục 2 cột chuyên nghiệp:
- Cột trái: Bar Chart phân bổ GP% dải gradient 3 màu sage-mint-emerald.
- Cột phải: Biểu đồ tròn **Doughnut Chart** thể hiện tỷ trọng đóng góp doanh thu của các nhóm Tag, và bảng xếp hạng **Tag Leaderboard** hiển thị danh sách tag hiệu suất cao với chỉ số vàng lá sang trọng.

### R5. Thanh Menu trượt mượt mà ở Sidebar (Slide-active Menu Indicator)
Xây dựng một thanh sáng kính mờ `.menu-indicator` ở Sidebar. Khi click chuyển đổi qua lại giữa các menu, thanh này tự động trượt mượt mà theo trục dọc từ menu cũ đến menu mới với gia tốc chuyển động mềm (`cubic-bezier(0.16, 1, 0.3, 1)` thời gian 0.4s).

## Acceptance Criteria

### Tính Trực quan & Chuyển động
- [ ] 4 orbs phát sáng chuyển động quỹ đạo tự do mượt mà 60 FPS, không gây giật lag hoặc quá tải CPU trên thiết bị.
- [ ] Biểu đồ Sparkline SVG hiển thị đúng trong cả 4 thẻ KPI và tự động vẽ đường cong mượt mà theo dữ liệu xu hướng thực tế của dự án.
- [ ] Hạt ngọc sức khỏe ROI nhấp nháy phát sáng đúng màu sắc phân loại dựa trên tỷ suất GP% của từng dòng dự án.

### Biểu đồ & Xếp hạng
- [ ] Trang ranks hiển thị đồng thời cả Bar Chart phân bổ GP% và Doughnut Chart tỷ trọng doanh thu Tag.
- [ ] Bảng xếp hạng Tag Leaderboard hiển thị chính xác các tag có doanh thu và GP% cao nhất.
- [ ] Thanh chỉ báo menu Sidebar trượt trơn tru từ tab cũ sang tab mới mỗi khi URL hash thay đổi.

## Follow-up — 2026-05-30T13:46:58+07:00

Refactoring mã nguồn Frontend của dự án ROI Project Dashboard bằng cách phân rã file `app.js` monolithic khổng lồ thành các ES6 Modules nguyên bản đặt trong thư mục `assets/js` để tối ưu hóa hiệu năng, tính bảo mật, và khả năng bảo trì.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Phân rã app.js thành các ES6 Modules trong assets/js/
Chia tách `app.js` thành các file module chuyên trách:
- `assets/js/config.js`: Định nghĩa các hằng số, ngưỡng GP Health, và `STATE_LABELS`.
- `assets/js/utils.js`: Chứa hàm định dạng VND, full VND, phần trăm, format date, debounce, và `escapeHTML`.
- `assets/js/api.js`: Đóng gói logic fetch dữ liệu `/api/projects-dashboard` với cơ chế AbortController và timeout 60 giây.
- `assets/js/state.js`: Lưu trữ State ứng dụng toàn cục và quản lý tải/ghi UI State vào LocalStorage.
- `assets/js/charts.js`: Đóng gói logic vẽ biểu đồ cột GP% (`gpChart`), biểu đồ tròn Doanh thu (`revenueDoughnutChart`) và Sparklines cho thẻ KPI. Tự động gọi `destroy()` trên các instance biểu đồ cũ khi nạp dữ liệu mới để tránh rò rỉ bộ nhớ.
- `assets/js/components/`:
  - `table.js`: Logic render bảng danh sách dự án, phân trang, hiển thị trạng thái và xuất file CSV.
  - `dashboard-kpi.js`: Logic cập nhật các thẻ KPI trên màn hình chính và thanh dữ liệu Scope bar.
  - `ops-panels.js`: Logic vẽ các danh sách bổ trợ (Mix trạng thái, GP rủi ro, Tag snapshot).

### R2. Entry point app.js tinh gọn
- `app.js` đóng vai trò là entry point chính của ứng dụng.
- File này chỉ chứa các câu lệnh `import` các module cần thiết và thiết lập bộ lắng nghe sự kiện `DOMContentLoaded` để khởi động ứng dụng.

### R3. Áp dụng Event Delegation cho Checkbox trong Table
- Loại bỏ hàm `attachCheckboxListeners` cũ (vốn lặp đi lặp lại việc gán event listener lên từng checkbox khi vẽ lại bảng).
- Thay thế bằng cơ chế Ủy quyền sự kiện (Event Delegation) duy nhất trên element `#projectsTable` (hoặc thẻ table tương ứng) để lắng nghe thay đổi của checkbox, tối ưu hóa bộ nhớ và tăng tốc độ vẽ DOM.

### R4. Tương thích hoàn toàn với Backend Flask
- Đảm bảo các module được tải tự động qua route `/assets/js/<file>.js` mà không phải chỉnh sửa bất kỳ dòng code nào của `app.py` hay thay đổi cơ sở hạ tầng phục vụ của Flask.
- Sử dụng các tính năng chuẩn ES6 có sẵn trên trình duyệt hiện đại (native ES6 modules), không tích hợp các công cụ build (npm/Vite/Webpack) nhằm duy trì dự án ở mức nhẹ tối đa.

## Acceptance Criteria

### Giao diện & Trình duyệt
- [ ] Ứng dụng nạp thành công ở trang chủ `http://localhost:5056` mà không phát sinh bất kỳ cảnh báo hoặc lỗi JS nào trong Console của trình duyệt.
- [ ] Màn hình tải (Loading overlay) và màn hình thông báo lỗi (Error state) hoạt động chính xác khi đồng bộ.

### Logic Điều hiện & Chức năng
- [ ] Chuyển đổi giữa các màn hình (SPA Hash Router: `/overview`, `/tags`, `/projects`, `/ranks`) hoạt động mượt mà và thanh trượt menu indicator ở Sidebar di chuyển chính xác.
- [ ] Các tính năng Lọc (Filter theo tag, status, GP health), Tìm kiếm (Search có debounce 300ms) hoạt động đồng bộ với dữ liệu hiển thị.
- [ ] Chức năng sắp xếp cột (Sorting) và phân trang (Pagination) hoạt động đúng như phiên bản cũ.

### Quản lý Trạng thái & Biểu đồ
- [ ] Việc chọn nhiều dự án (Multi-select) cập nhật chính xác tổng giá trị trên thanh trạng thái lựa chọn và tính đúng GP% trung bình có trọng số.
- [ ] Các biểu đồ Chart.js (Bar chart, Doughnut chart) và Sparklines hiển thị đẹp mắt, tự động thay đổi kích thước (`resize()`) chuẩn xác khi chuyển trang hoặc co giãn màn hình, và không bị lỗi chồng lấn/rò rỉ canvas cũ.
