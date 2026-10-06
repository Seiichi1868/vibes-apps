"""対訳の文分割。News は import しない。"""
from __future__ import annotations

import re

_LATIN_TERMINAL = set(".!?")
_CJK_TERMINAL = set("。！？")
_CLOSING_QUOTES = set("\"'”’」』)")
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "vs",
    "etc",
    "inc",
    "ltd",
    "co",
    "corp",
    "mt",
    "gen",
    "gov",
    "sen",
    "rep",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "a.m",
    "p.m",
    "e.g",
    "i.e",
    "u.s",
    "u.k",
    "u.n",
    "e.u",
    "u.s.a",
}

_TARGET_PROMPTS = {
    "ja": {
        "system": """\
あなたは、日本の高校の英語授業向けにニュース原稿を訳す翻訳者です。
番号付きの英語ユニットを、同じ順番・同じ件数で日本語に翻訳してください。
各ユニットは原則として1文です。左右対訳で並べられるように、文の対応を崩さないでください。

ルール:
- 前置き・解説・注釈は付けない。
- 出力は JSON オブジェクトのみ。キーは translations。
- translations は文字列配列で、入力ユニットと同じ件数・同じ順番にする。
- 1つの英語ユニットに対して、対応する日本語を1つだけ入れる。
- ニュースとして自然な日本語にする（直訳調にしない）。
- 固有名詞は、一般的な日本語表記があればそれを使い、なければ英語のまま残す。
- 数字・日付・肩書は原文の情報を落とさない。
""",
        "user": (
            "次の英語ユニットを日本語に翻訳してください。\n"
            "translations 配列は必ず {count} 件にしてください。\n\n"
            '形式: {{"translations": ["日本語1", "日本語2"]}}\n\n'
            "--- English units ---\n{numbered}\n--- End ---\n"
        ),
        "empty_error": "スクリプトが空です。和訳するには英語スクリプトが必要です。",
        "count_error": "AI が原文と同じ件数の和訳を返しませんでした。再試行してください。",
        "retry_note": "前回は {got} 件でした。必ず {need} 件にしてください。",
    },
    "es": {
        "system": """\
Eres traductor de noticias en inglés para clases de inglés de secundaria con alumnado hispanohablante.
Traduce las unidades numeradas al español, en el mismo orden y con el mismo número de elementos.

Reglas:
- No añadas prefacios, explicaciones ni notas.
- La salida es solo un objeto JSON con la clave translations.
- translations es un array de cadenas con exactamente el mismo número y orden que las unidades de entrada.
- Una unidad en inglés corresponde a una sola traducción al español.
- Cada unidad es normalmente una oración. Conserva la correspondencia frase a frase.
- Usa un español natural de noticias, no una traducción palabra por palabra.
- Si hay una forma habitual en español de un nombre propio, úsala; si no, deja el inglés.
- Conserva números, fechas y cargos del original.
""",
        "user": (
            "Traduce las siguientes unidades en inglés al español.\n"
            "El array translations debe tener exactamente {count} elementos.\n\n"
            'Formato: {{"translations": ["español1", "español2"]}}\n\n'
            "--- English units ---\n{numbered}\n--- End ---\n"
        ),
        "empty_error": "スクリプトが空です。翻訳するには英語スクリプトが必要です。",
        "count_error": "AI が原文と同じ件数の翻訳を返しませんでした。再試行してください。",
        "retry_note": "La respuesta anterior tenía {got} elementos. Debe tener {need}.",
    },
}


def _is_abbreviation(buffer: str) -> bool:
    core = re.sub(r"[\"'”’」』)]+$", "", str(buffer or "").rstrip())
    if not core.endswith("."):
        return False
    match = re.search(r"([A-Za-z][A-Za-z.]*)\.$", core)
    if not match:
        return False
    token = match.group(1).lower().rstrip(".")
    if token in _ABBREVIATIONS or match.group(1).lower() in _ABBREVIATIONS:
        return True
    return bool(re.fullmatch(r"[A-Za-z]", token))


def _split_sentences(text: str) -> list[str]:
    """句点・終止符で文に分ける。改行の有無に依存しない。"""
    source = str(text or "")
    if not source:
        return []
    units: list[str] = []
    buf: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        buf.append(char)
        if char in _LATIN_TERMINAL or char in _CJK_TERMINAL:
            if char == "." and index + 1 < length and source[index + 1] == ".":
                index += 1
                continue
            cursor = index + 1
            while cursor < length and source[cursor] in _CLOSING_QUOTES:
                buf.append(source[cursor])
                cursor += 1
            at_end = cursor >= length
            next_is_space = cursor < length and source[cursor].isspace()
            look = cursor
            while look < length and source[look].isspace():
                look += 1
            next_is_upper = look < length and source[look].isupper()
            is_cjk = char in _CJK_TERMINAL
            if is_cjk or at_end or next_is_space or next_is_upper:
                if char in _LATIN_TERMINAL and _is_abbreviation("".join(buf)):
                    index = cursor
                    continue
                candidate = "".join(buf).strip()
                if candidate:
                    units.append(candidate)
                buf = []
                index = cursor
                while index < length and source[index].isspace():
                    index += 1
                continue
        index += 1
    tail = "".join(buf).strip()
    if tail:
        units.append(tail)
    return units


def split_script_units(script: str) -> list[str]:
    """授業スクリプトを、左右対訳用の文ユニットに分ける。"""
    text = str(script or "").strip()
    if not text:
        return []
    collapsed = re.sub(r"\s+", " ", text)
    parts = _split_sentences(collapsed)
    if len(parts) > 1:
        return parts
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        units: list[str] = []
        for line in lines:
            units.extend(_split_sentences(line) or [line])
        return units
    return parts or [text]


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def sync_pairs_to_script(script: str, pairs: list[dict]) -> dict | None:
    """文字起こしの削除に合わせて、既存の対訳から消えた文を外す。

    文が短くなった箇所は ja を空にして、呼び出し側で訳し直す。
    変化がなければ None。
    """
    units = split_script_units(script)
    old = [row for row in pairs if isinstance(row, dict)]
    if not old:
        return None
    old_text = _norm_text(" ".join(str(row.get("en") or "") for row in old))
    if _norm_text(script) == old_text:
        return None
    kept: list[dict] = []
    cursor = 0
    retranslate: list[int] = []
    for unit in units:
        normalized = _norm_text(unit)
        hit = None
        trimmed = False
        for index in range(cursor, len(old)):
            english = _norm_text(old[index].get("en"))
            if not english:
                continue
            if english == normalized:
                hit = index
                break
            if len(normalized) >= 12 and english.startswith(normalized):
                hit = index
                trimmed = True
                break
        if hit is None:
            kept.append({"en": unit, "ja": ""})
            retranslate.append(len(kept) - 1)
            continue
        if trimmed:
            kept.append({"en": unit, "ja": ""})
            retranslate.append(len(kept) - 1)
        else:
            kept.append({
                "en": unit,
                "ja": str(old[hit].get("ja") or old[hit].get("es") or "").strip(),
            })
        cursor = hit + 1
    return {"pairs": kept, "retranslate": retranslate}


def expand_sentence_aligned_rows(rows: list[dict]) -> list[dict]:
    """1行に複数文が入っている対訳を、文ごとに左右へ展開する。"""
    expanded: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        english = str(row.get("en") or "").strip()
        translated = str(row.get("ja") or row.get("es") or row.get("text") or "").strip()
        en_parts = split_script_units(english) if english else []
        ja_parts = split_script_units(translated) if translated else []
        if len(en_parts) <= 1 and len(ja_parts) <= 1:
            if english or translated:
                expanded.append({"en": english, "ja": translated})
            continue
        count = max(len(en_parts), len(ja_parts))
        for index in range(count):
            expanded.append({
                "en": en_parts[index] if index < len(en_parts) else "",
                "ja": ja_parts[index] if index < len(ja_parts) else "",
            })
    return expanded
