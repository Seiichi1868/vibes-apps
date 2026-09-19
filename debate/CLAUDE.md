# debate/ — Claude向け設計（これ以上の探索は原則不要）

授業用の議会型ディベート練習。英語6パートを録音→文字起こし確認→AIジャッジ。
本番: `https://vibes-app-auz1.onrender.com/debate`（同一Renderの一部。`news/` 字幕経路は壊すな）。

## 触ってよいパス（これ以外禁止）

`debate/` `templates/debate/` `static/debate/`
禁止: `flask_app/` `news_app/` `templates/news/` `static/news/` 相互import / `shared/` / `data/` 実データコミット。
静的JSを変えたら該当 `url_for(..., v='YYYYMMDDx')` を上げる。

## 画面

| URL | 役割 |
|-----|------|
| `/debate/` | 論題選択（プルダウン+自由入力）。名前入力なし。news風オープニング約2秒 |
| `/debate/session/<id>` | 6パート進行（録音・一時停止・保存・確認） |
| `/debate/session/<id>/parts/<part>/review` | 文字起こし確認・確定 |
| `/debate/session/<id>/judge` | AIジャッジ結果 |
| `/debate/admin` | 背景は公開。文字起こし方式・ジャッジモデル変更だけパスワード |

タイトル: Parliamentary Debate Practice。PDA表記は出さない。

## パート（この順・この役割が正）

時間: PM/LO/MG/MO = 210秒、LOR/PMR = 150秒。Gov=PM,MG,PMR / Opp=LO,MO,LOR。
正規論点は各陣営 Point1+Point2 のみ。

- **PM** 定義+2論点予告。P1詳しく、P2は名前・概要でよい
- **LO** Gov再構築→反駁。自陣2論点予告。P1詳しく、P2概要でよい
- **MG** Opp P1反駁 → Gov P1再構築 → Gov P2詳細。Opp P2への反論不足は減点しない
- **MO** Gov P1反駁 → Opp P1再構築 → Opp P2詳細
- **LOR** 対立整理・Opp総括。新規論点不可
- **PMR** 先に Opp P2反駁、その後総括。新規論点不可

役割文・定型ガイド・ジャッジプロンプトの正本: `debate/config.py` の `PART_ROLES`/`PART_GUIDES` と `debate/judge.py`。矛盾させない。

## データ

JSON: `data/debate/sessions/<id>.json` 音声: `data/debate/audio/<id>/`
設定: `data/debate/settings.json`（背景・透過・transcription_mode・judge_model_mode）
書き込みは `get_session_lock(session_id)` で直列化。`save_session` は tmp→replace。
パート status: `not_started` → `recording` → `transcribing` → `needs_review` → `confirmed`
ジャッジ: `idle` → `judging` → `done`/`error`

## 録音（現行仕様・ここが最近よく変わる）

モードは管理設定。既定 **batch（モードA）**: MediaRecorder → POST audio → Whisper非同期。
**realtime（モードB）**: Web Speech 結果を transcript API へ。非対応ブラウザはAへフォールバック。

- 同時録音は1パートのみ。文字起こし中でも他パートは録音可
- **一時停止**: 録音・タイマー・合図音・ライブ認識が止まる。再開可。制限に入るのは発話時間だけ（停止中除外）。`elapsed_sec` はこの発話秒
- 止め方の文言は **「停止して保存」**（realtimeは「停止して確定」）。生徒向けに「アップロード」は出さない。内部関数名 `upload_part_audio` はそのままでよい
- 失敗メッセージも「保存に失敗／タイムアウト」
- 合図音: 残り1分1回 / 30秒2回 / 超過後連打
- ライブ音量+参考字幕は表示専用。保存される文字起こしはAならWhisper、BならWeb Speech
- 停止直後に IndexedDB へも保存（`static/debate/js/local-audio.js`）。確認画面は **同じ端末の録音を先に再生**、なければサーバーURL
- 「保存して中断」は録音中不可。トップへ戻り、同じ端末から再開

## 再開

トップの「続きから再開」は **この端末の localStorage ID だけ** を `/api/sessions/lookup` に渡す。他人のセッションは出さない。最大20件。

## 文字起こし・ジョブ

Whisper: `debate/transcription.py`（短タイムアウト）。ジョブ: `transcription_jobs.py`
本番 gunicorn は **gthread**（`Procfile`）。gthreadでは `ThreadPoolExecutor`。gevent monkey済みのときだけ `gevent.threadpool`。`spawn` 失敗時はスレッドへ落とす。ジャッジジョブも同じ（`judge_jobs.py`）。
`transcribing` が約90秒停滞 → 1回再キュー → だめなら `needs_review`。クライアントも90秒で確認画面へ誘導。
確認画面で再文字起こし可。確定は `transcript_edited` 必須。6パート確定後にジャッジ。

## ジャッジ

プロンプト正本は `debate/judge.py`（授業フロー準拠）。**PM/LOのP2概要は減点しない。Gov P2の深さはMG、Opp P2はMO。Opp P2本格反論はPMR。**
モデル選択肢: `judge_model_pricing.py`（既定 `5.6-luna`）。結果画面にコストは出さない。ジャッジ中は擬似進捗ログ。

## 管理

`/debate/admin` はリンク開放。パスワード必須は `transcription_mode` と `judge_model_mode` のみ（`DEBATE_ADMIN_PASSWORD` 既定2479）。セッション一覧・コピー・備考・削除あり。コピー時ジャッジはリセット、音声は複製。

## ファイル案内（必要なときだけ開け）

| 作業 | ファイル |
|------|----------|
| URL/API | `debate/routes.py` |
| スキーマ | `debate/models.py` `config.py` |
| JSON/音声 | `debate/storage.py` |
| 進行UI | `templates/debate/progress.html` `static/debate/js/progress.js` |
| 確認再生 | `static/debate/js/local-audio.js` `review.js` `templates/debate/review.html` |
| 再開一覧 | `static/debate/js/local-sessions.js` |
| 論題 | `templates/debate/index.html` `static/debate/js/index.js` |
| ジャッジUI | `templates/debate/judge.html` `static/debate/js/judge.js` |
| 管理 | `debate/admin.py` `templates/debate/admin.html` `static/debate/js/admin.js` |
| 見た目 | `templates/debate/base.html` `static/debate/css/style.css` |

## 直近の確定仕様（これと違う実装は回帰）

1. 再開一覧 = 自分の端末のみ
2. 確認画面の再生 = 同一端末IndexedDB優先
3. 録音一時停止 = 経過時間も止まる
4. 生徒向け「アップロード」→「保存」
5. ジャッジは授業フローの2論点分担に従う
6. オープニングタイトルは1行、PDAなし
7. 論題はプルダウン、生徒名なし
8. 配色は news 同様の淡い緑ガラス
