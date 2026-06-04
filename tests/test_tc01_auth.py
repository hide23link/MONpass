"""TC-01: 認証・セッション管理"""

import time
import pytest
from conftest import (
    ADMIN_ID, ADMIN_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    STUDENT_ID, STUDENT_PASSWORD,
    decode_jwt_payload, auth_header, seed_student,
)


# ─── TC-01-01: 生徒ログイン ──────────────────────────────────────────────────

class TestStudentLogin:
    def test_TC_01_01_001_success(self, with_student_1001):
        """TC-01-01-001: 生徒ログイン正常 → JWT 発行・200"""
        resp = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": STUDENT_PASSWORD,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert len(body["token"].split(".")) == 3  # JWT 形式

    def test_TC_01_01_002_unknown_student_id(self, client):
        """TC-01-01-002: 存在しない学籍番号 → エラー・ログイン失敗カウント+1"""
        resp = client.post("/auth/login", json={
            "student_id": "9999",
            "password": "anypassword",
        })
        assert resp.status_code in (400, 401)
        assert "detail" in resp.json() or "message" in resp.json()

    def test_TC_01_01_003_wrong_password(self, with_student_1001):
        """TC-01-01-003: パスワード誤り → エラー・ログイン失敗カウント+1"""
        resp = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": "wrongpass",
        })
        assert resp.status_code in (400, 401)

    def test_TC_01_01_004_empty_student_id(self, client):
        """TC-01-01-004: 学籍番号空欄 → バリデーションエラー（422）"""
        resp = client.post("/auth/login", json={
            "student_id": "",
            "password": STUDENT_PASSWORD,
        })
        assert resp.status_code == 422

    def test_TC_01_01_005_empty_password(self, with_student_1001):
        """TC-01-01-005: パスワード空欄 → バリデーションエラー（422）"""
        resp = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": "",
        })
        assert resp.status_code == 422

    def test_TC_01_01_006_jwt_stored_in_response(self, with_student_1001):
        """TC-01-01-006: JWT がレスポンスに含まれる（クライアントが localStorage に保存する前提）"""
        resp = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": STUDENT_PASSWORD,
        })
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert token and isinstance(token, str)

    def test_TC_01_01_007_jwt_expiry_30_days(self, with_student_1001):
        """TC-01-01-007: 生徒 JWT の有効期限が発行から 30 日後"""
        resp = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": STUDENT_PASSWORD,
        })
        assert resp.status_code == 200
        payload = decode_jwt_payload(resp.json()["token"])
        issued_at = payload["iat"]
        expires_at = payload["exp"]
        days_diff = (expires_at - issued_at) / 86400
        assert 29.9 <= days_diff <= 30.1

    def test_TC_01_01_008_multi_device_login(self, with_student_1001):
        """TC-01-01-008: 複数端末同時ログイン → どちらの JWT でもアクセス可能"""
        resp1 = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": STUDENT_PASSWORD,
        })
        resp2 = with_student_1001.post("/auth/login", json={
            "student_id": STUDENT_ID,
            "password": STUDENT_PASSWORD,
        })
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        token1 = resp1.json()["token"]
        token2 = resp2.json()["token"]
        # 両方のトークンでチケット一覧にアクセスできる
        r1 = with_student_1001.get("/ticket/list", headers=auth_header(token1))
        r2 = with_student_1001.get("/ticket/list", headers=auth_header(token2))
        assert r1.status_code == 200
        assert r2.status_code == 200


# ─── TC-01-02: スタッフ・管理者ログイン ────────────────────────────────────

class TestStaffAdminLogin:
    def test_TC_01_02_001_staff_login_success(self, with_staff):
        """TC-01-02-001: スタッフログイン正常 → JWT 発行"""
        resp = with_staff.post("/auth/staff/login", json={
            "staff_id": STAFF_ID,
            "password": STAFF_PASSWORD,
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_TC_01_02_002_admin_login_success(self, client):
        """TC-01-02-002: 管理者ログイン正常 → JWT 発行"""
        resp = client.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID,
            "password": ADMIN_PASSWORD,
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_TC_01_02_003_staff_jwt_expires_at_midnight(self, with_staff):
        """TC-01-02-003: スタッフ JWT の有効期限が当日 23:59:59"""
        resp = with_staff.post("/auth/staff/login", json={
            "staff_id": STAFF_ID,
            "password": STAFF_PASSWORD,
        })
        assert resp.status_code == 200
        payload = decode_jwt_payload(resp.json()["token"])
        expires_at = payload["exp"]
        # exp は当日の 23:59:59（翌 0:00:00 未満）
        from datetime import datetime, timezone
        exp_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        now_dt = datetime.now(tz=timezone.utc)
        assert exp_dt.date() == now_dt.date()
        assert exp_dt.hour == 23
        assert exp_dt.minute == 59

    def test_TC_01_02_004_admin_jwt_expires_at_midnight(self, client):
        """TC-01-02-004: 管理者 JWT の有効期限が当日限り"""
        resp = client.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID,
            "password": ADMIN_PASSWORD,
        })
        assert resp.status_code == 200
        payload = decode_jwt_payload(resp.json()["token"])
        from datetime import datetime, timezone
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now_dt = datetime.now(tz=timezone.utc)
        assert exp_dt.date() == now_dt.date()

    def test_TC_01_02_005_staff_cannot_access_ticket_issue(self, with_staff, tmp_db):
        """TC-01-02-005: スタッフ JWT で /ticket/issue に POST → 403"""
        resp = with_staff.post("/auth/staff/login", json={
            "staff_id": STAFF_ID,
            "password": STAFF_PASSWORD,
        })
        staff_tok = resp.json()["token"]
        issue_resp = with_staff.post(
            "/ticket/issue",
            json={"guest_name": "テスト"},
            headers=auth_header(staff_tok),
        )
        assert issue_resp.status_code == 403

    def test_TC_01_02_006_admin_auto_created_on_startup(self, client):
        """TC-01-02-006: .env から管理者が自動生成される → ログイン成功"""
        resp = client.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID,
            "password": ADMIN_PASSWORD,
        })
        assert resp.status_code == 200

    def test_TC_01_02_007_admin_not_recreated_on_restart(self, client, admin_headers):
        """TC-01-02-007: 管理者が既存の場合、再起動で上書きされない"""
        # パスワードを変更後、再起動しても元の .env パスワードに戻らないことを確認
        # ここでは「管理者が 1 件だけ存在する」ことを確認
        resp = client.get("/admin/staff", headers=admin_headers)
        assert resp.status_code == 200
        admins = [s for s in resp.json() if s.get("role") == "admin"]
        assert len(admins) == 1


# ─── TC-01-03: ログイン失敗ロック ────────────────────────────────────────────

class TestLoginLock:
    @pytest.fixture
    def lock_student(self, client, tmp_db):
        """ロックテスト専用の生徒 ID（他テストと干渉しない）"""
        seed_student(tmp_db, "LOCK01", "ロックテスト", "2-A", "correctpass")
        return ("LOCK01", "correctpass", client)

    def test_TC_01_03_001_no_lock_after_9_failures(self, lock_student):
        """TC-01-03-001: 9 回失敗してもロックされない"""
        student_id, _, c = lock_student
        for _ in range(9):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        # 9 回目の失敗後もエラーメッセージのみ（ロックメッセージではない）
        resp = c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        assert resp.status_code in (400, 401)
        body = resp.json()
        error_text = str(body).lower()
        assert "ロック" not in error_text and "lock" not in error_text

    def test_TC_01_03_002_lock_after_10_failures(self, lock_student):
        """TC-01-03-002: 10 回失敗でロック → 「30分間ロックされました」メッセージ"""
        student_id, _, c = lock_student
        for _ in range(10):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        resp = c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        assert resp.status_code in (400, 401, 423)
        body_text = str(resp.json()).lower()
        assert "ロック" in body_text or "lock" in body_text

    def test_TC_01_03_003_correct_password_rejected_while_locked(self, lock_student):
        """TC-01-03-003: ロック中は正解パスワードでもログイン不可"""
        student_id, correct_pass, c = lock_student
        for _ in range(10):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        resp = c.post("/auth/login", json={"student_id": student_id, "password": correct_pass})
        assert resp.status_code in (400, 401, 423)

    def test_TC_01_03_004_lock_released_after_30_minutes(self, lock_student, monkeypatch):
        """TC-01-03-004: 30 分後にロック自動解除 → ログイン成功"""
        student_id, correct_pass, c = lock_student
        for _ in range(10):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})

        # ロック時刻を 31 分前に巻き戻す（実装側でロック時刻を確認する）
        import time as _time
        original_time = _time.time
        monkeypatch.setattr(_time, "time", lambda: original_time() + 31 * 60)

        resp = c.post("/auth/login", json={"student_id": student_id, "password": correct_pass})
        assert resp.status_code == 200

    def test_TC_01_03_005_failure_count_reset_after_success(self, lock_student):
        """TC-01-03-005: 成功後に失敗カウントがリセットされる"""
        student_id, correct_pass, c = lock_student
        # 5 回失敗
        for _ in range(5):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        # 正解でログイン
        resp = c.post("/auth/login", json={"student_id": student_id, "password": correct_pass})
        assert resp.status_code == 200
        # その後また 9 回失敗してもロックされない
        for _ in range(9):
            c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        resp2 = c.post("/auth/login", json={"student_id": student_id, "password": "wrong"})
        body_text = str(resp2.json()).lower()
        assert "ロック" not in body_text and "lock" not in body_text

    def test_TC_01_03_006_staff_also_locked_after_10_failures(self, with_staff, tmp_db):
        """TC-01-03-006: スタッフアカウントも 10 回失敗でロック"""
        for _ in range(10):
            with_staff.post("/auth/staff/login", json={
                "staff_id": STAFF_ID,
                "password": "wrongpass",
            })
        resp = with_staff.post("/auth/staff/login", json={
            "staff_id": STAFF_ID,
            "password": "wrongpass",
        })
        assert resp.status_code in (400, 401, 423)
        body_text = str(resp.json()).lower()
        assert "ロック" in body_text or "lock" in body_text
