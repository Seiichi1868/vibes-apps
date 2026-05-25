# VibeSpeak（音読判定アプリ）

多言語音読・添削をブラウザで行う Flask Web アプリです。音読認識は Web Speech API、添削・OCR・発音アドバイスは OpenAI API を利用します。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY などを設定
```

## 起動

```bash
python run.py
```

ブラウザで `http://127.0.0.1:5001` を開いてください。

本番（Render 等）では `gunicorn run:app` を使用します。

## プロジェクト構成

```
音読判定アプリ/
├── flask_app/           # Flask アプリケーション本体
│   ├── api/             # API Blueprint
│   ├── services/        # ビジネスロジック
│   ├── utils/           # ユーティリティ
│   └── views/           # ページルート
├── static/
├── templates/
├── uploads/
├── learning_history/
├── run.py               # 起動スクリプト
└── requirements.txt
```

## 環境変数（.env）

- `OPENAI_API_KEY` — 必須（添削・OCR・TTS・発音アドバイス）
- `FLASK_SECRET_KEY` — セッション用（任意）
- `GATE_SECRET` — クラスコード認証用（任意）
- `GOOGLE_APPLICATION_CREDENTIALS` — サーバー側 STT 利用時のみ

## 主な API

| エンドポイント | 説明 |
|----------------|------|
| `GET /api/gate/status` | ゲート・言語・TTS 設定 |
| `POST /api/check-grammar` | 作文添削 |
| `POST /api/ocr` | 画像からテキスト抽出 |
| `POST /api/pronunciation-advice` | 発音アドバイス |
| `POST /api/generate-tts` | お手本音声生成 |

管理者画面: `/admin`
