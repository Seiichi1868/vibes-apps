# vibes-apps

複数の Flask アプリを1つの Render サービスに統合したプラットフォームです。

本番: https://vibes-app-auz1.onrender.com

## アプリ一覧

| アプリ | パッケージ | URL | 説明 |
|--------|-----------|-----|------|
| VibeSpeak（音読判定） | `flask_app/` | `/` | 多言語音読・添削・OCR・TTS |
| Vibe Speak News | `news_app/` | `/news/` | 動画要約・スピーチ評価 |

各アプリは **完全独立**（`*_app/` 同士の import 禁止）。共通 `shared/` フォルダは使いません。

## プロジェクト構成

```
vibes-apps/
├── flask_app/           # 音読判定（/）
├── news_app/            # Vibe Speak News（/news/）
├── templates/           # 音読・News テンプレート（news/ サブディレクトリ）
├── static/              # 音読静的ファイル（news/ サブディレクトリ）
├── data/                # 永続データ（Render ディスク、本番のみ）
├── wsgi.py              # Gunicorn エントリポイント（推奨）
├── app.py               # ローカル互換エントリポイント
├── run.py               # ローカル開発用（port 5001）
└── render.yaml
```

## セットアップ

```bash
cd vibes-apps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY などを設定
python run.py
```

| 画面 | URL |
|------|-----|
| 音読（生徒） | http://127.0.0.1:5001/ |
| 音読（管理） | http://127.0.0.1:5001/admin |
| News（生徒） | http://127.0.0.1:5001/news/ |
| News（管理） | http://127.0.0.1:5001/news/admin/ |

本番: `gunicorn wsgi:application`

## 環境変数（.env）

- `OPENAI_API_KEY` — 必須
- `FLASK_SECRET_KEY` — セッション用
- `GATE_SECRET` — クラスコード認証（音読）
- `NEWS_DATA_DIR` — News データ保存先（本番: Render 永続ディスク `/opt/render/project/src/data`）
- `GOOGLE_APPLICATION_CREDENTIALS` — サーバー側 STT 利用時のみ

## 開発ルール

- 音読修正 → `flask_app/`、`templates/`（`news/` 以外）、`static/`（`news/` 以外）
- News 修正 → `news_app/`、`templates/news/`、`static/news/`
- `*_app/` 間の import は禁止
- UI を全アプリに横展開するときは依頼文で明示する

## 関連リポジトリ

- **`vibe-speak-news`** — News 単体版（レガシー）。本番は本リポジトリの `news_app/` を使用。新規開発はこちら（`vibes-apps`）のみ。
