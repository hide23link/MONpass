# MONpass — 学園祭入場管理システム

学園祭の入場をQRコードで管理するWebシステムです。

> **このリポジトリはアーカイブ済みです。** 後継の Cloudflare Workers 版は [monpassC](https://github.com/hide23link/monpassC) で開発しています。本リポジトリは初期の Python（FastAPI + SQLite）実装として残しています。

## 機能概要

| ロール | 機能 |
|---|---|
| 生徒 | QR発行（最大5枚・固定）・発行済み一覧・QR保存 |
| スタッフ | QRスキャン・入場記録・オフライン対応 |
| 管理者 | ダッシュボード・チケット/生徒/スタッフ管理・CSV入出力 |

## 技術スタック

- **バックエンド**: Python / FastAPI / SQLite（WALモード）
- **フロントエンド**: Vanilla JS SPA / Tailwind CSS（CDN）
- **QR生成**: qrcode + Pillow（サーバーサイド、テキストラベル付き）
- **QRスキャン**: html5-qrcode（CDN）
- **認証**: JWT（生徒: 30日 / スタッフ・管理者: 当日限り）
- **オフライン対応**: IndexedDB キャッシュ + 同期API

## セットアップ

### 1. 依存ライブラリのインストール

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して JWT_SECRET と ADMIN_PASSWORD を設定
```

環境変数の一覧は [docs/spec.md の「12. 起動方法・環境変数」](docs/spec.md#12-起動方法環境変数) を参照。

### 3. 起動

```bash
mkdir -p data
uvicorn main:app --host 0.0.0.0 --port 8000
```

ブラウザで `http://localhost:8000` にアクセス。

初回起動時に `.env` の `ADMIN_ID` / `ADMIN_PASSWORD` で管理者アカウントが自動生成されます。

## 本番デプロイ（Nginx + systemd）

### systemd サービス例

```ini
[Unit]
Description=MONpass Gakuensai System
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/monpass
EnvironmentFile=/opt/monpass/.env
ExecStart=/opt/monpass/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx 設定例

```nginx
server {
    listen 80;
    server_name your-domain.example.com;
    client_max_body_size 10M;

    location ~* \.js$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## テスト

```bash
pip install -r requirements-test.txt

# バックエンドテスト
pytest tests/ -v

# E2Eテスト（Playwright）
playwright install chromium
pytest tests/e2e/ -v
```

## 生徒データのインポート

CSVフォーマット（ヘッダー行あり）:

```
学籍番号,氏名,クラス
1001,山田太郎,1-A
1002,佐藤花子,1-B
```

管理画面の「インポート」ページからアップロード。パスワードは自動生成されます。
インポート後に「パスワード一覧CSV」をダウンロードして生徒に配布してください。

サンプルデータ: `sample_students.csv`（20名分、架空データ）

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/spec.md](docs/spec.md) | 設計書（要件・認証・DB設計・API・オフライン対応・冗長化/当日運用） |
| [docs/frontend-spec.md](docs/frontend-spec.md) | フロントエンド仕様（画面ごとの詳細・IndexedDB・デザイン） |
| [docs/test-cases-backend.md](docs/test-cases-backend.md) | バックエンドテストケース一覧（TC-01〜13） |
| [docs/test-cases-frontend.md](docs/test-cases-frontend.md) | フロントエンド（E2E）テストケース一覧（FE-TC-01〜17） |

## ディレクトリ構成

```
MONpass/
├── main.py                  FastAPIアプリ本体
├── requirements.txt         本番依存ライブラリ
├── requirements-test.txt    テスト依存ライブラリ
├── .env.example             環境変数サンプル
├── pytest.ini
├── sample_students.csv      テスト用サンプルデータ（架空）
├── LICENSE
├── docs/                    仕様書・テストケース
├── static/
│   ├── index.html
│   ├── css/custom.css
│   └── js/
│       ├── api.js
│       ├── auth.js
│       ├── common.js
│       ├── router.js
│       └── pages/（10ファイル）
└── tests/
    ├── conftest.py
    ├── test_tc01_auth.py 〜 test_tc13_load.py
    └── e2e/
```

## ライセンス

[MIT](LICENSE)
