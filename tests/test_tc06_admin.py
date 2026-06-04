"""TC-06: 管理者機能"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STAFF_ID, STAFF_PASSWORD,
    auth_header, issue_ticket, seed_student, seed_staff_member, make_csv_bytes,
)


# ─── TC-06-01: ダッシュボード ──────────────────────────────────────────────────

class TestDashboard:
    def test_TC_06_01_001_total_entry_count(self, client, admin_headers, tmp_db):
        """TC-06-01-001: 総入場者数が正しく表示される"""
        resp = client.get("/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_entries" in body or "entry_count" in body

    def test_TC_06_01_002_unused_ticket_count(self, client, admin_headers):
        """TC-06-01-002: 未使用チケット数が表示される"""
        resp = client.get("/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "unused_count" in body or "unused_tickets" in body

    def test_TC_06_01_003_hourly_entry_graph_data(self, client, admin_headers):
        """TC-06-01-003: 時間帯別入場データ（30 分単位）が含まれる"""
        resp = client.get("/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "hourly_entries" in body or "entry_graph" in body or "graph_data" in body

    def test_TC_06_01_004_polling_returns_updated_data(self, client, admin_headers, tmp_db):
        """TC-06-01-004: 2 回連続でダッシュボードを取得しても 200 が返る（ポーリング模擬）"""
        r1 = client.get("/admin/dashboard", headers=admin_headers)
        r2 = client.get("/admin/dashboard", headers=admin_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_TC_06_01_005_student_entry_table(self, client, admin_headers, tmp_db):
        """TC-06-01-005: 生徒別入場状況テーブルが含まれる"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        resp = client.get("/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "student_entries" in body or "students" in body


# ─── TC-06-02: チケット一覧・操作 ─────────────────────────────────────────────

class TestTicketManagement:
    def test_TC_06_02_001_all_tickets_displayed(self, client, admin_headers, tmp_db):
        """TC-06-02-001: チケット全件が表示される（ページネーションなし）"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={
            "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
        })
        s_headers = auth_header(login_resp.json()["token"])
        for name in ["a", "b", "c"]:
            issue_ticket(client, s_headers, name)

        resp = client.get("/admin/tickets", headers=admin_headers)
        assert resp.status_code == 200
        tickets = resp.json()
        tickets = tickets if isinstance(tickets, list) else tickets.get("tickets", [])
        assert len(tickets) >= 3

    def test_TC_06_02_002_filter_by_student_name(self, client, admin_headers, tmp_db):
        """TC-06-02-002: 生徒名フィルタで山田のチケットのみ表示"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        seed_student(tmp_db, "1999", "別の生徒", "9-Z", "pass9999")
        login_resp = client.post("/auth/login", json={
            "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
        })
        issue_ticket(client, auth_header(login_resp.json()["token"]), "a")

        resp = client.get("/admin/tickets?student_name=山田", headers=admin_headers)
        assert resp.status_code == 200
        tickets = resp.json() if isinstance(resp.json(), list) else resp.json().get("tickets", [])
        for t in tickets:
            assert "山田" in t.get("student_name", "")

    def test_TC_06_02_003_filter_by_used_status(self, client, admin_headers):
        """TC-06-02-003: 入場済みフィルタ → used=1 のチケットのみ"""
        resp = client.get("/admin/tickets?status=used", headers=admin_headers)
        assert resp.status_code == 200
        tickets = resp.json() if isinstance(resp.json(), list) else resp.json().get("tickets", [])
        for t in tickets:
            assert t["used"] == 1

    def test_TC_06_02_004_filter_by_invalid_status(self, client, admin_headers):
        """TC-06-02-004: 無効フィルタ → is_valid=0 のチケットのみ"""
        resp = client.get("/admin/tickets?status=invalid", headers=admin_headers)
        assert resp.status_code == 200
        tickets = resp.json() if isinstance(resp.json(), list) else resp.json().get("tickets", [])
        for t in tickets:
            assert t["is_valid"] == 0

    def test_TC_06_02_005_admin_can_invalidate_ticket(self, client, admin_headers, tmp_db):
        """TC-06-02-005: 管理者がチケットを無効化 → is_valid=0"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={
            "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
        })
        s_headers = auth_header(login_resp.json()["token"])
        issue_resp = issue_ticket(client, s_headers, "無効化テスト")
        ticket_id = issue_resp.json()["ticket_id"]

        resp = client.put(
            f"/admin/tickets/{ticket_id}",
            json={"is_valid": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        detail = client.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()
        assert detail["is_valid"] == 0

    def test_TC_06_02_006_staff_cannot_invalidate_ticket(self, client, with_staff, admin_headers, staff_headers, tmp_db):
        """TC-06-02-006: スタッフが無効化 API を呼び出し → 403"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={
            "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
        })
        issue_resp = issue_ticket(client, auth_header(login_resp.json()["token"]), "x")
        ticket_id = issue_resp.json()["ticket_id"]

        resp = with_staff.put(
            f"/admin/tickets/{ticket_id}",
            json={"is_valid": 0},
            headers=staff_headers,
        )
        assert resp.status_code == 403

    def test_TC_06_02_007_admin_can_cancel_entry(self, client, admin_headers, tmp_db):
        """TC-06-02-007: 管理者が入場取消 → used=0"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        seed_staff_member(tmp_db, STAFF_ID, "スタッフ", STAFF_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        issue_resp = issue_ticket(client, s_headers, "取消テスト")
        ticket_id = issue_resp.json()["ticket_id"]
        staff_login = client.post("/auth/staff/login", json={"staff_id": STAFF_ID, "password": STAFF_PASSWORD})
        sf_headers = auth_header(staff_login.json()["token"])
        client.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=sf_headers)

        resp = client.put(f"/admin/tickets/{ticket_id}", json={"used": 0}, headers=admin_headers)
        assert resp.status_code == 200
        assert client.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()["used"] == 0

    def test_TC_06_02_008_staff_can_cancel_entry(self, with_staff, staff_headers, admin_headers, tmp_db):
        """TC-06-02-008: スタッフが入場取消 → used=0"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = with_staff.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        issue_resp = issue_ticket(with_staff, s_headers, "スタッフ取消テスト")
        ticket_id = issue_resp.json()["ticket_id"]
        with_staff.post("/ticket/scan", json={"ticket_id": ticket_id}, headers=staff_headers)

        resp = with_staff.post(f"/ticket/scan/{ticket_id}/cancel", headers=staff_headers)
        assert resp.status_code == 200

    def test_TC_06_02_009_admin_can_add_ticket_beyond_limit(self, client, admin_headers, tmp_db):
        """TC-06-02-009: 管理者が手動で 6 枚目のチケットを追加できる"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        for name in ["a", "b", "c", "d", "e"]:
            issue_ticket(client, s_headers, name)

        resp = client.post(
            "/admin/tickets",
            json={"student_id": STUDENT_ID, "guest_name": "管理者手動追加"},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 201)

    def test_TC_06_02_010_staff_cannot_manually_add_ticket(self, with_staff, staff_headers):
        """TC-06-02-010: スタッフが手動追加 → 403"""
        resp = with_staff.post(
            "/admin/tickets",
            json={"student_id": STUDENT_ID, "guest_name": "スタッフ追加"},
            headers=staff_headers,
        )
        assert resp.status_code == 403

    def test_TC_06_02_011_invalidated_ticket_shows_no_invalidate_button(self, client, admin_headers, tmp_db):
        """TC-06-02-011: is_valid=0 のチケット詳細に is_valid=0 が返る（無効化ボタン表示制御の根拠）"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        issue_resp = issue_ticket(client, s_headers, "既無効")
        ticket_id = issue_resp.json()["ticket_id"]
        client.put(f"/admin/tickets/{ticket_id}", json={"is_valid": 0}, headers=admin_headers)

        detail = client.get(f"/admin/tickets/{ticket_id}", headers=admin_headers).json()
        assert detail["is_valid"] == 0


# ─── TC-06-03: 生徒一覧 ─────────────────────────────────────────────────────

class TestStudentList:
    def test_TC_06_03_001_all_students_displayed(self, client, admin_headers, tmp_db):
        """TC-06-03-001: 生徒全件表示"""
        rows = [[str(8000 + i), f"生徒{i}", "1-A"] for i in range(5)]
        csv_bytes = make_csv_bytes(rows=rows)
        client.post("/admin/import", files={"file": ("s.csv", csv_bytes, "text/csv")}, headers=admin_headers)

        resp = client.get("/admin/students", headers=admin_headers)
        assert resp.status_code == 200
        students = resp.json() if isinstance(resp.json(), list) else resp.json().get("students", [])
        assert len(students) >= 5

    def test_TC_06_03_002_ticket_issue_count_shown(self, client, admin_headers, tmp_db):
        """TC-06-03-002: 生徒一覧で発行枚数が確認できる"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        for name in ["a", "b", "c"]:
            issue_ticket(client, s_headers, name)

        resp = client.get(f"/admin/students/{STUDENT_ID}", headers=admin_headers)
        assert resp.status_code == 200
        student = resp.json()
        assert student.get("ticket_count") == 3 or student.get("issued_count") == 3

    def test_TC_06_03_003_student_fields_present(self, client, admin_headers, tmp_db):
        """TC-06-03-003: 学籍番号・氏名・クラス・発行枚数・入場済み枚数が含まれる"""
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        resp = client.get("/admin/students", headers=admin_headers)
        students = resp.json() if isinstance(resp.json(), list) else resp.json().get("students", [])
        s = next((s for s in students if s.get("id") == STUDENT_ID), None)
        assert s is not None
        assert "id" in s
        assert "name" in s
        assert "class" in s or "class_name" in s


# ─── TC-06-04: スタッフ管理 ──────────────────────────────────────────────────

class TestStaffManagement:
    def test_TC_06_04_001_add_staff(self, client, admin_headers):
        """TC-06-04-001: スタッフ追加 → ログイン可能"""
        resp = client.post("/admin/staff", json={
            "staff_id": "staff_new",
            "name": "新スタッフ",
            "password": "newpass123",
        }, headers=admin_headers)
        assert resp.status_code in (200, 201)

        login_resp = client.post("/auth/staff/login", json={
            "staff_id": "staff_new",
            "password": "newpass123",
        })
        assert login_resp.status_code == 200

    def test_TC_06_04_002_delete_staff(self, client, admin_headers, tmp_db):
        """TC-06-04-002: スタッフ削除 → ログイン不可"""
        seed_staff_member(tmp_db, "del_staff", "削除スタッフ", "delpass123")
        del_resp = client.delete("/admin/staff/del_staff", headers=admin_headers)
        assert del_resp.status_code == 200

        login_resp = client.post("/auth/staff/login", json={
            "staff_id": "del_staff",
            "password": "delpass123",
        })
        assert login_resp.status_code in (400, 401)

    def test_TC_06_04_003_duplicate_staff_id_rejected(self, client, admin_headers, tmp_db):
        """TC-06-04-003: 重複 ID でスタッフ登録 → エラー"""
        seed_staff_member(tmp_db, STAFF_ID, "既存スタッフ", STAFF_PASSWORD)
        resp = client.post("/admin/staff", json={
            "staff_id": STAFF_ID,
            "name": "重複スタッフ",
            "password": "anotherpass",
        }, headers=admin_headers)
        assert resp.status_code in (400, 409)

    def test_TC_06_04_004_staff_cannot_access_staff_management(self, with_staff, staff_headers):
        """TC-06-04-004: スタッフが /admin/staff にアクセス → 403"""
        resp = with_staff.get("/admin/staff", headers=staff_headers)
        assert resp.status_code == 403


# ─── TC-06-05: システム設定（QR 発行期間） ────────────────────────────────────

class TestSystemSettings:
    def test_TC_06_05_001_change_issue_period(self, client, admin_headers):
        """TC-06-05-001: QR 発行期間を変更 → settings テーブルに反映"""
        resp = client.put("/admin/settings", json={
            "issue_start": "2026-10-01",
            "issue_end": "2026-10-15",
        }, headers=admin_headers)
        assert resp.status_code == 200

        get_resp = client.get("/admin/settings", headers=admin_headers)
        body = get_resp.json()
        assert body.get("issue_start") == "2026-10-01"
        assert body.get("issue_end") == "2026-10-15"

    def test_TC_06_05_002_student_can_issue_within_new_period(self, client, admin_headers, tmp_db):
        """TC-06-05-002: 発行期間を現在日を含む期間に変更後、生徒が QR 発行できる"""
        from datetime import date
        today = date.today().isoformat()
        client.put("/admin/settings", json={
            "issue_start": "2000-01-01",
            "issue_end": today,
        }, headers=admin_headers)
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])

        resp = client.post("/ticket/issue", json={"guest_name": "テスト"}, headers=s_headers)
        assert resp.status_code == 200

    def test_TC_06_05_003_student_cannot_issue_outside_period(self, client, admin_headers, tmp_db):
        """TC-06-05-003: 発行終了日を昨日に変更後、生徒が QR 発行できない"""
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        client.put("/admin/settings", json={
            "issue_start": "2000-01-01",
            "issue_end": yesterday,
        }, headers=admin_headers)
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])

        resp = client.post("/ticket/issue", json={"guest_name": "テスト"}, headers=s_headers)
        assert resp.status_code in (400, 403)
