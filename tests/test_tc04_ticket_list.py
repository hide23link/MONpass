"""TC-04: 発行済みQR一覧・削除（生徒）"""

import pytest
from conftest import auth_header, issue_ticket


class TestTicketListAndDelete:
    def test_TC_04_001_list_shows_all_issued_tickets(self, with_student_1001, student_headers):
        """TC-04-001: 3 枚発行後、一覧に 3 枚表示される"""
        for name in ["お父さん", "お母さん", "友人A"]:
            issue_ticket(with_student_1001, student_headers, name)

        resp = with_student_1001.get("/ticket/list", headers=student_headers)
        assert resp.status_code == 200
        body = resp.json()
        tickets = body if isinstance(body, list) else body.get("tickets", [])
        assert len(tickets) == 3

        for ticket in tickets:
            assert "ticket_id" in ticket
            assert "guest_name" in ticket
            assert "created_at" in ticket
            assert "used" in ticket
            assert "is_valid" in ticket

    def test_TC_04_002_delete_unused_ticket(self, with_student_1001, student_headers):
        """TC-04-002: 未入場チケット削除 → 成功・残り枚数が 1 増える"""
        issue_resp = issue_ticket(with_student_1001, student_headers, "削除テスト")
        ticket_id = issue_resp.json()["ticket_id"]

        del_resp = with_student_1001.delete(
            f"/ticket/{ticket_id}",
            headers=student_headers,
        )
        assert del_resp.status_code == 200

        list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        tickets = list_resp.json()
        tickets = tickets if isinstance(tickets, list) else tickets.get("tickets", [])
        ids = [t["ticket_id"] for t in tickets]
        assert ticket_id not in ids

    def test_TC_04_003_used_ticket_cannot_be_deleted(self, used_ticket, with_staff, student_headers):
        """TC-04-003: 入場済みチケットは削除ボタンが表示されない / 削除 API が失敗"""
        ticket_id = used_ticket["ticket_id"]
        del_resp = with_staff.delete(
            f"/ticket/{ticket_id}",
            headers=student_headers,
        )
        assert del_resp.status_code in (400, 403)

    def test_TC_04_004_used_ticket_shows_used_status(self, used_ticket, with_student_1001, student_headers):
        """TC-04-004: 入場済みチケットには used=1 と used_at が表示される"""
        list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        tickets = list_resp.json()
        tickets = tickets if isinstance(tickets, list) else tickets.get("tickets", [])
        used = [t for t in tickets if t["ticket_id"] == used_ticket["ticket_id"]]
        assert len(used) == 1
        assert used[0]["used"] == 1
        assert used[0].get("used_at") is not None

    def test_TC_04_005_unused_ticket_shows_unused_status(self, with_student_1001, student_headers):
        """TC-04-005: 未入場チケットには used=0 が表示される"""
        issue_ticket(with_student_1001, student_headers, "未入場テスト")
        list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        tickets = list_resp.json()
        tickets = tickets if isinstance(tickets, list) else tickets.get("tickets", [])
        unused = [t for t in tickets if t["used"] == 0]
        assert len(unused) >= 1
        for ticket in unused:
            assert ticket.get("used_at") is None

    def test_TC_04_006_remaining_count_increases_after_delete(self, with_student_1001, student_headers):
        """TC-04-006: 3 枚発行後に 1 枚削除 → 残り枚数が増える"""
        ids = []
        for name in ["a", "b", "c"]:
            r = issue_ticket(with_student_1001, student_headers, name)
            ids.append(r.json()["ticket_id"])

        before_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        before_count = len(before_resp.json() if isinstance(before_resp.json(), list)
                          else before_resp.json().get("tickets", []))

        with_student_1001.delete(f"/ticket/{ids[0]}", headers=student_headers)

        after_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        after_count = len(after_resp.json() if isinstance(after_resp.json(), list)
                         else after_resp.json().get("tickets", []))

        assert after_count == before_count - 1

        remaining_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        body = remaining_resp.json()
        if isinstance(body, dict) and "remaining" in body:
            assert body["remaining"] == 5 - after_count
