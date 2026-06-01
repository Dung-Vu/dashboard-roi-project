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

## Follow-up — 2026-06-01T15:12:25+07:00

Tích hợp tính năng Click-to-Odoo: Khi người dùng nhấp vào mã đơn hàng (Sale Order Name / Mã BG) trên bảng danh sách dự án chi tiết, hệ thống sẽ tự động mở một tab trình duyệt mới và chuyển trực tiếp đến giao diện form của đơn hàng đó trên Odoo.

Working directory: c:\Users\Admin\Desktop\Bonario\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Cung cấp Odoo URL cho Frontend từ Backend
- Cập nhật backend Flask trong `dashboard_service.py` để truyền thông tin `odoo_url` (lấy từ thuộc tính `url` của `OdooAPI` client) vào trong đối tượng `meta` trả về của API `/api/projects-dashboard` (thông qua hàm `_build_projects_dashboard_meta`).

### R2. Hiển thị mã đơn hàng dạng liên kết động (Clickable Link) trên bảng danh sách
- Thay thế văn bản tĩnh mã đơn hàng (`sale_order_name`) tại cột đầu tiên của bảng dự án chi tiết bằng một thẻ liên kết `<a>`.
- Đường dẫn liên kết sẽ được dựng động dựa trên URL Odoo và ID đơn hàng: `<odoo_url>/web#id=<sale_order_id>&model=sale.order&view_type=form`.
- Đảm bảo liên kết sẽ mở ở tab trình duyệt mới (`target="_blank"`, `rel="noopener noreferrer"`).
- Áp dụng các thay đổi này đồng bộ trên cả table.js và debug_combined.js.

### R3. Thiết kế thẩm mỹ giao diện cao cấp
- Thiết kế liên kết có màu xanh ngọc lục bảo (`var(--color-emerald)`), font chữ đồng bộ (`var(--font-heading)`), đi kèm đường gạch chân đứt nét tinh tế (`border-bottom: 1px dashed rgba(16, 120, 80, 0.4)`).
- Tích hợp hiệu ứng chuyển động mượt mà khi hover (ví dụ: thay đổi độ mờ `opacity` hoặc đổi màu nền nhẹ nhàng).

## Acceptance Criteria

### Tính Năng & Trải Nghiệm Giao Diện
- [ ] Mã đơn hàng (Sale Order Name) hiển thị dưới dạng đường link có thể click được trên mọi dòng dự án có liên kết đơn hàng hợp lệ.
- [ ] Khi click vào link, trình duyệt mở một tab mới trỏ đến đúng định dạng URL của Odoo: `https://<odoo-domain>/web#id=<sale_order_id>&model=sale.order&view_type=form`.
- [ ] Với các dự án không có `sale_order_id` hoặc thiếu thông tin URL, hệ thống hiển thị văn bản tĩnh dạng mã SO thông thường hoặc dấu gạch ngang `-` mà không bị lỗi JavaScript.
- [ ] Giao diện của liên kết tuân thủ đúng phong cách thẩm mỹ Aura Forest Theme.

## Follow-up — 2026-06-01T15:45:21+07:00

Nâng cấp giao diện và tối ưu hóa hiệu năng cho Bonario ROI Dashboard: điều chỉnh linh hoạt phân phối dải GP% trên biểu đồ cột (chỉ hiện các dải có dữ liệu), đồng bộ dải màu 4 nhóm tag đặc thù để tăng tính nhận diện trực quan, và khắc phục tình trạng lag/chậm của giao diện bằng việc tối ưu hóa GPU/CSS.

Working directory: c:\Users\Admin\Desktop\Bonario\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Điều chỉnh phân phối dải GP% linh hoạt trên biểu đồ cột
- Cập nhật logic backend (`dashboard_service.py` trong hàm `_build_tag_gp_ranks`) để trả về tất cả các khoảng phân dải GP% có xuất hiện dữ liệu dự án (thay vì chỉ lấy top 3 dải cao nhất).
- Khoảng phân dải GP% tuân theo logic: `0-20%`, `21-40%`, và từ `41%` trở lên bước nhảy là `5%` (ví dụ: `41-45%`, `46-50%`, `51-55%`, v.v.).
- Cập nhật logic frontend (`assets/js/charts.js` và `tests/debug_combined.js`) để gộp và sắp xếp tất cả các dải GP% nhận từ API. Chỉ hiển thị các dải thực sự có dữ án xuất hiện trên trục hoành; ẩn hoàn toàn bất kỳ dải nào không có dữ liệu (ví dụ: `61-65%` nếu không có dự án nào).

### R2. Đồng bộ màu sắc phân biệt trực quan cao cho 4 nhóm Tag
- Đổi màu 4 tag chủ đạo để người dùng dễ nhận biết và phân biệt rõ ràng:
  1. **Nội thất rời:** Xanh lục bảo đậm (Deep Emerald, ví dụ `#107850`).
  2. **Giấy dán tường:** Vàng hổ phách ấm (Amber Gold, ví dụ `#d97706`).
  3. **Rèm:** Xanh da trời/slate thanh lịch (Slate Blue, ví dụ `#0284c7`).
  4. **Vải nội thất:** Cam đất nung (Terracotta, ví dụ `#ea580c`).
- Áp dụng đồng bộ dải màu sắc này theo đúng tên tag ở cả biểu đồ cột (Bar Chart) và biểu đồ tròn (Doughnut Chart) trong `assets/js/charts.js` (và `tests/debug_combined.js`), thay vì gán màu theo chỉ mục (index) như cũ.

### R3. Tối ưu hóa hiệu năng hoạt ảnh giao diện (Lag reduction)
- Tối ưu hóa hiệu năng render các hoạt ảnh nền sinh thái động và hạt sương sinh học (`.particle`) trong styles.css để tránh quá tải CPU/GPU trên thiết bị.
- Áp dụng thuộc tính `will-change: transform, opacity` cho các phần tử chuyển động.
- Tránh lạm dụng các thuộc tính có chi phí vẽ cao như `backdrop-filter: blur(...)` chồng chéo hoặc tinh chỉnh lại mật độ/số lượng các hạt chuyển động để đạt hiệu suất 60 FPS mượt mà.

## Acceptance Criteria

### Phân phối Biểu đồ GP%
- [ ] Trục hoành của biểu đồ cột phân bổ GP% chỉ hiển thị những khoảng thực sự chứa ít nhất 1 dự án. Không hiển thị các khoảng trống không có dữ liệu.
- [ ] Phân dải GP% chạy chuẩn xác theo logic: `0-20%`, `21-40%`, và từ `41%` trở đi nhảy bước `5%`.

### Đồng bộ và Tương phản Màu sắc
- [ ] 4 nhóm tag chính hiển thị đúng các màu đặc thù được cấu hình ở cả Bar Chart và Doughnut Chart.
- [ ] Màu sắc của mỗi tag đồng bộ 100% giữa hai biểu đồ (ví dụ: "Giấy dán tường" luôn là màu Vàng hổ phách ở cả hai biểu đồ).
- [ ] Độ tương phản màu sắc đáp ứng tiêu chuẩn tiếp cận WCAG.

### Tối ưu hóa Hiệu năng
- [ ] Giao diện chạy mượt mà, không bị giật lag khi chuyển trang, cuộn trang hoặc tương tác bộ lọc.
- [ ] Giảm tải CPU tiêu thụ bởi hoạt ảnh nền so với phiên bản cũ.

## Follow-up — 2026-06-01T16:14:57+07:00

Đồng bộ logic không phân tách theo công ty cho 2 trang "Hiệu suất theo Tag" và "Xếp hạng & Biểu đồ" của Bonario ROI Dashboard: đảm bảo dữ liệu tag phân tích (`tag_buckets`) và phân phối hạng GP (`tag_gp_ranks`) luôn gộp chung của cả hai công ty kết hợp lại, trong khi trang "Overview" và danh sách "Projects" vẫn lọc chính xác theo công ty được chọn ở Sidebar.

Working directory: c:\Users\Admin\Desktop\Bonario\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Nạp toàn bộ dữ liệu của tất cả công ty từ Backend
- Cập nhật hàm `_get_dashboard_sale_orders` trong backend dashboard_service.py để lấy toàn bộ Sale Orders của tất cả các công ty thỏa mãn mốc thời gian `date_from` và nhân sự không bị loại trừ (bỏ bộ lọc theo `company_key` tại bước nạp dữ liệu thô này).
- Đảm bảo tất cả các dự án, chi phí và doanh thu tương ứng của cả hai công ty (`bonario` và `ordinaire`) đều được nạp và xử lý song song thông qua ThreadPoolExecutor.

### R2. Tách biệt bộ lọc công ty cho các trang chức năng
Trong hàm `build_projects_dashboard` của dashboard_service.py:
- **Trang Tags và Ranks (Gộp chung):** Tính toán `"tag_buckets"` và `"tag_gp_ranks"` dựa trên toàn bộ các dòng dự án có trạng thái `Done` (`done_rows`) của cả hai công ty kết hợp lại. Không thực hiện phân tách hay lọc theo công ty đối với hai thuộc tính này.
- **Trang Overview và Projects (Lọc theo công ty):**
  - Thực hiện lọc danh sách dự án trả về (`payload["projects"]`) theo đúng `company_key` được chọn.
  - Tính toán tổng quan tài chính (`payload["summary"]`) và metadata hiển thị (`payload["meta"]`) chỉ dựa trên danh sách dự án đã được lọc theo `company_key` này.

### R3. Xác minh hoạt động an toàn
- Đảm bảo việc nạp toàn bộ dữ liệu chạy trơn tru, không gây gián đoạn hay crash API.
- Đảm bảo cache persistent hoạt động chính xác với khóa cache tương ứng.
- Đảm bảo frontend nạp dữ liệu bình thường, hiển thị đúng các giá trị trên Scope bar và các biểu đồ.

## Acceptance Criteria

### Tính Toàn Vẹn Của Biểu Đồ & Tags (Gộp chung)
- [ ] Dữ liệu hiển thị trên biểu đồ "Phân bổ GP% theo nhóm Tag" (Ranks page) và phân tích hiệu suất Tag (Tags page) là dữ liệu gộp chung của cả hai công ty (Bonario + Ordinaire), không thay đổi khi chuyển đổi công ty ở Sidebar.
- [ ] Các khoảng phân dải GP% chỉ xuất hiện nếu có dự án chứa dữ liệu của ít nhất một trong hai công ty.

### Tính Chính Xác Của Overview & Bảng Dự Án (Lọc theo công ty)
- [ ] Bảng chi tiết dự án (Projects page) chỉ hiển thị đúng các dự án thuộc công ty được chọn ở Sidebar.
- [ ] Các thẻ KPI tài chính và Scope bar ở trang Overview chỉ tổng hợp số liệu của công ty được chọn.

