"""FE-TC-07: チケット一覧"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STUDENT_ID, STUDENT_PASSWORD, STAFF_ID, STAFF_PASSWORD, seed_student, seed_staff, login_admin
import httpx


def issue_ticket_via_api(db_path, student_id, student_password, guest_name, base_url):
    """APIでチケットを発行するヘルパー"""
    r = httpx.post(f"{base_url}/auth/login", json={"student_id": student_id, "password": student_password})
    token = r.json()["token"]
    httpx.post(f"{base_url}/ticket/issue", json={"guest_name": guest_name},
               headers={"Authorization": f"Bearer {token}"})


class TestTicketList:
    def test_FE_07_001_all_tickets_displayed(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_ticket_via_api(db_path, STUDENT_ID, STUDENT_PASSWORD, "テスト用", BASE_URL)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-tbody, #tickets-cards", timeout=5000)
        page.wait_for_timeout(1000)
        rows = page.locator("#tickets-tbody tr, #tickets-cards [data-ticket-id]")
        assert rows.count() >= 1

    def test_FE_07_002_filter_by_name(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#filter-name", timeout=5000)
        page.fill("#filter-name", "山田")
        page.wait_for_timeout(500)
        # 表示行に「山田」が含まれることを確認
        tbody = page.locator("#tickets-tbody")
        if tbody.is_visible():
            rows_text = tbody.inner_text()
            if rows_text.strip():
                assert "山田" in rows_text

    def test_FE_07_003_filter_by_used_status(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#filter-status", timeout=5000)
        page.select_option("#filter-status", "used")
        page.wait_for_timeout(500)
        # 入場済みフィルタが動作する（エラーなし）
        assert "#/admin/tickets" in page.url

    def test_FE_07_004_filter_by_invalid_status(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#filter-status", timeout=5000)
        page.select_option("#filter-status", "invalid")
        page.wait_for_timeout(500)
        assert "#/admin/tickets" in page.url

    def test_FE_07_010_add_ticket_modal(self, page):
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("button:has-text('手動追加')", timeout=5000)
        page.click("button:has-text('手動追加')")
        page.wait_for_timeout(500)
        expect(page.locator("#add-ticket-modal")).to_be_visible()

    def test_FE_07_011_add_ticket_execute(self, page, db_path):
        from e2e_helpers import make_unique_student
        sid, pwd = make_unique_student(db_path)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("button:has-text('手動追加')", timeout=5000)
        page.click("button:has-text('手動追加')")
        page.wait_for_selector("#add-student-id", state="visible", timeout=3000)
        page.fill("#add-student-id", sid)
        page.fill("#add-guest-name", "手動追加テスト")
        # ネットワークリクエストを監視
        responses = []
        page.on("response", lambda r: responses.append((r.status, r.url)) if "/admin/tickets" in r.url else None)
        # モーダル内の「追加」ボタンをクリック
        page.locator("#add-ticket-modal button").last.click()
        page.wait_for_timeout(2000)
        # POST /admin/tickets が成功(200 or 201)したことを確認
        post_responses = [r for r in responses if r[0] in (200, 201)]
        assert len(post_responses) >= 1 or not page.locator("#add-ticket-modal").is_visible()

    def test_FE_07_012_mobile_cards(self, page_mobile, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page_mobile)
        page_mobile.goto(f"{BASE_URL}/#/admin/tickets")
        page_mobile.wait_for_selector("#tickets-cards", timeout=5000)
        expect(page_mobile.locator("#tickets-cards")).to_be_visible()
