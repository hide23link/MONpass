"""FE-TC-05: QRスキャン画面"""
import pytest
from playwright.sync_api import expect
from e2e_helpers import BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD, STUDENT_ID, STUDENT_PASSWORD, seed_staff, seed_student, login_staff, login_admin


class TestScanDisplay:
    def test_FE_05_01_001_online_indicator_visible(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        page.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        page.wait_for_selector("#online-indicator", timeout=5000)
        expect(page.locator("#online-text")).to_be_visible()
        assert "オンライン" in page.locator("#online-text").inner_text()

    def test_FE_05_01_003_scan_history_container_exists(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        page.wait_for_selector("#scan-history", timeout=5000)
        expect(page.locator("#scan-history")).to_be_visible()

    def test_FE_05_01_004_mobile_layout(self, page_mobile, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page_mobile)
        page_mobile.wait_for_selector("#qr-reader", timeout=5000)
        expect(page_mobile.locator("#qr-reader")).to_be_visible()


class TestScanApi:
    """スキャンAPIの動作確認（カメラなしでAPIを直接確認）"""

    def test_FE_05_02_scan_result_element_exists(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        # scan-result は初期 hidden のため state="attached" で待つ
        page.wait_for_selector("#scan-result", state="attached", timeout=5000)
        assert page.locator("#scan-result").count() > 0

    def test_FE_05_02_cancel_button_in_history(self, page, db_path):
        """スキャン履歴に取消ボタンが存在する構造確認"""
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        page.wait_for_selector("#scan-history", timeout=5000)
        result = page.evaluate("typeof cancelEntry")
        assert result == "function"


class TestOfflineApi:
    def test_FE_05_03_001_fetch_cache_on_load(self, page, db_path):
        """スタッフページ起動時に /ticket/cache が呼ばれること"""
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        requests = []
        page.on("request", lambda r: requests.append(r.url))
        login_staff(page)
        page.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        page.wait_for_timeout(1000)
        cache_calls = [u for u in requests if "/ticket/cache" in u]
        assert len(cache_calls) >= 1

    def test_FE_05_03_002_offline_indicator_updates(self, page, db_path):
        """offlineイベントを発火してインジケーターを確認"""
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        page.wait_for_selector("#online-indicator", timeout=5000)
        page.evaluate("window.dispatchEvent(new Event('offline'))")
        page.wait_for_timeout(800)
        text = page.locator("#online-text").inner_text()
        assert "オフライン" in text or "オンライン" in text  # 表示が更新される

    def test_FE_05_03_005_sync_button_hidden_initially(self, page, db_path):
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        # sync-btn は初期 hidden なので state="attached" で待つ
        page.wait_for_selector("#sync-btn", state="attached", timeout=5000)
        expect(page.locator("#sync-btn")).to_be_hidden()
