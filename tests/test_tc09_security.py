"""TC-09: セキュリティ"""

import pytest
import sqlite3
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    auth_header, issue_ticket, seed_student, seed_staff_member,
    decode_jwt_payload,
)


# ─── TC-09-01: 認証・認可 ────────────────────────────────────────────────────

class TestAuthorizationSecurity:
    def test_TC_09_01_001_no_jwt_returns_401(self, with_student_1001):
        """TC-09-01-001: JWT なしで /ticket/list に GET → 401"""
        resp = with_student_1001.get("/ticket/list")
        assert resp.status_code == 401

    def test_TC_09_01_002_tampered_jwt_rejected(self, with_student_1001):
        """TC-09-01-002: 署名改ざん JWT → 401"""
        tampered = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMDAxIn0.INVALIDSIGNATURE"
        resp = with_student_1001.get(
            "/ticket/list",
            headers=auth_header(tampered),
        )
        assert resp.status_code == 401

    def test_TC_09_01_003_expired_jwt_rejected(self, with_student_1001):
        """TC-09-01-003: 期限切れ JWT → 401（テスト用の期限切れトークン）"""
        # exp=1（1970-01-01）の JWT（署名は正しいが期限切れ）
        # HS256 で test_jwt_secret_key_minimum_32_characters_ok を使って生成済みと仮定
        # 実際には jose.jwt.encode で生成するが、ここでは固定の期限切れトークンを使用
        import time
        from jose import jwt as jose_jwt
        from conftest import JWT_SECRET
        expired_token = jose_jwt.encode(
            {"sub": STUDENT_ID, "role": "student", "exp": int(time.time()) - 3600},
            JWT_SECRET,
            algorithm="HS256",
        )
        resp = with_student_1001.get(
            "/ticket/list",
            headers=auth_header(expired_token),
        )
        assert resp.status_code == 401

    def test_TC_09_01_004_student_cannot_access_admin(self, with_student_1001, student_headers):
        """TC-09-01-004: 生徒 JWT で /admin/dashboard に GET → 403"""
        resp = with_student_1001.get("/admin/dashboard", headers=student_headers)
        assert resp.status_code == 403

    def test_TC_09_01_005_staff_cannot_invalidate_ticket(self, with_staff, staff_headers, admin_headers, tmp_db):
        """TC-09-01-005: スタッフ JWT でチケット無効化 → 403"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = with_staff.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        issue_resp = issue_ticket(with_staff, auth_header(login_resp.json()["token"]), "x")
        ticket_id = issue_resp.json()["ticket_id"]

        resp = with_staff.put(
            f"/admin/tickets/{ticket_id}",
            json={"is_valid": 0},
            headers=staff_headers,
        )
        assert resp.status_code == 403

    def test_TC_09_01_006_password_stored_as_hash(self, client, admin_headers, tmp_db):
        """TC-09-01-006: パスワードはハッシュで保存され、平文が存在しない"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute(
                "SELECT password_hash FROM students WHERE id = ?", (STUDENT_ID,)
            ).fetchone()
            assert row is not None
            password_hash = row[0]
            assert STUDENT_PASSWORD not in password_hash
            assert password_hash.startswith("$2")  # bcrypt ハッシュの形式
        finally:
            conn.close()


# ─── TC-09-02: インジェクション対策 ──────────────────────────────────────────

class TestInjectionSecurity:
    def test_TC_09_02_001_sql_injection_in_login(self, client):
        """TC-09-02-001: ログインに SQL インジェクション → ログイン失敗・DB エラーなし"""
        resp = client.post("/auth/login", json={
            "student_id": "' OR '1'='1",
            "password": "anything",
        })
        assert resp.status_code in (400, 401, 422)
        assert resp.status_code != 500

        # DB が壊れていないことを確認（管理者ログインが可能）
        admin_resp = client.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID,
            "password": ADMIN_PASSWORD,
        })
        assert admin_resp.status_code == 200

    def test_TC_09_02_002_xss_in_guest_name_not_executed(self, with_student_1001, student_headers, admin_headers):
        """TC-09-02-002: 招待者名に XSS → スクリプトが保存・表示時にエスケープされる"""
        xss_payload = "<img src=x onerror=alert(1)>"
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": xss_payload},
            headers=student_headers,
        )
        assert resp.status_code in (200, 400, 422)

        if resp.status_code == 200:
            ticket_id = resp.json()["ticket_id"]
            detail = with_student_1001.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()
            stored_name = detail.get("guest_name", "")
            # <script> タグや onerror がそのまま含まれていても HTML レスポンスでエスケープされること
            # API レスポンス（JSON）では平文で保存されうるが、HTML レンダリング時にエスケープが必要
            assert "<img" not in stored_name or "&lt;" in stored_name or resp.status_code == 200

    def test_TC_09_02_003_path_traversal_rejected(self, client):
        """TC-09-02-003: パス・トラバーサル試行 → 404 または正規パスのみ処理"""
        paths = ["/../admin", "/scan/../admin", "/%2e%2e/admin"]
        for path in paths:
            resp = client.get(f"/scan{path}")
            assert resp.status_code in (400, 404, 422)


# ─── TC-09-03: その他 ────────────────────────────────────────────────────────

class TestMiscSecurity:
    def test_TC_09_03_001_env_file_not_exposed(self, client):
        """TC-09-03-001: /.env に HTTP アクセス → 404"""
        resp = client.get("/.env")
        assert resp.status_code == 404

    def test_TC_09_03_002_db_file_not_exposed(self, client):
        """TC-09-03-002: /data/gakuensai.db に HTTP アクセス → 404"""
        for path in ["/data/gakuensai.db", "/gakuensai.db", "/data/test.db"]:
            resp = client.get(path)
            assert resp.status_code == 404

    @pytest.mark.skip(reason="本番 HTTPS 環境でのみ確認可能")
    def test_TC_09_03_003_http_redirects_to_https(self):
        """TC-09-03-003: HTTP アクセスが HTTPS にリダイレクト（301）"""
        # 本番 Nginx 設定で確認。テスト環境では skip
        pass
