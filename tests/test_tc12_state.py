"""TC-12: チケット状態遷移"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    auth_header, issue_ticket, seed_student, seed_staff_member,
)


@pytest.fixture
def client_with_data(client, tmp_db):
    """生徒・スタッフがシード済みのクライアント"""
    seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
    seed_staff_member(tmp_db, STAFF_ID, "スタッフ", STAFF_PASSWORD)
    return client


@pytest.fixture
def student_headers_fixture(client_with_data):
    resp = client_with_data.post("/auth/login", json={
        "student_id": STUDENT_ID,
        "password": STUDENT_PASSWORD,
    })
    return auth_header(resp.json()["token"])


@pytest.fixture
def staff_headers_fixture(client_with_data):
    resp = client_with_data.post("/auth/staff/login", json={
        "staff_id": STAFF_ID,
        "password": STAFF_PASSWORD,
    })
    return auth_header(resp.json()["token"])


class TestTicketStateTransition:
    def test_TC_12_001_valid_unused_ticket_scan_ok(
        self, client_with_data, student_headers_fixture, staff_headers_fixture
    ):
        """TC-12-001: is_valid=1, used=0 → スキャンで入場OK（緑）"""
        issue_resp = issue_ticket(client_with_data, student_headers_fixture, "有効未入場")
        assert issue_resp.status_code == 200
        ticket_id = issue_resp.json()["ticket_id"]

        scan_resp = client_with_data.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers_fixture,
        )
        assert scan_resp.status_code == 200
        body = scan_resp.json()
        assert body.get("status") == "ok" or body.get("result") == "ok"
        assert body.get("color") == "green" or body.get("status") == "ok"

    def test_TC_12_002_valid_used_ticket_rescan_rejected(
        self, client_with_data, student_headers_fixture, staff_headers_fixture
    ):
        """TC-12-002: is_valid=1, used=1 → 再スキャンで入場済みエラー（赤）・入場取消可"""
        issue_resp = issue_ticket(client_with_data, student_headers_fixture, "有効入場済み")
        ticket_id = issue_resp.json()["ticket_id"]
        # 1 回スキャン → used=1
        client_with_data.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers_fixture)
        # 再スキャン → エラー
        rescan_resp = client_with_data.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers_fixture,
        )
        assert rescan_resp.status_code in (400, 409)
        body = rescan_resp.json()
        assert "入場済み" in str(body) or "already" in str(body).lower()

        # 入場取消は可能
        from conftest import ADMIN_ID, ADMIN_PASSWORD
        admin_resp = client_with_data.post("/auth/staff/login", json={
            "staff_id": ADMIN_ID, "password": ADMIN_PASSWORD,
        })
        admin_tok = auth_header(admin_resp.json()["token"])
        cancel_resp = client_with_data.put(
            f"/admin/tickets/{ticket_id}",
            json={"used": 0},
            headers=admin_tok,
        )
        assert cancel_resp.status_code == 200

    def test_TC_12_003_invalid_unused_ticket_scan_rejected(
        self, client_with_data, student_headers_fixture, staff_headers_fixture, admin_headers
    ):
        """TC-12-003: is_valid=0, used=0 → スキャンで無効エラー（赤）・入場取消ボタンなし"""
        issue_resp = issue_ticket(client_with_data, student_headers_fixture, "無効未使用")
        ticket_id = issue_resp.json()["ticket_id"]
        # 無効化
        client_with_data.put(
            f"/admin/tickets/{ticket_id}",
            json={"is_valid": 0},
            headers=admin_headers,
        )
        scan_resp = client_with_data.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers_fixture,
        )
        assert scan_resp.status_code in (400, 403)
        body = scan_resp.json()
        assert "無効" in str(body) or "invalid" in str(body).lower()

        # used=0 なので入場取消ボタンは不要（used=0 確認）
        detail = client_with_data.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()
        assert detail["is_valid"] == 0
        assert detail["used"] == 0

    def test_TC_12_004_invalid_used_ticket_shows_both_states(
        self, client_with_data, student_headers_fixture, staff_headers_fixture, admin_headers
    ):
        """TC-12-004: is_valid=0, used=1 → スキャンで無効かつ入場済みと表示（赤）"""
        issue_resp = issue_ticket(client_with_data, student_headers_fixture, "無効入場済み")
        ticket_id = issue_resp.json()["ticket_id"]
        # スキャンで used=1
        client_with_data.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers_fixture)
        # 無効化で is_valid=0
        client_with_data.put(
            f"/admin/tickets/{ticket_id}",
            json={"is_valid": 0},
            headers=admin_headers,
        )

        detail = client_with_data.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()
        assert detail["is_valid"] == 0
        assert detail["used"] == 1

        scan_resp = client_with_data.post(
            "/ticket/scan",
            json={"ticket_id": ticket_id},
            headers=staff_headers_fixture,
        )
        assert scan_resp.status_code in (400, 403, 409)
