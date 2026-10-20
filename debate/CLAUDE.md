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
| `/debate/` | 論題選択（プルダウン+自由入力）→所属を選択して開始。名前入力なし。news風オープニング約2秒 |
| `/debate/session/<id>` | 6パート進行（録音・一時停止・保存・確認） |
| `/debate/session/<id>/parts/<part>/review` | 文字起こし確認・確定 |
| `/debate/session/<id>/judge` | AIジャッジ結果 |
| `/debate/admin` | 管理ログイン後に所属・セッション・スクリプト・設定を操作 |

タイトル: Parliamentary Debate Practice。PDA表記は出さない。

## パート（この順・この役割が正）

時間: PM/LO/MG/MO = 210秒、LOR/PMR = 150秒。Gov=PM,MG,PMR / Opp=LO,MO,LOR。
正規論点は各陣営 Point1+Point2 のみ。

- **PM** 定義+2論点予告。P1詳しく、P2は名前・概要でよい
- **LO** Gov P1再構築→反駁。自陣2論点予告。P1詳しく、P2概要でよい。PMがGov P2をタイトルだけにしたことは攻撃しない（詳細はMG）
- **MG** Opp P1反駁 → Gov P1再構築 → Gov P2詳細。Opp P2への反論不足は減点しない
- **MO** MGによるGov P1再構築への反駁 → その直後にGov P2反駁 → Opp P1再構築 → Opp P2詳細
- **LOR** 対立整理・Opp総括。新規論点不可。Gov P2への反論は冒頭で行わない（MOの2番目）
- **PMR** 先に Opp P2反駁、その後総括。新規論点不可

役割文・定型ガイド・ジャッジプロンプトの正本: `debate/config.py` の `PART_ROLES`/`PART_GUIDES` と `debate/judge.py`。矛盾させない。

## ソロ練習（Solo Practice）

既存の通常対戦（`mode` 欠落時は duo）を壊さず追加。コード値 `"solo"`。UIは「AI対戦モード」（1人でも複数人の協力でも、片方の陣営を担当してAIと対戦する）。生徒画面に「デュオ」は出さない。

- Gov: 生徒=PM/MG/PMR、AI=LO/MO/LOR。Opp: その逆。進行は順序固定。
- 生徒確定後に AI テキスト生成→TTS。Opp の PM はセッション作成直後から生成可。MO→LOR は同一チェーン（並列なのは MO の TTS と LOR テキスト）。
- AIパートは録音なし。`status=confirmed`・`elapsed_sec=null`。確認画面は進行へリダイレクト。
- 音声: サーバーTTS（`data/debate/audio/<id>/ai_<part>.mp3`）。IndexedDB 対象外。Range 対応。自動再生しない。
- ジョブ: `debate/solo_jobs.py`（judge_jobs と同じ起動方式）。プールはワーカーあたり既定 **8**（全体 16、`DEBATE_SOLO_POOL_SIZE`）。生成: `debate/opponent.py`。TTS: `debate/tts.py`。ガード: `debate/solo.py`。
- 生成・TTS の停滞も、ワーカー開始時刻（`generation_started_at` / `tts_started_at`）から測る。キュー投入は `generation_queued_at` / `tts_queued_at`。未開始は開始後より長い `*_QUEUE_STUCK_SEC`（試み時間の2倍+60秒。開始後は timeout×(retries+1)+60秒）。画面はポーリングのみ。
- 対戦AIはジャッジと別プロンプト。`opponent.py` の硬い制約で PM/LO は P2 を名前＋一文まで（本論は MG/MO）。難易度の「両方反論」より分担が優先。

## パート練習（Part Practice）

ソロの隣の第3モード。コード値 `"practice"`。UIは「パート練習モード」。通常対戦モードとAI対戦モードは壊さない。

- 各パートを `human` / `ai` / 未選択。PMから連続した担当だけが範囲。未選択のあとで担当を付けるのは不可。自分が話すパートが1つ以上必要。
- 未選択パートは `speaker=none`・`status=omitted`・`included=false`。進行画面にもジャッジにも出さない。評価は選んだ範囲が全部 `confirmed` になったときだけ。
- 例: PMだけ自分。LOだけなら PM=AI → LO=自分。MG以降を未選択にすればそこまで。
- AIの生成・TTS・順番ロックはソロと同じ経路（`uses_partner_flow`）。範囲の先頭がAIなら作成直後に生成する。
- ジャッジは範囲が6パート未満のときだけ `PARTIAL_PRACTICE_ADDENDUM` を足す。未実施の役割は減点しない。片方の陣営しか無いときは winner を出さない。全文の通常・ソロ判定プロンプトは変えない。

## データ

JSON: `data/debate/sessions/<id>.json` 音声: `data/debate/audio/<id>/`
設定: `data/debate/settings.json`（背景・透過・transcription_mode・judge_model_mode・opponent_model_mode・poi_protected_start_sec・poi_protected_end_sec・affiliations）
セッションに `affiliation` / `affiliation_id` を保存。所属選択肢の変更・削除後も、既存セッションの所属名は残す。
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
- **POI**: 建設的スピーチ（PM/LO/MG/MO）のみ。Reply（LOR/PMR）は不可。保護時間は管理画面で開始側・終了側を別スライダー（0＝無し、既定各60秒、最大90秒）。申し出→スピーカーが受理/却下（無応答約8秒で却下）。受理後最長15秒。録音も持ち時間も止まらない（POIは同一音声に入る）。一時停止はPOI対応中は不可。
- ライブ音量+参考字幕は表示専用。保存される文字起こしはAならWhisper、BならWeb Speech
- モードAでは停止時のブラウザ字幕を `browser_transcript` で音声と一緒に送り、パートの `transcript_browser` に残す。IndexedDB にも音声と一緒に残し、保存失敗後の「端末の録音で文字起こし」でも送る。Whisper 成功時は従来どおり Whisper で置き換え（`transcript_source=whisper`）。失敗・空・停滞で確認待ちになり本文が空なら、ブラウザ文を `transcript_edited` に入れ `transcript_source=browser`。確認画面は「これはブラウザの簡易文字起こしです…」と出し、再試行ボタンは残す。生徒が下書きを編集したあとの再試行は確認し、OK のときだけ Whisper で置き換える。キャンセルなら再試行しない。モードBの挙動は変えない
- 停止直後に IndexedDB へも保存（`static/debate/js/local-audio.js`）。確認画面は **同じ端末の録音を先に再生**、なければサーバーURL
- サーバーに音声が無い（保存失敗・`audio_url` 空）が、同じ端末の IndexedDB に録音があるときは、進行画面と確認画面に **「端末の録音で文字起こし」** を出す。既存の `POST /api/sessions/<id>/parts/<part>/audio` へ再保存し、その後は再文字起こしと同じポーリング。保存失敗でも IndexedDB は消さない。`recording_guard` は `recording` / `transcribing` / `needs_review` からの再保存を許可する（先行パート未確定では止めない）
- 「保存して中断」は録音中不可。トップへ戻り、同じ端末から再開

## 再開

トップの「続きから再開」は **この端末の localStorage ID だけ** を `/api/sessions/lookup` に渡す。他人のセッションは出さない。最大20件。

## 文字起こし・ジョブ

Whisper: `debate/transcription.py`（短タイムアウト）。ジョブ: `transcription_jobs.py`
本番 gunicorn は **gthread**（`Procfile`）。gthreadでは `ThreadPoolExecutor`。gevent monkey済みのときだけ `gevent.threadpool`。`spawn` 失敗時はスレッドへ落とす。ジャッジジョブも同じ（`judge_jobs.py`）。
本番は gunicorn **2 ワーカー**。各プールはワーカーあたりで、同時実行の上限は 2 倍。
文字起こしプールはワーカーあたり既定 **12**（全体 24、`DEBATE_TRANSCRIBE_POOL_SIZE`）。ワーカー開始時に `transcribe_started_at` を書く。停滞判定はその時刻から（未開始のキュー待ちは `end_time` または再キュー時刻から、より長い `TRANSCRIBE_QUEUE_STUCK_SEC`）。閾値は Whisper の timeout×(retries+1) を上回る（開始後は +60秒、待ちは試み時間の2倍+60秒。環境変数 `DEBATE_TRANSCRIBE_STUCK_SEC` / `DEBATE_TRANSCRIBE_QUEUE_STUCK_SEC`）。クライアントのポーリングも同じ秒数。1回だけ再キューし、だめなら `needs_review`。
遅れても、`needs_review` で文字起こしが空・生徒が編集/確定していなければ結果を書く。`confirmed` や `transcript_edited` ありは上書きしない。
確認画面で再文字起こし可。サーバー音声が無いときは端末の録音から再保存できる。確定は `transcript_edited` 必須。6パート確定後にジャッジ。

## ジャッジ

プロンプト正本は `debate/judge.py`（授業フロー準拠）。**PM/LOのP2概要は減点しない。LOがPMのGov P2説明不足を攻撃してもGovの欠点にしない。Gov P2の深さはMG、本格反論はMOの2番目（LORの冒頭ではない）。Opp P2の深さはMO。Opp P2本格反論はPMR。**
論点の状態は `config.py` の `ARGUMENT_STATUS`（intact / weakened / collapsed）と `argument_status_rules_text()`。生成プロンプトも同じ文面。extended は history の action。画面は英語ラベル。旧状態名は表示時だけ変換し、保存JSONは書き換えない。勝敗は weight の合計で、同点は Content。
モデル選択肢: `judge_model_pricing.py`（既定 `5.6-luna`）。結果画面にコストは出さない。ジャッジ中は擬似進捗ログ。
ジャッジプールはワーカーあたり既定 **8**（全体 16、`DEBATE_JUDGE_POOL_SIZE`）。`started_at` は受付時刻、`work_started_at` はワーカー開始。停滞は開始後 `JUDGE_STUCK_SEC`（timeout×(retries+1)+60秒）、未開始は `JUDGE_QUEUE_STUCK_SEC`（試みの2倍+60秒）。画面はサーバーの状態をポーリングするだけなので、クライアントが先にエラーにしない。

## 管理

`/debate/admin` はサーバー側ログイン必須。`POST /debate/admin/api/login` が `DEBATE_ADMIN_PASSWORD`（なければ `ADMIN_PASSWORD`）を `hmac.compare_digest` で照合し、署名付き Flask セッションを発行する。未設定なら 503。失敗は IP あたり 15 分で 5 回、全体で 30 回まで（JSON + flock、gunicorn 2 ワーカー共有）。以降の管理 API はセッション Cookie を見る（パスワードをリクエストに載せない）。ログアウトは `POST /debate/admin/api/logout`。観戦プレビュートークンの署名は `DEBATE_PREVIEW_SECRET`（未設定なら発行不可）。生徒画面と公開観戦はログイン不要。所属「アップデート確認用」だけ、選択時とセッション作成時に同じ管理パスワード（試行制限あり）。一覧は所属を表示し、所属フィルターと更新日時／所属ソートがある。コピー時ジャッジはリセット、音声（AI音声含む）は複製。所属もコピー先へ引き継ぐ。

## 観戦（お手本）

AI同士の6パートを保存して生徒は再生するだけ。生成APIは管理パスワード必須。ソロの `opponent.py` / `tts.py` は触らない。

- 一覧 `/debate/watch` は `published` のみ。観戦 `/debate/watch/<script_id>`。下書きは `?preview=1&token=` のときだけ。
- JSON: `data/debate/scripts/<id>.json`。音声は `data/debate/script_audio/<id>/<PART>.mp3`。読み上げは `debate/speech.py`（ソロの `tts.py` とは別）。ジョブは `debate/speech_jobs.py`。
- 生成: `debate/ai_script.py`（プロンプトは `PART_ROLES` / `PART_GUIDES`）。出力キーは `argument_map`。ジャッジの `argument_flow` は生成プロンプトに書かない。共有するのは `argument_status_rules_text()` だけ。ジョブ: `debate/script_jobs.py`。保存: `debate/script_storage.py`。
- 失敗した生レスポンスは `data/debate/scripts/_failed/`（最新20件）。費用は失敗したAPI呼び出しも `gen_cost_usd` に足す。140語/分で制限時間を超えたパートは、優勢差と同じ再生成1回の対象。まだ超えるときは強い警告つきで下書きに残す。
- 下書きプレビューのトークンは署名付き（ワーカーが2つでも有効）。error の行はプレビューしない。
- セッション・スクリプト・設定の更新ロックは `debate/file_lock.py`（プロセス内 RLock + flock）。ジョブの状態はセッションJSON / スクリプトJSON / `<script_id>.checks.json` に書く。
- ジャッジ照合は管理画面だけ。`debate/judge.py` の `run_judge` を、設計情報なしの仮セッションで呼ぶ。結果は `data/debate/scripts/<script_id>.checks.json`。練習セッションには保存しない。
- 管理画面「観戦用スクリプト」。モデル既定 `5.6-terra`。`speech_mode` 既定 `openai`。公開時に6パートの mp3 を作る。`browser` のときと、ファイルが無い・古いときは、生徒画面がブラウザ読み上げに静かに切り替わる。配信は `/debate/watch/<id>/audio/<PART>`（Range 対応）。声は Gov=`sage` / Opp=`ash`。
- 生徒画面にコスト・モデル名は出さない。

## ファイル案内（必要なときだけ開け）

| 作業 | ファイル |
|------|----------|
| URL/API | `debate/routes.py` |
| スキーマ | `debate/models.py` `config.py` |
| JSON/音声 | `debate/storage.py` |
| 進行UI | `templates/debate/progress.html` `static/debate/js/progress.js` `solo.js` |
| 確認再生 | `static/debate/js/local-audio.js` `review.js` `templates/debate/review.html` |
| 再開一覧 | `static/debate/js/local-sessions.js` |
| 論題 | `templates/debate/index.html` `static/debate/js/index.js` |
| ジャッジUI | `templates/debate/judge.html` `static/debate/js/judge.js` |
| 管理 | `debate/admin.py` `debate/admin_auth.py` `templates/debate/admin.html` `static/debate/js/admin.js` |
| 見た目 | `templates/debate/base.html` `static/debate/css/style.css` |
| ソロ生成 | `debate/solo.py` `opponent.py` `solo_jobs.py` `tts.py` |
| 観戦スクリプト | `debate/ai_script.py` `script_jobs.py` `script_storage.py` `speech.py` `speech_jobs.py` `templates/debate/watch.html` `watch_list.html` |

## 直近の確定仕様（これと違う実装は回帰）

1. 再開一覧 = 自分の端末のみ
2. 確認画面の再生 = 同一端末IndexedDB優先
3. 録音一時停止 = 経過時間も止まる
4. 生徒向け「アップロード」→「保存」
5. ジャッジは授業フローの2論点分担に従う
6. オープニングタイトルは1行、PDAなし
7. 論題はプルダウン、生徒名なし。開始前に管理画面で作った所属を必須選択。所属「アップデート確認用」だけ透過30%で、選択時とセッション作成時に管理パスワードが必要
8. 配色は news 同様の淡い緑ガラス
9. POIは建設的スピーチのみ。保護時間は開始側・終了側を管理画面で別々に変更（0＝無し、既定各60秒）。POI中も持ち時間は止まらない。最長15秒。Replyでは不可。回数で勝敗を変えない。
