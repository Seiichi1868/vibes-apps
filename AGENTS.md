# AGENTS.md

開発ルール（編集範囲・禁止事項・本番）は `.cursor/rules/` と `README.md` を参照。

## Cursor Cloud specific instructions

### 構成（要点）
- 単一の Flask プロセスに 2 アプリを統合: VibeSpeak 音読 (`flask_app/`, ルート `/`) と Vibe Speak News (`news_app/`, プレフィックス `/news/`)。
- 依存は Python のみ。`requirements.txt` を venv (`.venv/`) にインストール済み（update script が再現）。

### 起動（開発）
- 開発サーバ: `.venv/bin/python run.py`（`run.py` は debug 有効・`0.0.0.0:5001`）。本番相当は `gunicorn wsgi:application`。
- ヘルスチェック: `/health`（音読）、`/news/health`（News）。

### 非自明な注意点
- `OPENAI_API_KEY` 未設定でもアプリは起動する。OCR/TTS/文法チェック/文字起こし/News 評価など OpenAI 依存機能を実際に使うときのみ必要（未設定だと該当 API がエラー/無効になる）。`.env`（git 無視）に置けば自動読込。
- 音読のクラスコードゲート (`GATE_LOCK_ENABLED`) はローカルでは既定 ON（本番=Render では OFF）。入室コードはその日の日付の SHA256 から生成され、`GET /api/gate/status` の `code` で確認できる（例: `curl -s localhost:5001/api/gate/status`）。
- 音読の発話判定はブラウザの Web Speech API を使うクライアント側処理。実際の録音判定にはマイクのある実ブラウザが必要（ヘッドレスでは不可）。サンプル文の読み込み等は API キー無しで動作確認できる。
- 自動テスト・lint 設定は無し（テストフレームワーク/リンタ未導入）。
- `data/`・`uploads/`・`learning_history/` は実行時に生成される永続/一時データ。
