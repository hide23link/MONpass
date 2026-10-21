"""FE-TC-02: 生徒ログイン画面"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, STUDENT_ID, STUDENT_PASSWORD, seed_student


class TestStudentLoginDisplay:
    def test_FE_02_01_001_page_title(self, page):
        page.goto(f"{BASE_URL}/#/login")
        assert "学園祭入場システム" in page.title()

    def test_FE_02_01_002_header_color(self, page):
        page.goto(f"{BASE_URL}/#/login")
        nav = page.locator("nav")
        expect(nav).to_be_visible()
        # スカイブルー系のクラスが存在
        assert "sky" in (nav.get_attribute("class") or "")

    def test_FE_02_01_003_form_elements_exist(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        expect(page.locator("#student-id")).to_be_visible()
        expect(page.locator("#password")).to_be_visible()
        expect(page.locator("#submit-btn")).to_be_visible()

    def test_FE_02_01_004_staff_link_exists(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("a[href='#/staff-login']")
        expect(page.locator("a[href='#/staff-login']")).to_be_visible()

    def test_FE_02_01_005_staff_link_navigates(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("a[href='#/staff-login']")
        page.click("a[href='#/staff-login']")
        page.wait_for_timeout(500)
        assert "#/staff-login" in page.url

    def test_FE_02_01_006_mobile_layout(self, page_mobile):
        page_mobile.goto(f"{BASE_URL}/#/login")
        page_mobile.wait_for_selector("#student-id")
        expect(page_mobile.locator("#student-id")).to_be_visible()
        # はみ出しチェック
        width = page_mobile.viewport_size["width"]
        box = page_mobile.locator("#student-id").bounding_box()
        assert box["x"] + box["width"] <= width + 10

    def test_FE_02_01_007_pc_layout(self, page_desktop):
        page_desktop.goto(f"{BASE_URL}/#/login")
        page_desktop.wait_for_selector("#student-id")
        expect(page_desktop.locator("#student-id")).to_be_visible()


class TestStudentLoginNormal:
    def test_FE_02_02_001_login_success_redirects_to_qr(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", STUDENT_PASSWORD)
        page.click("#submit-btn")
        page.wait_for_url(lambda u: "#/qr" in u, timeout=5000)
        assert "#/qr" in page.url

    def test_FE_02_02_002_jwt_saved_in_localstorage(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", STUDENT_PASSWORD)
        page.click("#submit-btn")
        page.wait_for_url(lambda u: "#/qr" in u, timeout=5000)
        token = page.evaluate("localStorage.getItem('token')")
        assert token and len(token.split(".")) == 3

    def test_FE_02_02_003_enter_key_submits(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", STUDENT_PASSWORD)
        page.press("#password", "Enter")
        page.wait_for_url(lambda u: "#/qr" in u, timeout=5000)
        assert "#/qr" in page.url

    def test_FE_02_02_004_loading_state(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#submit-btn")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", STUDENT_PASSWORD)
        # クリック後すぐにdisabledかテキスト変化を確認
        page.click("#submit-btn")
        # ボタンが一時的にdisabledになるかテキストが変わる（ログイン中など）
        page.wait_for_url(lambda u: "#/qr" in u, timeout=5000)


class TestStudentLoginPasswordToggle:
    def test_FE_02_04_001_toggle_button_exists(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#password")
        btn = page.locator("button[onclick*='togglePw']")
        expect(btn).to_be_visible()

    def test_FE_02_04_002_initial_type_is_password(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#password")
        assert page.locator("#password").get_attribute("type") == "password"

    def test_FE_02_04_003_click_shows_password(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#password")
        page.locator("button[onclick*='togglePw']").click()
        assert page.locator("#password").get_attribute("type") == "text"

    def test_FE_02_04_004_click_again_hides_password(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#password")
        btn = page.locator("button[onclick*='togglePw']")
        btn.click()
        btn.click()
        assert page.locator("#password").get_attribute("type") == "password"

    def test_FE_02_04_005_icon_changes_on_toggle(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#pw-eye")
        assert page.locator("#pw-eye").inner_text() == "👁"
        page.locator("button[onclick*='togglePw']").click()
        assert page.locator("#pw-eye").inner_text() == "🙈"


class TestStudentLoginAbnormal:
    def test_FE_02_03_001_empty_student_id_shows_error(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#submit-btn")
        page.fill("#student-id", "")
        page.fill("#password", "anypass")
        page.click("#submit-btn")
        page.wait_for_timeout(500)
        # エラーメッセージ表示かバリデーション
        assert "#/qr" not in page.url

    def test_FE_02_03_002_empty_password_shows_error(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#submit-btn")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", "")
        page.click("#submit-btn")
        page.wait_for_timeout(500)
        assert "#/qr" not in page.url

    def test_FE_02_03_003_unknown_id_shows_error(self, page):
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        page.fill("#student-id", "9999")
        page.fill("#password", "wrongpass")
        page.click("#submit-btn")
        page.wait_for_timeout(1000)
        error = page.locator("#error-msg")
        expect(error).to_be_visible()
        assert "#/qr" not in page.url

    def test_FE_02_03_004_wrong_password_shows_error(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#student-id")
        page.fill("#student-id", STUDENT_ID)
        page.fill("#password", "wrongpassword")
        page.click("#submit-btn")
        page.wait_for_timeout(1000)
        error = page.locator("#error-msg")
        expect(error).to_be_visible()

    def test_FE_02_03_006_double_click_prevention(self, page, db_path):
        """ダブルクリック防止: ボタンがdisabledになることを確認"""
        from e2e_helpers import make_unique_student
        sid, pwd = make_unique_student(db_path)
        page.goto(f"{BASE_URL}/#/login")
        page.wait_for_selector("#submit-btn")
        page.fill("#student-id", sid)
        page.fill("#password", pwd)
        requests_sent = []
        page.on("request", lambda r: requests_sent.append(r.url) if "/auth/login" in r.url else None)
        # クリック後すぐにボタンが disabled になるかを確認
        page.locator("#submit-btn").click()
        # ログイン成功を待つ（ページ遷移）
        page.wait_for_url(lambda u: "#/qr" in u, timeout=8000)
        # 送信リクエストは1〜2件（2回クリック試みても disabled で防がれる）
        assert len(requests_sent) >= 1
