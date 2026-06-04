"""TC-13: 負荷・スケール（参考）

NOTE: これらは性能目標であり、CI では時間がかかるため
      @pytest.mark.slow でタグ付けして任意実行にする。
      実行する場合: pytest -m slow
"""

import time
import pytest
from conftest import make_csv_bytes, auth_header, seed_student, STUDENT_ID, STUDENT_PASSWORD


pytestmark = pytest.mark.slow


class TestLoadAndScale:
    def test_TC_13_001_1000_students_list_under_3_seconds(self, client, admin_headers, tmp_db):
        """TC-13-001: 生徒 1000 件一覧が 3 秒以内に表示される"""
        rows = [[str(i), f"生徒{i:04d}", f"{(i % 3) + 1}-A"] for i in range(1000)]
        csv_bytes = make_csv_bytes(rows=rows)
        import_resp = client.post(
            "/admin/import",
            files={"file": ("1000.csv", csv_bytes, "text/csv")},
            headers=admin_headers,
        )
        assert import_resp.status_code == 200

        start = time.perf_counter()
        resp = client.get("/admin/students", headers=admin_headers)
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        students = resp.json() if isinstance(resp.json(), list) else resp.json().get("students", [])
        assert len(students) == 1000
        assert elapsed < 3.0, f"生徒一覧取得が {elapsed:.2f}秒かかった（上限 3 秒）"

    def test_TC_13_002_6000_tickets_list_under_5_seconds(self, client, admin_headers, tmp_db):
        """TC-13-002: チケット 6000 件一覧が 5 秒以内に表示される"""
        # 生徒 1200 人を登録（各 5 枚 = 6000 チケット）
        rows = [[str(i), f"生徒{i:04d}", "1-A"] for i in range(1200)]
        client.post(
            "/admin/import",
            files={"file": ("students.csv", make_csv_bytes(rows=rows), "text/csv")},
            headers=admin_headers,
        )
        # 管理者で全生徒に各 5 枚チケットを手動追加
        for i in range(1200):
            for _ in range(5):
                client.post(
                    "/admin/tickets",
                    json={"student_id": str(i), "guest_name": "来場者"},
                    headers=admin_headers,
                )

        start = time.perf_counter()
        resp = client.get("/admin/tickets", headers=admin_headers)
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        tickets = resp.json() if isinstance(resp.json(), list) else resp.json().get("tickets", [])
        assert len(tickets) == 6000
        assert elapsed < 5.0, f"チケット一覧取得が {elapsed:.2f}秒かかった（上限 5 秒）"

    def test_TC_13_003_concurrent_scans_no_duplicate_entry(self, client, admin_headers, tmp_db):
        """TC-13-003: 複数端末が同一チケットをほぼ同時にスキャン → 重複入場なし"""
        import threading

        seed_student(tmp_db, STUDENT_ID, "山田太郎", "1-A", STUDENT_PASSWORD)
        login_resp = client.post("/auth/login", json={"student_id": STUDENT_ID, "password": STUDENT_PASSWORD})
        s_headers = auth_header(login_resp.json()["token"])
        issue_resp = client.post("/ticket/issue", json={"guest_name": "同時スキャンテスト"}, headers=s_headers)
        ticket_id = issue_resp.json()["ticket_id"]

        from conftest import STAFF_ID, STAFF_PASSWORD, seed_staff_member
        staff_tokens = []
        for i in range(5):
            staff_id = f"concurrent_staff_{i:02d}"
            seed_staff_member(tmp_db, staff_id, f"スタッフ{i}", f"pass{i}0000")
            resp = client.post("/auth/staff/login", json={"staff_id": staff_id, "password": f"pass{i}0000"})
            staff_tokens.append(auth_header(resp.json()["token"]))

        results = []
        errors = []

        def scan(headers):
            try:
                r = client.post(
                    "/ticket/scan",
                    json={"ticket_id": ticket_id},
                    headers=headers,
                )
                results.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=scan, args=(h,)) for h in staff_tokens]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 成功（200）は 1 件のみ、残りはエラー（入場済みや競合）
        success_count = results.count(200)
        assert success_count == 1, f"重複入場: {results}"
        assert not errors, f"スレッドエラー: {errors}"
