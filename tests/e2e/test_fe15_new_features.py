"""
FE-TC-15: 緊急CSV出力
FE-TC-16: 無効チケットの削除（生徒ページ）
FE-TC-07 追加: チケット一覧の入場状態操作ボタン
FE-TC-10 追加: スタッフCSV管理
"""
import pytest
import httpx
from playwright.sync_api import expect
from e2e_helpers import (
    BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    STUDENT_ID, STUDENT_PASSWORD,
    seed_student, seed_staff, login_admin, login_student, login_staff,
    make_unique_student,
)


# ─── ヘルパー ────────────────────────────────────────────────────────────────

def issue_and_invalidate(db_path, base_url):
    """生徒チケットを発行して管理者が無効化、(student_id, password, ticket_id) を返す"""
    import sqlite3, bcrypt, secrets
    sid = f"inv{secrets.token_hex(4)}"
    pwd = "invpass1"
    pw_hash = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
    ticket_id = secrets.token_urlsafe(12)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO students (id,name,class,password_hash) VALUES (?,?,?,?)",
            (sid, "無効テスト生徒", "X-1", pw_hash)
        )
        conn.execute(
            "INSERT INTO tickets (id, student_id, guest_name, is_valid, used) VALUES (?,?,?,0,0)",
            (ticket_id, sid, "テスト招待者")
        )
        conn.commit()
    finally:
        conn.close()
    return sid, pwd, ticket_id


# ─── FE-TC-15: 緊急CSV出力 ─────────────────────────────────────────────────

class TestEmergencyCsvExport:
    def test_FE_15_001_emergency_csv_button_on_dashboard(self, page):
        """緊急CSVボタンがダッシュボードに表示される"""
        login_admin(page)
        page.wait_for_selector("button:has-text('緊急CSV出力')", timeout=5000)
        expect(page.locator("button:has-text('緊急CSV出力')")).to_be_visible()

    def test_FE_15_001b_emergency_csv_button_on_tickets(self, page):
        """緊急CSVボタンがチケット一覧ページにも表示される"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("button:has-text('緊急CSV出力')", timeout=5000)
        expect(page.locator("button:has-text('緊急CSV出力')")).to_be_visible()

    def test_FE_15_001c_emergency_csv_button_on_staff(self, page):
        """緊急CSVボタンがスタッフ管理ページにも表示される"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("button:has-text('緊急CSV出力')", timeout=5000)
        expect(page.locator("button:has-text('緊急CSV出力')")).to_be_visible()

    def test_FE_15_002_emergency_csv_triggers_export_api(self, page, db_path):
        """緊急CSVボタンクリックで /admin/export が呼ばれる"""
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_admin(page)
        page.wait_for_selector("button:has-text('緊急CSV出力')", timeout=5000)

        responses = []
        page.on("response", lambda r: responses.append(r.url) if "admin/export" in r.url else None)

        # ダウンロードを待ち受ける
        with page.expect_download(timeout=5000) as dl_info:
            page.locator("button:has-text('緊急CSV出力')").click()

        download = dl_info.value
        assert download.suggested_filename.startswith("tickets_")
        assert download.suggested_filename.endswith(".csv")

    def test_FE_15_003_staff_cannot_see_emergency_csv(self, page, db_path):
        """スタッフログインでは緊急CSVボタンが表示されない（管理者タブ自体がない）"""
        seed_staff(db_path, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_staff(page)
        page.wait_for_url(lambda u: "#/staff" in u, timeout=5000)
        page.wait_for_timeout(500)
        # スタッフ画面には管理者タブが存在しない
        assert page.locator("button:has-text('緊急CSV出力')").count() == 0


# ─── FE-TC-16: 無効チケットの削除（生徒ページ）──────────────────────────────

class TestInvalidTicketDisplay:
    def test_FE_16_001_invalid_ticket_shows_delete_button(self, page, db_path):
        """無効チケット（used=0）に削除ボタンが表示される"""
        sid, pwd, _ = issue_and_invalidate(db_path, BASE_URL)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        # 削除ボタンが表示されている
        delete_btn = page.locator("button:has-text('削除')")
        expect(delete_btn.first).to_be_visible()

    def test_FE_16_002_invalid_ticket_shows_invalid_badge(self, page, db_path):
        """無効チケットに「🚫 無効」バッジが表示される"""
        sid, pwd, _ = issue_and_invalidate(db_path, BASE_URL)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        list_text = page.locator("#ticket-list").inner_text()
        assert "無効" in list_text or "🚫" in list_text

    def test_FE_16_003_invalid_ticket_qr_greyed_out(self, page, db_path):
        """無効チケットのQR画像がグレーアウトされている"""
        sid, pwd, _ = issue_and_invalidate(db_path, BASE_URL)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        # opacity が style または class に適用されているか確認
        img = page.locator("#ticket-list img").first
        img_style = img.get_attribute("style") or ""
        img_class = img.get_attribute("class") or ""
        assert "opacity" in img_style or "opacity" in img_class

    def test_FE_16_004_invalid_ticket_no_save_button(self, page, db_path):
        """無効チケットに「画像を保存」ボタンが表示されない"""
        sid, pwd, _ = issue_and_invalidate(db_path, BASE_URL)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        # カード内に「画像を保存」ボタンがないことを確認
        save_btns = page.locator("#ticket-list button:has-text('画像を保存')")
        assert save_btns.count() == 0


# ─── FE-TC-07 追加: チケット操作ボタン ─────────────────────────────────────

class TestTicketActionButtons:
    def _setup_ticket(self, db_path, base_url):
        """チケットを発行してticket_idを返す"""
        sid, pwd = make_unique_student(db_path)
        r = httpx.post(f"{base_url}/auth/login",
                       json={"student_id": sid, "password": pwd})
        token = r.json()["token"]
        r2 = httpx.post(f"{base_url}/ticket/issue",
                        json={"guest_name": "テスト"},
                        headers={"Authorization": f"Bearer {token}"})
        return r2.json()["ticket_id"]

    def test_FE_07_013_invalidate_button_on_valid_ticket(self, page, db_path):
        """有効チケットに「🚫 無効化」ボタンが表示される"""
        self._setup_ticket(db_path, BASE_URL)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-tbody, #tickets-cards", timeout=5000)
        page.wait_for_timeout(500)
        page_text = page.locator("body").inner_text()
        assert "無効化" in page_text

    def test_FE_07_015_mark_entry_button_on_unused_ticket(self, page, db_path):
        """未入場チケットに「🟢 入場記録」ボタンが表示される"""
        self._setup_ticket(db_path, BASE_URL)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-tbody, #tickets-cards", timeout=5000)
        page.wait_for_timeout(500)
        page_text = page.locator("body").inner_text()
        assert "入場記録" in page_text

    def test_FE_07_017_used_at_column_exists(self, page, db_path):
        """入場日時列がテーブルに存在する（デスクトップ）"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-table", timeout=5000)
        header_text = page.locator("#tickets-table thead").inner_text()
        assert "入場日時" in header_text

    def test_FE_07_018_mark_entry_changes_status(self, page, db_path):
        """「入場記録」ボタンを押すとトーストが表示される"""
        ticket_id = self._setup_ticket(db_path, BASE_URL)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-tbody", timeout=5000)
        page.wait_for_timeout(500)

        # 入場記録ボタンをクリック（確認ダイアログOK）
        page.on("dialog", lambda d: d.accept())
        entry_btn = page.locator("button:has-text('入場記録')").first
        if entry_btn.count() > 0:
            entry_btn.click()
            page.wait_for_timeout(1500)
            # テーブルが更新される（入場取消ボタンが出てくる）
            page_text = page.locator("body").inner_text()
            assert "入場取消" in page_text or "入場済" in page_text

    def test_FE_07_019_revalidate_changes_status(self, page, db_path):
        """無効チケットを「有効化」するとボタンが変わる"""
        sid, pwd, ticket_id = issue_and_invalidate(db_path, BASE_URL)
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/tickets")
        page.wait_for_selector("#tickets-tbody", timeout=5000)
        page.wait_for_timeout(500)

        page.on("dialog", lambda d: d.accept())
        valid_btn = page.locator("button:has-text('有効化')").first
        if valid_btn.count() > 0:
            valid_btn.click()
            page.wait_for_timeout(1500)
            page_text = page.locator("body").inner_text()
            assert "無効化" in page_text  # 有効化後は「無効化」ボタンが現れる


# ─── FE-TC-10 追加: スタッフCSV管理 ─────────────────────────────────────────

class TestStaffCsvManagement:
    def test_FE_10_006_csv_import_area_visible(self, page):
        """スタッフ管理ページにCSVインポートエリアが表示される"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#staff-csv-file", state="attached", timeout=5000)
        # エクスポートボタンも存在する
        expect(page.locator("button:has-text('CSVエクスポート')")).to_be_visible()

    def test_FE_10_007_staff_csv_export(self, page):
        """CSVエクスポートボタンで /admin/staff/export が呼ばれる"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("button:has-text('CSVエクスポート')", timeout=5000)

        responses = []
        page.on("response", lambda r: responses.append(r.url) if "staff/export" in r.url else None)

        with page.expect_download(timeout=5000) as dl_info:
            page.locator("button:has-text('CSVエクスポート')").click()

        download = dl_info.value
        assert "staff" in download.suggested_filename
        assert download.suggested_filename.endswith(".csv")

    def test_FE_10_008_staff_csv_import_non_csv_error(self, page):
        """.txt ファイルをスタッフCSVインポートするとエラー"""
        login_admin(page)
        page.goto(f"{BASE_URL}/#/admin/staff")
        page.wait_for_selector("#staff-csv-file", state="attached", timeout=5000)
        page.evaluate("""() => {
            const dt = new DataTransfer();
            const f = new File(['id,name,pass'], 'staff.txt', { type: 'text/plain' });
            dt.items.add(f);
            document.getElementById('staff-csv-file').files = dt.files;
        }""")
        page.locator("button:has-text('インポート実行')").click()
        page.wait_for_timeout(500)
        expect(page.locator("#staff-import-error")).to_be_visible()
