"""FE-TC-03: スタッフ・管理者ログイン"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD, seed_staff


class TestStaffLogin:
    def test_FE_03_001_staff_login_success(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "テストスタッフ", STAFF_PASSWORD, "staff")
        page.goto(f"{BASE_URL}/#/staff-login")
        page.wait_for_selector("#staff-id")
        page.fill("#staff-id", STAFF_ID)
        page.fill("#password", STAFF_PASSWORD)
        page.click("#submit-btn")
        page.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        assert "#/staff" in page.url

    def test_FE_03_002_admin_login_redirects_to_admin(self, page):
        page.goto(f"{BASE_URL}/#/staff-login")
        page.wait_for_selector("#staff-id")
        page.fill("#staff-id", ADMIN_ID)
        page.fill("#password", ADMIN_PASSWORD)
        page.click("#submit-btn")
        page.wait_for_url(lambda u: "#/admin" in u, timeout=5000)
        assert "#/admin" in page.url

    def test_FE_03_003_wrong_credentials_shows_error(self, page):
        page.goto(f"{BASE_URL}/#/staff-login")
        page.wait_for_selector("#staff-id")
        page.fill("#staff-id", "wrongid")
        page.fill("#password", "wrongpass")
        page.click("#submit-btn")
        page.wait_for_timeout(1500)
        # staff-login-form内のerrorメッセージを確認
        error = page.locator("#error-msg")
        expect(error).to_be_visible()

    def test_FE_03_004_student_link_navigates(self, page):
        page.goto(f"{BASE_URL}/#/staff-login")
        page.wait_for_selector("a[href='#/login']")
        page.click("a[href='#/login']")
        page.wait_for_timeout(500)
        assert "#/login" in page.url
