# 1分スピーチ：授業化の取り消し後のデータ確認・復旧手順

このリポジトリは「担当教員→クラス」構成に戻してあります。
ブラウザの localStorage には、授業化のコードが書いたデータが残っている場合があります。
**自動では何も消しません。** 下のスクリプトを、ブラウザのコンソール（Toolbox 画面で F12）に手で貼って使います。

## 授業化が localStorage に書いたキー

| キー | 内容 |
|---|---|
| `toolbox.local_courses.v1` | 授業マスタ（授業化で新規） |
| `toolbox.minuteSpeech.v1` | `courseState` / `lastCourse` / `schemaVersion` / `migrationNotes` / `_migrationDone` を追加。旧キー（scopes/history/rounds/nextUse/archived/lastClass）は「移行を完了する」を押さない限り**残る** |
| `toolbox.minuteSpeech.migrationBackup.<ISO日時(:.は-)>.minuteSpeech / .classes / .teachers / .courses` | 初回移行直前の自動バックアップ。値は文字列を JSON.stringify したもの（`null` なら "null"） |
| `toolbox.minuteSpeech.assignBackup.<ISO日時>` | 振り分け直前のバックアップ（JSON。teachers/classes/courses/speech は元の文字列） |
| `toolbox.minuteSpeech.assignBackupLast` | 直近の振り分けバックアップの日時 |
| `toolbox.local_classes.v1` | 授業化は `teacher_id` や行を変更していない（読み取りのみ。クラス追加時のみ従来どおり行を追加） |
| `toolbox.local_teachers.v1` | 変更なし |

旧コード（今回の戻し先）は、保存時に未知のキーを落とさず、`schemaVersion` で拒否もしません。
そのため授業化後のデータがあっても壊れませんが、**授業化の後に付けた使用済みは `courseState` 側にしかなく、クラス別の「使用済み」には出ません。**

## 手順

1. デプロイ後、Toolbox を**強めに再読み込み**（Service Worker は `toolbox-v2`。古いJSが残る場合は一度タブを閉じて開き直す）。
2. **スクリプトA（確認）** を実行して、状態を確認する。
3. 状態に応じて：
   - 授業化の痕跡がなく、使用済みも見えている → 何もしなくてよい。
   - 授業化前に書き出した履歴JSONがある → 画面の「読み込む」で復元するのが最も安全。
   - 使用済みが消えている／設定が戻らない → 「移行バックアップ」が見つかっていれば **スクリプトB** で復元。
4. 授業化の後に付けた使用済みを残したいときは、**B を実行する前**に、授業化版の `backup/courses-attempt` ブランチで書き出しておく。B は授業化前の時点に戻すため、それ以降の記録は戻る先に含まれない（退避キーには残る）。

## スクリプトA：読み取り専用の確認

```js
(() => {
  const rows = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!/^toolbox\.(local_|minuteSpeech)/.test(k)) continue;
    rows.push({ key: k, bytes: (localStorage.getItem(k) || "").length });
  }
  console.table(rows);
  const parse = (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (_) { return null; } };
  const ms = parse("toolbox.minuteSpeech.v1") || {};
  const classes = parse("toolbox.local_classes.v1") || [];
  const histCount = Object.values(ms.history || {}).reduce((n, byType) => n + Object.values(byType || {}).reduce((m, l) => m + (Array.isArray(l) ? l.length : 0), 0), 0);
  console.log({
    local_courses: !!localStorage.getItem("toolbox.local_courses.v1"),
    courseState: Object.keys(ms.courseState || {}).length,
    schemaVersion: ms.schemaVersion || null,
    migrationDone: !!ms._migrationDone,
    oldKeys: ["scopes", "history", "rounds", "nextUse", "archived", "lastClass"].map((k) => [k, k in ms]),
    oldHistoryEntries: histCount,
    classes: classes.length,
    migrationBackups: rows.filter((r) => r.key.startsWith("toolbox.minuteSpeech.migrationBackup.")).map((r) => r.key),
    assignBackups: rows.filter((r) => r.key.startsWith("toolbox.minuteSpeech.assignBackup.")).map((r) => r.key),
  });
})();
```

## スクリプトB：授業化前のバックアップから復元

実行前に、現在の状態を `toolbox.minuteSpeech.rollbackSaved.<日時>.*` へ退避します。
使うバックアップは、**最も古い移行バックアップ（＝授業化の直前）** です。

```js
(() => {
  const prefix = "toolbox.minuteSpeech.migrationBackup.";
  const stamps = [...new Set(Object.keys(localStorage).filter((k) => k.startsWith(prefix)).map((k) => k.slice(prefix.length).split(".")[0]))].sort();
  if (!stamps.length) { console.warn("移行バックアップが見つかりません。復元しません。"); return; }
  const stamp = stamps[0];
  const targets = {
    minuteSpeech: "toolbox.minuteSpeech.v1",
    classes: "toolbox.local_classes.v1",
    teachers: "toolbox.local_teachers.v1",
    courses: "toolbox.local_courses.v1",
  };
  if (!confirm(`バックアップ ${stamp} から復元します。現在の状態は別キーへ退避します。よろしいですか？`)) return;
  const saved = "toolbox.minuteSpeech.rollbackSaved." + new Date().toISOString().replace(/[:.]/g, "-");
  Object.entries(targets).forEach(([name, key]) => {
    const cur = localStorage.getItem(key);
    if (cur != null) localStorage.setItem(`${saved}.${name}`, cur);
  });
  Object.entries(targets).forEach(([name, key]) => {
    const raw = localStorage.getItem(`${prefix}${stamp}.${name}`);
    if (raw == null) return;
    let value = null;
    try { value = JSON.parse(raw); } catch (_) { value = null; }
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  });
  console.log("復元しました。退避先:", saved, " ページを再読み込みしてください。");
})();
```

元に戻したいときは、退避した値を `toolbox.minuteSpeech.v1` などへ `localStorage.setItem` で書き戻します。
