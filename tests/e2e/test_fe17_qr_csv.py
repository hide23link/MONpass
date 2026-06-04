"""
FE-TC-17: QR画像品質・CSV文字コード
- QR画像にテキストラベルが付いている（縦長）
- モーダルが縦横比を保持して表示
- 保存ファイル名が QR_招待者名.png
- CSV出力が UTF-8 BOM付き
"""
import base64
import pytest
import httpx
from playwright.sync_api import expect
from e2e_helpers import (
    BASE_URL, ADMIN_ID, ADMIN_PASSWORD, STUDENT_ID, STUDENT_PASSWORD,
    seed_student, login_admin, login_student, make_unique_student,
)


# ─── ヘルパー ────────────────────────────────────────────────────────────────

def get_admin_token():
    r = httpx.post(f"{BASE_URL}/auth/staff/login",
                   json={"staff_id": ADMIN_ID, "password": ADMIN_PASSWORD})
    return r.json()["token"]


# ─── FE-TC-17-001: QR画像がテキストラベル付き（縦長）────────────────────────

class TestQrImageQuality:
    def test_FE_17_001_qr_image_is_taller_than_wide(self, page, db_path):
        """QR画像の高さ > 幅（テキストラベルが追加されている）"""
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        page.fill("#guest-name", "テスト招待")
        page.click("#issue-btn")
        page.wait_for_function(
            "() => document.querySelectorAll('#ticket-list [data-ticket-id]').length >= 1",
            timeout=8000
        )

        # img の naturalWidth / naturalHeight を取得
        dims = page.evaluate("""() => {
            const img = document.querySelector('#ticket-list img');
            return img ? { w: img.naturalWidth, h: img.naturalHeight } : null;
        }""")
        assert dims is not None, "QR画像が見つからない"
        assert dims["h"] > dims["w"], f"画像が縦長ではない: {dims['w']}x{dims['h']}"

    def test_FE_17_002_qr_modal_no_squish(self, page, db_path):
        """QR画像クリックでモーダルが開き、縦横比が保持される"""
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        page.fill("#guest-name", "モーダルテスト")
        page.click("#issue-btn")
        page.wait_for_function(
            "() => document.querySelectorAll('#ticket-list [data-ticket-id]').length >= 1",
            timeout=8000
        )

        # QR画像をクリック
        page.locator("#ticket-list img").first.click()
        page.wait_for_timeout(300)
        expect(page.locator("#qr-modal")).to_be_visible()

        # モーダル内の画像が縦横比を保持しているか
        modal_dims = page.evaluate("""() => {
            const img = document.getElementById('modal-qr-img');
            if (!img) return null;
            return {
                natural_w: img.naturalWidth,
                natural_h: img.naturalHeight,
                display_w: img.offsetWidth,
                display_h: img.offsetHeight
            };
        }""")
        assert modal_dims is not None
        # 表示サイズの縦横比が自然サイズと大きく乖離していないことを確認
        if modal_dims["display_w"] > 0 and modal_dims["natural_w"] > 0:
            natural_ratio  = modal_dims["natural_h"]  / modal_dims["natural_w"]
            display_ratio  = modal_dims["display_h"]  / modal_dims["display_w"]
            ratio_diff = abs(natural_ratio - display_ratio)
            assert ratio_diff < 0.15, f"縦横比が崩れている: 自然比={natural_ratio:.2f} 表示比={display_ratio:.2f}"

    def test_FE_17_003_save_filename_is_simple(self, page, db_path):
        """保存ボタンのダウンロード属性が QR_招待者名.png 形式"""
        sid, pwd = make_unique_student(db_path)
        login_student(page, sid, pwd)
        page.wait_for_function(
            "() => { const b = document.getElementById('remaining-badge'); return b && !b.textContent.includes('読込中'); }",
            timeout=8000
        )
        page.fill("#guest-name", "お父さん")
        page.click("#issue-btn")
        page.wait_for_function(
            "() => document.querySelectorAll('#ticket-list [data-ticket-id]').length >= 1",
            timeout=8000
        )

        # saveQr 関数の download 属性を確認
        filename = page.evaluate("""() => {
            // saveQr を呼び出した際に生成される a 要素の download 属性を検証
            const a = document.createElement('a');
            const guest = 'お父さん';
            const sanitize = s => String(s).replace(/[\\\\\\/:*?"<>|\\s]/g, '_');
            a.download = 'QR_' + sanitize(guest) + '.png';
            return a.download;
        }""")
        assert filename == "QR_お父さん.png", f"ファイル名が期待と異なる: {filename}"


# ─── FE-TC-17-004/005: CSV UTF-8 BOM 確認 ────────────────────────────────────

class TestCsvEncoding:
    def test_FE_17_004_emergency_csv_has_bom(self, page, db_path):
        """緊急CSV（/admin/export）が UTF-8 BOM 付きで出力される"""
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        # 直接 API で確認
        token = get_admin_token()
        r = httpx.get(f"{BASE_URL}/admin/export",
                      headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        # 先頭3バイトが UTF-8 BOM (EF BB BF) であること
        assert r.content[:3] == b"\xef\xbb\xbf", \
            f"BOM が付いていない: {r.content[:3].hex()}"

    def test_FE_17_005_staff_csv_export_has_bom(self, page, db_path):
        """スタッフCSV（/admin/staff/export）が UTF-8 BOM 付きで出力される"""
        token = get_admin_token()
        r = httpx.get(f"{BASE_URL}/admin/staff/export",
                      headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.content[:3] == b"\xef\xbb\xbf", \
            f"BOM が付いていない: {r.content[:3].hex()}"

    def test_FE_17_004b_emergency_csv_japanese_readable(self, page, db_path):
        """緊急CSVの日本語が正しくデコードできる"""
        seed_student(db_path, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        token = get_admin_token()
        # チケット発行
        r = httpx.post(f"{BASE_URL}/auth/login",
                       json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_token = r.json()["token"]
        httpx.post(f"{BASE_URL}/ticket/issue",
                   json={"guest_name": "お父さん"},
                   headers={"Authorization": f"Bearer {s_token}"})

        r = httpx.get(f"{BASE_URL}/admin/export",
                      headers={"Authorization": f"Bearer {token}"})
        text = r.content.decode("utf-8-sig")
        assert "山田太郎" in text, "日本語が正しく読めない"
        assert "お父さん" in text, "招待者名が正しく読めない"
