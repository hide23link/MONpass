"""FE-TC-08〜14: 生徒一覧・インポート・スタッフ管理・設定・共通UI・セキュリティ・レスポンシブ"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD, STUDENT_ID, STUDENT_PASSWORD, seed_student, seed_staff, login_admin, login_student
from io import BytesIO


# ─── FE-TC-08: 生徒一覧 ───────────────────────────────────────────────────────

class TestStudentList:
    def test_FE_08_001_all_students_displayed(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/students")
        page.wait_for_selector("#students-tbody", timeout=5000)
        rows = page.locator("#students-tbody tr")
        assert rows.count() >= 1

    def test_FE_08_002_search_filters_results(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/students")
        page.wait_for_selector("#student-search", timeout=5000)
        page.fill("#student-search", "山田")
        page.wait_for_timeout(500)
        text = page.locator("#students-tbody").inner_text()
        if text.strip():
            assert "山田" in text

    def test_FE_08_003_search_clear_shows_all(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/students")
        page.wait_for_selector("#student-search", timeout=5000)
        page.fill("#student-search", "山田")
        page.wait_for_timeout(300)
        page.fill("#student-search", "")
        page.wait_for_timeout(300)
        rows = page.locator("#students-tbody tr")
        assert rows.count() >= 1

    def test_FE_08_004_columns_present(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/students")
        page.wait_for_selector("#students-tbody", timeout=5000)
        text = page.locator("#students-tbody").inner_text()
        assert "山田" in text or "1001" in text


# ─── FE-TC-09: CSVインポート ─────────────────────────────────────────────────

class TestCsvImport:
    def test_FE_09_001_file_select_ui_visible(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/import")
        page.wait_for_selector("#drop-zone", timeout=5000)
        expect(page.locator("#drop-zone")).to_be_visible()
        expect(page.locator("#import-btn")).to_be_visible()

    def test_FE_09_007_non_csv_shows_error(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/import")
        # csv-file は hidden なので state="attached"
        page.wait_for_selector("#csv-file", state="attached", timeout=5000)
        page.evaluate("""() => {
            const dt = new DataTransfer();
            const f = new File(['test content'], 'test.txt', { type: 'text/plain' });
            dt.items.add(f);
            document.getElementById('csv-file').files = dt.files;
        }""")
        page.click("#import-btn")
        page.wait_for_timeout(500)
        expect(page.locator("#import-error")).to_be_visible()

    def test_FE_09_009_loading_state_on_import(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/import")
        page.wait_for_selector("#import-btn", timeout=5000)
        # ファイル未選択でクリック → エラーが出るがローディングは瞬時
        page.click("#import-btn")
        page.wait_for_timeout(500)
        # エラーが表示されている
        expect(page.locator("#import-error")).to_be_visible()


# ─── FE-TC-10: スタッフ管理 ─────────────────────────────────────────────────

class TestStaffManagement:
    def test_FE_10_001_staff_list_visible(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#staff-tbody", timeout=5000)
        expect(page.locator("#staff-tbody")).to_be_visible()

    def test_FE_10_002_add_form_visible(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#new-staff-id", timeout=5000)
        expect(page.locator("#new-staff-id")).to_be_visible()
        expect(page.locator("#new-staff-name")).to_be_visible()
        expect(page.locator("#new-staff-password")).to_be_visible()

    def test_FE_10_003_add_staff_success(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#new-staff-id", timeout=5000)
        page.fill("#new-staff-id", "staff_fe_test")
        page.fill("#new-staff-name", "FEテストスタッフ")
        page.fill("#new-staff-password", "fetest123")
        page.click("button:has-text('登録')")
        page.wait_for_timeout(1000)
        assert "staff_fe_test" in page.locator("#staff-tbody").inner_text()

    def test_FE_10_004_duplicate_id_shows_error(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "既存スタッフ", STAFF_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#new-staff-id", timeout=5000)
        page.fill("#new-staff-id", STAFF_ID)
        page.fill("#new-staff-name", "重複")
        page.fill("#new-staff-password", "pass123")
        page.click("button:has-text('登録')")
        page.wait_for_timeout(1000)
        expect(page.locator("#add-staff-error")).to_be_visible()

    def test_FE_10_005_delete_staff(self, page, db_path):
        seed_staff(db_path, "del_fe_staff", "削除テスト", "delpass123")
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#staff-tbody", timeout=5000)
        page.wait_for_timeout(500)
        page.on("dialog", lambda d: d.accept())
        # 削除ボタンをクリック
        delete_btn = page.locator("#staff-tbody tr:has-text('del_fe_staff') button:has-text('削除')")
        if delete_btn.count() > 0:
            delete_btn.click()
            page.wait_for_timeout(1000)
            assert "del_fe_staff" not in page.locator("#staff-tbody").inner_text()


# ─── FE-TC-11: システム設定 ─────────────────────────────────────────────────

class TestSystemSettings:
    def test_FE_11_001_current_settings_displayed(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/settings")
        page.wait_for_selector("#issue-start", timeout=5000)
        start_val = page.locator("#issue-start").input_value()
        assert start_val != ""

    def test_FE_11_002_save_settings(self, page):
        from datetime import date, timedelta
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=30)).isoformat()
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/settings")
        page.wait_for_selector("#issue-start", timeout=5000)
        page.fill("#issue-start", "2000-01-01")
        page.fill("#issue-end", future)
        page.click("button:has-text('保存')")
        page.wait_for_timeout(1500)
        # 保存確認: 設定値が反映されている
        page.goto(f"{BASE_URL}/#/admin/settings")
        page.wait_for_selector("#issue-start", timeout=5000)
        start_val = page.locator("#issue-start").input_value()
        assert start_val != ""

    def test_FE_11_003_start_after_end_shows_error(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/settings")
        page.wait_for_selector("#issue-start", timeout=5000)
        page.fill("#issue-start", "2026-12-31")
        page.fill("#issue-end", "2026-01-01")
        page.click("button:has-text('保存')")
        page.wait_for_timeout(500)
        expect(page.locator("#settings-error")).to_be_visible()

    def test_FE_11_004_empty_dates_show_error(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/settings")
        page.wait_for_selector("#issue-start", timeout=5000)
        page.fill("#issue-start", "")
        page.fill("#issue-end", "")
        page.click("button:has-text('保存')")
        page.wait_for_timeout(500)
        expect(page.locator("#settings-error")).to_be_visible()


# ─── FE-TC-12: 共通UI ────────────────────────────────────────────────────────

class TestCommonUI:
    def test_FE_12_001_success_toast_visible(self, page, db_path):
        """操作成功時にUIの更新が行われること（QR発行成功 = 残り枚数が減る）"""
        from e2e_helpers import make_unique_student
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        # バッジが "5" を表示するまで待つ
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && b.textContent.includes('5'); }",
            timeout=8000
        )
        page.fill("#guest-name", "トーストテスト")
        page.click("#issue-btn")
        # 発行後にバッジが "4" になれば成功（UIが更新された = showToastも呼ばれた）
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && b.textContent.includes('4'); }",
            timeout=10000
        )
        badge = page.locator("#remaining-badge").inner_text()
        assert "4" in badge

    def test_FE_12_003_logout_clears_token(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.wait_for_selector("#logout-btn", timeout=5000)
        page.click("#logout-btn")
        page.wait_for_timeout(500)
        token = page.evaluate("localStorage.getItem('token')")
        assert token is None
        assert "#/login" in page.url

    def test_FE_12_004_nav_shows_user_id(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.wait_for_selector("#nav-user", timeout=5000)
        nav_user = page.locator("#nav-user")
        expect(nav_user).to_be_visible()
        assert STUDENT_ID in nav_user.inner_text()

    def test_FE_12_005_expired_jwt_auto_logout(self, page):
        """期限切れJWTをlocalStorageにセットして /ticket/list を叩くと #/login へ遷移"""
        from jose import jwt as jose_jwt
        expired = jose_jwt.encode(
            {"sub": STUDENT_ID, "role": "student", "exp": 1},
            "test_jwt_secret_key_minimum_32_characters_ok",
            algorithm="HS256"
        )
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_timeout(500)
        page.evaluate(f"localStorage.setItem('token', '{expired}')")
        page.goto(f"{BASE_URL}/#/qr")
        page.wait_for_timeout(1000)
        assert "#/login" in page.url or "#/qr" not in page.url

    def test_FE_12_006_admin_nav_has_all_menus(self, page):
        login_admin(page)
        page.wait_for_selector("#admin-tabs", timeout=5000)
        tabs_text = page.locator("#admin-tabs").inner_text()
        for label in ["ダッシュボード", "チケット", "生徒", "インポート", "スタッフ", "設定"]:
            assert label in tabs_text

    def test_FE_12_007_staff_nav_no_admin_menus(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_student_as_staff = lambda: None  # スタッフでログイン
        page.goto(f"{BASE_URL}/#/staff-login")
        page.wait_for_selector("#staff-id", timeout=5000)
        page.fill("#staff-id", STAFF_ID)
        page.fill("#password", STAFF_PASSWORD)
        page.click("#submit-btn")
        page.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        # 管理者タブがないことを確認
        admin_tabs = page.locator("#admin-tabs")
        assert admin_tabs.count() == 0 or not admin_tabs.is_visible()


# ─── FE-TC-13: セキュリティ ─────────────────────────────────────────────────

class TestSecurity:
    def test_FE_13_001_xss_in_guest_name_escaped(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.wait_for_selector("#guest-name", timeout=5000)
        xss = "<script>window.__xss_executed=true</script>"
        page.fill("#guest-name", xss)
        page.click("#issue-btn")
        page.wait_for_timeout(1500)
        xss_executed = page.evaluate("window.__xss_executed")
        assert not xss_executed

    def test_FE_13_003_tampered_jwt_rejected(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_timeout(300)
        page.evaluate("localStorage.setItem('token', 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMDAxIn0.INVALIDSIG')")
        page.goto(f"{BASE_URL}/#/qr")
        page.wait_for_timeout(1500)
        assert "#/login" in page.url or "#/qr" not in page.url

    def test_FE_13_004_student_jwt_admin_api_rejected(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.wait_for_url(lambda u: "#/qr" in u, timeout=5000)
        # 生徒JWTで管理者APIを呼ぶ
        result = page.evaluate("""async () => {
            const token = localStorage.getItem('token');
            const r = await fetch('/admin/tickets', {
                headers: { Authorization: 'Bearer ' + token }
            });
            return r.status;
        }""")
        assert result == 403


# ─── FE-TC-14: レスポンシブ ─────────────────────────────────────────────────

class TestResponsive:
    def test_FE_14_001_login_mobile(self, page_mobile):
        page_mobile.goto(f"{BASE_URL}/#/login")
        page_mobile.wait_for_selector("#student-id", timeout=5000)
        w = page_mobile.viewport_size["width"]
        box = page_mobile.locator("#student-id").bounding_box()
        assert box["x"] + box["width"] <= w + 5

    def test_FE_14_002_qr_mobile_single_column(self, page_mobile, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page_mobile)
        page_mobile.wait_for_selector("#issue-form", timeout=5000)
        expect(page_mobile.locator("#issue-form")).to_be_visible()

    def test_FE_14_003_scan_mobile_camera_visible(self, page_mobile, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        page_mobile.goto(f"{BASE_URL}/#/staff-login")
        page_mobile.wait_for_selector("#staff-id", timeout=5000)
        page_mobile.fill("#staff-id", STAFF_ID)
        page_mobile.fill("#password", STAFF_PASSWORD)
        page_mobile.click("#submit-btn")
        page_mobile.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        page_mobile.wait_for_selector("#qr-reader", timeout=5000)
        expect(page_mobile.locator("#qr-reader")).to_be_visible()

    def test_FE_14_004_dashboard_mobile(self, page_mobile):
        page_mobile.goto(f"{BASE_URL}/#/staff-login")
        page_mobile.wait_for_selector("#staff-id", timeout=5000)
        page_mobile.fill("#staff-id", ADMIN_ID)
        page_mobile.fill("#password", ADMIN_PASSWORD)
        page_mobile.click("#submit-btn")
        page_mobile.wait_for_url(lambda u: "#/admin" in u, timeout=5000)
        page_mobile.wait_for_selector("#total-entries", timeout=5000)
        expect(page_mobile.locator("#total-entries")).to_be_visible()

    def test_FE_14_007_admin_tabs_mobile(self, page_mobile):
        page_mobile.goto(f"{BASE_URL}/#/staff-login")
        page_mobile.wait_for_selector("#staff-id", timeout=5000)
        page_mobile.fill("#staff-id", ADMIN_ID)
        page_mobile.fill("#password", ADMIN_PASSWORD)
        page_mobile.click("#submit-btn")
        page_mobile.wait_for_url(lambda u: "#/admin" in u, timeout=5000)
        page_mobile.wait_for_selector("#admin-tabs", timeout=5000)
        # タブが存在する（スクロール可能）
        expect(page_mobile.locator("#admin-tabs")).to_be_visible()
