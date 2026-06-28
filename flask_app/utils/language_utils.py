import re

from flask_app.config import Config
import flask_app.state as state
from flask_app.state import AI_MODE_OPTIONS, DEFAULT_ENABLED_LANGUAGES, STUDY_LANGUAGE_CATALOG


def normalize_study_lang_id(raw: str) -> str:
    value = (raw or "").strip().lower().replace("_", "-")
    aliases = {
        "en-us": "en",
        "english": "en",
        "es-es": "es",
        "spanish": "es",
        "ja-jp": "ja",
        "japanese": "ja",
        "ro-ro": "ro",
        "romanian": "ro",
    }
    if value in STUDY_LANGUAGE_CATALOG:
        return value
    return aliases.get(value, "en")


def normalize_study_lang(raw: str) -> str:
    lang_id = normalize_study_lang_id(raw)
    return STUDY_LANGUAGE_CATALOG.get(lang_id, STUDY_LANGUAGE_CATALOG["en"])["api_lang"]


def lang_id_from_api(api_lang: str) -> str:
    for lang_id, meta in STUDY_LANGUAGE_CATALOG.items():
        if meta["api_lang"] == api_lang:
            return lang_id
    return "en"


def get_enabled_study_languages() -> list[str]:
    return list(state.ENABLED_STUDY_LANGUAGES)


def normalize_enabled_languages(raw) -> list[str]:
    if raw is None:
        return list(DEFAULT_ENABLED_LANGUAGES)
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part).strip() for part in raw if str(part).strip()]
    else:
        raise ValueError("enabled_languages must be a list")

    normalized: list[str] = []
    for item in items:
        lang_id = normalize_study_lang_id(item)
        if lang_id not in STUDY_LANGUAGE_CATALOG:
            raise ValueError(f"unsupported language: {item}")
        if lang_id not in normalized:
            normalized.append(lang_id)
    if not normalized:
        raise ValueError("at least one language must be enabled")
    return normalized


def set_enabled_study_languages(languages: list[str]) -> list[str]:
    from flask_app.services.runtime_settings import update_runtime_settings

    normalized = normalize_enabled_languages(languages)
    update_runtime_settings(enabled_study_languages=normalized)
    return get_enabled_study_languages()


def languages_response() -> dict:
    enabled = get_enabled_study_languages()
    return {
        "ok": True,
        "enabled_languages": enabled,
        "languages": [
            {**STUDY_LANGUAGE_CATALOG[lang_id], "enabled": lang_id in enabled}
            for lang_id in STUDY_LANGUAGE_CATALOG
        ],
    }


def normalize_ai_mode(raw: str) -> str:
    value = (raw or "").strip().lower().replace("_", "-")
    aliases = {
        "gpt-4o-mini": "4o-mini",
        "4omini": "4o-mini",
        "economy": "4o-mini",
        "gpt-5-mini": "5-mini",
        "5mini": "5-mini",
        "premium": "5-mini",
        "gpt-5.4-mini": "5.4-mini",
        "gpt-54-mini": "5.4-mini",
        "5.4mini": "5.4-mini",
        "gpt-5.4-nano": "5.4-nano",
        "gpt-54-nano": "5.4-nano",
        "5.4nano": "5.4-nano",
        "gpt-4o": "4o",
        "4o": "4o",
        "gpt-54": "5.4",
        "gpt-5.4": "5.4",
        "5.4": "5.4",
    }
    value = aliases.get(value, value)
    if value in AI_MODE_OPTIONS:
        return value
    raise ValueError(f"unsupported ai_mode: {raw}")


def get_ai_mode() -> str:
    return state.AI_MODE


def set_ai_mode(mode: str) -> str:
    from flask_app.services.runtime_settings import update_runtime_settings

    normalized = normalize_ai_mode(mode)
    update_runtime_settings(ai_mode=normalized)
    return state.AI_MODE


def ai_mode_response() -> dict:
    mode = get_ai_mode()
    option = AI_MODE_OPTIONS[mode]
    return {
        "ok": True,
        "ai_mode": mode,
        "active_model": option["model"],
        "label": option["label"],
        "hint": option["hint"],
        "ocr_model": Config.OCR_MODEL,
        "modes": [{"id": key, **AI_MODE_OPTIONS[key]} for key in AI_MODE_OPTIONS],
        "use_gpt5_mode": mode != Config.DEFAULT_AI_MODE,
    }


def normalize_ui_language(raw) -> str:
    value = str(raw or "").strip().lower()
    if value in {"ja", "jp", "japanese", "日本語"}:
        return "ja"
    if value in {"en", "english", "英語"}:
        return "en"
    return "ja"


def get_default_ui_language() -> str:
    return state.DEFAULT_UI_LANGUAGE


def set_default_ui_language(raw) -> str:
    from flask_app.services.runtime_settings import update_runtime_settings

    normalized = normalize_ui_language(raw)
    update_runtime_settings(default_ui_language=normalized)
    return state.DEFAULT_UI_LANGUAGE


def is_tts_enabled() -> bool:
    return state.TTS_ENABLED


def set_tts_enabled(enabled: bool) -> bool:
    from flask_app.services.runtime_settings import update_runtime_settings

    saved = update_runtime_settings(tts_enabled=bool(enabled))
    return bool(saved["tts_enabled"])


def ocr_system_prompt(api_lang: str) -> str:
    lang_id = lang_id_from_api(api_lang)
    specs = {
        "en": "画像内の英語の文章だけを正確に抜き出してください。",
        "es": "画像内のスペイン語（スペイン）の文章だけを正確に抜き出してください。",
        "ja": "画像内の日本語（ひらがな・カタカナ・漢字）の文章だけを正確に抜き出してください。",
        "ro": "画像内のルーマニア語（ă â î ș ț などの文字を含む）の文章だけを正確に抜き出してください。",
    }
    target = specs.get(lang_id, specs["en"])
    return (
        f"{target}"
        "挨拶や解説などの余計な日本語の返答は一切不要です。"
        "対象言語のテキストのみを返してください。"
    )


def ocr_user_prompt(api_lang: str) -> str:
    lang_id = lang_id_from_api(api_lang)
    labels = {
        "en": "Extract all English text from this image.",
        "es": "Extract all Spanish text from this image.",
        "ja": "Extract all Japanese text from this image.",
        "ro": "Extract all Romanian text from this image.",
    }
    return labels.get(lang_id, labels["en"])


def grammar_system_prompt(api_lang: str) -> str:
    lang_id = lang_id_from_api(api_lang)
    if lang_id == "ja":
        return """あなたは日本語を学ぶ外国人向けの日本語教師です。日本語の作文（約50語）を優しく、かつ正確に添削してください。

必ず守ること:
- 助詞のミス、不自然な語順、敬語の誤り、漢字の誤用、ひらがな・カタカナ・漢字のバランスを見逃さない。
- corrected は日本語全文で返す。
- tips は各修正点ごとに1件、優しい日本語のみで書く（ルーマニア語は使わない）。
- tips_english には、tips 全体の内容を英語に翻訳したテキストを1つだけ入れる（日本語 tips の下に表示する全体英訳）。
- 「〜可能性があります」など曖昧な表現は禁止。断定調のみ。
- 修正点ごとに tips を1件ずつ。最大8件。
- 問題がなければ corrected は原文のまま、has_issues は false、tips は1件:
  「修正の必要はありません。完璧な日本語です！」
  tips_english は "No corrections needed. Your Japanese is perfect!"

出力は次のJSONオブジェクトのみ:
{
  "corrected": "修正後の日本語全文",
  "tips": ["優しい日本語の解説1", "優しい日本語の解説2"],
  "tips_english": "All tips translated into English as one block",
  "has_issues": true または false,
  "detected_lang": "ja"
}"""

    lang_names = {
        "en": "英語",
        "es": "スペイン語（スペイン）",
        "ro": "ルーマニア語",
    }
    perfect = {
        "en": "修正の必要はありません。完璧な英文です！",
        "es": "修正の必要はありません。完璧なスペイン語です！",
        "ro": "修正の必要はありません。完璧なルーマニア語です！",
    }
    target = lang_names.get(lang_id, "英語")
    perfect_tip = perfect.get(lang_id, perfect["en"])
    detected = lang_id if lang_id in {"en", "es", "ro"} else "en"

    return f"""あなたは高校生向けの{target}教師です。生徒の作文（約50語）を優しく、かつ正確に添削してください。

必ず守ること:
- {target}で文法チェックする。フロントから lang ヒントが付く場合はその言語を優先する。
- 時制、冠詞、性数一致、スペル・綴りミスを見逃さない。
- corrected は入力と同じ言語の全文で返す。tips は常に日本語のみ。
- 「〜可能性があります」など曖昧な表現は禁止。「〜です」「〜してください」の断定調のみ。
- 修正点ごとに tips を1件ずつ（最大8件）。
- 問題がなければ corrected は原文のまま、has_issues は false、tips は1件のみ:
  「{perfect_tip}」

出力は次のJSONオブジェクトのみ:
{{
  "corrected": "修正後の全文（入力と同じ言語）",
  "tips": ["誤り → 正しい形: 日本語の解説"],
  "has_issues": true または false,
  "detected_lang": "{detected}"
}}"""


def pronunciation_system_prompt(api_lang: str) -> str:
    lang_id = lang_id_from_api(api_lang)
    if lang_id == "ja":
        return """あなたは日本語音読コーチです。お手本テキストと生徒の音読（STT）テキストを比較し、発音アドバイスを書いてください。

必ず守ること:
- 日本語学習者が間違いやすい音（長短母音、促音、濁音・半濁音、イントネーションなど）に注目する。
- STT上でずれ・置き換え・欠落が見える部分を中心に解説する。
- advice は優しい日本語のみで2〜3行（短文）にまとめる。ルーマニア語は一切使わない。
- advice_english には advice と同じ内容の完全な英訳を1つ入れる。
- 一致率の復唱や長い講義は不要。励ましを1文含めてもよい。

出力は次のJSONオブジェクトのみ:
{"advice": "優しい日本語のアドバイス2〜3行", "advice_english": "Complete English translation of the advice"}"""

    if lang_id == "en":
        focus = "日本人の英語学習者が間違いやすい発音（L/R、th、V/B、語尾の母音など）"
    elif lang_id == "es":
        focus = "日本人のスペイン語学習者が間違いやすい発音（r/rr、ñ、母音、強勢など）"
    else:
        focus = "日本人のルーマニア語学習者が間違いやすい発音（特殊文字 ă â î ș ț、強勢、母音など）"

    return f"""あなたは音読コーチです。お手本テキストと生徒の音読（STT）テキストを比較し、発音アドバイスを書いてください。

必ず守ること:
- {focus}に注目する。
- STT上でずれ・置き換え・欠落が見える部分を中心に解説する。
- 次から意識すべきコツを優しい日本語で2〜3行（短文）にまとめる。
- 一致率の復唱や長い講義は不要。励ましを1文含めてもよい。

出力は次のJSONオブジェクトのみ:
{{"advice": "優しい日本語のアドバイス2〜3行"}}"""


def grammar_user_message(text: str, lang: str) -> str:
    lang_id = lang_id_from_api(lang)
    labels = {
        "en": "英語（en-US）",
        "es": "スペイン語（スペイン / es-ES）",
        "ja": "日本語（ja-JP）",
        "ro": "ルーマニア語（ro-RO）",
    }
    label = labels.get(lang_id, labels["en"])
    return f"[学習言語ヒント: {label}]\n\n{text}"


def perfect_grammar_tip(lang: str) -> str:
    lang_id = lang_id_from_api(lang)
    tips = {
        "en": "修正の必要はありません。完璧な英文です！",
        "es": "修正の必要はありません。完璧なスペイン語です！",
        "ja": "修正の必要はありません。完璧な日本語です！",
        "ro": "修正の必要はありません。完璧なルーマニア語です！",
    }
    return tips.get(lang_id, tips["en"])


def grammar_fallback_tip(lang: str) -> str:
    lang_id = lang_id_from_api(lang)
    tips = {
        "en": "英文を見直し、上の修正案を参考にしてください。",
        "es": "スペイン語文を見直し、上の修正案を参考にしてください。",
        "ja": "日本語文を見直し、上の修正案を参考にしてください。",
        "ro": "ルーマニア語文を見直し、上の修正案を参考にしてください。",
    }
    return tips.get(lang_id, tips["en"])


def pronunciation_reference_label(lang: str) -> str:
    lang_id = lang_id_from_api(lang)
    labels = {
        "en": "お手本の英文",
        "es": "お手本のスペイン語文",
        "ja": "お手本の日本語文",
        "ro": "お手本のルーマニア語文",
    }
    return labels.get(lang_id, labels["en"])


def normalize_grammar_tips(raw_tips) -> list[str]:
    if isinstance(raw_tips, str):
        candidates = [raw_tips]
    elif isinstance(raw_tips, list):
        candidates = raw_tips
    else:
        candidates = []

    items: list[str] = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        parts = re.split(r"\n+|(?:^|\s)[-•・]\s+", text)
        for part in parts:
            cleaned = re.sub(r"^\d+[\.\)、]\s*", "", str(part).strip())
            if cleaned:
                items.append(cleaned)

    unique: list[str] = []
    seen: set[str] = set()
    for tip in items:
        if tip in seen:
            continue
        seen.add(tip)
        unique.append(tip)
    return unique[: Config.GRAMMAR_TIPS_MAX]
