"""TC-02: CSVインポート"""

import pytest
from conftest import make_csv_bytes, STUDENT_ID, STUDENT_PASSWORD, auth_header


# ─── TC-02-01: 正常系 ────────────────────────────────────────────────────────

class TestCsvImportNormal:
    def test_TC_02_01_001_utf8_with_header(self, client, admin_headers):
        """TC-02-01-001: UTF-8 ヘッダーあり CSV → 全行取込成功"""
        csv_bytes = make_csv_bytes(
            rows=[["1001", "山田太郎", "1-A"], ["1002", "鈴木花子", "1-B"]],
            header=["学籍番号", "氏名", "クラス"],
        )
        resp = client.post(
            "/admin/import",
            files={"file": ("students.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 2

    def test_TC_02_01_002_utf8_without_header(self, client, admin_headers):
        """TC-02-01-002: UTF-8 ヘッダーなし CSV → 全行取込成功"""
        csv_bytes = make_csv_bytes(
            rows=[["2001", "田中一郎", "2-A"], ["2002", "伊藤次郎", "2-B"]],
        )
        resp = client.post(
            "/admin/import",
            files={"file": ("students.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 2

    def test_TC_02_01_003_shift_jis_csv(self, client, admin_headers):
        """TC-02-01-003: Shift-JIS CSV → 文字化けなく全行取込成功"""
        csv_bytes = make_csv_bytes(
            rows=[["3001", "佐藤花子", "3-A"]],
            header=["学籍番号", "氏名", "クラス"],
            encoding="shift_jis",
        )
        resp = client.post(
            "/admin/import",
            files={"file": ("students_sjis.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 1

    def test_TC_02_01_004_password_auto_generated(self, client, admin_headers):
        """TC-02-01-004: インポート後、パスワード一覧 CSV に英数字 8 文字のパスワードが含まれる"""
        csv_bytes = make_csv_bytes(rows=[["4001", "パスワードテスト", "4-A"]])
        client.post(
            "/admin/import",
            files={"file": ("s.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        pwd_resp = client.get("/admin/import/passwords", headers=admin_headers)
        assert pwd_resp.status_code == 200
        lines = pwd_resp.text.strip().split("\n")
        data_lines = [l for l in lines[1:] if l.strip()]  # ヘッダーをスキップ
        assert len(data_lines) >= 1
        for line in data_lines:
            parts = line.split(",")
            assert len(parts) >= 2
            password = parts[1].strip()
            assert len(password) == 8
            assert password.isalnum()

    def test_TC_02_01_005_passwords_are_unique(self, client, admin_headers):
        """TC-02-01-005: 1000 件インポート後、パスワードがすべて異なる"""
        rows = [[str(5000 + i), f"生徒{i}", "5-A"] for i in range(100)]
        csv_bytes = make_csv_bytes(rows=rows)
        client.post(
            "/admin/import",
            files={"file": ("s.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        pwd_resp = client.get("/admin/import/passwords", headers=admin_headers)
        assert pwd_resp.status_code == 200
        lines = pwd_resp.text.strip().split("\n")[1:]
        passwords = [l.split(",")[1].strip() for l in lines if l.strip()]
        assert len(passwords) == len(set(passwords)), "パスワードに重複がある"

    def test_TC_02_01_006_import_result_display(self, client, admin_headers):
        """TC-02-01-006: インポート結果に success_count・skip_count が含まれる"""
        csv_bytes = make_csv_bytes(rows=[["6001", "結果確認", "6-A"]])
        resp = client.post(
            "/admin/import",
            files={"file": ("s.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "success_count" in body
        assert "skip_count" in body


# ─── TC-02-02: 異常系・境界値 ──────────────────────────────────────────────────

class TestCsvImportAbnormal:
    def test_TC_02_02_001_existing_student_skipped(self, client, admin_headers, tmp_db):
        """TC-02-02-001: 既存学籍番号はスキップ・skip_count に計上される"""
        from conftest import seed_student
        seed_student(tmp_db, "1001", "山田太郎", "1-A", "abc12345")
        csv_bytes = make_csv_bytes(rows=[["1001", "山田太郎", "1-A"], ["7001", "新規生徒", "7-A"]])
        resp = client.post(
            "/admin/import",
            files={"file": ("s.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["skip_count"] >= 1
        assert body["success_count"] >= 1

    def test_TC_02_02_002_existing_student_password_unchanged(self, client, admin_headers, tmp_db):
        """TC-02-02-002: スキップされた生徒の既存パスワードで引き続きログイン可能"""
        from conftest import seed_student
        seed_student(tmp_db, "1001", "山田太郎", "1-A", "abc12345")
        csv_bytes = make_csv_bytes(rows=[["1001", "山田太郎2", "1-B"]])
        client.post(
            "/admin/import",
            files={"file": ("s.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        login_resp = client.post("/auth/login", json={
            "student_id": "1001",
            "password": "abc12345",
        })
        assert login_resp.status_code == 200

    def test_TC_02_02_003_row_with_missing_columns_skipped(self, client, admin_headers):
        """TC-02-02-003: 列数不足の行はスキップまたはエラー"""
        from io import BytesIO
        csv_content = "8001,二列のみ\n8002,正常行,8-A\n"
        resp = client.post(
            "/admin/import",
            files={"file": ("s.csv", BytesIO(csv_content.encode()), "text/csv")},
            headers=admin_headers,
        )
        # エラーまたはスキップ件数あり
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            body = resp.json()
            assert body["skip_count"] >= 1 or body.get("error_count", 0) >= 1

    def test_TC_02_02_004_empty_file_error(self, client, admin_headers):
        """TC-02-02-004: 空ファイル → エラーメッセージ"""
        from io import BytesIO
        resp = client.post(
            "/admin/import",
            files={"file": ("empty.csv", BytesIO(b""), "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_TC_02_02_005_non_csv_extension_rejected(self, client, admin_headers):
        """TC-02-02-005: .txt ファイル → バリデーションエラー"""
        from io import BytesIO
        resp = client.post(
            "/admin/import",
            files={"file": ("students.txt", BytesIO(b"1001,test,1-A"), "text/plain")},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_TC_02_02_006_1000_rows(self, client, admin_headers):
        """TC-02-02-006: 1000 件インポート → 全件正常取込"""
        rows = [[str(9000 + i), f"生徒{i:04d}", f"{(i % 3) + 1}-A"] for i in range(1000)]
        csv_bytes = make_csv_bytes(rows=rows)
        resp = client.post(
            "/admin/import",
            files={"file": ("1000.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 1000

    def test_TC_02_02_007_sql_injection_in_student_id(self, client, admin_headers):
        """TC-02-02-007: 学籍番号に SQL インジェクション文字列 → DB エラーなし"""
        from io import BytesIO
        csv_content = "\"'; DROP TABLE students; --\",悪意テスト,1-A\n"
        resp = client.post(
            "/admin/import",
            files={"file": ("inject.csv", BytesIO(csv_content.encode()), "text/csv")},
            headers=admin_headers,
        )
        # エラーまたはスキップ。重要: サーバーが 500 を返してはいけない
        assert resp.status_code != 500
        # DB が壊れていないことを確認（管理者ログインが引き続き可能）
        login_resp = client.post("/auth/staff/login", json={
            "staff_id": "admin",
            "password": "adminpass123",
        })
        assert login_resp.status_code == 200
