"""TC-05: QRスキャン・入場記録（スタッフ）"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    auth_header, issue_ticket, seed_student, seed_staff_member,
)


# ─── TC-05-01: 正常系 ────────────────────────────────────────────────────────

class TestScanNormal:
    def test_TC_05_01_001_valid_ticket_scan(self, with_staff, student_headers, staff_headers, tmp_db):
        """TC-05-01-001: 有効チケットのスキャン → used=1 に更新・入場 OK"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_resp = issue_ticket(with_staff, student_headers, "お父さん")
        assert issue_resp.status_code == 200
        ticket_id = issue_resp.json()["ticket_id"]

        scan_resp = with_staff.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers,
        )
        assert scan_resp.status_code == 200
        body = scan_resp.json()
        assert body.get("status") == "ok" or body.get("result") == "ok"

    def test_TC_05_01_002_used_at_recorded_after_scan(self, with_staff, student_headers, staff_headers, tmp_db):
        """TC-05-01-002: スキャン後に used_at が記録される"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_resp = issue_ticket(with_staff, student_headers, "お母さん")
        ticket_id = issue_resp.json()["ticket_id"]
        with_staff.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers)

        # 管理者権限でチケット詳細を確認
        from conftest import ADMIN_ID, ADMIN_PASSWORD
        admin_resp = with_staff.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID, "password": ADMIN_PASSWORD,
        })
        admin_tok = admin_resp.json()["token"]
        detail_resp = with_staff.get(
            f"/admin/tickets/{ticket_id}",
            headers=auth_header(admin_tok),
        )
        assert detail_resp.status_code == 200
        ticket = detail_resp.json()
        assert ticket.get("used") == 1
        assert ticket.get("used_at") is not None

    def test_TC_05_01_003_admin_can_cancel_entry(self, admin_headers, with_student_1001, student_headers, staff_headers, with_staff, tmp_db):
        """TC-05-01-003: 管理者が入場取消 → used=0 に更新"""
        seed_staff_member(tmp_db, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        issue_resp = issue_ticket(with_student_1001, student_headers, "友人")
        ticket_id = issue_resp.json()["ticket_id"]
        with_student_1001.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers)

        cancel_resp = with_student_1001.put(
            f"/admin/tickets/{ticket_id}",
            json={"used": 0},
            headers=admin_headers,
        )
        assert cancel_resp.status_code == 200
        detail_resp = with_student_1001.get(
            f"/admin/tickets/{ticket_id}", headers=admin_headers,
        )
        assert detail_resp.json()["used"] == 0

    def test_TC_05_01_004_staff_can_cancel_entry(self, with_staff, student_headers, staff_headers, tmp_db):
        """TC-05-01-004: スタッフが入場取消 → used=0 に更新"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_resp = issue_ticket(with_staff, student_headers, "祖父")
        ticket_id = issue_resp.json()["ticket_id"]
        with_staff.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers)

        cancel_resp = with_staff.post(
            f"/ticket/scan/{ticket_id}/cancel",
            headers=staff_headers,
        )
        assert cancel_resp.status_code == 200

        # 再スキャンで used=0 を確認
        rescan_resp = with_staff.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers,
        )
        assert rescan_resp.status_code == 200  # 取消後は再スキャン可能


# ─── TC-05-02: 異常系 ────────────────────────────────────────────────────────

class TestScanAbnormal:
    def test_TC_05_02_001_rescan_used_ticket_rejected(self, with_staff, student_headers, staff_headers, tmp_db):
        """TC-05-02-001: 入場済みチケットの再スキャン → エラー・入場済みメッセージ"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_resp = issue_ticket(with_staff, student_headers, "祖母")
        ticket_id = issue_resp.json()["ticket_id"]
        with_staff.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers)

        rescan_resp = with_staff.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers,
        )
        assert rescan_resp.status_code in (400, 409)
        body = rescan_resp.json()
        assert "入場済み" in str(body) or "already" in str(body).lower()

    def test_TC_05_02_002_invalid_ticket_rejected(self, with_staff, admin_headers, student_headers, staff_headers, tmp_db):
        """TC-05-02-002: is_valid=0 のチケットをスキャン → 無効チケットエラー"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        issue_resp = issue_ticket(with_staff, student_headers, "無効テスト")
        ticket_id = issue_resp.json()["ticket_id"]
        # 管理者がチケットを無効化
        with_staff.put(f"/admin/tickets/{ticket_id}", json={"is_valid": 0}, headers=admin_headers)

        scan_resp = with_staff.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers,
        )
        assert scan_resp.status_code in (400, 403)
        body = scan_resp.json()
        assert "無効" in str(body) or "invalid" in str(body).lower()

    def test_TC_05_02_003_nonexistent_ticket_rejected(self, with_staff, staff_headers):
        """TC-05-02-003: 存在しないチケット ID をスキャン → 存在しないエラー"""
        resp = with_staff.post(
            "/ticket/scan",
            json={"ticket_id": "FAKE_TICKET_ID_DOES_NOT_EXIST"},
            headers=staff_headers,
        )
        assert resp.status_code in (400, 404)
        body = resp.json()
        assert "存在しない" in str(body) or "not found" in str(body).lower()

    def test_TC_05_02_004_unauthenticated_cannot_access_staff_page(self, with_staff):
        """TC-05-02-004: JWT なしで /staff にアクセス → ログインへリダイレクトまたは 401"""
        resp = with_staff.get("/staff")
        assert resp.status_code in (401, 302, 307)

    def test_TC_05_02_005_student_jwt_cannot_access_staff_page(self, with_student_1001, student_headers):
        """TC-05-02-005: 生徒 JWT で /staff にアクセス → 403 またはリダイレクト"""
        resp = with_student_1001.get("/staff", headers=student_headers)
        assert resp.status_code in (403, 302, 307)
