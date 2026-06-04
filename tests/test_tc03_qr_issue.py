"""TC-03: QR発行（生徒）"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STUDENT_ID_2,
    auth_header, seed_student,
)


# ─── TC-03-01: 正常系 ────────────────────────────────────────────────────────

class TestQrIssueNormal:
    def test_TC_03_01_001_issue_first_ticket(self, with_student_1001, student_headers):
        """TC-03-01-001: QR 発行 1 枚目 → QR 生成・残り 4 枚"""
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "お父さん"},
            headers=student_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "ticket_id" in body
        assert "qr_url" in body or "qr_image" in body
        assert body.get("remaining", -1) == 4

    def test_TC_03_01_002_issue_fifth_ticket(self, with_student_1001, student_headers):
        """TC-03-01-002: QR 発行 5 枚目 → 残り 0 枚・フォーム非表示フラグ"""
        for name in ["お父さん", "お母さん", "兄", "姉"]:
            with_student_1001.post(
                "/ticket/issue",
                json={"guest_name": name},
                headers=student_headers,
            )
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "友人A"},
            headers=student_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("remaining", -1) == 0

    def test_TC_03_01_003_qr_image_available(self, with_student_1001, student_headers):
        """TC-03-01-003: 発行済み QR 一覧から QR 画像 URL が取得できる"""
        with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "お父さん"},
            headers=student_headers,
        )
        list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        assert list_resp.status_code == 200
        tickets = list_resp.json()
        assert len(tickets) >= 1
        ticket = tickets[0]
        assert "qr_url" in ticket or "qr_image" in ticket

    def test_TC_03_01_004_qr_url_format(self, with_student_1001, student_headers):
        """TC-03-01-004: QR コード内 URL が https://<DOMAIN>/scan/<ticket_id> 形式"""
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "お父さん"},
            headers=student_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        ticket_id = body["ticket_id"]
        qr_content = body.get("qr_url") or body.get("qr_content", "")
        assert f"/scan/{ticket_id}" in qr_content

    def test_TC_03_01_005_remaining_count_displayed(self, with_student_1001, student_headers):
        """TC-03-01-005: 2 枚発行後、残り枚数が 3 と返される"""
        for name in ["お父さん", "お母さん"]:
            with_student_1001.post(
                "/ticket/issue",
                json={"guest_name": name},
                headers=student_headers,
            )
        list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
        assert list_resp.status_code == 200
        body = list_resp.json()
        # レスポンスに remaining フィールドがあるか、tickets で計算できる
        if isinstance(body, dict):
            assert body.get("remaining") == 3
        else:
            assert 5 - len(body) == 3


# ─── TC-03-02: 異常系・境界値 ──────────────────────────────────────────────────

class TestQrIssueAbnormal:
    def test_TC_03_02_001_sixth_ticket_rejected(self, with_student_1001, student_headers):
        """TC-03-02-001: 6 枚目の発行は 403 または 400"""
        for name in ["a", "b", "c", "d", "e"]:
            with_student_1001.post(
                "/ticket/issue",
                json={"guest_name": name},
                headers=student_headers,
            )
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "6枚目"},
            headers=student_headers,
        )
        assert resp.status_code in (400, 403)

    def test_TC_03_02_002_issue_before_period_rejected(self, client, tmp_db, monkeypatch):
        """TC-03-02-002: 発行期間開始前 → 発行不可エラー"""
        monkeypatch.setenv("ISSUE_START_DATE", "2099-01-01")
        monkeypatch.setenv("ISSUE_END_DATE", "2099-12-31")
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)

        from main import create_app
        from fastapi.testclient import TestClient
        test_app = create_app()
        with TestClient(test_app) as c:
            login_resp = c.post("/auth/login", json={
                "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
            })
            token = login_resp.json()["token"]
            resp = c.post(
                "/ticket/issue",
                json={"guest_name": "テスト"},
                headers=auth_header(token),
            )
        assert resp.status_code in (400, 403)

    def test_TC_03_02_003_issue_after_period_rejected(self, client, tmp_db, monkeypatch):
        """TC-03-02-003: 発行期間終了後 → 発行不可エラー"""
        monkeypatch.setenv("ISSUE_START_DATE", "2000-01-01")
        monkeypatch.setenv("ISSUE_END_DATE", "2000-12-31")
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)

        from main import create_app
        from fastapi.testclient import TestClient
        test_app = create_app()
        with TestClient(test_app) as c:
            login_resp = c.post("/auth/login", json={
                "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
            })
            token = login_resp.json()["token"]
            resp = c.post(
                "/ticket/issue",
                json={"guest_name": "テスト"},
                headers=auth_header(token),
            )
        assert resp.status_code in (400, 403)

    def test_TC_03_02_004_issue_on_last_day_succeeds(self, client, tmp_db, monkeypatch):
        """TC-03-02-004: 発行期間最終日（当日）は発行可能"""
        from datetime import date
        today = date.today().isoformat()
        monkeypatch.setenv("ISSUE_START_DATE", "2000-01-01")
        monkeypatch.setenv("ISSUE_END_DATE", today)
        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)

        from main import create_app
        from fastapi.testclient import TestClient
        test_app = create_app()
        with TestClient(test_app) as c:
            login_resp = c.post("/auth/login", json={
                "student_id": STUDENT_ID, "password": STUDENT_PASSWORD,
            })
            token = login_resp.json()["token"]
            resp = c.post(
                "/ticket/issue",
                json={"guest_name": "テスト"},
                headers=auth_header(token),
            )
        assert resp.status_code == 200

    def test_TC_03_02_005_empty_guest_name_rejected(self, with_student_1001, student_headers):
        """TC-03-02-005: 招待者名が空欄 → バリデーションエラー"""
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": ""},
            headers=student_headers,
        )
        assert resp.status_code == 422

    def test_TC_03_02_006_xss_in_guest_name_escaped(self, with_student_1001, student_headers):
        """TC-03-02-006: 招待者名に XSS スクリプト → エスケープされて保存"""
        xss_name = "<script>alert(1)</script>"
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": xss_name},
            headers=student_headers,
        )
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            list_resp = with_student_1001.get("/ticket/list", headers=student_headers)
            tickets = list_resp.json()
            for ticket in (tickets if isinstance(tickets, list) else tickets.get("tickets", [])):
                assert "<script>" not in ticket.get("guest_name", "")

    def test_TC_03_02_007_unauthenticated_issue_rejected(self, with_student_1001):
        """TC-03-02-007: JWT なしで発行 API 呼び出し → 401"""
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "テスト"},
        )
        assert resp.status_code == 401

    def test_TC_03_02_008_other_student_jwt_cannot_issue_for_self(
        self, with_student_1002, tmp_db
    ):
        """TC-03-02-008: 他生徒の JWT で自分用 QR 発行 → 403"""
        login_resp = with_student_1002.post("/auth/login", json={
            "student_id": STUDENT_ID,  # 生徒 1001 のトークン
            "password": STUDENT_PASSWORD,
        })
        token_1001 = login_resp.json()["token"]
        # 生徒 1002 の student_id を指定して発行しようとする
        resp = with_student_1002.post(
            "/ticket/issue",
            json={"guest_name": "テスト", "student_id": STUDENT_ID_2},
            headers=auth_header(token_1001),
        )
        assert resp.status_code == 403
