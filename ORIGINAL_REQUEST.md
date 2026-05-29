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
