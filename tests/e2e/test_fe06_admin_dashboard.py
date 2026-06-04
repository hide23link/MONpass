"""FE-TC-06: 管理者ダッシュボード"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STUDENT_ID, STUDENT_PASSWORD, seed_student, login_admin


class TestDashboardLayout:
    def test_FE_06_01_001_tabs_visible(self, page):
        login_admin(page)
        page.wait_for_selector("#admin-tabs", timeout=5000)
        tabs = page.locator("#admin-tabs a")
        assert tabs.count() >= 6

    def test_FE_06_01_002_active_tab_highlighted(self, page):
        login_admin(page)
        page.wait_for_selector("#admin-tabs", timeout=5000)
        active_tab = page.locator("#admin-tabs a[data-tab='dashboard']")
        classes = active_tab.get_attribute("class") or ""
        assert "sky" in classes or "border-sky" in classes

    def test_FE_06_01_003_tab_click_navigates(self, page):
        login_admin(page)
        page.wait_for_selector("#admin-tabs", timeout=5000)
        page.locator("#admin-tabs a[data-tab='tickets']").click()
        page.wait_for_url(lambda u: "#/admin/tickets" in u, timeout=3000)
        assert "#/admin/tickets" in page.url

    def test_FE_06_01_004_pc_three_column_cards(self, page_desktop):
        login_admin(page_desktop)
        page_desktop.wait_for_selector("#total-entries", timeout=5000)
        # 3枚のサマリーカードが存在する
        expect(page_desktop.locator("#total-entries")).to_be_visible()
        expect(page_desktop.locator("#unused-count")).to_be_visible()
        expect(page_desktop.locator("#issued-students")).to_be_visible()


class TestDashboardData:
    def test_FE_06_02_001_total_entries_displayed(self, page):
        login_admin(page)
        page.wait_for_selector("#total-entries", timeout=5000)
        text = page.locator("#total-entries").inner_text()
        assert text.strip() != "" and text.strip() != "-"

    def test_FE_06_02_002_unused_count_displayed(self, page):
        login_admin(page)
        page.wait_for_selector("#unused-count", timeout=5000)
        text = page.locator("#unused-count").inner_text()
        assert text.strip() != "" and text.strip() != "-"

    def test_FE_06_02_003_chart_rendered(self, page):
        login_admin(page)
        page.wait_for_selector("#entry-chart", timeout=5000)
        expect(page.locator("#entry-chart")).to_be_visible()

    def test_FE_06_02_004_polling_does_not_break(self, page):
        """30秒待たずに2回アクセスして200が返ることを確認"""
        responses = []
        page.on("response", lambda r: responses.append(r) if "/admin/dashboard" in r.url else None)
        login_admin(page)
        page.wait_for_timeout(500)
        page.reload()
        page.wait_for_selector("#total-entries", timeout=5000)
        dashboard_responses = [r for r in responses if "/admin/dashboard" in r.url]
        assert all(r.status == 200 for r in dashboard_responses)

    def test_FE_06_02_005_student_table_visible(self, page, db_path):
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.wait_for_selector("#student-table", timeout=5000)
        expect(page.locator("#student-table")).to_be_visible()

    def test_FE_06_02_006_promote_tree_visible(self, page):
        login_admin(page)
        page.wait_for_selector("#promote-tree", timeout=5000)
        expect(page.locator("#promote-tree")).to_be_visible()
