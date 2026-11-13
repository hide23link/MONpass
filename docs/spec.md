# 学園祭入場システム 設計書

作成日: 2026年6月3日  
最終更新: 2026年11月14日

---

## 1. 要件

| 項目 | 内容 |
|---|---|
| 対象生徒 | 1000人 |
| 最大来場者 | 6000人（生徒1人あたり最大5名） |
| 招待者名入力 | 必須（QR発行時） |
| QR発行期間 | 学園祭2週間前〜当日 |
| 公開範囲 | インターネット公開（サブドメイン） |
| 管理者 | 5名 |
| パスキー | 後で検討 |

---

## 2. 認証方式

```
生徒:    学籍番号 + 配布パスワード
スタッフ: ID + パスワード（管理者が事前登録 or CSV一括登録）
管理者:  ID + パスワード（.envの初期値から自動生成）
※パスキーは後で追加可能な設計にしておく
```

### セッション管理

| 項目 | 内容 |
|---|---|
| 方式 | JWT（localStorageに保存） |
| 有効期限（生徒） | 30日間 |
| 有効期限（スタッフ・管理者） | 当日限り（翌0時失効） |
| ログイン失敗ロック | 10回失敗で30分ロック（自動解除） |
| パスワードリセット | 管理者が再発行のみ（自動リセット機能なし） |
| 複数端末同時ログイン | 許可（生徒が家でQR発行→当日スマホで確認など） |
| 初期管理者アカウント | .envファイルに ADMIN_ID / ADMIN_PASSWORD を記載、起動時に自動生成 |

---

## 3. 全体フロー

```
【事前準備・管理者】
名簿CSVインポート → 学籍番号+パスワード自動生成 → 印刷配布
スタッフアカウント登録（手動 or CSVインポート）

【QR発行期間・生徒（2週間前〜当日）】
サイトにアクセス（インターネット経由）
→ 学籍番号 + パスワードでログイン
→ 招待者の名前を入力してQR発行（最大5枚）
→ 発行済みQR一覧で確認・画像保存
→ 保護者・知人にLINE等で送付

【当日・保護者/知人】
QR画像をスマホで提示（オフラインでOK）

【当日・スタッフ】
学内Wi-Fiに接続
→ スタッフ画面でQRスキャン
→ 入場済みフラグ確認・記録

【当日・管理者】
管理者ダッシュボードで状況確認
→ 生徒別・招待者名別で入場状況を閲覧
→ チケットの無効化・有効化・入場記録・入場取消
```

---

## 4. 画面一覧

```
[生徒向け]
├── ログイン画面
├── QR発行画面（招待者名入力 → QR生成）
└── 発行済みQR一覧（招待者名・発行日時・入場状況・QR画像）
    └── 管理者モードに切替ボタン（昇格QR表示）

[スタッフ向け]
├── ログイン画面
└── QRスキャン画面（カメラ起動・入場記録・オフライン対応）

[管理者向け]
├── ログイン画面
├── ダッシュボード（入場数リアルタイム・グラフ・昇格ツリー）
├── チケット一覧（無効化/有効化・入場記録/取消・手動追加・削除）
├── 生徒一覧（追加・編集・削除・パスワードリセット）
├── CSVインポート（名簿取込）
├── スタッフ管理（手動登録・CSV一括登録・CSV出力・削除）
└── システム設定（QR発行期間変更）
```

---

## 4-A. 管理者ページ詳細仕様

### ダッシュボード
| 表示要素 | 内容 |
|---|---|
| 総入場者数 | 入場済み件数 / 6000（上限） |
| 未使用チケット数 | まだ入場していないQRの枚数 |
| 生徒別入場状況 | 各生徒の発行枚数・入場済み枚数（一覧テーブル） |
| 時間帯別入場グラフ | 30分単位の入場人数推移（棒グラフ / Chart.js） |
| 昇格ツリー | 誰が誰を昇格させたかのツリー表示 |

- データは自動更新（ポーリング、30秒）

### チケット一覧
**表示カラム**: 生徒名 / クラス / 招待者名 / 発行日時 / 入場状態 / 入場日時 / 操作

**操作ボタン（全状態に対応）**:
| ボタン | 表示条件 | 内容 |
|---|---|---|
| 🚫 無効化 | is_valid=1 | is_valid を 0 にする |
| ✅ 有効化 | is_valid=0 | is_valid を 1 に戻す |
| 🟢 入場記録 | used=0 | used を 1 にする（used_at も記録） |
| ↩ 入場取消 | used=1 | used を 0 に戻す |
| 🗑 削除 | 常時 | チケットをDBから完全削除 |
| ＋ 手動追加 | 常時 | 生徒を指定して上限超えの特例発行 |

**フィルタ・検索**: 生徒名 / クラス / 入場状況（全件・入場済み・未使用・無効）

### 生徒一覧
**表示カラム**: 学籍番号 / 氏名 / クラス / 発行枚数 / 入場済み枚数 / 操作

**操作ボタン**:
| ボタン | 内容 |
|---|---|
| 編集 | 氏名・クラス・パスワードを変更するモーダルを開く |
| 🔑 PW | パスワードリセットモーダルを開く |
| 削除 | 生徒と発行済み全チケットをDBから削除（確認ダイアログあり） |

**パスワードリセット仕様**:
- リセットモーダルで「自動生成」ボタン（ランダム8文字英数字）または任意のパスワードを入力
- 空欄のまま「リセット」を押した場合も自動生成
- 最小4文字のバリデーションあり
- リセット後、結果モーダルに新パスワードを大きく表示（再表示不可）

**テキスト検索**: 学籍番号または氏名でフィルタ

**CSVインポート**: CSVインポートページで名簿を一括取込可（フォーマット: 学籍番号,氏名,クラス）

### スタッフ管理
- スタッフアカウントの手動登録（ID・氏名・パスワード設定）
- **CSVインポート**: 一括登録（フォーマット: スタッフID,氏名,パスワード,ロール）
- **CSVエクスポート**: 現在のスタッフ一覧をダウンロード（パスワードは含めない）
- 全CSV出力は **UTF-8 BOM付き**（Excel・Numbers で文字化けなし）
- アカウント削除
- ロール: `staff`（スキャン・入場取消のみ） or `admin`（全権限）

---

## 4-B. 生徒ページ詳細仕様

### 発行済みQR一覧

**QR画像の構成**（テキストラベル付き）:
```
┌────────────────────────┐
│ 招待者：お父さん        │  ← 大きめフォント
│ 発行者：山田太郎        │  ← 小さめフォント
│ 発行日：2026/10/15 10:32│
│ 🎪 学園祭入場チケット  │
├────────────────────────┤
│                        │
│       QRコード          │  300×300px
│                        │
└────────────────────────┘
```
- LINEなどで送信した際に誰宛の何のQRか一目でわかる
- 日本語フォント（IPAゴシック）を使用

**チケット状態の表示**:
| 状態 | 表示 |
|---|---|
| 有効・未入場 | ⬜ 未入場（スカイブルー） |
| 有効・入場済み | ✅ 入場済み（グリーン）＋入場日時 |
| 無効化済み | 🚫 無効（管理者により無効化）（レッド）＋取り消し線・QRグレーアウト |

**操作**:
- 「画像を保存」ボタン → `QR_招待者名.png` として保存
- 削除ボタン（used=0 なら有効・無効問わず削除可）
- 入場済みチケットは削除不可
- QR画像クリック → モーダルで拡大表示（縦横比保持）

---

## 5. DBテーブル設計

```sql
CREATE TABLE students (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class TEXT,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    guest_name TEXT NOT NULL,
    is_valid INTEGER DEFAULT 1,
    used INTEGER DEFAULT 0,
    used_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

-- チケット状態の組み合わせ:
--   is_valid=1, used=0 → 有効・未入場
--   is_valid=1, used=1 → 入場済み
--   is_valid=0, used=0 → 無効化（未使用のまま無効）
--   is_valid=0, used=1 → 無効化（入場後に無効化）

CREATE TABLE staff (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL  -- 'staff' or 'admin'
);

CREATE TABLE temp_promotions (
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

CREATE TABLE offline_scan_queue (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    scanned_at DATETIME NOT NULL,
    session_id TEXT NOT NULL,
    synced INTEGER DEFAULT 0,
    synced_at DATETIME,
    conflict INTEGER DEFAULT 0,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- 初期データ:
--   ('issue_start', 'YYYY-MM-DD')  QR発行開始日
--   ('issue_end',   'YYYY-MM-DD')  QR発行終了日

CREATE TABLE login_failures (
    user_key TEXT PRIMARY KEY,
    failure_count INTEGER DEFAULT 0,
    locked_at REAL
);
```

---

## 6. 技術スタック

| 役割 | 技術 |
|---|---|
| バックエンド | Python / FastAPI |
| フロントエンド | HTML + Vanilla JS（SPA） |
| CSS | Tailwind CSS（CDN） |
| QR生成 | qrcode + Pillow（Python / サーバーサイド） |
| QRスキャン | html5-qrcode（CDN） |
| グラフ | Chart.js（CDN） |
| DB | SQLite（WALモード） |
| オフラインキャッシュ | IndexedDB（ブラウザ内蔵） |
| サーバー | Proxmox上Ubuntu + Nginx + Gunicorn |
| HTTPS | Let's Encrypt（サブドメイン） |
| パスキー | 後で追加（設計上考慮済み） |

---

## 7. APIエンドポイント

```
# 認証
POST /auth/login              生徒ログイン
POST /auth/staff/login        スタッフ・管理者ログイン

# チケット（生徒・スタッフ）
POST   /ticket/issue          QR発行（上限5枚チェック）
GET    /ticket/list           発行済みチケット一覧（生徒用）
DELETE /ticket/{id}           チケット削除（未入場のみ）
POST   /ticket/scan           スキャン・入場記録
POST   /ticket/scan/{id}/cancel  入場取消（スタッフ用）
GET    /ticket/cache          全有効チケット一括取得（オフライン用）
POST   /ticket/sync           オフラインスキャンの一括同期

# 昇格
POST /promote/request         昇格リクエストQR発行（生徒 → サーバー）
POST /promote/approve         昇格承認（管理者 or 昇格済み生徒）
GET  /promote/list            昇格ツリー一覧（管理者用）

# 管理者
GET  /admin/dashboard         ダッシュボード
GET    /admin/tickets           チケット一覧（フィルタ対応）
GET    /admin/tickets/{id}      チケット詳細
PUT    /admin/tickets/{id}      チケット更新（is_valid / used）
POST   /admin/tickets           チケット手動追加
DELETE /admin/tickets/{id}      チケット削除（管理者用）
GET    /admin/students          生徒一覧
GET    /admin/students/{id}     生徒詳細
POST   /admin/students          生徒追加
PUT    /admin/students/{id}     生徒編集（氏名・クラス・パスワード）
DELETE /admin/students/{id}     生徒削除（チケットも全削除）
POST   /admin/students/{id}/reset-password  パスワードリセット（自動生成 or 任意指定）
POST /admin/import            生徒CSVインポート
GET  /admin/import/passwords  インポート時パスワード一覧CSV
GET  /admin/export            緊急用チケットCSV出力
GET  /admin/staff             スタッフ一覧
POST /admin/staff             スタッフ手動追加
DELETE /admin/staff/{id}      スタッフ削除
GET  /admin/staff/export      スタッフCSVエクスポート
POST /admin/staff/import      スタッフCSVインポート
GET  /admin/settings          QR発行期間取得
PUT  /admin/settings          QR発行期間更新

# その他
GET /health                   ヘルスチェック
GET /                         SPA（index.html）
```

---

## 8. フロントエンド構成（SPA）

### ルーティング（ハッシュベース）

| URL | 画面 | 必要ロール |
|---|---|---|
| `#/login` | 生徒ログイン | なし |
| `#/staff-login` | スタッフ・管理者ログイン | なし |
| `#/qr` | QR発行・一覧 | student |
| `#/staff` | QRスキャン | staff / admin / promoted_student |
| `#/admin` | ダッシュボード | admin |
| `#/admin/tickets` | チケット一覧 | admin |
| `#/admin/students` | 生徒一覧 | admin |
| `#/admin/import` | CSVインポート | admin |
| `#/admin/staff` | スタッフ管理 | admin |
| `#/admin/settings` | システム設定 | admin |

### ファイル構成

```
static/
├── index.html
├── css/custom.css
└── js/
    ├── api.js          fetch wrapper（JWT自動付与・401処理）
    ├── auth.js         JWT管理・ロール判定
    ├── common.js       トースト・管理レイアウト・共通ヘルパー
    ├── router.js       ハッシュルーティング
    └── pages/
        ├── student-login.js
        ├── staff-login.js
        ├── student-qr.js
        ├── staff-scan.js
        ├── admin-dashboard.js
        ├── admin-tickets.js
        ├── admin-students.js
        ├── admin-import.js
        ├── admin-staff.js
        └── admin-settings.js
```

---

## 9. オフライン対応

```
スキャン画面を開いた時点で /ticket/cache を呼び出し
→ 全有効チケットID（+使用済みフラグ）をIndexedDBに保存
→ Wi-Fi切断時: IndexedDBで入場可否を判定
→ スキャン結果をIndexedDB（offline_queue）に積む
→ Wi-Fi復旧時: /ticket/sync に一括POST
→ 競合（複数端末が同一チケットをオフラインでスキャン）は
   サーバー側で先着1件を有効・残りをconflict=1として返す
```

- 60秒ごとに差分更新（`/ticket/cache?since=<timestamp>`）
- 画面上部に「オンライン / オフライン（キャッシュ使用中）」を表示

---

## 10. 冗長化・緊急時対応

### 10.1 リスク想定

```
当日起こりうる障害:
├── サーバーダウン
├── Wi-Fi過負荷・切断
├── DBクラッシュ
├── スタッフ端末のバッテリー切れ
└── QR画像を保護者が持ってこない
```

### 10.2 サーバー冗長化構成

```
[インターネット]
       ↓
[サブドメイン DNS]
       ↓
  ┌────────────────────────┐
  │  メインサーバー         │  ← Proxmox VM1
  │  FastAPI + SQLite      │
  │  Nginx + Gunicorn      │
  └────────────────────────┘
           ↓ 定期同期（5分ごと）
  ┌────────────────────────┐
  │  バックアップサーバー   │  ← Proxmox VM2
  │  同じ構成               │  ← 障害時に手動切替
  └────────────────────────┘
           ↓ 定期バックアップ
  ┌────────────────────────┐
  │  SQLiteファイル         │  ← USBメモリにも保存
  └────────────────────────┘
```

### 10.3 障害レベル別対応

#### Level 0：完全正常
```
✅ QRスキャン → サーバー照合 → 入場記録
✅ リアルタイムダッシュボード
✅ 重複入場チェック
```

#### Level 1：Wi-Fi不安定
```
✅ オフラインキャッシュモード（IndexedDB）
   スキャン画面を開いた時点で全有効チケットIDをIndexedDBに保存
   → Wi-Fi切断時はローカルキャッシュで入場可否を判定
   → スキャン結果をIndexedDBのキューに積む
   → 復旧後に /ticket/sync へ一括送信
```

#### Level 2：サーバーダウン
```
✅ 当日朝に全チケットIDをCSV出力 → スタッフに配布
   /admin/export で緊急CSV出力
   スタッフはCSVをスマホで開いて目視確認
   手書きチェックシートに切替
```

#### Level 3：完全オフライン（最終手段）
```
✅ 紙のチェックリスト（学籍番号・招待者名一覧）
   → 手書きで入場管理
```

### 10.4 具体的な冗長化施策

#### DBの自動バックアップ

```bash
# cronで5分ごとにSQLiteをコピー
*/5 * * * * cp /app/db/gakuensai.db /backup/gakuensai_$(date +\%H\%M).db

# 当日朝にUSBメモリへも保存
0 8 * * * cp /app/db/gakuensai.db /mnt/usb/gakuensai_backup.db
```

#### 当日朝の緊急用CSV自動出力

```
# 毎朝8時に全チケット一覧CSVを自動生成（/admin/export を cron で叩く）
# tickets_YYYYMMDD.csv
学籍番号, 生徒名, クラス, 招待者名, チケットID
1001, 山田太郎, 1-A, お父さん, aB3xYz8kQr
1001, 山田太郎, 1-A, お母さん, cD4wVu9mPs
```

#### バックアップサーバーへの切替

```
通常:   ${DOMAIN} → Route53 Aレコード → ${MAIN_SERVER_IP}（VM1）
障害時: Route53のAレコードを ${BACKUP_SERVER_IP}（VM2）に変更 or
        スタッフに直接 http://${BACKUP_SERVER_IP}:8000 を共有（LAN内）
```

### 10.5 当日オペレーション手順書

```
【正常時】
1. スタッフ画面を開く: https://${DOMAIN}/#/staff
2. QRをカメラにかざす
3. 緑 → 入場OK / 赤 → NG（使用済み or 無効）

【Wi-Fi不安定時】
1. オフラインモードに自動切替（画面上部に「🔴 オフライン」表示）
2. そのままスキャン継続
3. Wi-Fi復旧後に「同期」ボタンを押す

【サーバーダウン時】
1. 管理者に連絡
2. 緊急CSVをスマホで開く（管理者から共有: /admin/export）
3. チケットIDを目視確認してチェック

【完全オフライン時】
1. 紙チェックリストに切替（受付に保管）
2. 学籍番号・招待者名を口頭確認
3. 手書きチェック
```

---

## 11. インフラ構成（想定例）

| 項目 | 内容 |
|---|---|
| メインサーバー | 仮想マシン（例: Proxmox VM）/ Ubuntu 24.04 LTS |
| バックアップサーバー | 同構成のVMを待機系として用意 |
| DB同期 | cronで5分ごとSQLiteファイルコピー |
| USBバックアップ | 当日朝8時に自動保存 |
| ドメイン | `DOMAIN` 環境変数で指定 |
| HTTPS | Let's Encrypt（Certbot） |
| リバースプロキシ | Nginx |
| アプリサーバー | uvicorn（workers=2） |
| サービス管理 | systemd（monpass.service） |

Nginx・systemdの設定例は [README.md](../README.md#本番デプロイnginx--systemd) を参照。

---

## 12. 起動方法・環境変数

起動手順は [README.md](../README.md#セットアップ) を参照。環境変数の一覧と既定値は [.env.example](../.env.example) にまとめている。

| 変数 | 必須 | 既定値 | 説明 |
|---|---|---|---|
| `JWT_SECRET` | ✅ | なし | JWT署名シークレット（未設定だと起動時エラー） |
| `ADMIN_PASSWORD` | ✅ | なし | 初期管理者パスワード（初回起動時に管理者を自動生成） |
| `ADMIN_ID` | | `admin` | 初期管理者ID |
| `DB_PATH` | | `./data/gakuensai.db` | SQLiteファイルのパス |
| `DOMAIN` | | `localhost:8000` | QRコードに埋め込むドメイン |
| `ISSUE_START_DATE` | | `2000-01-01` | QR発行開始日 |
| `ISSUE_END_DATE` | | `2099-12-31` | QR発行終了日 |
| `LOGIN_MAX_FAILURES` | | `10` | ロックまでの連続失敗回数 |
| `LOGIN_LOCKOUT_MINUTES` | | `30` | ロック時間（分） |

---

*本ドキュメントは2026年6月時点の実装を反映しています。ディレクトリ構成は [README.md](../README.md#ディレクトリ構成) を参照。*
