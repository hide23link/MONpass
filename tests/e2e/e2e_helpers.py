"""
E2Eテスト共通フィクスチャ
- テストごとに独立した SQLite DB を使用
- uvicorn でテストサーバーを起動
- Playwright ブラウザで操作
"""

import os
import threading
import time
import sqlite3
import pytest
import bcrypt
import uvicorn

# ─── テスト定数 ──────────────────────────────────────────────────────────────
ADMIN_ID       = "admin"
ADMIN_PASSWORD = "adminpass123"
STAFF_ID       = "staff01"
STAFF_PASSWORD = "staffpass123"
STUDENT_ID     = "1001"
STUDENT_PASSWORD = "abc12345"
STUDENT_NAME   = "山田太郎"
JWT_SECRET     = "test_jwt_secret_key_minimum_32_characters_ok"
BASE_URL       = "http://localhost:18765"


# ─── テストサーバー ───────────────────────────────────────────────────────────

class TestServer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._thread = None
        self._server = None

    def start(self):
        os.environ["DB_PATH"]           = self.db_path
        os.environ["JWT_SECRET"]        = JWT_SECRET
        os.environ["ADMIN_ID"]          = ADMIN_ID
        os.environ["ADMIN_PASSWORD"]    = ADMIN_PASSWORD
        os.environ["DOMAIN"]            = "localhost:18765"
        os.environ["LOGIN_MAX_FAILURES"]  = "10"
        os.environ["LOGIN_LOCKOUT_MINUTES"] = "30"
        os.environ["ISSUE_START_DATE"]  = "2000-01-01"
        os.environ["ISSUE_END_DATE"]    = "2099-12-31"

        # モジュールキャッシュをリセット
        import importlib, sys
        for mod in list(sys.modules.keys()):
            if mod == "main" or mod.startswith("main."):
                del sys.modules[mod]

        import main
        app = main.create_app()

        config = uvicorn.Config(app, host="127.0.0.1", port=18765, log_level="warning")
        self._server = uvicorn.Server(config)

        def run():
            self._server.run()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

        # 起動待ち
        import httpx
        for _ in range(30):
            try:
                httpx.get(f"{BASE_URL}/health", timeout=1)
                return
            except Exception:
                time.sleep(0.3)
        raise RuntimeError("テストサーバーが起動しませんでした")

    def stop(self):
        if self._server:
            self._server.should_exit = True


# ─── フィクスチャ ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def server(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("e2e") / "test_e2e.db")
    srv = TestServer(db_path)
    srv.start()
    yield srv, db_path
    srv.stop()


@pytest.fixture(scope="session")
def db_path(server):
    _, path = server
    return path


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def page(browser, server):
    """テストごとに新しいページ（コンテキスト）"""
    context = browser.new_context(base_url=BASE_URL)
    pg = context.new_page()
    yield pg
    context.close()


@pytest.fixture
def page_desktop(browser, server):
    context = browser.new_context(base_url=BASE_URL, viewport={"width": 1280, "height": 800})
    pg = context.new_page()
    yield pg
    context.close()


@pytest.fixture
def page_mobile(browser, server):
    context = browser.new_context(base_url=BASE_URL, viewport={"width": 375, "height": 812})
    pg = context.new_page()
    yield pg
    context.close()


# ─── ヘルパー ─────────────────────────────────────────────────────────────────

def seed_student(db_path, student_id, name, class_, password):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, class, password_hash) VALUES (?,?,?,?)",
            (student_id, name, class_, pw_hash)
        )
        conn.commit()
    finally:
        conn.close()


def seed_staff(db_path, staff_id, name, password, role="staff"):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO staff (id, name, password_hash, role) VALUES (?,?,?,?)",
            (staff_id, name, pw_hash, role)
        )
        conn.commit()
    finally:
        conn.close()


def login_student(page, student_id=STUDENT_ID, password=STUDENT_PASSWORD):
    page.goto(f"{BASE_URL}/#/login")
    page.wait_for_selector("#student-id")
    page.fill("#student-id", student_id)
    page.fill("#password", password)
    page.click("#submit-btn")
    page.wait_for_url(lambda u: "#/qr" in u or "#/login" in u, timeout=8000)


import random as _random
_counter = 0
def make_unique_student(db_path):
    """テストごとにユニークな生徒を作成して (id, password) を返す"""
    global _counter
    _counter += 1
    sid = f"uniq{_counter:04d}{_random.randint(10,99)}"
    pwd = "upass1234"
    seed_student(db_path, sid, f"ユニーク生徒{_counter}", "U-A", pwd)
    return sid, pwd


def login_staff(page, staff_id=STAFF_ID, password=STAFF_PASSWORD):
    page.goto(f"{BASE_URL}/#/staff-login")
    page.wait_for_selector("#staff-id")
    page.fill("#staff-id", staff_id)
    page.fill("#password", password)
    page.click("#submit-btn")
    page.wait_for_url(lambda u: "#/staff" in u or "#/admin" in u or "#/staff-login" in u, timeout=5000)


def login_admin(page, admin_id=ADMIN_ID, password=ADMIN_PASSWORD):
    page.goto(f"{BASE_URL}/#/staff-login")
    page.wait_for_selector("#staff-id")
    page.fill("#staff-id", admin_id)
    page.fill("#password", password)
    page.click("#submit-btn")
    page.wait_for_url(lambda u: "#/admin" in u, timeout=5000)


def set_jwt(page, token):
    page.evaluate(f"localStorage.setItem('token', '{token}')")
