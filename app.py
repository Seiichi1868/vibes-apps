import base64
import datetime
import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
AUDIO_CACHE_DIR = BASE_DIR / "static" / "audio"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ECONOMY = "gpt-4o-mini"
OCR_MODEL = MODEL_ECONOMY
DEFAULT_AI_MODE = "4o-mini"
PREMIUM_MAX_COMPLETION_TOKENS = 4096
PREMIUM_REASONING_EFFORT = "low"

AI_MODE_OPTIONS: dict[str, dict[str, str]] = {
    "4o-mini": {
        "label": "節約モード",
        "hint": "全機能で gpt-4o-mini を使用",
        "model": MODEL_ECONOMY,
    },
    "5-mini": {
        "label": "前世代miniモード",
        "hint": "添削・解説・発音に gpt-5-mini",
        "model": "gpt-5-mini",
    },
    "5.4-mini": {
        "label": "最新高精度モード",
        "hint": "添削・解説・発音に gpt-5.4-mini",
        "model": "gpt-5.4-mini",
    },
    "5.4-nano": {
        "label": "最安実験モード",
        "hint": "添削・解説・発音に gpt-5.4-nano",
        "model": "gpt-5.4-nano",
    },
}

# 添削・解説・発音アドバイス用の現在モード（OCR は常に gpt-4o-mini）
AI_MODE = DEFAULT_AI_MODE
TTS_MODEL = "tts-1"
TTS_VOICE_BY_LANG = {
    "en-US": "nova",
    "es-ES": "shimmer",
    "ja-JP": "nova",
    "ro-RO": "onyx",
}
TTS_GENERATE_VOICE_BY_LANG = {
    "en-US": "alloy",
    "es-ES": "shimmer",
    "ja-JP": "nova",
    "ro-RO": "onyx",
}
TTS_DEFAULT_LANG = "en-US"

STUDY_LANGUAGE_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "id": "en",
        "api_lang": "en-US",
        "label": "English",
        "label_ja": "英語",
        "flag": "🇬🇧",
    },
    "es": {
        "id": "es",
        "api_lang": "es-ES",
        "label": "Spanish",
        "label_ja": "スペイン語",
        "flag": "🇪🇸",
    },
    "ja": {
        "id": "ja",
        "api_lang": "ja-JP",
        "label": "Japanese",
        "label_ja": "日本語",
        "flag": "🇯🇵",
    },
    "ro": {
        "id": "ro",
        "api_lang": "ro-RO",
        "label": "Romanian",
        "label_ja": "ルーマニア語",
        "flag": "🇷🇴",
    },
}
DEFAULT_ENABLED_LANGUAGES = ["en", "es", "ja", "ro"]
ENABLED_STUDY_LANGUAGES: list[str] = list(DEFAULT_ENABLED_LANGUAGES)

# False = 生徒画面はブラウザ標準TTS / True = 再生ボタン押下時のみ OpenAI TTS
TTS_ENABLED = False


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
    return list(ENABLED_STUDY_LANGUAGES)


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
    global ENABLED_STUDY_LANGUAGES
    ENABLED_STUDY_LANGUAGES = normalize_enabled_languages(languages)
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


OCR_ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

OCR_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

OCR_MAX_BYTES = 10 * 1024 * 1024

GRAMMAR_TIPS_MAX = 8


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
    }
    value = aliases.get(value, value)
    if value in AI_MODE_OPTIONS:
        return value
    raise ValueError(f"unsupported ai_mode: {raw}")


def get_ai_mode() -> str:
    return AI_MODE


def set_ai_mode(mode: str) -> str:
    global AI_MODE
    AI_MODE = normalize_ai_mode(mode)
    return AI_MODE


def get_ai_chat_model() -> str:
    return AI_MODE_OPTIONS[get_ai_mode()]["model"]


def ai_mode_response() -> dict:
    mode = get_ai_mode()
    option = AI_MODE_OPTIONS[mode]
    return {
        "ok": True,
        "ai_mode": mode,
        "active_model": option["model"],
        "label": option["label"],
        "hint": option["hint"],
        "ocr_model": OCR_MODEL,
        "modes": [
            {"id": key, **AI_MODE_OPTIONS[key]}
            for key in AI_MODE_OPTIONS
        ],
        # 旧トグルUIとの互換
        "use_gpt5_mode": mode != DEFAULT_AI_MODE,
    }


def reasoning_effort_for_model(model: str) -> str | None:
    name = (model or "").strip().lower()
    if not is_reasoning_chat_model(model):
        return None
    if name.startswith("gpt-5.4") or name.startswith("gpt-5.1"):
        return "none"
    return PREMIUM_REASONING_EFFORT


def is_reasoning_chat_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return True
    return name.startswith(("o1", "o3", "o4"))


def parse_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("Expected JSON object", text, 0)
    return data


def extract_completion_text(completion) -> str:
    if not completion.choices:
        return ""
    message = completion.choices[0].message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
            else:
                text = getattr(part, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts).strip()
    return str(content or "").strip()


def create_json_chat_completion(
    client: OpenAI,
    model: str,
    messages: list,
    *,
    temperature: float = 0.2,
) -> dict:
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if is_reasoning_chat_model(model):
        kwargs["max_completion_tokens"] = PREMIUM_MAX_COMPLETION_TOKENS
        effort = reasoning_effort_for_model(model)
        if effort:
            kwargs["reasoning_effort"] = effort
    else:
        kwargs["temperature"] = temperature

    completion = client.chat.completions.create(**kwargs)
    raw = extract_completion_text(completion)
    if not raw:
        finish_reason = ""
        if completion.choices:
            finish_reason = str(completion.choices[0].finish_reason or "")
        raise ValueError(f"Empty model response (finish_reason={finish_reason or 'unknown'})")
    return parse_json_object(raw)


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
    return unique[:GRAMMAR_TIPS_MAX]


def get_openai_client() -> OpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _today_date_key() -> str:
    return datetime.date.today().strftime("%Y%m%d")


# True = クラスコード入力が必要 / False = 全員がコードなしで利用可能
CLASS_CODE_LOCK_ENABLED = True


def is_gate_lock_enabled() -> bool:
    return CLASS_CODE_LOCK_ENABLED


def set_gate_lock_enabled(enabled: bool) -> bool:
    global CLASS_CODE_LOCK_ENABLED
    CLASS_CODE_LOCK_ENABLED = bool(enabled)
    return CLASS_CODE_LOCK_ENABLED


def gate_access_allowed() -> bool:
    if not is_gate_lock_enabled():
        return True
    return is_valid_gate_token(request.headers.get("X-Gate-Token", ""))


def daily_class_code() -> str:
    digest = hashlib.sha256(_today_date_key().encode("utf-8")).hexdigest()
    return str(int(digest[:8], 16) % 10000).zfill(4)


def gate_token_for_today() -> str:
    secret = os.getenv("GATE_SECRET", "").strip() or os.getenv("OPENAI_API_KEY", "vibespeak-gate")
    digest = hashlib.sha256(f"{secret}:{_today_date_key()}".encode("utf-8")).hexdigest()
    return digest[:24]


def is_valid_gate_token(token: str) -> bool:
    value = (token or "").strip()
    if not value:
        return False
    return hmac.compare_digest(value, gate_token_for_today())


def gate_auth_error():
    return jsonify({"error": "class code required", "code": "GATE_REQUIRED"}), 403


def cache_key_for_text(text: str, lang: str = TTS_DEFAULT_LANG, voice: str | None = None) -> str:
    voice_part = voice or TTS_VOICE_BY_LANG.get(lang, TTS_VOICE_BY_LANG[TTS_DEFAULT_LANG])
    digest = hashlib.sha256(f"{lang}\n{voice_part}\n{text}".encode("utf-8")).hexdigest()
    return digest[:32]


def is_tts_enabled() -> bool:
    return TTS_ENABLED


def set_tts_enabled(enabled: bool) -> bool:
    global TTS_ENABLED
    TTS_ENABLED = bool(enabled)
    return TTS_ENABLED


def synthesize_openai_tts(text: str, lang: str, voice: str) -> bytes:
    client = get_openai_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    speech = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text,
        response_format="mp3",
    )
    return speech.read()


def resolve_tts_audio(text: str, lang: str, voice: str) -> tuple[str, bool]:
    cache_name = f"{cache_key_for_text(text, lang, voice)}.mp3"
    cache_path = AUDIO_CACHE_DIR / cache_name
    if cache_path.is_file():
        return f"/static/audio/{cache_name}", True

    audio_bytes = synthesize_openai_tts(text, lang, voice)
    cache_path.write_bytes(audio_bytes)
    return f"/static/audio/{cache_name}", False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/api/gate/status", methods=["GET"])
def gate_status():
    return jsonify(
        {
            "lock_enabled": is_gate_lock_enabled(),
            "code": daily_class_code(),
            "tts_enabled": is_tts_enabled(),
            "enabled_languages": get_enabled_study_languages(),
            "languages": languages_response()["languages"],
        }
    )


@app.route("/api/admin/gate-lock", methods=["GET", "POST"])
def admin_gate_lock():
    if request.method == "GET":
        return jsonify({"lock_enabled": is_gate_lock_enabled(), "ok": True})

    payload = request.get_json(silent=True) or {}
    raw = payload.get("lock_enabled")
    if isinstance(raw, bool):
        enabled = raw
    else:
        value = str(raw or "").strip().lower()
        if value in {"1", "true", "on", "yes"}:
            enabled = True
        elif value in {"0", "false", "off", "no"}:
            enabled = False
        else:
            return jsonify({"error": "lock_enabled is required"}), 400

    return jsonify({"ok": True, "lock_enabled": set_gate_lock_enabled(enabled)})


@app.route("/api/admin/ai-mode", methods=["GET", "POST"])
def admin_ai_mode():
    if request.method == "GET":
        return jsonify(ai_mode_response())

    payload = request.get_json(silent=True) or {}
    raw_mode = payload.get("ai_mode")
    if raw_mode is None and payload.get("use_gpt5_mode") is not None:
        raw = payload.get("use_gpt5_mode")
        if isinstance(raw, bool):
            raw_mode = "5-mini" if raw else DEFAULT_AI_MODE
        else:
            value = str(raw or "").strip().lower()
            raw_mode = "5-mini" if value in {"1", "true", "on", "yes"} else DEFAULT_AI_MODE

    if raw_mode is None:
        return jsonify({"error": "ai_mode is required"}), 400

    try:
        set_ai_mode(str(raw_mode))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(ai_mode_response())


@app.route("/api/admin/tts", methods=["GET", "POST"])
def admin_tts():
    if request.method == "GET":
        return jsonify({"ok": True, "tts_enabled": is_tts_enabled()})

    payload = request.get_json(silent=True) or {}
    raw = payload.get("tts_enabled")
    if raw is None:
        raw = payload.get("enabled")
    if isinstance(raw, bool):
        enabled = raw
    else:
        value = str(raw or "").strip().lower()
        if value in {"1", "true", "on", "yes"}:
            enabled = True
        elif value in {"0", "false", "off", "no"}:
            enabled = False
        else:
            return jsonify({"error": "tts_enabled is required"}), 400

    return jsonify({"ok": True, "tts_enabled": set_tts_enabled(enabled)})


@app.route("/api/admin/languages", methods=["GET", "POST"])
def admin_languages():
    if request.method == "GET":
        return jsonify(languages_response())

    payload = request.get_json(silent=True) or {}
    raw = payload.get("enabled_languages")
    if raw is None:
        raw = payload.get("languages")
    try:
        enabled = set_enabled_study_languages(raw if raw is not None else get_enabled_study_languages())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(languages_response() | {"enabled_languages": enabled})


@app.route("/api/gate/verify", methods=["POST"])
def gate_verify():
    if not is_gate_lock_enabled():
        return jsonify(
            {
                "ok": True,
                "token": gate_token_for_today(),
                "lock_enabled": False,
                "bypass": True,
            }
        )

    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    if code == daily_class_code():
        return jsonify({"ok": True, "token": gate_token_for_today(), "lock_enabled": True})
    return jsonify({"ok": False, "error": "invalid code"}), 403


@app.route("/api/gate/today", methods=["GET"])
def gate_today():
    return jsonify({"code": daily_class_code(), "lock_enabled": is_gate_lock_enabled()})


@app.route("/api/check-grammar", methods=["POST"])
def check_grammar():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang_raw = payload.get("lang") or payload.get("lang_id") or payload.get("language") or ""
    lang = normalize_study_lang(lang_raw)
    lang_id = lang_id_from_api(lang)
    if not text:
        return jsonify({"error": "text is required"}), 400

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    try:
        data = create_json_chat_completion(
            client,
            get_ai_chat_model(),
            [
                {"role": "system", "content": grammar_system_prompt(lang)},
                {"role": "user", "content": grammar_user_message(text, lang)},
            ],
            temperature=0.2,
        )
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from grammar model"}), 502
    except Exception as exc:
        return jsonify({"error": f"Grammar check failed: {exc}"}), 502

    corrected = str(data.get("corrected") or text).strip()
    tips = normalize_grammar_tips(data.get("tips"))
    has_issues = bool(data.get("has_issues", corrected != text))

    if not tips:
        if has_issues:
            tips = [grammar_fallback_tip(lang)]
        else:
            tips = [perfect_grammar_tip(lang)]

    tips_english = ""
    if lang_id == "ja":
        tips_english = str(data.get("tips_english") or "").strip()
        if not tips_english and not has_issues:
            tips_english = "No corrections needed. Your Japanese is perfect!"

    detected_lang = str(data.get("detected_lang") or "").strip().lower()
    allowed_detected = {"en", "es", "ja", "ro"}
    if detected_lang not in allowed_detected:
        detected_lang = lang_id

    response = {
        "corrected": corrected,
        "tips": tips,
        "has_issues": has_issues,
        "source": text,
        "detected_lang": detected_lang,
        "lang": lang,
        "lang_id": lang_id,
        "active_model": get_ai_chat_model(),
        "ai_mode": get_ai_mode(),
    }
    if tips_english:
        response["tips_english"] = tips_english
    return jsonify(response)


def resolve_image_mime(file_storage) -> str:
    mime = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if mime in OCR_ALLOWED_MIME:
        return mime
    ext = Path(file_storage.filename or "").suffix.lower()
    return OCR_MIME_BY_EXT.get(ext, "image/jpeg")


def clean_ocr_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


@app.route("/api/ocr", methods=["POST"])
def ocr():
    if not gate_access_allowed():
        return gate_auth_error()

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "image is required"}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "image is empty"}), 400
    if len(image_bytes) > OCR_MAX_BYTES:
        return jsonify({"error": "image is too large (max 10MB)"}), 400

    mime = resolve_image_mime(file)
    if mime not in OCR_ALLOWED_MIME:
        return jsonify({"error": "unsupported image type"}), 400

    lang = normalize_study_lang(request.form.get("lang") or request.args.get("lang") or "")

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

    try:
        completion = client.chat.completions.create(
            model=OCR_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": ocr_system_prompt(lang)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": ocr_user_prompt(lang),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        )
        extracted = clean_ocr_text(completion.choices[0].message.content or "")
    except Exception as exc:
        return jsonify({"error": f"OCR failed: {exc}"}), 502

    if not extracted:
        return jsonify({"error": "No text found in image"}), 422

    return jsonify({"text": extracted, "lang": lang})


@app.route("/api/generate-tts", methods=["POST"])
def generate_tts():
    if not gate_access_allowed():
        return gate_auth_error()
    if not is_tts_enabled():
        return jsonify({"error": "TTS is disabled", "code": "TTS_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang = normalize_study_lang(payload.get("lang") or "")
    voice = TTS_GENERATE_VOICE_BY_LANG.get(lang, TTS_GENERATE_VOICE_BY_LANG[TTS_DEFAULT_LANG])

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 4000:
        return jsonify({"error": "text is too long"}), 400

    try:
        url, cached = resolve_tts_audio(text, lang, voice)
    except Exception as exc:
        return jsonify({"error": f"TTS generation failed: {exc}"}), 502

    return jsonify(
        {
            "url": url,
            "cached": cached,
            "lang": lang,
            "voice": voice,
        }
    )


@app.route("/api/tts", methods=["POST"])
def tts():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang = normalize_study_lang(payload.get("lang") or "")
    voice = TTS_VOICE_BY_LANG.get(lang, TTS_VOICE_BY_LANG[TTS_DEFAULT_LANG])
    use_cache = bool(payload.get("cache", False))

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 4000:
        return jsonify({"error": "text is too long"}), 400

    cache_name = f"{cache_key_for_text(text, lang, voice)}.mp3"
    cache_path = AUDIO_CACHE_DIR / cache_name

    if use_cache and cache_path.is_file():
        return jsonify(
            {
                "url": f"/static/audio/{cache_name}",
                "cached": True,
                "lang": lang,
                "voice": voice,
            }
        )

    try:
        if use_cache:
            url, cached = resolve_tts_audio(text, lang, voice)
            return jsonify(
                {
                    "url": url,
                    "cached": cached,
                    "lang": lang,
                    "voice": voice,
                }
            )

        audio_bytes = synthesize_openai_tts(text, lang, voice)
    except Exception as exc:
        return jsonify({"error": f"TTS generation failed: {exc}"}), 502

    return Response(
        audio_bytes,
        mimetype="audio/mpeg",
        headers={"Content-Disposition": "inline"},
    )


@app.route("/api/pronunciation-advice", methods=["POST"])
def pronunciation_advice():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    reference = (payload.get("reference") or "").strip()
    spoken = (payload.get("spoken") or "").strip()
    lang = normalize_study_lang(payload.get("lang") or "")

    if not reference:
        return jsonify({"error": "reference is required"}), 400
    if not spoken:
        return jsonify({"error": "spoken is required"}), 400

    accuracy_raw = payload.get("accuracy_percent")
    try:
        accuracy_percent = int(accuracy_raw)
    except (TypeError, ValueError):
        accuracy_percent = None

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    user_message = (
        f"{pronunciation_reference_label(lang)}:\n{reference}\n\n"
        f"生徒の音読（STT）:\n{spoken}\n\n"
    )
    if accuracy_percent is not None:
        user_message += f"発音一致率: {accuracy_percent}%\n"

    try:
        data = create_json_chat_completion(
            client,
            get_ai_chat_model(),
            [
                {"role": "system", "content": pronunciation_system_prompt(lang)},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from pronunciation model"}), 502
    except Exception as exc:
        return jsonify({"error": f"Pronunciation advice failed: {exc}"}), 502

    advice = str(data.get("advice") or "").strip()
    if not advice:
        return jsonify({"error": "Empty advice from pronunciation model"}), 502

    lang_id = lang_id_from_api(lang)
    response = {
        "advice": advice,
        "model": get_ai_chat_model(),
        "lang": lang,
        "lang_id": lang_id,
    }
    if lang_id == "ja":
        advice_english = str(data.get("advice_english") or "").strip()
        if advice_english:
            response["advice_english"] = advice_english
    return jsonify(response)


@app.route("/static/audio/<path:filename>")
def serve_cached_audio(filename: str):
    safe_name = Path(filename).name
    return send_from_directory(AUDIO_CACHE_DIR, safe_name, mimetype="audio/mpeg")


@app.route("/api/evaluate", methods=["POST"])
def legacy_evaluate_endpoint():
    return (
        jsonify(
            {
                "error": "This app now runs fully in-browser with Web Speech API.",
                "message": "Please reload the page and use the browser-side recognition flow.",
            }
        ),
        410,
    )


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    return ("Not Found", 404)


@app.errorhandler(500)
def internal_error(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return ("Internal Server Error", 500)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
