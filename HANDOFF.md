# HANDOFF — SA-1 (Bảo mật & Hạ tầng)

## 1. SEC-01: Kết quả quét Working Tree & Lịch sử Git

### 1.1. Quét Working Tree (không đọc `.env`)
- **Hardcoded API Key / Secret**: Không còn file nào trong working tree chứa API key hardcode (đã được loại bỏ khỏi 4 script điều tra trong commit `9ffd129`).
- **Chuỗi `bonario-vietnam.odoo.com` còn xuất hiện trong working tree**:
  - `tests/conftest.py:9` — Hằng số `PROD_HOST` phục vụ guard chặn production (hợp lệ).
  - `tests/test_production_security.py` — Chỉ xuất hiện duy nhất trong `test_odoo_block_prod_guard` để kiểm thử chặn `SystemExit("PROD BLOCKED")` (hợp lệ).
  - Các file ngoài phạm vi quyền sửa của SA-1 (cần Lead xử lý thêm nếu muốn dọn sạch hoàn toàn URL prod khỏi test/script):
    - `tests/test_encapsulation.py` (dòng 25, 46, 56, 67, 74, 85, 99, 103, 114, 127)
    - `tests/investigate_shipping.py:12`
    - `tests/investigate_shipping_detail.py:13`
    - `tests/survey_shipping_master.py:15`
    - `tests/verify_shipping_fix.py:11`

### 1.2. Quét Lịch sử Git (chỉ báo cáo, tuyệt đối không rewrite history)
- **Commit từng chứa hardcoded Odoo API key (40-char hex literal)**:
  - `faf8547` (`2026-07-05`, *"feat: implement interactive monthly shipping detail modal and optimize cache warmer locking"*):
    - Các file bị ảnh hưởng trong commit:
      - `tests/investigate_shipping.py`
      - `tests/investigate_shipping_detail.py`
      - `tests/survey_shipping_master.py`
      - `tests/verify_shipping_fix.py`
  - `9ffd129` (`2026-10-14`, *"chore(security): read Odoo key from env in investigation scripts"*): Đã xóa key hardcode khỏi working tree ở 4 file trên.
- **Các commit từng chứa chuỗi `bonario-vietnam.odoo.com`**:
  - `b4517b4` (`2026-06-02`): `tests/test_encapsulation.py`
  - `faf8547` (`2026-07-05`): `tests/investigate_shipping.py`, `tests/investigate_shipping_detail.py`, `tests/survey_shipping_master.py`, `tests/verify_shipping_fix.py`
  - `9ffd129` (`2026-10-14`): `tests/investigate_shipping_detail.py`, `tests/survey_shipping_master.py`, `tests/verify_shipping_fix.py`
  - `f822888` (`2026-10-14`): `tests/conftest.py` (guard chặn prod)

---

## 2. Các thay đổi đã thực hiện bởi SA-1

### 2.1. `config.py`
- Mở rộng dataclass `Settings` với giá trị mặc định an toàn (tương thích ngược 100% với mọi lệnh gọi `Settings(...)` hiện có):
  - `behind_proxy: bool = False` (đọc từ `BEHIND_PROXY == "1"`)
  - `odoo_block_prod: bool = False` (đọc từ `ODOO_BLOCK_PROD == "1"`)
  - `shipping_analytic_ids: tuple[int, ...] = ()` (đọc từ `SHIPPING_ANALYTIC_IDS`, phân tách dấu phẩy)
  - `allowed_sale_order_states: tuple[str, ...] = ("sale",)` (đọc từ `ALLOWED_SO_STATES`, mặc định `"sale"`)

### 2.2. `odoo_client.py` (Luật 1 & Sanitization)
- Thêm `_assert_not_prod()` trong cả `OdooAPI.__init__` và `OdooAPI.call_method`:
  - Khi `os.getenv("ODOO_BLOCK_PROD", "1") == "1"`, nếu `self.url` chứa `"bonario-vietnam.odoo.com"` hoặc `self.db == "bonario-vietnam"`, lập tức `raise SystemExit("PROD BLOCKED")` trước khi tạo kết nối mạng.
- Sửa `OdooAPI._sanitize`:
  - Luôn che `api_key`, `db`, `url`, `netloc`, `hostname`, subdomain (`>= 3` ký tự), và `str(self.user_id)` / `str(self.uid)` (hỗ trợ cả `uid` 3 chữ số như `208` cũng như `uid` ngắn qua regex word-boundary).

### 2.3. `app.py` (SEC-02 & G-02)
- **SEC-02**:
  - Xóa bỏ `"unittest" in sys.modules or "pytest" in sys.modules` khỏi `require_auth`. Chỉ cho phép bypass `@require_auth` khi `app.testing or app.config.get("TESTING") is True`.
  - Chỉ tự động khởi chạy `service.start_background_warmer` khi `not app.testing and not app.config.get("TESTING") and "unittest" not in sys.modules and "pytest" not in sys.modules and os.environ.get("DISABLE_WARMER") != "1"`.
- **G-02**:
  - Chỉ bọc `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)` khi `settings.behind_proxy` hoặc `os.getenv("BEHIND_PROXY", "0") == "1"`.
  - Sử dụng `hmac.compare_digest` khi kiểm tra `username` và `password` trong `/api/login`.
  - Thiết lập `PERMANENT_SESSION_LIFETIME = timedelta(hours=12)` và đánh dấu `session.permanent = True` khi đăng nhập thành công.
  - Validate chặt `POST /api/projects-dashboard/update-giai-trinh`: từ chối `bool`, chuỗi không phải số nguyên dương cho `project_id` (`400`), kiểm tra `isinstance(giai_trinh, str)` và `len <= 5000` (`400`), trả HTTP `502` khi `service.update_project_giai_trinh(...)` trả về `False`.
  - Đưa `@app.errorhandler(ValueError)` qua `_sanitize_error_message(error, settings)`.
  - Thêm endpoint `GET /api/shipping/unassigned` hỗ trợ cả JSON và CSV (`format=csv` xuất UTF-8-SIG gồm các cột `date,move_name,ref,partner_name,name,amount,shipping_account_id,shipping_account_name,company_name,is_po`).

### 2.4. `cache.py` (F-05)
- Nâng cấp `PersistentCache`:
  - Thêm cột `expires_at REAL` vào bảng `cache` và `owner_id TEXT` vào bảng `locks`, tự động `ALTER TABLE` nếu mở file DB cũ.
  - Dùng chung `threading.Lock` theo `db_path.resolve()` ở cấp class (`PersistentCache._db_locks`) để các instance cùng trỏ vào 1 file SQLite luôn đồng bộ thread-safe.
  - `set(key, value, ttl=None)` tính và lưu `expires_at = now + effective_ttl`.
  - `get(key, allow_stale=False)` và `get_with_meta(key, allow_stale=False)` kiểm tra `expires_at`, tự động xóa dòng hết hạn (khi `allow_stale=False`), và tự phục hồi khi JSON lỗi hoặc SQLite DB hỏng (xóa key hỏng / tái tạo bảng, trả `None` thay vì crash 500).
  - `cleanup_expired()` xóa theo `WHERE (expires_at IS NOT NULL AND ? > expires_at) OR (expires_at IS NULL AND ? - created_at > ?)` để instance có `ttl=1800` không bao giờ xóa nhầm các key `dashboard_payload:*` có `ttl=30 ngày`.
  - `acquire_warmer_lock(lock_key, lock_ttl=None, owner_id=None, ttl_seconds=None)` và `release_warmer_lock(lock_key, owner_id=None)` hỗ trợ `owner_id` (tương thích ngược với cả tham số `lock_ttl` và `ttl_seconds`).

---

## 3. Ghi chú phối hợp cho Lead & SA-2 (`dashboard_service.py`)

1. **Hợp nhất Cache & Warmer Lock trong `dashboard_service.py`**:
   - `PersistentCache` hiện đã hỗ trợ `ttl` riêng trên từng lệnh `set(key, value, ttl=...)` và chia sẻ `_lock` theo `db_path`. `DashboardService` có thể dùng chung 1 instance `PersistentCache` hoặc giữ `self._db_cache` / `self._profitability_cache` mà không còn xung đột lock hay lỗi `cleanup_expired()` xóa nhầm dữ liệu.
   - Trong `start_background_warmer`, có thể truyền `owner_id` (ví dụ `f"{os.getpid()}:{threading.get_ident()}:{uuid.uuid4().hex}"`) vào `acquire_warmer_lock("warmer_lock", ttl_seconds=300, owner_id=owner_id)` và `release_warmer_lock("warmer_lock", owner_id=owner_id)`.
   - Trong `update_project_in_all_caches`, nếu ghi trực tiếp SQL vào bảng `cache`, nên bảo toàn cột `expires_at` (hoặc dùng `self._db_cache.set(key, payload)`).
2. **Endpoint `/api/shipping/unassigned`**:
   - `app.py` gọi `service.get_unassigned_shipping_items(date_from=date_from, company=company)` nếu method này tồn tại trên `DashboardService`.
3. **Lưu ý về `tests/test_encapsulation.py` (ngoài phạm vi file của SA-1)**:
   - File `tests/test_encapsulation.py` hiện đang khởi tạo `OdooAPI(url="https://bonario-vietnam.odoo.com", ...)` và gọi `self.client.get("/api/redirect/sale-order/45")` mà chưa bật `self.app.config["TESTING"] = True`. Do Luật 1 (`ODOO_BLOCK_PROD=1` mặc định) và SEC-02 (bắt buộc `TESTING=True` mới bypass `@require_auth`), Lead cần đổi URL mock trong `tests/test_encapsulation.py` sang `https://test.odoo.example.com` và thêm `self.app.config["TESTING"] = True` trong `setUp()`.
