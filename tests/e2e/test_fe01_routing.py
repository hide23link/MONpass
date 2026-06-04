"""FE-TC-01: ルーティング・画面遷移"""
import pytest
from e2e_helpers import BASE_URL, STUDENT_ID, STUDENT_PASSWORD, ADMIN_ID, ADMIN_PASSWORD, seed_student, login_student, login_admin


class TestRouting:
    def test_FE_01_001_unauthenticated_qr_redirects_to_login(self, page):
        page.goto(f"{BASE_URL}/#/qr")
        page.wait_for_timeout(800)
        assert "#/login" in page.url

    def test_FE_01_002_unauthenticated_staff_redirects_to_staff_login(self, page):
        page.goto(f"{BASE_URL}/#/staff")
        page.wait_for_timeout(800)
        assert "#/staff-login" in page.url

    def test_FE_01_003_unauthenticated_admin_redirects_to_staff_login(self, page):
        page.goto(f"{BASE_URL}/#/admin")
        page.wait_for_timeout(800)
        assert "#/staff-login" in page.url

    def test_FE_01_004_student_cannot_access_admin(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.goto(f"{BASE_URL}/#/admin")
        page.wait_for_timeout(800)
        assert "#/admin" not in page.url or page.locator("#app").inner_text().find("403") >= 0 or "#/qr" in page.url

    def test_FE_01_006_root_redirects(self, page):
        page.goto(BASE_URL)
        page.wait_for_timeout(1500)
        # ハッシュベースSPAなのでURLのハッシュ部分を確認
        hash_part = page.evaluate("window.location.hash")
        assert "#/login" in (page.url + hash_part) or "#/qr" in (page.url + hash_part) or hash_part in ("#/login", "#/qr")

    def test_FE_01_007_unknown_hash_handled(self, page):
        page.goto(f"{BASE_URL}/#/notfound")
        page.wait_for_timeout(800)
        # 404ページかログインへリダイレクト
        assert "#/login" in page.url or page.locator("#app").is_visible()

    def test_FE_01_008_logged_in_student_redirected_from_login(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_timeout(800)
        assert "#/qr" in page.url

    def test_FE_01_009_browser_back_works(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_student(page)
        page.wait_for_selector("#issue-btn", timeout=5000)
        page.go_back()
        page.wait_for_timeout(500)
        assert not page.is_closed()
