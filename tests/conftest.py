"""
テスト共通フィクスチャ・ヘルパー

前提:
  - main.py に create_app() ファクトリが実装されていること
  - テスト分離のために関数スコープで DB を都度作り直す
"""

import os
import json
import base64
import sqlite3
from io import BytesIO

import bcrypt
import pytest
from fastapi.testclient import TestClient

# ─── テスト定数 ──────────────────────────────────────────────────────────────
ADMIN_ID = "admin"
ADMIN_PASSWORD = "adminpass123"
STAFF_ID = "staff01"
STAFF_PASSWORD = "staffpass123"
STUDENT_ID = "1001"
STUDENT_PASSWORD = "abc12345"
STUDENT_ID_2 = "1002"
STUDENT_PASSWORD_2 = "def67890"
STUDENT_NAME = "山田太郎"
STUDENT_CLASS = "1-A"
JWT_SECRET = "test_jwt_secret_key_minimum_32_characters_ok"


# ─── ヘルパー関数 ──────────────────────────────────────────────────────────────

def decode_jwt_payload(token: str) -> dict:
    """JWT ペイロードをデコード（署名検証なし）"""
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64).decode())


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_csv_bytes(rows: list, header: list | None = None, encoding: str = "utf-8") -> BytesIO:
    """テスト用 CSV を BytesIO で返す"""
    lines = []
    if header:
        lines.append(",".join(str(c) for c in header))
    for row in rows:
        lines.append(",".join(str(c) for c in row))
    return BytesIO("\n".join(lines).encode(encoding))


def seed_student(db_path: str, student_id: str, name: str, class_: str, password: str) -> None:
    """テスト用: 既知パスワードで生徒を SQLite に直接挿入する"""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, class, password_hash) VALUES (?, ?, ?, ?)",
            (student_id, name, class_, pwd_hash),
        )
        conn.commit()
    finally:
        conn.close()


def seed_staff_member(db_path: str, staff_id: str, name: str, password: str, role: str = "staff") -> None:
    """テスト用: スタッフを SQLite に直接挿入する"""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO staff (id, name, password_hash, role) VALUES (?, ?, ?, ?)",
            (staff_id, name, pwd_hash, role),
        )
        conn.commit()
    finally:
        conn.close()


def issue_ticket(client: TestClient, headers: dict, guest_name: str) -> dict:
    """チケットを発行してレスポンスを返す"""
    resp = client.post("/ticket/issue", json={"guest_name": guest_name}, headers=headers)
    return resp


# ─── フィクスチャ ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path) -> str:
    """テスト毎に独立した SQLite DB ファイルパスを返す"""
    return str(tmp_path / "test.db")


@pytest.fixture
def client(tmp_db, monkeypatch) -> TestClient:
    """テスト毎に独立した TestClient（DB を新規作成）

    main.py に create_app() ファクトリが必要:
        def create_app() -> FastAPI: ...
        app = create_app()
    """
    monkeypatch.setenv("DB_PATH", tmp_db)
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ADMIN_ID", ADMIN_ID)
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DOMAIN", "localhost:8000")
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "10")
    monkeypatch.setenv("LOGIN_LOCKOUT_MINUTES", "30")
    monkeypatch.setenv("ISSUE_START_DATE", "2000-01-01")
    monkeypatch.setenv("ISSUE_END_DATE", "2099-12-31")

    from main import create_app
    test_app = create_app()

    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def with_student_1001(client, tmp_db) -> TestClient:
    """生徒 1001（パスワード abc12345）をシードしたクライアント"""
    seed_student(tmp_db, STUDENT_ID, STUDENT_NAME, STUDENT_CLASS, STUDENT_PASSWORD)
    return client


@pytest.fixture
def with_student_1002(client, tmp_db) -> TestClient:
    """生徒 1002 も追加したクライアント"""
    seed_student(tmp_db, STUDENT_ID, STUDENT_NAME, STUDENT_CLASS, STUDENT_PASSWORD)
    seed_student(tmp_db, STUDENT_ID_2, "鈴木花子", "1-B", STUDENT_PASSWORD_2)
    return client


@pytest.fixture
def with_staff(client, tmp_db) -> TestClient:
    """スタッフ staff01 をシードしたクライアント"""
    seed_staff_member(tmp_db, STAFF_ID, "テストスタッフ", STAFF_PASSWORD, "staff")
    return client


@pytest.fixture
def admin_token(client) -> str:
    """管理者 JWT を返す（管理者は起動時に自動生成される）"""
    resp = client.post("/auth/staff/login", json={
        "staff_id": ADMIN_ID,
        "password": ADMIN_PASSWORD,
    })
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return auth_header(admin_token)


@pytest.fixture
def staff_token(with_staff) -> str:
    resp = with_staff.post("/auth/staff/login", json={
        "staff_id": STAFF_ID,
        "password": STAFF_PASSWORD,
    })
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def staff_headers(staff_token) -> dict:
    return auth_header(staff_token)


@pytest.fixture
def student_token(with_student_1001) -> str:
    resp = with_student_1001.post("/auth/login", json={
        "student_id": STUDENT_ID,
        "password": STUDENT_PASSWORD,
    })
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def student_headers(student_token) -> dict:
    return auth_header(student_token)


@pytest.fixture
def issued_ticket(with_student_1001, student_headers) -> dict:
    """生徒 1001 が発行した未使用チケット 1 枚を返す"""
    resp = issue_ticket(with_student_1001, student_headers, "お父さん")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def used_ticket(with_staff, with_student_1001, student_headers, staff_headers, tmp_db) -> dict:
    """入場済みチケットを返す（発行→スキャン済み）"""
    seed_student(tmp_db, STUDENT_ID, STUDENT_NAME, STUDENT_CLASS, STUDENT_PASSWORD)
    seed_staff_member(tmp_db, STAFF_ID, "スタッフ", STAFF_PASSWORD)
    resp = issue_ticket(with_student_1001, student_headers, "お母さん")
    assert resp.status_code == 200
    ticket_id = resp.json()["ticket_id"]
    scan_resp = with_student_1001.post(
        "/ticket/scan",
        json={"ticket_id": ticket_id},
        headers=staff_headers,
    )
    assert scan_resp.status_code == 200
    return resp.json()
