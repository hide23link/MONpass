"""
学園祭入場システム - FastAPI メインアプリ
"""

import os
import re
import sqlite3
import secrets
import string
import csv
import io
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List

import base64
import html
import bcrypt
import qrcode
import qrcode.image.svg
from PIL import Image
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.responses import StreamingResponse, Response, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel, field_validator


# ─── 設定 ────────────────────────────────────────────────────────────────────

def get_config():
    return {
        "db_path": os.environ.get("DB_PATH", "./data/gakuensai.db"),
        "jwt_secret": os.environ.get("JWT_SECRET", ""),
        "admin_id": os.environ.get("ADMIN_ID", "admin"),
        "admin_password": os.environ.get("ADMIN_PASSWORD", ""),
        "domain": os.environ.get("DOMAIN", "localhost:8000"),
        "login_max_failures": int(os.environ.get("LOGIN_MAX_FAILURES", "10")),
        "login_lockout_minutes": int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "30")),
        "issue_start_date": os.environ.get("ISSUE_START_DATE", "2000-01-01"),
        "issue_end_date": os.environ.get("ISSUE_END_DATE", "2099-12-31"),
    }


# ─── DB ──────────────────────────────────────────────────────────────────────

def get_db(config=None):
    if config is None:
        config = get_config()
    db_path = config["db_path"]
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(config):
    conn = get_db(config)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                class TEXT,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                guest_name TEXT NOT NULL,
                is_valid INTEGER DEFAULT 1,
                used INTEGER DEFAULT 0,
                used_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
            CREATE TABLE IF NOT EXISTS staff (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS temp_promotions (
                id TEXT PRIMARY KEY,
                promote_token TEXT UNIQUE,
                token_used INTEGER DEFAULT 0,
                session_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                promoted_by_type TEXT NOT NULL,
                promoted_by_id TEXT NOT NULL,
                promoted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
            CREATE TABLE IF NOT EXISTS offline_scan_queue (
                id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                scanned_at DATETIME NOT NULL,
                session_id TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                synced_at DATETIME,
                conflict INTEGER DEFAULT 0,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_failures (
                user_key TEXT PRIMARY KEY,
                failure_count INTEGER DEFAULT 0,
                locked_at REAL
            );
        """)
        conn.commit()

        # settings 初期データ（起動時のenv値で上書き）
        issue_start = config.get("issue_start_date", "2000-01-01")
        issue_end = config.get("issue_end_date", "2099-12-31")
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('issue_start', ?)",
            (issue_start,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('issue_end', ?)",
            (issue_end,)
        )
        conn.commit()

        # 管理者の自動生成（INSERT OR IGNORE で競合回避）
        admin_id = config["admin_id"]
        admin_password = config["admin_password"]
        if admin_password:
            existing = conn.execute("SELECT id FROM staff WHERE id = ?", (admin_id,)).fetchone()
            if not existing:
                pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
                conn.execute(
                    "INSERT OR IGNORE INTO staff (id, name, password_hash, role) VALUES (?, ?, ?, 'admin')",
                    (admin_id, admin_id, pw_hash)
                )
                conn.commit()
    finally:
        conn.close()


# ─── JWT ─────────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"

def make_token(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def today_midnight_utc() -> int:
    """当日 23:59:59 の UTC タイムスタンプ"""
    now = datetime.now(tz=timezone.utc)
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(midnight.timestamp())


def issue_student_token(student_id: str, secret: str, promoted: bool = False) -> str:
    now = int(time.time())
    payload = {
        "sub": student_id,
        "role": "student",
        "iat": now,
        "exp": now + 30 * 24 * 3600,
    }
    if promoted:
        payload["promoted"] = True
        payload["exp"] = today_midnight_utc()
    return make_token(payload, secret)


def issue_staff_token(staff_id: str, role: str, secret: str) -> str:
    now = int(time.time())
    payload = {
        "sub": staff_id,
        "role": role,
        "iat": now,
        "exp": today_midnight_utc(),
    }
    return make_token(payload, secret)


# ─── 認証依存 ─────────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def decode_token(credentials: HTTPAuthorizationCredentials, secret: str) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="認証が必要です")
    try:
        payload = jwt.decode(credentials.credentials, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="無効なトークンです")


# ─── ログイン失敗ロック ───────────────────────────────────────────────────────

def check_and_lock(conn, user_key: str, config: dict) -> bool:
    """ロック中の場合 True を返す"""
    max_failures = config["login_max_failures"]
    lockout_minutes = config["login_lockout_minutes"]

    row = conn.execute(
        "SELECT failure_count, locked_at FROM login_failures WHERE user_key = ?",
        (user_key,)
    ).fetchone()

    if row is None:
        return False

    failure_count = row["failure_count"]
    locked_at = row["locked_at"]

    if locked_at is not None:
        elapsed = time.time() - locked_at
        if elapsed < lockout_minutes * 60:
            return True
        else:
            # ロック解除
            conn.execute(
                "UPDATE login_failures SET failure_count = 0, locked_at = NULL WHERE user_key = ?",
                (user_key,)
            )
            conn.commit()
            return False

    return False


def record_failure(conn, user_key: str, config: dict):
    max_failures = config["login_max_failures"]
    row = conn.execute(
        "SELECT failure_count FROM login_failures WHERE user_key = ?",
        (user_key,)
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO login_failures (user_key, failure_count, locked_at) VALUES (?, 1, NULL)",
            (user_key,)
        )
        new_count = 1
    else:
        new_count = row["failure_count"] + 1
        conn.execute(
            "UPDATE login_failures SET failure_count = ? WHERE user_key = ?",
            (new_count, user_key)
        )

    if new_count >= max_failures:
        conn.execute(
            "UPDATE login_failures SET locked_at = ? WHERE user_key = ?",
            (time.time(), user_key)
        )

    conn.commit()


def reset_failures(conn, user_key: str):
    conn.execute(
        "DELETE FROM login_failures WHERE user_key = ?",
        (user_key,)
    )
    conn.commit()


# ─── Pydantic モデル ─────────────────────────────────────────────────────────

class StudentLoginRequest(BaseModel):
    student_id: str
    password: str

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v):
        if not v or not v.strip():
            raise ValueError("学籍番号は必須です")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not v or not v.strip():
            raise ValueError("パスワードは必須です")
        return v


class StaffLoginRequest(BaseModel):
    staff_id: str
    password: str


class TicketIssueRequest(BaseModel):
    guest_name: str
    student_id: Optional[str] = None

    @field_validator("guest_name")
    @classmethod
    def validate_guest_name(cls, v):
        if not v or not v.strip():
            raise ValueError("招待者名は必須です")
        return v


class TicketUpdateRequest(BaseModel):
    is_valid: Optional[int] = None
    used: Optional[int] = None


class AdminTicketCreateRequest(BaseModel):
    student_id: str
    guest_name: str


class StaffCreateRequest(BaseModel):
    staff_id: str
    name: str
    password: str
    role: str = "staff"


class SettingsUpdateRequest(BaseModel):
    issue_start: str
    issue_end: str


class OfflineScanItem(BaseModel):
    ticket_id: str
    scanned_at: str
    session_id: str


# ─── アプリファクトリ ─────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    config = get_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not config["jwt_secret"]:
            raise RuntimeError("JWT_SECRET が設定されていません。.envを確認してください。")
        init_db(config)
        yield

    app = FastAPI(lifespan=lifespan)

    # 静的ファイル配信
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # ─── 認証ヘルパー (クロージャでconfigをキャプチャ) ──

    def require_any(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        return decode_token(credentials, config["jwt_secret"])

    def require_student(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        payload = decode_token(credentials, config["jwt_secret"])
        role = payload.get("role", "")
        if role != "student":
            raise HTTPException(status_code=403, detail="生徒権限が必要です")
        return payload

    def require_staff_or_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        payload = decode_token(credentials, config["jwt_secret"])
        role = payload.get("role", "")
        # 昇格した生徒も許可
        if role in ("staff", "admin") or (role == "student" and payload.get("promoted")):
            return payload
        raise HTTPException(status_code=403, detail="スタッフ権限が必要です")

    def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        payload = decode_token(credentials, config["jwt_secret"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="管理者権限が必要です")
        return payload

    def require_student_or_promoted(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        """チケット発行: 生徒または昇格した生徒"""
        payload = decode_token(credentials, config["jwt_secret"])
        role = payload.get("role", "")
        if role == "student":
            return payload
        raise HTTPException(status_code=403, detail="生徒権限が必要です")

    def get_issue_period(conn):
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        return rows.get("issue_start", config["issue_start_date"]), rows.get("issue_end", config["issue_end_date"])

    # ─── CSV レスポンス生成ヘルパー ───────────────────────────────────────

    def make_csv_response(output: io.StringIO, filename: str) -> Response:
        """UTF-8 BOM付きCSVレスポンス（Excel・Numbers・Google スプレッドシート対応）"""
        content = output.getvalue().encode("utf-8-sig")
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # ─── QR 画像生成ヘルパー ─────────────────────────────────────────────

    # 日本語フォントパス（優先順で試行）
    _JP_FONT_PATHS = [
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]

    def _load_font(size: int):
        from PIL import ImageFont
        for path in _JP_FONT_PATHS:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def make_qr_base64(content: str, size: int = 300,
                       guest_name: str = "", issued_at: str = "",
                       student_name: str = "") -> str:
        from PIL import ImageDraw

        # QRコード生成（高解像度）
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(content)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        qr_img = qr_img.resize((size, size), Image.LANCZOS)

        # テキストなしの場合はそのまま返す
        if not guest_name and not issued_at and not student_name:
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

        # フォントサイズはQR幅に比例させる
        font_title = _load_font(max(18, size // 14))
        font_body  = _load_font(max(15, size // 18))
        padding    = max(14, size // 20)
        line_h     = font_title.size + 8 if hasattr(font_title, 'size') else 28

        # 各行のテキスト（タイトル・本文・サブ）
        lines = []
        if guest_name:
            lines.append((f"招待者：{guest_name}", font_title, (20, 20, 20)))
        if student_name:
            lines.append((f"発行者：{student_name}", font_body, (60, 60, 60)))
        if issued_at:
            try:
                dt = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y/%m/%d %H:%M")
            except Exception:
                date_str = str(issued_at)[:16]
            lines.append((f"発行日：{date_str}", font_body, (60, 60, 60)))
        lines.append(("🎪 学園祭入場チケット", font_body, (120, 120, 120)))

        header_h = len(lines) * line_h + padding * 2
        footer_h = padding
        total_h  = header_h + size + footer_h

        canvas = Image.new("RGB", (size, total_h), (255, 255, 255))
        draw   = ImageDraw.Draw(canvas)

        # テキスト描画
        y = padding
        for text, font, color in lines:
            draw.text((padding, y), text, font=font, fill=color)
            y += line_h

        # 区切り線
        draw.line([(0, header_h - 1), (size, header_h - 1)], fill=(200, 200, 200), width=1)

        # QRコードを貼り付け
        canvas.paste(qr_img, (0, header_h))

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # ─── フロントエンド配信 ──────────────────────────────────────────────

    _static_version = str(int(time.time()))

    @app.get("/", response_class=HTMLResponse)
    def spa_root():
        index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r'(/static/[^"\']+\.js)', r'\1?v=' + _static_version, content)
            return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
        return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)

    # SPA の全ルート（ハッシュルーティングなので / だけで OK だが念のため）
    @app.get("/app", response_class=HTMLResponse)
    def spa_app():
        return spa_root()

    # ─── ヘルスチェック ──────────────────────────────────────────────────

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ─── 生徒ページ（HTML stub） ─────────────────────────────────────────

    @app.get("/staff")
    def staff_page(credentials: HTTPAuthorizationCredentials = Depends(security)):
        if not credentials:
            raise HTTPException(status_code=401, detail="認証が必要です")
        try:
            payload = jwt.decode(credentials.credentials, config["jwt_secret"], algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=401, detail="無効なトークンです")
        role = payload.get("role", "")
        if role in ("staff", "admin"):
            return {"message": "スタッフページ"}
        if role == "student" and payload.get("promoted"):
            return {"message": "スタッフページ（昇格）"}
        raise HTTPException(status_code=403, detail="スタッフ権限が必要です")

    # ─── 認証 ────────────────────────────────────────────────────────────

    @app.post("/auth/login")
    def student_login(req: StudentLoginRequest):
        conn = get_db(config)
        try:
            user_key = f"student:{req.student_id}"
            if check_and_lock(conn, user_key, config):
                raise HTTPException(status_code=401, detail="アカウントがロックされています (lock)。30分後に再試行してください。")

            row = conn.execute(
                "SELECT id, password_hash FROM students WHERE id = ?",
                (req.student_id,)
            ).fetchone()

            if row is None or not bcrypt.checkpw(req.password.encode(), row["password_hash"].encode()):
                record_failure(conn, user_key, config)
                raise HTTPException(status_code=401, detail="学籍番号またはパスワードが正しくありません")

            reset_failures(conn, user_key)
            token = issue_student_token(req.student_id, config["jwt_secret"])
            return {"token": token}
        finally:
            conn.close()

    @app.post("/auth/staff/login")
    def staff_login(req: StaffLoginRequest):
        conn = get_db(config)
        try:
            user_key = f"staff:{req.staff_id}"
            if check_and_lock(conn, user_key, config):
                raise HTTPException(status_code=401, detail="アカウントがロックされています (lock)。30分後に再試行してください。")

            row = conn.execute(
                "SELECT id, password_hash, role FROM staff WHERE id = ?",
                (req.staff_id,)
            ).fetchone()

            if row is None or not bcrypt.checkpw(req.password.encode(), row["password_hash"].encode()):
                record_failure(conn, user_key, config)
                raise HTTPException(status_code=401, detail="IDまたはパスワードが正しくありません")

            reset_failures(conn, user_key)
            token = issue_staff_token(req.staff_id, row["role"], config["jwt_secret"])
            return {"token": token}
        finally:
            conn.close()

    # ─── チケット ────────────────────────────────────────────────────────

    @app.post("/ticket/issue")
    def issue_ticket(req: TicketIssueRequest, payload: dict = Depends(require_student_or_promoted)):
        student_id = payload["sub"]

        # 他の生徒IDを指定した場合は403
        if req.student_id and req.student_id != student_id:
            raise HTTPException(status_code=403, detail="他の生徒のチケットは発行できません")

        conn = get_db(config)
        try:
            # 発行期間チェック
            issue_start, issue_end = get_issue_period(conn)
            today = date.today().isoformat()
            if today < issue_start or today > issue_end:
                raise HTTPException(status_code=400, detail="QR発行期間外です")

            # 上限チェック（5枚）
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM tickets WHERE student_id = ? AND is_valid = 1",
                (student_id,)
            ).fetchone()["cnt"]
            if count >= 5:
                raise HTTPException(status_code=403, detail="発行上限（5枚）に達しています")

            ticket_id = secrets.token_urlsafe(12)
            domain = config["domain"]
            qr_content = f"https://{domain}/scan/{ticket_id}"
            safe_guest_name = html.escape(req.guest_name)

            conn.execute(
                "INSERT INTO tickets (id, student_id, guest_name) VALUES (?, ?, ?)",
                (ticket_id, student_id, safe_guest_name)
            )
            conn.commit()

            # 発行直後の日時・生徒名を取得してQR画像に埋め込む
            issued_row = conn.execute(
                "SELECT t.created_at, s.name FROM tickets t JOIN students s ON t.student_id = s.id WHERE t.id = ?",
                (ticket_id,)
            ).fetchone()
            issued_at    = issued_row["created_at"] if issued_row else ""
            student_name = issued_row["name"]       if issued_row else student_id

            remaining = 5 - (count + 1)
            qr_image = make_qr_base64(
                qr_content,
                guest_name=safe_guest_name,
                issued_at=issued_at,
                student_name=student_name,
            )
            return {
                "ticket_id": ticket_id,
                "qr_url": qr_content,
                "qr_content": qr_content,
                "qr_image": qr_image,
                "remaining": remaining,
            }
        finally:
            conn.close()

    @app.get("/ticket/list")
    def list_tickets(payload: dict = Depends(require_student_or_promoted)):
        student_id = payload["sub"]
        conn = get_db(config)
        try:
            rows = conn.execute(
                """SELECT t.id as ticket_id, t.guest_name, t.is_valid, t.used,
                          t.used_at, t.created_at, s.name as student_name
                   FROM tickets t JOIN students s ON t.student_id = s.id
                   WHERE t.student_id = ?""",
                (student_id,)
            ).fetchall()
            domain = config["domain"]
            tickets = []
            for r in rows:
                t = dict(r)
                qr_content = f"https://{domain}/scan/{t['ticket_id']}"
                t["qr_url"] = qr_content
                t["qr_image"] = make_qr_base64(
                    qr_content,
                    guest_name=t.get("guest_name", ""),
                    issued_at=t.get("created_at", ""),
                    student_name=t.get("student_name", ""),
                )
                tickets.append(t)
            return tickets
        finally:
            conn.close()

    @app.delete("/ticket/{ticket_id}")
    def delete_ticket(ticket_id: str, payload: dict = Depends(require_student_or_promoted)):
        student_id = payload["sub"]
        conn = get_db(config)
        try:
            row = conn.execute(
                "SELECT id, student_id, used FROM tickets WHERE id = ?",
                (ticket_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="チケットが見つかりません")
            if row["student_id"] != student_id:
                raise HTTPException(status_code=403, detail="他の生徒のチケットは削除できません")
            if row["used"] == 1:
                raise HTTPException(status_code=400, detail="入場済みチケットは削除できません")
            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            conn.commit()
            return {"message": "削除しました"}
        finally:
            conn.close()

    @app.post("/ticket/scan")
    def scan_ticket(body: dict, payload: dict = Depends(require_staff_or_admin)):
        ticket_id = body.get("ticket_id", "")
        conn = get_db(config)
        try:
            # BEGIN IMMEDIATE で書き込みロックを取得してから読み書き
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT id, is_valid, used FROM tickets WHERE id = ?",
                (ticket_id,)
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise HTTPException(status_code=404, detail="存在しないチケットです (not found)")
            if row["is_valid"] == 0:
                conn.execute("ROLLBACK")
                raise HTTPException(status_code=400, detail="無効なチケットです (invalid ticket)")
            if row["used"] == 1:
                conn.execute("ROLLBACK")
                raise HTTPException(status_code=409, detail="入場済みチケットです (already used)")

            used_at = datetime.now(tz=timezone.utc).isoformat()
            conn.execute(
                "UPDATE tickets SET used = 1, used_at = ? WHERE id = ?",
                (used_at, ticket_id)
            )
            conn.execute("COMMIT")
            return {"status": "ok", "result": "ok", "color": "green", "used_at": used_at}
        except HTTPException:
            raise
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    @app.post("/ticket/scan/{ticket_id}/cancel")
    def cancel_scan(ticket_id: str, payload: dict = Depends(require_staff_or_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id, used FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="チケットが見つかりません")
            conn.execute("UPDATE tickets SET used = 0, used_at = NULL WHERE id = ?", (ticket_id,))
            conn.commit()
            return {"message": "入場取消しました"}
        finally:
            conn.close()

    @app.get("/ticket/cache")
    def get_ticket_cache(since: Optional[str] = None, payload: dict = Depends(require_staff_or_admin)):
        conn = get_db(config)
        try:
            if since:
                rows = conn.execute(
                    "SELECT id as ticket_id, is_valid, used, used_at, created_at FROM tickets WHERE created_at > ? OR used_at > ?",
                    (since, since)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id as ticket_id, is_valid, used, used_at, created_at FROM tickets WHERE is_valid = 1"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.post("/ticket/sync")
    def sync_tickets(items: List[OfflineScanItem], payload: dict = Depends(require_staff_or_admin)):
        conn = get_db(config)
        try:
            results = []
            for item in items:
                sync_id = secrets.token_urlsafe(8)
                row = conn.execute("SELECT id, is_valid, used FROM tickets WHERE id = ?", (item.ticket_id,)).fetchone()
                if row is None:
                    results.append({"ticket_id": item.ticket_id, "conflict": 0, "error": "not found"})
                    continue

                if row["used"] == 1:
                    # 競合
                    conn.execute(
                        "INSERT INTO offline_scan_queue (id, ticket_id, scanned_at, session_id, synced, conflict) VALUES (?, ?, ?, ?, 1, 1)",
                        (sync_id, item.ticket_id, item.scanned_at, item.session_id)
                    )
                    results.append({"ticket_id": item.ticket_id, "conflict": 1})
                else:
                    used_at = item.scanned_at
                    conn.execute(
                        "UPDATE tickets SET used = 1, used_at = ? WHERE id = ?",
                        (used_at, item.ticket_id)
                    )
                    conn.execute(
                        "INSERT INTO offline_scan_queue (id, ticket_id, scanned_at, session_id, synced, synced_at) VALUES (?, ?, ?, ?, 1, ?)",
                        (sync_id, item.ticket_id, item.scanned_at, item.session_id, used_at)
                    )
                    results.append({"ticket_id": item.ticket_id, "conflict": 0, "synced": 1})
                conn.commit()
            return results
        finally:
            conn.close()

    # ─── 管理者 ──────────────────────────────────────────────────────────

    @app.get("/admin/dashboard")
    def admin_dashboard(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            total_entries = conn.execute("SELECT COUNT(*) as cnt FROM tickets WHERE used = 1").fetchone()["cnt"]
            unused_count = conn.execute("SELECT COUNT(*) as cnt FROM tickets WHERE used = 0 AND is_valid = 1").fetchone()["cnt"]

            # 30分単位の入場グラフデータ
            rows = conn.execute(
                "SELECT used_at FROM tickets WHERE used = 1 AND used_at IS NOT NULL"
            ).fetchall()
            graph_data = {}
            for r in rows:
                try:
                    dt = datetime.fromisoformat(r["used_at"].replace("Z", "+00:00"))
                    slot = dt.strftime("%H:%M").replace(
                        dt.strftime("%M"),
                        "30" if int(dt.strftime("%M")) >= 30 else "00"
                    )
                    key = f"{dt.strftime('%H')}:{slot.split(':')[1]}"
                    graph_data[key] = graph_data.get(key, 0) + 1
                except Exception:
                    pass

            # 生徒別入場状況
            student_rows = conn.execute("""
                SELECT s.id, s.name, s.class,
                       COUNT(t.id) as issued_count,
                       SUM(CASE WHEN t.used = 1 THEN 1 ELSE 0 END) as entry_count
                FROM students s
                LEFT JOIN tickets t ON s.id = t.student_id
                GROUP BY s.id
            """).fetchall()

            return {
                "total_entries": total_entries,
                "entry_count": total_entries,
                "unused_count": unused_count,
                "unused_tickets": unused_count,
                "hourly_entries": graph_data,
                "entry_graph": graph_data,
                "graph_data": graph_data,
                "student_entries": [dict(r) for r in student_rows],
                "students": [dict(r) for r in student_rows],
            }
        finally:
            conn.close()

    @app.get("/admin/tickets")
    def admin_list_tickets(
        student_name: Optional[str] = None,
        status: Optional[str] = None,
        payload: dict = Depends(require_admin)
    ):
        conn = get_db(config)
        try:
            query = """
                SELECT t.id as ticket_id, t.student_id, s.name as student_name, s.class,
                       t.guest_name, t.is_valid, t.used, t.used_at, t.created_at
                FROM tickets t
                JOIN students s ON t.student_id = s.id
            """
            conditions = []
            params = []
            if student_name:
                conditions.append("s.name LIKE ?")
                params.append(f"%{student_name}%")
            if status == "used":
                conditions.append("t.used = 1")
            elif status == "invalid":
                conditions.append("t.is_valid = 0")
            elif status == "unused":
                conditions.append("t.used = 0 AND t.is_valid = 1")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.get("/admin/tickets/{ticket_id}")
    def admin_get_ticket(ticket_id: str, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute(
                """SELECT t.id as ticket_id, t.student_id, s.name as student_name, s.class,
                          t.guest_name, t.is_valid, t.used, t.used_at, t.created_at
                   FROM tickets t JOIN students s ON t.student_id = s.id
                   WHERE t.id = ?""",
                (ticket_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="チケットが見つかりません")
            return dict(row)
        finally:
            conn.close()

    @app.put("/admin/tickets/{ticket_id}")
    def admin_update_ticket(ticket_id: str, req: TicketUpdateRequest, payload: dict = Depends(require_admin)):
        # スタッフが無効化しようとした場合のチェックは require_admin が担当
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="チケットが見つかりません")

            if req.is_valid is not None:
                conn.execute("UPDATE tickets SET is_valid = ? WHERE id = ?", (req.is_valid, ticket_id))
            if req.used is not None:
                if req.used == 0:
                    conn.execute("UPDATE tickets SET used = 0, used_at = NULL WHERE id = ?", (ticket_id,))
                else:
                    used_at = datetime.now(tz=timezone.utc).isoformat()
                    conn.execute(
                        "UPDATE tickets SET used = 1, used_at = ? WHERE id = ?",
                        (used_at, ticket_id)
                    )
            conn.commit()

            row = conn.execute("SELECT id as ticket_id, is_valid, used, used_at FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    @app.post("/admin/tickets")
    def admin_add_ticket(req: AdminTicketCreateRequest, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            student = conn.execute("SELECT id FROM students WHERE id = ?", (req.student_id,)).fetchone()
            if student is None:
                raise HTTPException(status_code=404, detail="生徒が見つかりません")
            ticket_id = secrets.token_urlsafe(12)
            conn.execute(
                "INSERT INTO tickets (id, student_id, guest_name) VALUES (?, ?, ?)",
                (ticket_id, req.student_id, req.guest_name)
            )
            conn.commit()
            return {"ticket_id": ticket_id}
        finally:
            conn.close()

    @app.delete("/admin/tickets/{ticket_id}")
    def admin_delete_ticket(ticket_id: str, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="チケットが見つかりません")
            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            conn.commit()
            return {"message": "削除しました"}
        finally:
            conn.close()

    @app.get("/admin/students")
    def admin_list_students(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            rows = conn.execute("""
                SELECT s.id, s.name, s.class,
                       COUNT(t.id) as ticket_count,
                       SUM(CASE WHEN t.used = 1 THEN 1 ELSE 0 END) as entry_count
                FROM students s
                LEFT JOIN tickets t ON s.id = t.student_id
                GROUP BY s.id
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.get("/admin/students/{student_id}")
    def admin_get_student(student_id: str, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("""
                SELECT s.id, s.name, s.class,
                       COUNT(t.id) as ticket_count,
                       COUNT(t.id) as issued_count,
                       SUM(CASE WHEN t.used = 1 THEN 1 ELSE 0 END) as entry_count
                FROM students s
                LEFT JOIN tickets t ON s.id = t.student_id
                WHERE s.id = ?
                GROUP BY s.id
            """, (student_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="生徒が見つかりません")
            return dict(row)
        finally:
            conn.close()

    class StudentCreateRequest(BaseModel):
        student_id: str
        name: str
        class_name: str = ""
        password: str

    class StudentUpdateRequest(BaseModel):
        name: Optional[str] = None
        class_name: Optional[str] = None
        password: Optional[str] = None

    @app.post("/admin/students")
    def admin_create_student(req: StudentCreateRequest, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            existing = conn.execute("SELECT id FROM students WHERE id = ?", (req.student_id,)).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="この学籍番号は既に登録されています")
            if not req.student_id or not req.name or not req.password:
                raise HTTPException(status_code=400, detail="学籍番号・氏名・パスワードは必須です")
            pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO students (id, name, class, password_hash) VALUES (?, ?, ?, ?)",
                (req.student_id, req.name, req.class_name, pw_hash)
            )
            conn.commit()
            return {"message": "生徒を登録しました", "student_id": req.student_id}
        finally:
            conn.close()

    @app.put("/admin/students/{student_id}")
    def admin_update_student(student_id: str, req: StudentUpdateRequest, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="生徒が見つかりません")
            if req.name is not None:
                conn.execute("UPDATE students SET name = ? WHERE id = ?", (req.name, student_id))
            if req.class_name is not None:
                conn.execute("UPDATE students SET class = ? WHERE id = ?", (req.class_name, student_id))
            if req.password is not None and req.password:
                pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
                conn.execute("UPDATE students SET password_hash = ? WHERE id = ?", (pw_hash, student_id))
            conn.commit()
            return {"message": "更新しました"}
        finally:
            conn.close()

    class ResetPasswordRequest(BaseModel):
        password: Optional[str] = None

    @app.post("/admin/students/{student_id}/reset-password")
    def admin_reset_student_password(student_id: str, req: ResetPasswordRequest = ResetPasswordRequest(), payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="生徒が見つかりません")
            if req.password and len(req.password.strip()) > 0:
                new_password = req.password.strip()
                if len(new_password) < 4:
                    raise HTTPException(status_code=400, detail="パスワードは4文字以上で入力してください")
            else:
                chars = string.ascii_letters + string.digits
                new_password = "".join(secrets.choice(chars) for _ in range(8))
            pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
            conn.execute("UPDATE students SET password_hash = ? WHERE id = ?", (pw_hash, student_id))
            conn.commit()
            return {"password": new_password}
        finally:
            conn.close()

    @app.delete("/admin/students/{student_id}")
    def admin_delete_student(student_id: str, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            row = conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="生徒が見つかりません")
            # チケットも削除
            conn.execute("DELETE FROM tickets WHERE student_id = ?", (student_id,))
            conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
            conn.commit()
            return {"message": "削除しました"}
        finally:
            conn.close()

    @app.post("/admin/import")
    async def import_csv(file: UploadFile = File(...), payload: dict = Depends(require_admin)):
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="CSVファイルのみアップロード可能です")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="空のファイルです")

        # エンコーディング判定
        for encoding in ("utf-8-sig", "utf-8", "shift_jis", "cp932"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(status_code=400, detail="文字コードを判定できませんでした")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            raise HTTPException(status_code=400, detail="データが空です")

        # ヘッダー判定: 1列目が数値でなければヘッダーとみなす
        start_idx = 0
        if rows and not rows[0][0].strip().isdigit():
            start_idx = 1

        conn = get_db(config)
        try:
            success_count = 0
            skip_count = 0
            new_passwords = []

            for row in rows[start_idx:]:
                if len(row) < 3:
                    skip_count += 1
                    continue
                student_id, name, class_ = row[0].strip(), row[1].strip(), row[2].strip()
                if not student_id:
                    skip_count += 1
                    continue

                existing = conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
                if existing:
                    skip_count += 1
                    continue

                # パスワード自動生成（英数字8文字）
                chars = string.ascii_letters + string.digits
                password = "".join(secrets.choice(chars) for _ in range(8))
                pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                conn.execute(
                    "INSERT INTO students (id, name, class, password_hash) VALUES (?, ?, ?, ?)",
                    (student_id, name, class_, pw_hash)
                )
                new_passwords.append((student_id, password, name, class_))
                success_count += 1

            conn.commit()

            # セッションに保存（簡易実装: メモリ）
            if not hasattr(app.state, "last_import_passwords"):
                app.state.last_import_passwords = []
            app.state.last_import_passwords = new_passwords

            return {"success_count": success_count, "skip_count": skip_count}
        finally:
            conn.close()

    @app.get("/admin/import/passwords")
    def get_import_passwords(payload: dict = Depends(require_admin)):
        passwords = getattr(app.state, "last_import_passwords", [])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["学籍番号", "パスワード", "氏名", "クラス"])
        for row in passwords:
            writer.writerow(row)
        return make_csv_response(output, "passwords.csv")

    @app.get("/admin/export")
    def export_tickets_csv(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            rows = conn.execute("""
                SELECT s.id as student_id, s.name as student_name, s.class,
                       t.guest_name, t.id as ticket_id, t.used, t.is_valid
                FROM tickets t JOIN students s ON t.student_id = s.id
            """).fetchall()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["学籍番号", "生徒名", "クラス", "招待者名", "チケットID", "入場状況", "有効"])
            for r in rows:
                used_label = "入場済み" if r["used"] == 1 else "未入場"
                valid_label = "有効" if r["is_valid"] == 1 else "無効"
                writer.writerow([r["student_id"], r["student_name"], r["class"], r["guest_name"], r["ticket_id"], used_label, valid_label])

            return make_csv_response(output, "tickets_export.csv")
        finally:
            conn.close()

    @app.get("/admin/staff")
    def list_staff(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            rows = conn.execute("SELECT id, name, role FROM staff").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.post("/admin/staff")
    def create_staff(req: StaffCreateRequest, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            existing = conn.execute("SELECT id FROM staff WHERE id = ?", (req.staff_id,)).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="既に存在するIDです")
            pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO staff (id, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (req.staff_id, req.name, pw_hash, req.role)
            )
            conn.commit()
            return {"message": "スタッフを登録しました"}
        finally:
            conn.close()

    @app.delete("/admin/staff/{staff_id}")
    def delete_staff(staff_id: str, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
            conn.commit()
            return {"message": "削除しました"}
        finally:
            conn.close()

    @app.get("/admin/staff/export")
    def export_staff_csv(payload: dict = Depends(require_admin)):
        """スタッフ一覧をCSVでエクスポート（パスワードは含めない）"""
        conn = get_db(config)
        try:
            rows = conn.execute("SELECT id, name, role FROM staff").fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["スタッフID", "氏名", "ロール"])
            for r in rows:
                writer.writerow([r["id"], r["name"], r["role"]])
            return make_csv_response(output, "staff_export.csv")
        finally:
            conn.close()

    @app.post("/admin/staff/import")
    async def import_staff_csv(file: UploadFile = File(...), payload: dict = Depends(require_admin)):
        """
        スタッフCSVインポート
        フォーマット: スタッフID,氏名,パスワード,ロール（ロール省略時は staff）
        """
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="CSVファイルのみアップロード可能です")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="空のファイルです")

        for encoding in ("utf-8-sig", "utf-8", "shift_jis", "cp932"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(status_code=400, detail="文字コードを判定できませんでした")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="データが空です")

        # ヘッダー判定: 1列目が数値でなければヘッダーとみなす
        start_idx = 1 if rows and not rows[0][0].strip()[0:1].isascii() or (rows and rows[0][0].strip().lower() in ("スタッフid", "id", "staff_id")) else 0

        conn = get_db(config)
        try:
            success_count = 0
            skip_count = 0
            error_rows = []

            for i, row in enumerate(rows[start_idx:], start=start_idx + 1):
                if len(row) < 3:
                    skip_count += 1
                    continue
                staff_id = row[0].strip()
                name     = row[1].strip()
                password = row[2].strip()
                role     = row[3].strip() if len(row) >= 4 else "staff"

                if not staff_id or not name or not password:
                    skip_count += 1
                    continue
                if role not in ("staff", "admin"):
                    role = "staff"

                existing = conn.execute("SELECT id FROM staff WHERE id = ?", (staff_id,)).fetchone()
                if existing:
                    skip_count += 1
                    continue

                pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                conn.execute(
                    "INSERT INTO staff (id, name, password_hash, role) VALUES (?, ?, ?, ?)",
                    (staff_id, name, pw_hash, role)
                )
                success_count += 1

            conn.commit()
            return {"success_count": success_count, "skip_count": skip_count}
        finally:
            conn.close()

    @app.get("/admin/settings")
    def get_settings(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
            return {"issue_start": rows.get("issue_start", ""), "issue_end": rows.get("issue_end", "")}
        finally:
            conn.close()

    @app.put("/admin/settings")
    def update_settings(req: SettingsUpdateRequest, payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('issue_start', ?)", (req.issue_start,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('issue_end', ?)", (req.issue_end,))
            conn.commit()
            return {"issue_start": req.issue_start, "issue_end": req.issue_end}
        finally:
            conn.close()

    # ─── 昇格機能 ────────────────────────────────────────────────────────

    @app.post("/promote/request")
    def promote_request(payload: dict = Depends(require_student)):
        student_id = payload["sub"]
        promote_token = secrets.token_urlsafe(24)
        session_id = secrets.token_urlsafe(16)

        conn = get_db(config)
        try:
            now = datetime.now(tz=timezone.utc)
            expires_at = now.replace(hour=23, minute=59, second=59, microsecond=0)

            promo_id = secrets.token_urlsafe(8)
            conn.execute(
                """INSERT INTO temp_promotions
                   (id, promote_token, token_used, session_id, student_id,
                    promoted_by_type, promoted_by_id, expires_at)
                   VALUES (?, ?, 0, ?, ?, 'pending', 'pending', ?)""",
                (promo_id, promote_token, session_id, student_id, expires_at.isoformat())
            )
            conn.commit()
            # QRコードに埋め込むURL
            domain = config["domain"]
            qr_content = f"https://{domain}/promote/approve?token={promote_token}"
            qr_image = make_qr_base64(qr_content)
            return {
                "promote_token": promote_token,
                "session_id": session_id,
                "qr_image": qr_image,
                "qr_content": qr_content,
            }
        finally:
            conn.close()

    @app.post("/promote/approve")
    def promote_approve(body: dict, credentials: HTTPAuthorizationCredentials = Depends(security)):
        if not credentials:
            raise HTTPException(status_code=401, detail="認証が必要です")
        try:
            payload = jwt.decode(credentials.credentials, config["jwt_secret"], algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=401, detail="無効なトークンです")

        role = payload.get("role", "")
        promoted = payload.get("promoted", False)

        # 管理者・スタッフ・昇格済み生徒のみ昇格承認可能
        if role not in ("admin", "staff") and not (role == "student" and promoted):
            raise HTTPException(status_code=403, detail="昇格承認権限がありません")

        promote_token = body.get("promote_token", "")
        conn = get_db(config)
        try:
            row = conn.execute(
                "SELECT id, student_id, token_used FROM temp_promotions WHERE promote_token = ?",
                (promote_token,)
            ).fetchone()

            if row is None:
                raise HTTPException(status_code=400, detail="無効な昇格トークンです")
            if row["token_used"] == 1:
                raise HTTPException(status_code=409, detail="使用済みの昇格トークンです")

            student_id = row["student_id"]
            approver_id = payload["sub"]
            approver_type = "staff" if role in ("admin", "staff") else "student"

            now = datetime.now(tz=timezone.utc)
            expires_at = now.replace(hour=23, minute=59, second=59, microsecond=0)

            conn.execute(
                """UPDATE temp_promotions
                   SET token_used = 1, promoted_by_type = ?, promoted_by_id = ?,
                       promoted_at = ?, expires_at = ?
                   WHERE promote_token = ?""",
                (approver_type, approver_id, now.isoformat(), expires_at.isoformat(), promote_token)
            )
            conn.commit()

            # 昇格フラグ付きJWT発行
            token = issue_student_token(student_id, config["jwt_secret"], promoted=True)
            return {"token": token, "student_id": student_id}
        finally:
            conn.close()

    @app.get("/promote/list")
    def promote_list(payload: dict = Depends(require_admin)):
        conn = get_db(config)
        try:
            rows = conn.execute(
                """SELECT id, student_id, promoted_by_type, promoted_by_id,
                          promoted_at, expires_at
                   FROM temp_promotions WHERE token_used = 1"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return app


app = create_app()
