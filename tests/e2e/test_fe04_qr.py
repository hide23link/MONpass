"""FE-TC-04: QR発行・一覧画面"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, STUDENT_ID, STUDENT_PASSWORD, seed_student, login_student, make_unique_student


def wait_for_qr_loaded(page):
    """QRページのAPI読み込み完了を待つ"""
    page.wait_for_function(
        "() => document.getElementById('remaining-badge') && "
        "!document.getElementById('remaining-badge').textContent.includes('読込中')",
        timeout=8000
    )


class TestQrDisplay:
    def test_FE_04_01_001_remaining_count_initial(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        badge = page.locator("#remaining-badge").inner_text()
        assert "5" in badge

    def test_FE_04_01_002_remaining_count_after_issue(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        page.fill("#guest-name", "テスト発行")
        page.click("#issue-btn")
        page.wait_for_function(
            "() => document.getElementById('remaining-badge') && "
            "document.getElementById('remaining-badge').textContent.includes('4')",
            timeout=8000
        )
        badge = page.locator("#remaining-badge").inner_text()
        assert "4" in badge

    def test_FE_04_01_003_form_hidden_after_5_issues(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        for name in ["a", "b", "c", "d", "e"]:
            page.fill("#guest-name", name)
            page.click("#issue-btn")
            page.wait_for_timeout(1200)
        page.wait_for_function("() => document.getElementById('limit-reached') && !document.getElementById('limit-reached').classList.contains('hidden')", timeout=8000)
        expect(page.locator("#issue-form")).to_be_hidden()
        expect(page.locator("#limit-reached")).to_be_visible()

    def test_FE_04_01_004_qr_image_size(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        page.fill("#guest-name", "サイズテスト")
        page.click("#issue-btn")
        page.wait_for_function("() => document.querySelectorAll('#ticket-list img').length > 0", timeout=8000)
        img = page.locator("#ticket-list img").first
        box = img.bounding_box()
        assert box is not None
        assert box["width"] >= 60

    def test_FE_04_01_005_pc_two_column_layout(self, page_desktop, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page_desktop, sid, pwd)
        wait_for_qr_loaded(page_desktop)
        grid = page_desktop.locator(".grid.grid-cols-1.lg\\:grid-cols-2")
        expect(grid).to_be_visible()

    def test_FE_04_01_006_mobile_single_column(self, page_mobile, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page_mobile, sid, pwd)
        wait_for_qr_loaded(page_mobile)
        expect(page_mobile.locator("#issue-form")).to_be_visible()


def issue_and_wait(page, guest_name):
    """チケット発行してカードが追加されるまで待つ"""
    page.fill("#guest-name", guest_name)
    page.click("#issue-btn")
    page.wait_for_function(
        f"() => document.querySelector('#ticket-list [data-ticket-id]') !== null",
        timeout=8000
    )


class TestQrIssue:
    def test_FE_04_02_001_issue_success_adds_card(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "カード追加テスト")
        cards = page.locator("#ticket-list [data-ticket-id]")
        assert cards.count() >= 1

    def test_FE_04_02_002_issued_card_content(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "カード内容テスト")
        card = page.locator("#ticket-list [data-ticket-id]").first
        assert "カード内容テスト" in card.inner_text()
        expect(card.locator("img")).to_be_visible()
        expect(card.locator("button", has_text="画像を保存")).to_be_visible()

    def test_FE_04_02_003_empty_guest_name_shows_error(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        page.fill("#guest-name", "")
        page.click("#issue-btn")
        page.wait_for_timeout(500)
        expect(page.locator("#issue-error")).to_be_visible()

    def test_FE_04_02_005_form_reset_after_issue(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "リセットテスト")
        assert page.locator("#guest-name").input_value() == ""


class TestQrListActions:
    def test_FE_04_03_001_save_button_exists(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "保存テスト")
        expect(page.locator("button", has_text="画像を保存").first).to_be_visible()

    def test_FE_04_03_002_qr_image_click_opens_modal(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "モーダルテスト")
        page.locator("#ticket-list img").first.click()
        expect(page.locator("#qr-modal")).to_be_visible()

    def test_FE_04_03_003_delete_unused_ticket(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "削除テスト")
        page.on("dialog", lambda d: d.accept())
        page.locator("button", has_text="削除").first.click()
        page.wait_for_function("() => !document.querySelector('#ticket-list').textContent.includes('削除テスト')", timeout=5000)
        assert page.locator("#ticket-list").inner_text().find("削除テスト") == -1

    def test_FE_04_03_004_delete_cancel_keeps_ticket(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        wait_for_qr_loaded(page)
        issue_and_wait(page, "キャンセルテスト")
        page.on("dialog", lambda d: d.dismiss())
        page.locator("button", has_text="削除").first.click()
        page.wait_for_timeout(500)
        assert "キャンセルテスト" in page.locator("#ticket-list").inner_text()


class TestPromoteButton:
    def test_FE_04_04_001_promote_button_visible(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        page.wait_for_selector("#promote-btn", timeout=5000)
        expect(page.locator("#promote-btn")).to_be_visible()

    def test_FE_04_04_002_promote_btn_shows_qr_modal(self, page, db_path):
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        page.wait_for_selector("#promote-btn", timeout=5000)
        page.click("#promote-btn")
        page.wait_for_timeout(1000)
        expect(page.locator("#promote-modal")).to_be_visible()
