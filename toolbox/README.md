# Toolbox

教員向け授業補助ツール。URL: `/toolbox/`

他アプリ（news / conjugate / debate など）は import しません。データは `data/toolbox/` の JSON です。

## 管理画面

URL: `/toolbox/admin/`

**Toolbox の教員ログインは不要**です。管理パスワードを入力すると入れます。ユーザー作成などの重要操作では、同じ管理パスワードの再入力を求めます。パスワードの値は画面に出しません。変更は環境変数 `TOOLBOX_ADMIN_PASSWORD` です。

教員ログインは管理画面の「教員ログインを必須にする」で切り替えます。オフ（既定）のときはランチャーと各ツールに自動で入れます。

## 初期管理者の作成（教員ログイン用）

固定パスワードはコードにありません。自分で発行します。

```bash
python -m toolbox create-user --role admin --username YOUR_NAME
# または
FLASK_APP=wsgi:application flask toolbox create-user --role admin
```

パスワードは 10 文字以上です。

## 環境変数

既存アプリと同じ名前を使います。

| 変数 | 用途 |
|------|------|
| `FLASK_SECRET_KEY` | セッション署名 |
| `OPENAI_API_KEY` | 文字起こし・問題生成 |
| `TOOLBOX_DATA_DIR` | 省略時は `data/toolbox`。本番の Render ディスクを使うなら `/opt/render/project/src/data/toolbox` |
| `TOOLBOX_WHISPER_TIMEOUT_SEC` | 既定 90 |
| `TOOLBOX_GENERATE_TIMEOUT_SEC` | 既定 90 |
| `TOOLBOX_ADMIN_PASSWORD` | 管理画面の入口パスワード。省略時は他アプリと同じ既定 |

新規に必須なのは `TOOLBOX_DATA_DIR` だけです（省略可）。API キーと SECRET は既存のものを共有します。

## 運用メモ

- ALT のスピーチを録音する前に、本人の同意を得てください。
- 音声ファイルはサーバーに残しません。文字起こし後に一時ファイルを削除します。
- 生徒の氏名・成績は保存しません。指名は出席番号のみです。
- ログにスピーチ本文は出しません。
- 価格は `toolbox/pricing.py` にあります。`# TODO: 要確認` の値は後から差し替えてください。
- gunicorn の timeout は現状 180 秒です。文字起こし／生成は別リクエストで、想定最長 120 秒に余裕があります。

## ライブラリ

新しい Python / JS ライブラリは追加していません。既存の Flask / werkzeug / openai / pydantic だけを使います。
