"""TC-10: 緊急用CSV出力"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    auth_header, issue_ticket, seed_student, seed_staff_member,
)


class TestEmergencyCsvExport:
    def test_TC_10_001_admin_can_export_all_tickets_csv(self, client, admin_headers, tmp_db):
        """TC-10-001: 管理者が /admin/export に GET → 全チケット一覧 CSV をダウンロード"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        issue_ticket(client, s_headers, "お父さん")
        issue_ticket(client, s_headers, "お母さん")

        resp = client.get("/admin/export", headers=admin_headers)
        assert resp.status_code == 200
        # Content-Type が CSV であること
        content_type = resp.headers.get("content-type", "")
        assert "csv" in content_type or "text/plain" in content_type or "application/octet-stream" in content_type

        # CSV の内容検証
        text = resp.text
        lines = [l for l in text.strip().split("\n") if l.strip()]
        assert len(lines) >= 2  # ヘッダー + データ行

        # ヘッダーに必須カラムが含まれること
        header = lines[0].lower()
        required_fields = ["学籍番号", "生徒名", "招待者名", "チケット"]
        required_fields_en = ["student_id", "student_name", "guest_name", "ticket_id"]
        has_required = any(f in header for f in required_fields) or \
                       any(f in header for f in required_fields_en)
        assert has_required

    def test_TC_10_002_staff_cannot_export_csv(self, with_staff, staff_headers):
        """TC-10-002: スタッフ JWT で /admin/export に GET → 403"""
        resp = with_staff.get("/admin/export", headers=staff_headers)
        assert resp.status_code == 403
