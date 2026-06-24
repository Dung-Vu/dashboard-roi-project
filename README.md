# Bonario ROI Dashboard

Dự án **Bonario ROI Dashboard** là một ứng dụng web Single Page Application (SPA) được thiết kế theo phong cách giao diện Biophilic Modern Glassmorphism (Aura Forest Theme 2.0).

Hệ thống kết nối trực tiếp với nguồn dữ liệu Odoo dưới dạng Read-Only để phân tích, tính toán và hiển thị các chỉ số hiệu quả đầu tư (ROI) cũng như Tỷ suất lợi nhuận gộp (Gross Profit - GP) của các dự án.

## Các Tính Năng Chính
* **Đồng bộ dữ liệu Odoo**: Tự động lấy thông tin từ các đơn bán hàng (Sale Order) và chi phí thực tế liên quan đến từng dự án để tính toán và phân tích hiệu suất tài chính.
* **Giao diện Trực quan Biophilic**: Thiết kế màu sắc hài hòa (Moss, Mint, Emerald), tích hợp các hiệu ứng chuyển động mượt mà, quả cầu năng lượng hiển thị sức khỏe dự án (ROI Health Orbs), và các đường xu hướng (Sparklines).
* **Bảng Xếp Hạng & Phân Tích Tag**: Hệ thống phân tích đóng góp doanh thu theo các nhóm sản phẩm (Nội thất rời, Giấy dán tường, Rèm) cùng bảng xếp hạng Tag Performance Leaderboard với hiệu ứng trực quan sinh động.
* **Bảo Mật Thông Tin**: Cơ chế ẩn và mã hóa thông tin nhạy cảm của Odoo (API Key, URL, Database Name) trong quá trình truyền dữ liệu và nhật ký lỗi nhằm đảm bảo an toàn tuyệt đối.

## Kiến Trúc Hệ Thống
* **Backend**: Flask (Python) chịu trách nhiệm kết nối Odoo, xử lý nghiệp vụ, tính toán phân bổ chi phí, caching dữ liệu và cung cấp API bảo mật cho Frontend.
* **Frontend**: Vanilla HTML5, CSS3 và Javascript (ES Modules) đảm bảo hiệu năng tải trang nhanh, mượt mà và trực quan hóa dữ liệu thông qua Chart.js.
