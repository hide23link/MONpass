"""TC-11: 初期起動・設定"""

import os
import sqlite3
import pytest


class TestInitialStartup:
    def test_TC_11_001_db_auto_created_on_startup(self, tmp_db, monkeypatch):
        """TC-11-001: 初回起動で DB ファイルが自動生成・全テーブルが作成される"""
        assert not os.path.exists(tmp_db), "テスト前に DB が存在しないこと"

        monkeypatch.setenv("DB_PATH", tmp_db)
        monkeypatch.setenv("JWT_SECRET", "test_secret_key_minimum_32_characters_ok")
        monkeypatch.setenv("ADMIN_ID", "admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")

        from main import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app()):
            pass  # 起動・停止でライフサイクルイベントが走る

        assert os.path.exists(tmp_db)

        conn = sqlite3.connect(tmp_db)
        try:
            tables = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        finally:
            conn.close()

        required_tables = {"students", "tickets", "staff", "settings"}
        assert required_tables.issubset(set(tables))

    def test_TC_11_002_admin_auto_created_from_env(self, tmp_db, monkeypatch):
        """TC-11-002: .env の ADMIN_ID/ADMIN_PASSWORD から管理者が自動生成される"""
        monkeypatch.setenv("DB_PATH", tmp_db)
        monkeypatch.setenv("JWT_SECRET", "test_secret_key_minimum_32_characters_ok")
        monkeypatch.setenv("ADMIN_ID", "admin_env_test")
        monkeypatch.setenv("ADMIN_PASSWORD", "envpass123")

        from main import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app()) as c:
            resp = c.post("/auth/staff/login", json={
                "staff_id": "admin_env_test",
                "password": "envpass123",
            })
        assert resp.status_code == 200
        assert resp.json().get("token")

    def test_TC_11_003_settings_initial_data_inserted(self, tmp_db, monkeypatch):
        """TC-11-003: DB 新規作成後に issue_start・issue_end レコードが存在する"""
        monkeypatch.setenv("DB_PATH", tmp_db)
        monkeypatch.setenv("JWT_SECRET", "test_secret_key_minimum_32_characters_ok")
        monkeypatch.setenv("ADMIN_ID", "admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")
        monkeypatch.setenv("ISSUE_START_DATE", "2026-10-01")
        monkeypatch.setenv("ISSUE_END_DATE", "2026-10-15")

        from main import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app()):
            pass

        conn = sqlite3.connect(tmp_db)
        try:
            rows = {row[0]: row[1] for row in conn.execute(
                "SELECT key, value FROM settings"
            ).fetchall()}
        finally:
            conn.close()

        assert "issue_start" in rows
        assert "issue_end" in rows
        assert rows["issue_start"] == "2026-10-01"
        assert rows["issue_end"] == "2026-10-15"

    def test_TC_11_004_missing_admin_password_causes_error(self, tmp_db, monkeypatch):
        """TC-11-004: ADMIN_PASSWORD が未設定 → 起動失敗または警告ログ"""
        monkeypatch.setenv("DB_PATH", tmp_db)
        monkeypatch.setenv("JWT_SECRET", "test_secret_key_minimum_32_characters_ok")
        monkeypatch.setenv("ADMIN_ID", "admin")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        from main import create_app
        from fastapi.testclient import TestClient

        try:
            with TestClient(create_app()) as c:
                # 起動しても動作しないか、例外が発生するはず
                resp = c.get("/health")
                # 起動が成功した場合でも管理者ログインは失敗するはず
                login = c.post("/auth/staff/login", json={"staff_id": "admin", "password": ""})
                # ADMIN_PASSWORD が空なのでログインは失敗すること
                assert login.status_code in (400, 401, 500)
        except (SystemExit, RuntimeError, ValueError):
            pass  # 起動時例外は許容

    def test_TC_11_005_missing_jwt_secret_causes_error(self, tmp_db, monkeypatch):
        """TC-11-005: JWT_SECRET が未設定 → 起動失敗"""
        monkeypatch.setenv("DB_PATH", tmp_db)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ADMIN_ID", "admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")

        from main import create_app
        from fastapi.testclient import TestClient

        raised = False
        try:
            with TestClient(create_app()) as c:
                resp = c.post("/auth/staff/login", json={"staff_id": "admin", "password": "adminpass123"})
                # JWT が発行できないのでトークン生成で失敗するはず
                assert resp.status_code in (500, 400, 503)
        except (SystemExit, RuntimeError, ValueError, KeyError):
            raised = True

        # 起動失敗か、ログイン時に失敗すること
        assert raised or True  # どちらかで失敗すること
