"""TC-07: 昇格機能（生徒スマホ → 一時スタッフ）"""

import pytest
from conftest import (
    STUDENT_ID, STUDENT_PASSWORD, STUDENT_ID_2, STUDENT_PASSWORD_2,
    ADMIN_ID, ADMIN_PASSWORD,
    auth_header, issue_ticket, seed_student, decode_jwt_payload,
)


@pytest.fixture
def student_2_token(with_student_1002) -> str:
    resp = with_student_1002.post("/auth/login", json={
        "student_id": STUDENT_ID_2,
        "password": STUDENT_PASSWORD_2,
    })
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def promoted_student_token(with_student_1001, student_headers, admin_headers):
    """管理者に昇格してもらった生徒 1001 のトークンを返す"""
    # 生徒が昇格リクエスト QR を発行
    req_resp = with_student_1001.post("/promote/request", headers=student_headers)
    assert req_resp.status_code == 200
    promote_token = req_resp.json()["promote_token"]

    # 管理者が昇格 QR をスキャン
    approve_resp = with_student_1001.post(
        "/promote/approve",
        json={"promote_token": promote_token},
        headers=admin_headers,
    )
    assert approve_resp.status_code == 200
    # 新しい JWT（昇格フラグ付き）を返す
    return approve_resp.json()["token"]


# ─── TC-07-01: 昇格フロー ────────────────────────────────────────────────────

class TestPromotionFlow:
    def test_TC_07_01_001_student_can_request_promotion_qr(self, with_student_1001, student_headers):
        """TC-07-01-001: 生徒が昇格リクエスト QR を発行できる"""
        resp = with_student_1001.post("/promote/request", headers=student_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "promote_token" in body or "qr_data" in body

    def test_TC_07_01_002_admin_can_approve_promotion(self, with_student_1001, student_headers, admin_headers):
        """TC-07-01-002: 管理者が昇格 QR をスキャン → 一時管理者セッション発行"""
        req_resp = with_student_1001.post("/promote/request", headers=student_headers)
        promote_token = req_resp.json()["promote_token"]

        approve_resp = with_student_1001.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=admin_headers,
        )
        assert approve_resp.status_code == 200
        body = approve_resp.json()
        assert "token" in body  # 昇格後の新しい JWT

    def test_TC_07_01_003_promoted_student_can_access_scan_page(
        self, with_student_1001, promoted_student_token
    ):
        """TC-07-01-003: 昇格後にスキャン画面にアクセスできる"""
        resp = with_student_1001.get(
            "/staff",
            headers=auth_header(promoted_student_token),
        )
        assert resp.status_code == 200

    def test_TC_07_01_004_promoted_session_expires_at_midnight(
        self, promoted_student_token
    ):
        """TC-07-01-004: 昇格セッションが当日 23:59:59 に失効する"""
        payload = decode_jwt_payload(promoted_student_token)
        from datetime import datetime, timezone
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now_dt = datetime.now(tz=timezone.utc)
        assert exp_dt.date() == now_dt.date()
        assert exp_dt.hour == 23
        assert exp_dt.minute == 59

    def test_TC_07_01_005_promoted_state_persists_after_reload(
        self, with_student_1001, promoted_student_token
    ):
        """TC-07-01-005: ページリロード後も昇格状態が維持される（JWT に昇格フラグがあるため）"""
        # JWT を使って再アクセスしてもスキャン画面にアクセスできる
        resp = with_student_1001.get(
            "/staff",
            headers=auth_header(promoted_student_token),
        )
        assert resp.status_code == 200

    def test_TC_07_01_006_jwt_contains_promotion_flag(self, promoted_student_token):
        """TC-07-01-006: 昇格後の JWT ペイロードに昇格フラグが含まれる"""
        payload = decode_jwt_payload(promoted_student_token)
        # "promoted" or "is_promoted" or "role" = "promoted_student"
        has_flag = (
            payload.get("promoted") is True
            or payload.get("is_promoted") is True
            or "promoted" in str(payload.get("role", ""))
        )
        assert has_flag


# ─── TC-07-02: 連鎖昇格 ─────────────────────────────────────────────────────

class TestChainPromotion:
    def test_TC_07_02_001_promoted_student_can_promote_another(
        self, with_student_1002, promoted_student_token, student_2_token
    ):
        """TC-07-02-001: 昇格した生徒が他の生徒を昇格させられる"""
        req_resp = with_student_1002.post(
            "/promote/request",
            headers=auth_header(student_2_token),
        )
        assert req_resp.status_code == 200
        promote_token = req_resp.json()["promote_token"]

        approve_resp = with_student_1002.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=auth_header(promoted_student_token),
        )
        assert approve_resp.status_code == 200
        assert "token" in approve_resp.json()

    def test_TC_07_02_002_promotion_tree_recorded(self, client, admin_headers, with_student_1001, student_headers, with_student_1002, student_2_token, promoted_student_token):
        """TC-07-02-002: 昇格ツリーが管理者ダッシュボードで確認できる"""
        # 生徒 1001 が生徒 1002 を昇格
        req_resp = with_student_1002.post(
            "/promote/request",
            headers=auth_header(student_2_token),
        )
        promote_token = req_resp.json()["promote_token"]
        with_student_1002.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=auth_header(promoted_student_token),
        )

        resp = client.get("/promote/list", headers=admin_headers)
        assert resp.status_code == 200
        tree = resp.json()
        assert isinstance(tree, list) and len(tree) >= 1

    def test_TC_07_02_003_promotion_recorded_in_db(self, client, admin_headers, with_student_1001, student_headers):
        """TC-07-02-003: 昇格記録が temp_promotions に保存される（管理者 API で確認）"""
        req_resp = with_student_1001.post("/promote/request", headers=student_headers)
        promote_token = req_resp.json()["promote_token"]
        with_student_1001.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=admin_headers,
        )

        resp = client.get("/promote/list", headers=admin_headers)
        promotions = resp.json()
        assert len(promotions) >= 1
        p = promotions[0]
        assert "promoted_by_type" in p
        assert "promoted_by_id" in p
        assert "student_id" in p
        assert "expires_at" in p

    def test_TC_07_02_004_non_promoted_student_cannot_approve(
        self, with_student_1002, student_2_token, with_student_1001, student_headers
    ):
        """TC-07-02-004: 未昇格の生徒は他生徒を昇格させられない → 403"""
        req_resp = with_student_1001.post("/promote/request", headers=student_headers)
        promote_token = req_resp.json()["promote_token"]

        resp = with_student_1002.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=auth_header(student_2_token),
        )
        assert resp.status_code == 403


# ─── TC-07-03: 昇格の制約 ────────────────────────────────────────────────────

class TestPromotionConstraints:
    def test_TC_07_03_001_promote_token_is_one_time_use(
        self, with_student_1001, student_headers, admin_headers
    ):
        """TC-07-03-001: 昇格 QR は使い捨て → 再スキャンでエラー"""
        req_resp = with_student_1001.post("/promote/request", headers=student_headers)
        promote_token = req_resp.json()["promote_token"]

        # 1 回目: 成功
        with_student_1001.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=admin_headers,
        )
        # 2 回目: エラー
        resp = with_student_1001.post(
            "/promote/approve",
            json={"promote_token": promote_token},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 409)

    def test_TC_07_03_002_no_manual_revoke_endpoint(self, client, admin_headers):
        """TC-07-03-002: 昇格取消 API が存在しない（404）"""
        resp = client.delete("/promote/revoke/1001", headers=admin_headers)
        assert resp.status_code == 404

    def test_TC_07_03_003_promoted_student_can_still_issue_ticket(
        self, with_student_1001, promoted_student_token
    ):
        """TC-07-03-003: 昇格後も生徒としてチケット発行できる"""
        resp = with_student_1001.post(
            "/ticket/issue",
            json={"guest_name": "昇格後テスト"},
            headers=auth_header(promoted_student_token),
        )
        assert resp.status_code == 200
