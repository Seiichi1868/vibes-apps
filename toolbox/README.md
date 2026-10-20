# Toolbox

教員向け授業補助ツール。URL: `/toolbox/`

タイマー・ランダム指名・ランダム座席表・QRコード・スピーチ理解度チェックを教室内で大きく表示して使います。

他アプリ（news / conjugate / debate など）は import しません。データは `data/toolbox/` の JSON です。

## 管理画面

URL: `/toolbox/admin/`

**Toolbox の教員ログインは不要**です。管理パスワードを入力すると入れます。ユーザー作成などの重要操作では、同じ管理パスワードの再入力を求めます。パスワードの値は画面に出しません。共通の `ADMIN_PASSWORD` を使い、`TOOLBOX_ADMIN_PASSWORD` があればそちらを優先します。どちらも未設定なら管理操作は拒否します。

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
| `ADMIN_PASSWORD` | 管理画面の入口（全アプリ共通）。未設定かつ下の上書きも無いと拒否 |
| `TOOLBOX_ADMIN_PASSWORD` | Toolbox だけの上書き。設定時は `ADMIN_PASSWORD` より優先 |

`TOOLBOX_DATA_DIR` は省略可。管理画面を使うには `ADMIN_PASSWORD` か `TOOLBOX_ADMIN_PASSWORD` が必要です。API キーと SECRET は既存のものを共有します。

## 運用メモ

- スピーチを録音する前に、話者の同意を得てください。
- 音声ファイルはサーバーに残しません。文字起こし後に一時ファイルを削除します。
- 生徒の氏名・成績は保存しません。指名は出席番号のみです。
- ログにスピーチ本文は出しません。
- 価格は `toolbox/pricing.py` にあります。`# TODO: 要確認` の値は後から差し替えてください。
- gunicorn の timeout は現状 180 秒です。文字起こし／生成は別リクエストで、想定最長 120 秒に余裕があります。

## ライブラリ

新しい Python / JS ライブラリは追加していません。既存の Flask / werkzeug / openai / pydantic だけを使います。
