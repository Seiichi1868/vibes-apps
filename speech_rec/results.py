"""結果一覧。永続してある数値だけを読む。音声と本文は返さない。"""
from __future__ import annotations

import csv
import io
import statistics

from speech_rec.assignments import get_assignment, list_assignments, records_dir
from speech_rec.pricing import JPY_PER_USD
from speech_rec.scoring import cap_delivery_level, score, speaking_wpm
from speech_rec.settings import get_settings
from speech_rec.store import list_json_files, read_json, write_json

COLUMNS = (
    "time", "id", "attempt", "status", "words", "wpm_points",
    "general_description", "delivery", "language_use", "topic_development",
    "rubric", "total", "oreo", "pauses", "snr", "flags", "code", "yen",
)


def _rows(assignment_id: str) -> list[dict]:
    assignment = get_assignment(assignment_id) or {}
    speak = float(assignment.get("speak_sec") or 60)
    rows = []
    for path in list_json_files(records_dir(assignment_id)):
        record = read_json(path)
        if isinstance(record, dict):
            rows.append(present(record, speak_sec=speak))
    return rows


def present(record: dict, *, speak_sec: float) -> dict:
    scores = record.get("scores") if isinstance(record.get("scores"), dict) else {}
    points = scores.get("points") if isinstance(scores.get("points"), dict) else {}
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    levels = record.get("levels") if isinstance(record.get("levels"), dict) else {}
    fields = record.get("id_fields") if isinstance(record.get("id_fields"), dict) else None
    oreo = record.get("oreo") if isinstance(record.get("oreo"), dict) else {}
    rubric = round(sum(float(points.get(key) or 0) for key in ("general_description", "delivery", "language_use", "topic_development")), 4)
    created = str(record.get("created_at") or "")
    pause_n = metrics.get("pause_n")
    pause_max = metrics.get("pause_max")
    silent = metrics.get("silent_ratio")
    pauses = ""
    if pause_n is not None:
        pauses = f"{pause_n}/{pause_max}/{silent}"
    ident = ""
    if fields:
        ident = f"{fields.get('grade')}-{fields.get('class')}-{fields.get('number')}"
    wpm = scores.get("wpm")
    if wpm is None and metrics.get("words_counted") is not None:
        wpm = speaking_wpm(int(metrics.get("words_counted") or 0), speak_sec)
    return {
        "id": record.get("id"),
        "time": created[11:16] if len(created) >= 16 else created,
        "created_at": created,
        "student_id": ident,
        "attempt": record.get("attempt"),
        "status": record.get("status"),
        "error_code": record.get("error_code"),
        "words": metrics.get("words_counted"),
        "wpm": wpm,
        "wpm_points": scores.get("wpm_points"),
        "points": points,
        "levels": levels,
        "rubric": rubric,
        "total": scores.get("total"),
        "oreo": _oreo_flags(oreo),
        "pauses": pauses,
        "snr_db": metrics.get("snr_db"),
        "flags": record.get("flags") or [],
        "code": record.get("verify_code"),
        "yen": round(float(record.get("cost_usd") or 0) * JPY_PER_USD, 2),
        "delivery_cap": scores.get("delivery_cap"),
    }


def _oreo_flags(oreo: dict) -> dict:
    def on(key: str, legacy: str | None = None) -> bool:
        if key in oreo:
            return bool(oreo.get(key))
        if legacy:
            return bool(oreo.get(legacy))
        return False

    reason_1 = on("reason_1", "reason")
    example_1 = on("example_1", "example")
    reason_2 = on("reason_2")
    example_2 = on("example_2")
    return {
        "opinion_open": on("opinion_open"),
        "reason_1": reason_1,
        "reason_2": reason_2,
        "example_1": example_1,
        "example_2": example_2,
        "opinion_close": on("opinion_close"),
        "reason": reason_1 or reason_2 or on("reason"),
        "example": example_1 or example_2 or on("example"),
    }


def list_results(assignment_id: str) -> dict:
    rows = _rows(assignment_id)
    done = [row for row in rows if row["status"] == "done" and isinstance(row.get("total"), (int, float))]
    totals = [float(row["total"]) for row in done]
    summary = {}
    if totals:
        summary = {"mean": round(statistics.fmean(totals), 2), "median": round(statistics.median(totals), 2), "n": len(totals)}
    return {"rows": rows, "summary": summary}


def delete_record(assignment_id: str, record_id: str) -> bool:
    path = records_dir(assignment_id) / f"{record_id}.json"
    record = read_json(path)
    if not isinstance(record, dict):
        return False
    token = str(record.get("read_token") or "")
    path.unlink(missing_ok=True)
    if token:
        from speech_rec.assignments import reads_dir

        (reads_dir() / f"{token}.json").unlink(missing_ok=True)
    return True


def delete_assignment_records(assignment_id: str) -> int:
    count = 0
    for path in list_json_files(records_dir(assignment_id)):
        record = read_json(path)
        if isinstance(record, dict) and delete_record(assignment_id, str(record.get("id") or path.stem)):
            count += 1
    return count


def recalc(assignment_id: str) -> int:
    """保存済みのレベルと語数から点数だけやり直す。APIは呼ばない。"""
    assignment = get_assignment(assignment_id) or {}
    speak = float(assignment.get("speak_sec") or 60)
    config = get_settings()["score_config"]
    updated = 0
    for path in list_json_files(records_dir(assignment_id)):
        record = read_json(path)
        if not isinstance(record, dict) or record.get("status") != "done":
            continue
        levels = dict(record.get("levels") or {})
        pause = record.get("delivery_pause_level")
        if pause is None:
            pause = levels.get("delivery") or 1
            record["delivery_pause_level"] = int(pause)
        levels["delivery"] = int(pause)
        words = int((record.get("metrics") or {}).get("words_counted") or 0)
        on_topic = "off_topic" not in (record.get("flags") or [])
        scored = score(levels, words, on_topic, config, speak_sec=speak)
        levels["delivery"] = cap_delivery_level(int(pause), speaking_wpm(words, speak))
        record["levels"] = levels
        record["scores"] = scored
        record["wpm"] = scored["wpm"]
        write_json(path, record)
        updated += 1
    return updated


def csv_text(assignment_id: str) -> str:
    payload = list_results(assignment_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["時刻", "ID", "試行", "状態", "語数", "WPM", "WPM点", "GD", "DEL", "LU", "TD", "計", "合計", "OREO", "間", "SNR", "旗", "コード", "円"])
    for row in payload["rows"]:
        points = row["points"]
        oreo = row["oreo"]
        writer.writerow([
            row["time"], row["student_id"], row["attempt"], row["status"], row["words"], row["wpm"], row["wpm_points"],
            points.get("general_description"), points.get("delivery"), points.get("language_use"), points.get("topic_development"),
            row["rubric"], row["total"],
            "".join(letter if oreo.get(key) else "·" for letter, key in (
                ("O", "opinion_open"), ("R", "reason_1"), ("R", "reason_2"),
                ("E", "example_1"), ("E", "example_2"), ("O", "opinion_close"),
            )),
            row["pauses"], row["snr_db"], " ".join(row["flags"]), row["code"], row["yen"],
        ])
    return buffer.getvalue()


def purge_expired() -> int:
    """保持日数を過ぎた数値記録を消す。音声ファイルは対象にしない。"""
    from datetime import timedelta

    from speech_rec.assignments import now

    days = int(get_settings().get("record_retention_days") or 60)
    cutoff = now() - timedelta(days=days)
    removed = 0
    root = records_dir("_").parent
    if not root.is_dir():
        return 0
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for path in list_json_files(folder):
            record = read_json(path)
            if not isinstance(record, dict):
                continue
            from speech_rec.assignments import parse_time

            moment = parse_time(str(record.get("created_at") or ""))
            if moment is not None and moment < cutoff and delete_record(folder.name, str(record.get("id") or path.stem)):
                removed += 1
    return removed


def assignment_choices() -> list[dict]:
    return [{"id": row["id"], "label": row.get("label") or str((row.get("topic") or {}).get("text") or "")[:40], "created_at": row.get("created_at")} for row in list_assignments()]
