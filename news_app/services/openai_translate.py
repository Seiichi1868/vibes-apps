"""英語ニューススクリプトを日本語またはスペイン語に翻訳する。"""
from __future__ import annotations

import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from news_app.config import DEFAULT_AI_MODEL, resolve_display_language
from news_app.services.openai_utils import (
    PREMIUM_MAX_COMPLETION_TOKENS,
    is_reasoning_chat_model,
    parse_json_object,
    reasoning_effort_for_model,
)

TRANSLATION_MODEL = DEFAULT_AI_MODEL
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
TRANSLATE_TIMEOUT_SEC = 90

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
            is_cjk = char in _CJK_TERMINAL
            if is_cjk or at_end or next_is_space:
                if char in _LATIN_TERMINAL and _is_abbreviation("".join(buf)):
                    index = cursor
                    continue
                if char in _LATIN_TERMINAL and not at_end:
                    look = cursor
                    while look < length and source[look].isspace():
                        look += 1
                    if look < length and source[look].islower():
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
        if len(en_parts) > 1 and len(en_parts) == len(ja_parts):
            expanded.extend({"en": en, "ja": ja} for en, ja in zip(en_parts, ja_parts))
        elif english or translated:
            expanded.append({"en": english, "ja": translated})
    return expanded


def _target_spec(target_lang: str) -> tuple[str, dict]:
    lang = resolve_display_language(target_lang)
    if lang != "es":
        lang = "ja"
    return lang, _TARGET_PROMPTS[lang]


def _build_user_prompt(units: list[str], spec: dict) -> str:
    numbered = "\n".join(f"{index}. {unit}" for index, unit in enumerate(units, start=1))
    return spec["user"].format(count=len(units), numbered=numbered)


def _extract_message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def _create_chat_completion(*, api_key: str, model: str, messages: list[dict]) -> dict:
    payload: dict = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if is_reasoning_chat_model(model):
        payload["max_completion_tokens"] = PREMIUM_MAX_COMPLETION_TOKENS
        effort = reasoning_effort_for_model(model)
        if effort:
            payload["reasoning_effort"] = effort
    else:
        payload["temperature"] = 0.2

    request = Request(
        OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=TRANSLATE_TIMEOUT_SEC, context=ssl_context) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API エラー ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API に接続できませんでした: {exc.reason}") from exc

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("AI からの応答形式が不正です。")
    return data


def _request_translations(
    *,
    api_key: str,
    model: str,
    units: list[str],
    spec: dict,
    extra_note: str = "",
) -> list[str]:
    user_prompt = _build_user_prompt(units, spec)
    if extra_note:
        user_prompt += f"\n\n{extra_note}"
    payload = _create_chat_completion(
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": spec["system"]},
            {"role": "user", "content": user_prompt},
        ],
    )
    parsed = parse_json_object(_extract_message_text(payload))
    raw_items = parsed.get("translations")
    if not isinstance(raw_items, list):
        raise ValueError("AI が対訳配列を返しませんでした。")
    return [str(item or "").strip() for item in raw_items]


def translate_script(
    script: str,
    *,
    api_key: str,
    model: str = TRANSLATION_MODEL,
    target_lang: str = "ja",
) -> dict:
    """英語スクリプトを指定言語へ訳し、左右対訳ペアも返す。"""
    lang, spec = _target_spec(target_lang)
    script = str(script or "").strip()
    if not script:
        raise ValueError(spec["empty_error"])
    if not api_key:
        raise ValueError(
            "OpenAI API キーが未設定です。"
            "管理画面（/news/admin/）の「OpenAI API キー」欄にキーを入力して保存してください。"
        )

    units = split_script_units(script)
    translations = _request_translations(api_key=api_key, model=model, units=units, spec=spec)
    if len(translations) != len(units):
        translations = _request_translations(
            api_key=api_key,
            model=model,
            units=units,
            spec=spec,
            extra_note=spec["retry_note"].format(got=len(translations), need=len(units)),
        )
    if len(translations) != len(units) or not any(translations):
        raise ValueError(spec["count_error"])

    pairs = expand_sentence_aligned_rows(
        [{"en": en, "ja": translated} for en, translated in zip(units, translations)]
    )
    text = "\n".join(item["ja"] for item in pairs).strip()
    return {
        "target_lang": lang,
        "script_translation": text,
        "script_ja": text if lang == "ja" else "",
        "pairs": pairs,
    }


def translate_script_to_japanese(
    script: str,
    *,
    api_key: str,
    model: str = TRANSLATION_MODEL,
) -> dict:
    """英語スクリプトを日本語訳し、左右対訳ペアも返す。"""
    return translate_script(script, api_key=api_key, model=model, target_lang="ja")
