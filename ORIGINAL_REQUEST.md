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
  - `ops-panels.js`: Logic vẽ các danh sách bổ trợ (Theo trạng thái đơn hàng, GP rủi ro, Tag snapshot).

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

## Follow-up — 2026-06-01T20:22:59+07:00

Cập nhật toàn diện giao diện Bonario ROI Dashboard sang tông màu xanh lam pastel sáng cao cấp (Soft Coastal Pastel Blue), thiết lập phạm vi mặc định là "Tất cả công ty" (All companies) ở cả Backend & Frontend, và tinh chỉnh trực quan biểu đồ cột GP% (skipNull và tối ưu độ dày cột).

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Hỗ trợ hiển thị mặc định "Tất cả công ty" (All companies)

- **Backend (`dashboard_service.py`):**
  - Thêm khóa `"all"` vào `COMPANY_SCOPES` với nhãn là `"Tất cả công ty"` và aliases tương ứng (`all`, `tat ca`, `tatca`).
  - Cập nhật logic `build_projects_dashboard` để nếu `company_key` is `"all"`, bỏ qua việc lọc danh sách dự án theo `company_key` (giữ lại và xử lý dữ liệu của tất cả các công ty).
- **Backend (`app.py`):**
  - Thay đổi giá trị mặc định của tham số `company` trong endpoint `/api/projects-dashboard` từ `"bonario"` thành `"all"`.
- **Frontend (`assets/js/config.js`):**
  - Đổi giá trị hằng số `DEFAULT_COMPANY` thành `'all'`.
  - Thêm tùy chọn `{ key: 'all', label: 'Tất cả công ty' }` vào đầu mảng `COMPANY_OPTIONS`.

### R2. Đổi giao diện sang tông màu Xanh lam pastel sáng (Soft Coastal Pastel Blue)

- **styles.css:**
  - Tại `body`, loại bỏ thuộc tính ảnh nền `url('assets/bg.png')` cũ. Thay bằng dải màu chuyển sắc lam sáng mượt mà: `background-image: linear-gradient(135deg, #f0f4f8 0%, #e6ecf2 100%);`.
  - Cập nhật biến màu `:root` để chuyển đổi sang hệ màu xanh pastel và tương phản với Sidebar màu xanh phiến thạch trầm nhã (`#1e293b`):
    - `--bg-sidebar` (Sidebar): `#1e293b` (Deep Slate Slate)
    - `--color-emerald` (Màu chủ đạo chính): `#2b6cb0` (Ocean Blue)
    - `--color-emerald-glow`: `rgba(43, 108, 176, 0.25)`
    - `--color-mint` (Màu điểm nhấn phát sáng): `#60a5fa` (Sky Blue)
    - `--color-mint-glow`: `rgba(96, 165, 250, 0.35)`
    - `--color-clay` (Xám xanh đá): `#5a6e7f`
    - `--color-moss` (Xanh lam đậm): `#1a365d`
    - `--color-text-primary` (Xám đen phiến thạch): `#1e293b`
    - `--color-text-secondary` (Xám cool slate): `#64748b`
    - `--color-sage` (Lam pastel nhạt): `#90cdf4`
    - `--glass-border` & `--glass-border-hover`: Đổi từ tông xanh lá sang tông xanh lam nhạt bán trong suốt.
  - Cập nhật dải màu chuyển sắc của các hạt trôi nổi `.particle` sang tông màu xanh da trời nhạt/trắng.
  - Điều chỉnh các hạt phát sáng `.glow-orb` sang hệ màu xanh pastel và tím lavender nhạt.
  - Đảm bảo các thành phần gradient khác (như logo `.brand-logo`, các nút bấm `.btn-primary-forest` / `.btn-export` và status card `.sidebar-status-card`) được chuyển đổi đồng bộ sang hệ màu xanh dương mới.

### R3. Thiết kế lại trực quan Biểu đồ Cột GP% (`gpChart`)

- **assets/js/charts.js (`renderGPChart`):**
  - Bổ sung thuộc tính `skipNull: true` trên từng dataset để Chart.js tự động ẩn các khoảng trống của các tag có giá trị bằng 0 trong cùng phân khúc.
  - Cập nhật logic ánh xạ dữ liệu: Trả về `null` thay vì `0` khi không có đơn hàng nào thuộc tag đó trong nhóm GP% để kích hoạt tính năng `skipNull` hoạt động chính xác.
  - Thiết lập kích thước cột cân đối trong Chart options: cấu hình `categoryPercentage: 0.85`, `barPercentage: 0.8`, và `maxBarThickness: 28` để cột đơn lẻ tự động giãn rộng và nằm chính giữa đẹp mắt.
  - Cập nhật hệ màu hiển thị trong `TAG_COLORS` và tooltip để đồng bộ với tông màu mới nhưng vẫn đảm bảo sự tương phản rõ ràng giữa các nhóm Tag:
    - _Nội thất rời:_ Xanh dương (`#2b6cb0`, `rgba(43, 108, 176, 0.4)`)
    - _Giấy dán tường:_ Cam pastel (`#f6ad55`, `rgba(246, 173, 85, 0.4)`)
    - _Rèm:_ Xanh ngọc thanh lịch (`#319795`, `rgba(49, 151, 149, 0.4)`)
    - _Vải nội thất:_ Tím lavender (`#9f7aea`, `rgba(159, 122, 234, 0.4)`)

### R4. Đảm bảo tính toàn vẹn và Kiểm thử

- Chạy kiểm thử `pytest` để đảm bảo toàn bộ logic backend hoạt động bình thường, không gây ảnh hưởng đến logic tính toán GP và phân bổ chi phí analytic.
- Ứng dụng nạp thành công trên trình duyệt mà không phát sinh bất kỳ cảnh báo hoặc lỗi JS nào trong Console của trình duyệt.

## Acceptance Criteria

### Giao diện & Trực quan (Pastel Blue Theme)

- [ ] Ảnh nền `bg.png` được loại bỏ hoàn toàn khỏi body, thay bằng dải màu gradient lam sáng `#f0f4f8` đến `#e6ecf2`.
- [ ] Sidebar đổi màu phiến thạch đậm `#1e293b`. Các biểu tượng, chữ, và nút đồng bộ màu lam.
- [ ] Hiệu ứng quả cầu `.glow-orb` đổi sang hệ xanh pastel và tím lavender nhạt, hạt `.particle` đổi sang màu lam nhạt/trắng.

### Phạm vi hiển thị đa công ty (Default "All")

- [ ] Mặc định khi tải trang, dropdown chọn công ty hiển thị "Tất cả công ty" (all) và thanh chỉ báo Scope bar hiển thị "Tất cả công ty" (all).
- [ ] Khi chọn "Tất cả công ty", tổng số dự án và các chỉ số KPI doanh thu/chi phí hiển thị đầy đủ tổng cộng của cả Bonario và Ordinaire.
- [ ] Dropdown chọn công ty cho phép chuyển đổi mượt mà sang "Bonario" hoặc "Ordinaire" và cập nhật đúng số liệu riêng của từng công ty.

### Biểu đồ GP% nâng cao (Advanced Charts)

- [ ] Biểu đồ cột GP% tự động ẩn các khoảng trống thừa (nhờ `skipNull: true` và ánh xạ giá trị `null`).
- [ ] Cột đơn lẻ trong dải tự động giãn rộng và nằm chính giữa đẹp mắt nhờ cấu hình tỷ lệ cột (`maxBarThickness: 28`).
- [ ] Các tag hiển thị đúng màu mới trong `TAG_COLORS` ở cả biểu đồ Bar chart và biểu đồ tròn Doughnut chart.

### Kiểm thử QA

- [ ] Toàn bộ các bài test `pytest` (bao gồm `tests/test_cost_pipeline.py`) chạy thành công 100%.

## Follow-up — 2026-06-01T20:44:40+07:00

Triển khai cơ chế lưu cache nâng cao Stale-While-Revalidate (SWR) cho Bonario ROI Dashboard để người dùng khi truy cập trang web nhận được dữ liệu ngay lập tức (<50ms) từ SQLite Persistent Cache, đồng thời hệ thống tự động kiểm tra và thực hiện cập nhật lại dữ liệu từ Odoo trong nền nếu cache đã cũ mà không bắt người dùng phải chờ đợi.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Tách biệt logic lấy dữ liệu Odoo trong dashboard_service.py

- Trích xuất toàn bộ logic kết nối Odoo, ThreadPoolExecutor, tính toán dòng dự án, và tổng hợp thống kê hiện có từ phương thức `build_projects_dashboard` ra một phương thức helper riêng:
  ```python
  def _fetch_projects_dashboard_from_odoo(self, date_from: str, company_key: str) -> dict[str, Any]:
  ```
- Đảm bảo logic lấy dữ liệu này hoạt động hoàn hảo và độc lập để phục vụ cho cả luồng gọi đồng bộ lẫn luồng chạy ngầm revalidate.

### R2. Thiết lập Persistent Cache cho toàn bộ payload Dashboard

- Sử dụng SQLite `PersistentCache` (`self._db_cache`) có sẵn trong dịch vụ để lưu trữ toàn bộ payload kết quả JSON của Dashboard dưới khóa:
  `dashboard_payload:{company_key}:{date_from}`
- Trước khi lưu cache vào SQLite, tích hợp một trường `cached_at` lưu mốc thời gian dạng float (`time.time()`) bên trong payload để quản lý độ tuổi của dữ liệu.

### R3. Triển khai logic Stale-While-Revalidate (SWR)

Tại phương thức `build_projects_dashboard`:

- **Trường hợp `refresh=True` (Người dùng click "Đồng bộ Odoo"):**
  - Xóa cache Odoo cũ (`self._db_cache.clear("profitability:")`) và xóa cache payload SQLite tương ứng.
  - Gọi đồng bộ lấy dữ liệu mới từ Odoo bằng helper vừa viết, lưu kết quả (kèm `cached_at`) vào cả SQLite cache và in-memory cache, rồi trả về dữ liệu mới.
- **Trường hợp `refresh=False` (Truy cập thông thường hoặc tải trang đầu):**
  - **Bước 1:** Kiểm tra in-memory cache (`self._projects_dashboard_cache`). Nếu hợp lệ và chưa hết hạn, trả về ngay lập tức.
  - **Bước 2:** Nếu in-memory cache trống hoặc hết hạn, truy vấn SQLite Persistent Cache bằng `self._db_cache.get(db_cache_key)`.
  - **Bước 3 (Xử lý Cache Hit):** Nếu SQLite có cache:
    - Lưu cache này vào in-memory cache để tối ưu các request tiếp theo trong session.
    - Kiểm tra độ tuổi của cache (`age = time.time() - cached_at`).
    - **Nếu `age < 300` (dưới 5 phút):** Coi như dữ liệu còn **tươi (Fresh)**, trả về lập tức cho người dùng.
    - **Nếu `age >= 300` (trên 5 phút - Stale):** Coi như dữ liệu đã **cũ (Stale)**. **Lập tức trả về dữ liệu cũ này cho người dùng (thời gian phản hồi <50ms, người dùng không phải chờ đợi loading spinner!)**, đồng thời kích hoạt một Thread chạy ngầm (Daemon Thread) thực hiện gọi `_async_update_projects_dashboard` để nạp dữ liệu mới từ Odoo ngầm và ghi đè lại cache SQLite + in-memory.
  - **Bước 4 (Xử lý Cache Miss):** Nếu SQLite hoàn toàn chưa có cache:
    - Gọi đồng bộ lấy dữ liệu từ Odoo, lưu vào cả hai cache, rồi trả về.

### R4. Viết hàm chạy ngầm an toàn

- Phương thức chạy ngầm nạp lại dữ liệu:
  ```python
  def _async_update_projects_dashboard(self, date_from: str, company_key: str, cache_key: str, db_cache_key: str) -> None:
  ```
  phải được bao bọc hoàn toàn bằng khối `try-except` để tránh việc luồng chạy ngầm gặp lỗi làm sập máy chủ Flask.
- Khi chạy thành công, tự động cập nhật cả Persistent Cache (SQLite) và Memory Cache.

### R5. Viết Unit Tests kiểm thử toàn diện

- Bổ sung các hàm test trong `tests/test_cost_pipeline.py` hoặc file test mới để kiểm tra:
  - SQLite cache hit dưới 5 phút trả về dữ liệu lập tức.
  - SQLite cache hit trên 5 phút trả về dữ liệu lập tức và kích hoạt luồng chạy ngầm (revalidation thread).
  - Bypass cache khi `refresh=True`.

## Acceptance Criteria

### Tốc độ tải trang & UX

- [ ] Khi truy cập trang web (nếu SQLite đã có cache từ lần truy cập trước), giao diện **hoàn tất hiển thị ngay lập tức**, người dùng **không phải chờ đợi** màn hình tải xoay tròn "Đang đồng bộ dữ liệu doanh thu..." nữa.
- [ ] Thời gian phản hồi API `/api/projects-dashboard` when has cache đạt dưới **50ms**.
- [ ] Nút "Đồng bộ Odoo" vẫn hoạt động đúng vai trò cưỡng bức đồng bộ thời gian thực (hiển thị loading spinner cho đến khi nạp xong).

### Tính toàn vẹn của dữ liệu và luồng ngầm

- [ ] Khi dữ liệu cũ (stale) được trả về, luồng chạy ngầm tự động kích hoạt và cập nhật thành công SQLite cache mà không gây cản trở hay tạo lỗi trên giao diện người dùng.
- [ ] Khởi chạy lại dự án và vượt qua toàn bộ các bài test `pytest` thành công 100%.

## Follow-up — 2026-06-01T21:33:27+07:00

Thực hiện cải tiến toàn diện Frontend, điều chỉnh layout và sửa các lỗi giao diện còn tồn đọng trên Bonario ROI Dashboard nhằm tối ưu hóa trực quan, mang lại giao diện Soft Coastal Pastel Blue đồng bộ, mượt mà và cao cấp nhất.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Đồng bộ hệ màu Coastal Blue cho toàn bộ hiệu ứng Loading & Overlay

- **Vấn đề**: Khi nạp dữ liệu ban đầu hoặc click "Đồng bộ Odoo", hệ thống đang hiển thị vòng xoay loading overlay với màu sắc xanh lá cây cũ (`#107850` và `#0c2317`), không ăn khớp với tông Coastal Blue hiện tại.
- **Giải pháp**:
  - Cập nhật hàm `loadDashboard` trong [app.js](file:///d:/dashboard-roi-project/app.js) và hàm `showLoadingOverlay` trong [utils.js](file:///d:/dashboard-roi-project/assets/js/utils.js).
  - Thay thế toàn bộ mã màu xanh lá cây cũ bằng tông màu xanh lam của hệ màu mới (`#2b6cb0` cho viền spinner chính, và màu text `#1e293b`).
  - Tối ưu hóa backdrop-filter làm mờ nền nhẹ (`backdrop-filter: blur(4px)`) và màu nền bán trong suốt sang trọng (`rgba(240, 244, 248, 0.75)`).

### R2. Tối ưu hóa khoảng cách và thiết kế Empty State cho bảng dự án

- **Vấn đề**: Giao diện khi bộ lọc không trả về kết quả (Empty State) hiện tại hiển thị emoji `📭` đơn giản, chưa tương xứng với độ cao cấp của dashboard.
- **Giải pháp**:
  - Chỉnh sửa hàm `renderProjectsTable` trong [table.js](file:///d:/dashboard-roi-project/assets/js/components/table.js).
  - Thiết kế lại vùng hiển thị trống: sử dụng biểu tượng SVG tinh tế hoặc icon FontAwesome lớn phát sáng mờ (`fa-folder-open` hoặc `fa-inbox`), đi kèm thông điệp hướng dẫn rõ ràng, căn chỉnh padding và margin hợp lý.
  - Đảm bảo nút "✕ Xóa bộ lọc" (`clearFiltersBtn`) chèn động có CSS riêng trong [styles.css](file:///d:/dashboard-roi-project/styles.css) để nút này luôn nằm thẳng hàng, không bị lệch hoặc méo layout trên các kích thước màn hình.

### R3. Hiệu ứng chuyển cảnh và tương tác mượt mà (Micro-animations)

- **Giải pháp**:
  - Cập nhật [styles.css](file:///d:/dashboard-roi-project/styles.css) để bổ sung hiệu ứng mờ dần và trượt nhẹ (`fade-in-up`) khi vẽ lại các hàng của bảng danh sách (`#projectsTable tr`), giúp trải nghiệm đổi trang hoặc đổi bộ lọc có cảm giác mượt mà và phản hồi nhanh.
  - Thêm hover hiệu ứng phát sáng nhẹ cho các KPI cards và các thẻ Scope bar để tăng tính sinh động.

### R4. Đảm bảo tính toàn vẹn và Kiểm thử

- Đảm bảo toàn bộ ứng dụng nạp thành công trên trình duyệt mà không phát sinh bất kỳ cảnh báo hoặc lỗi JS nào trong Console.
- Chạy lại bộ unit tests và stress tests thành công 100%.

## Acceptance Criteria

### Hệ màu Loading & Overlay đồng bộ

- [ ] Vòng xoay Loading khi tải trang hoặc đồng bộ hiển thị chuẩn tông màu xanh lam Coastal Blue (`#2b6cb0` hoặc `--color-emerald`), không còn màu xanh lá cũ.
- [ ] Chữ thông báo và nền overlay sử dụng đúng hệ màu đen xám phiến thạch (`#1e293b` hoặc `--color-text-primary`) trên nền kính mờ lam nhạt.

### Thiết kế Empty State & Layout Table

- [ ] Khi bộ lọc trả về 0 kết quả, bảng hiển thị vùng trống được thiết kế đẹp mắt, cân đối và chuyên nghiệp.
- [ ] Nút "✕ Xóa bộ lọc" hiển thị thẳng hàng, cân xứng trong vùng Table Filters.
- [ ] Số lượng dự án và định dạng tiền tệ trong toàn bộ bảng không bị lỗi ngắt dòng hay rớt chữ "đ".

### Trải nghiệm tương tác & Tests

- [ ] Các hàng của bảng trượt mờ dần nhẹ nhàng khi chuyển trang hoặc áp dụng bộ lọc mới.
- [ ] Chạy bộ kiểm thử tự động `pytest` thành công 100% (23/23 tests pass).
- [ ] Chạy bộ stress test JS thành công 100% (12/12 assertions pass).

## Follow-up — 2026-06-01T22:18:30+07:00

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Nghiên cứu, phân tích và cải tiến toàn diện khía cạnh Visual (Giao diện hiển thị trực quan) và Performance (Hiệu năng tải trang, phản hồi API, render biểu đồ và bảng) của hệ thống Bonario ROI Dashboard nhằm mang lại một sản phẩm có tính thẩm mỹ và hiệu năng cao.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Phân tích & Tối ưu hóa Visual (Giao diện trực quan)

- Thực hiện rà soát toàn diện giao diện của Bonario ROI Dashboard trên các màn hình và tỷ lệ zoom khác nhau (đặc biệt là 100% và 80%).
- Tinh chỉnh khoảng cách (padding, margin), font chữ, căn lề của các khối (Scope Bar, Table Filters, KPI Cards, Project Table) để loại bỏ các khoảng trống thừa hoặc hiện tượng lệch hàng, rớt chữ.
- Đồng bộ hóa các hiệu ứng chuyển động vi mô (micro-animations), hiệu ứng hover và loading overlay với hệ màu Soft Coastal Pastel Blue chủ đạo.

### R2. Tối ưu hóa Performance (Hiệu năng hiển thị & Render)

- Phân tích hiệu năng tải trang ban đầu, thời gian phản hồi API và tốc độ render dữ liệu.
- Đảm bảo cơ chế cache SQLite và in-memory hoạt động mượt mà, tối ưu hóa các luồng revalidation chạy ngầm để không gây ảnh hưởng đến luồng chính.
- Loại bỏ hoàn toàn các lỗi layout shifts (CLS) và hiện tượng xuất hiện thanh cuộn dọc/ngang tạm thời khi chuyển trang (0.3s đầu).
- Giảm thiểu việc tính toán DOM trùng lặp và tối ưu hóa việc vẽ biểu đồ Chart.js (tránh chồng chéo canvas hoặc rò rỉ bộ nhớ).

### R3. Hệ thống kiểm thử tự động & Stress Test

- Đảm bảo toàn bộ các bài test backend (`pytest`) và frontend stress tests đều vượt qua với tỷ lệ thành công 100%.

## Acceptance Criteria

### Visual & Layout Quality

- [ ] Giao diện hiển thị cân đối hoàn toàn ở cả tỷ lệ zoom 100% và 80% mà không bị lỗi layout shift, clipping hay vỡ khung.
- [ ] Các dropdown của bộ lọc trong Table Filters nằm thẳng hàng và đẹp mắt trên màn hình Desktop, không bị rớt hàng lệch lạc.
- [ ] Thanh chỉ báo Scope Bar hiển thị cân đối tuyệt đối, không có khoảng trống thừa màu lam nhạt ở bên phải.
- [ ] Không còn bất kỳ hiện tượng xuất hiện thanh cuộn dọc/ngang tạm thời (0.3s) khi chuyển đổi giữa các trang chi tiết trong list order.

### Performance & Response Time

- [ ] Thời gian phản hồi của API `/api/projects-dashboard` đạt dưới 50ms khi lấy dữ liệu từ cache.
- [ ] Biểu đồ Chart.js và các sparklines hiển thị mượt mà, tự động resize chính xác mà không bị rò rỉ bộ nhớ hay chồng canvas cũ.
- [ ] Nút "Đồng bộ Odoo" hiển thị spinner đồng màu Coastal Blue và cập nhật chính xác dữ liệu từ Odoo ngầm.

---

_Next: when approved → delegate via invoke_subagent (see Delegation Protocol)_

## Follow-up — 2026-06-01T23:01:16+07:00

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Nghiên cứu, rà soát và điều chỉnh toàn bộ mã nguồn Bonario ROI Dashboard để đồng bộ hóa hoàn hảo cấu trúc co giãn CSS Layout tự nhiên (Native 80% Scaling) trên tất cả các trang, linh kiện, và biểu đồ dưới mức zoom mặc định 100% của trình duyệt. Đảm bảo loại bỏ hoàn toàn các lỗi tọa độ trỏ chuột của Chart.js và các vấn đề vỡ khung hiển thị.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Rà soát & Đồng bộ hóa Native 80% CSS Layout toàn trang

- Quét toàn bộ tệp `styles.css` và các tệp JS thành phần để đảm bảo hệ thống co giãn tự nhiên `font-size: 13px` hoạt động hoàn hảo trên mọi ngóc ngách của dashboard.
- Rà soát các thuộc tính kích thước cứng bằng pixel (px) như chiều rộng, khoảng cách, lề, chiều cao của tất cả các linh kiện (Overview cards, KPI cards, table filters, table rows, tag analysis panels, ranks views) và điều chỉnh giảm 20% hoặc chuyển sang đơn vị tương đối (rem/em) để đạt tính cân đối tuyệt đối.
- Đảm bảo Sidebar (240px) và Main Container chiếm trọn vẹn màn hình `100vh` một cách đẹp mắt và ổn định.

### R2. Tối ưu hóa biểu đồ & phần tử tương tác (Chart.js & Tooltips)

- Đảm bảo toàn bộ các biểu đồ Chart.js (cột GP%, tròn doanh thu, sparklines) và các phần tử tương tác khác có tọa độ rê chuột (hover/tooltip) khớp chính xác tuyệt đối với trỏ chuột dưới hệ thống layout mới.
- Tinh chỉnh các tooltip của biểu đồ hiển thị chữ rõ nét, phối màu tương phản cao (Coastal Blue theme) và không bị lệch dòng hay tràn viền.

### R3. Rà soát và Tối ưu hóa Giao diện Di động (Mobile Responsive & Zoom)

- Thực hiện rà soát sâu khả năng hiển thị responsive trên các màn hình có chiều rộng hẹp (di động, máy tính bảng) và các chế độ co giãn trình duyệt khác nhau.
- Đảm bảo các bộ lọc, thanh chỉ báo Scope Bar, bảng dự án, phân trang và footer tự động chuyển đổi sang giao diện di động một cách hoàn hảo, không có bất kỳ hiện tượng rớt chữ hoặc tràn viền ngang.

### R4. Tính toàn vẹn của mã nguồn & Kiểm thử QA

- Vượt qua 100% tất cả 28 bài unit tests backend (Python) và 12 bài stress tests frontend JS.

## Acceptance Criteria

### Giao diện & Layout (Visual Excellence)

- [ ] Toàn bộ các trang (Overview, Tags, Projects Table, Ranks Chart) hiển thị đồng bộ ở tỉ lệ co giãn 80% tự nhiên (dưới mức zoom 100% mặc định của trình duyệt) mà không bị lỗi layout shift, clipping hay vỡ khung.
- [ ] Thanh chỉ báo Scope Bar và các bộ lọc Table Filters hiển thị thẳng hàng, cân xứng tuyệt đối trên cả Desktop và di động.
- [ ] Tất cả các nhãn KPI, thẻ số liệu, nút bấm không bị rớt chữ hoặc tràn viền ngang.

### Tương tác biểu đồ & Hover (Interaction accuracy)

- [ ] Các điểm dữ liệu, cột biểu đồ Chart.js khi rê chuột hiển thị tooltip chính xác 100%, không bị lệch cột hoặc hiển thị sai thông số.
- [ ] Các Sparkline KPI cards và tooltip có màu chữ sắc nét, độ tương phản cao, hòa hợp với tông màu Soft Coastal Pastel Blue.

### Tương thích Responsive & QA Tests

- [ ] Không còn bất kỳ lỗi Console JS hay cảnh báo CSS nào xuất hiện khi chuyển trang hoặc tương tác.
- [ ] Vượt qua 100% tất cả các bài kiểm thử tự động (28/28 Python tests và 12/12 JS stress tests).

---

_Next: when approved → delegate via invoke_subagent (see Delegation Protocol)_

## Follow-up — 2026-06-01T23:50:48+07:00

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Rà soát toàn diện website và mã nguồn Bonario ROI Dashboard để đảm bảo an toàn thông tin tuyệt đối, ngăn chặn và loại bỏ mọi nguy cơ rò rỉ thông tin kết nối Odoo (URL, DB, USER_ID, API KEY) lên frontend hoặc tệp giao diện công khai.

Working directory: `d:\dashboard-roi-project`
Integrity mode: `development`

## Requirements

### R1. Kiểm toán An toàn Giao diện Frontend (Client-side Audit)

- Quét toàn bộ mã nguồn giao diện bao gồm `index.html`, `app.js`, `styles.css` và tất cả các mô-đun Javascript trong thư mục `assets/js/` để kiểm tra có bất kỳ biến, chuỗi viết cứng hoặc chú thích mã nguồn nào chứa thông tin kết nối Odoo hay không.
- Đảm bảo các kết nối API từ frontend chỉ giao tiếp thông qua các cổng API nội bộ của máy chủ Flask (như `/api/projects-dashboard` và `/api/health`) chứ không gọi trực tiếp hoặc gửi thông tin XML-RPC của Odoo về phía trình duyệt client.

### R2. Kiểm toán Đóng gói Server-side (Server-side Encapsulation)

- Xác nhận các tệp cấu hình Python (`config.py`, `app.py`, `odoo_client.py`) đọc đầy đủ các biến môi trường từ tệp `.env` cục bộ và không lưu vết cứng.
- Đảm bảo các Flask endpoint không trả về thông tin mật như `odoo_api_key` hay `odoo_password` trong các phản hồi JSON thông thường cũng như các phản hồi lỗi (error stack traces) khi Odoo gặp sự cố.

### R3. Rà soát Cơ chế Cố định Lịch sử (Git History & Logs)

- Xác nhận tệp `.gitignore` bỏ qua chính xác tất cả các tệp nhạy cảm (`.env`, `*.db`, `*.log`, `agents/`, v.v.).
- Chạy các bài kiểm thử tự động để đảm bảo tính ổn định và bảo mật của toàn bộ luồng truyền dữ liệu.

## Acceptance Criteria

### An toàn Frontend (Client-side Security)

- [ ] Không phát hiện bất kỳ chuỗi thông tin đăng nhập, API key, địa chỉ URL instance Odoo, cơ sở dữ liệu Odoo hoặc mã định danh user nào trong toàn bộ tệp HTML, JS, CSS ở phía client.
- [ ] Mọi yêu cầu truy vấn dữ liệu từ frontend được gửi an toàn đến các API endpoint cục bộ của Flask máy chủ, không có kết nối XML-RPC trực tiếp nào từ trình duyệt đến Odoo.

### An toàn API Backend (API Encapsulation)

- [ ] API endpoint `/api/health` và `/api/projects-dashboard` không trả về khóa `odoo_api_key` hoặc thông tin kết nối trong gói JSON phản hồi.
- [ ] Các thông tin đăng nhập Odoo chỉ được lưu trữ dưới dạng biến môi trường cục bộ và được đóng gói an toàn tại backend.

### Tính ổn định và QA (Stability & Testing)

- [ ] Vượt qua 100% tất cả 28 bài unit/integration tests backend (Python) và 12 bài stress tests frontend JS.

---

_Next: when approved → delegate via invoke_subagent (see Delegation Protocol)_

## Follow-up — 2026-06-02T09:49:42Z

Tái cấu trúc giao diện trang "Hiệu suất theo Tags" trên ROI Dashboard thành 5 biểu đồ trực quan cao cấp: 4 biểu đồ cột (Bar Chart) hiển thị tần suất phân bổ dự án theo dải GP% của 4 nhóm tag phổ biến nhất và 1 biểu đồ cột chồng (Stacked Bar Chart) phân chia doanh thu theo các dải giá trị (<10tr, 10-100tr, 100-200tr, >200tr) gộp chung cho cả 4 nhóm tag.

Working directory: c:\Users\Admin\Desktop\Bonario\dashboard-roi-project
Integrity mode: development

## Requirements

### R1. 4 Biểu đồ phân bổ GP% cho 4 nhóm Tag chủ đạo
- Tạo 4 biểu đồ cột (Bar Chart) độc lập hiển thị số lượng dự án phân bổ theo các dải GP% cho từng nhóm tag chính:
  1. **Nội thất rời** (Xanh lục bảo đậm, ví dụ `#107850` hoặc `var(--color-emerald)`)
  2. **Giấy dán tường** (Vàng hổ phách, ví dụ `#d97706` hoặc `var(--color-amber)`)
  3. **Rèm** (Xanh da trời/slate, ví dụ `#0284c7` hoặc `var(--color-blue)`)
  4. **Vải nội thất** (Cam đất nung, ví dụ `#ea580c` hoặc `var(--color-terracotta)`)
- Phân bổ dải GP% trên trục hoành tuân theo các khoảng: `0-20%`, `21-40%`, và từ `41%` trở đi tăng bước nhảy `5%` (ví dụ `41-45%`, `46-50%`, v.v.). Chỉ vẽ những dải thực sự có dữ liệu để tránh khoảng trắng thừa.
- Trục tung của 4 biểu đồ thể hiện số lượng dự án (project count).

### R2. 1 Biểu đồ cột chồng phân khúc Doanh thu cho cả 4 Tag
- Tạo biểu đồ thứ 5 là biểu đồ cột chồng (Stacked Bar Chart) tổng hợp cho cả 4 nhóm tag chính.
- Trục hoành của biểu đồ này gồm 4 phân khúc doanh thu dựa trên `bg_untaxed` của dự án:
  - Phân khúc dưới 10 triệu (`<10tr`)
  - Phân khúc từ 10 triệu đến dưới 100 triệu (`10-100tr`)
  - Phân khúc từ 100 triệu đến dưới 200 triệu (`100-200tr`)
  - Phân khúc từ 200 triệu trở lên (`>200tr`)
- Trục tung thể hiện tổng doanh thu tích lũy của phân khúc.
- Mỗi phân khúc (cột) trên biểu đồ sẽ gồm 4 phân đoạn màu sắc tương ứng đại diện cho tỷ trọng đóng góp doanh thu của 4 nhóm tag trong phân khúc đó (sử dụng chính xác mã màu của 4 tag).

### R3. Bố cục giao diện Glassmorphism cao cấp
- Sắp xếp 5 biểu đồ khoa học và cân đối trên trang:
  - 4 biểu đồ GP% của các tag chính được sắp xếp dưới dạng lưới 2x2 gọn gàng.
  - 1 biểu đồ doanh thu phân khúc (Stacked Bar Chart) chiếm chiều rộng đầy đủ (full-width) nằm nổi bật ở trên hoặc dưới lưới.
- Áp dụng các hiệu ứng chuyển động mượt mờ khi di chuột qua cột biểu đồ (hover tooltips), hiển thị chú thích (legends) rõ ràng.
- Giao diện đồng bộ hoàn hảo với bộ lọc thời gian và bộ lọc công ty trên Sidebar (các thay đổi bộ lọc sẽ tính toán lại và vẽ lại biểu đồ tức thời).

## Acceptance Criteria

### Bố cục giao diện & Biểu đồ
- [ ] Trang "Hiệu suất theo Tags" hiển thị chính xác 5 biểu đồ trực quan (4 biểu đồ cột đơn GP% của các tag và 1 biểu đồ cột chồng dải doanh thu gộp).
- [ ] Biểu đồ dải doanh thu gộp phân chia chính xác dự án vào 4 phân khúc giá trị và hiển thị đúng tỷ trọng màu sắc của các tag tham gia.
- [ ] Toàn bộ 5 biểu đồ đồng bộ dữ liệu thời gian thực khi chọn bộ lọc công ty hoặc khoảng thời gian.
- [ ] Không xảy ra lỗi hiển thị, chồng lấn canvas hoặc lỗi JavaScript trong bảng điều khiển của trình duyệt (Browser Console).
- [ ] Đồng bộ màu sắc 4 tag chủ đạo xuyên suốt cả 5 biểu đồ.

## Follow-up — 2026-06-24T04:28:17Z

Audit the Bonario ROI Dashboard codebase to identify potential bugs, logic flaws, security vulnerabilities, or performance bottlenecks, and implement comprehensive fixes and UX improvements to ensure a bulletproof, production-grade user experience.

Working directory: c:/Users/Admin/Desktop/Bonario/dashboard-roi-project
Integrity mode: development

## Requirements

### R1. Codebase Audit and Bug Resolution
Identify and fix any logical bugs, edge cases, potential exceptions, memory leaks, or race conditions in both backend (Python Flask application, SQLite cache system, Odoo client) and frontend (JavaScript SPA, charts rendering, router).

### R2. Performance Optimization
Optimize frontend rendering performance (including debounce mechanisms for event handlers, efficient DOM manipulation, Chart.js updates) and backend response latency (database queries, caching strategy, Odoo XML-RPC requests).

### R3. Security Hardening
Audit backend endpoints to ensure proper session authentication, prevent information disclosure, ensure rate limits are securely enforced, and ensure no credentials or secrets are leaked.

### R4. Automated Testing
Expand the existing pytest suite with new automated tests to cover all fixed bugs and improved logic, ensuring the entire test suite passes without regressions.

## Acceptance Criteria

### Execution & Cleanliness
- [ ] No hardcoded secrets, credentials, or private keys in the codebase.
- [ ] No syntax errors, linting warnings, or runtime exceptions on the frontend/backend.
- [ ] The local git repository remains on the `master` branch with all modifications kept local (no automatic push to origin).

### Verification
- [ ] All 32 existing tests in the `tests/` directory pass successfully.
- [ ] At least 3 new test cases/files are added to the `tests/` directory, testing the new fixes or optimizations.
- [ ] `python -m pytest` executes and reports 100% success rate.
