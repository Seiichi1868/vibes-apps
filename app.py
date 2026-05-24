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
}
TTS_DEFAULT_LANG = "en-US"

OCR_SYSTEM_PROMPT = (
    "画像内の英語の文章だけを正確に抜き出してください。"
    "挨拶や解説などの余計な日本語の返答は一切不要です。"
    "英語のテキストのみを返してください。"
)

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

GRAMMAR_SYSTEM_PROMPT = """あなたは高校生向けの英語・スペイン語（スペイン）教師です。生徒の作文（約50語）を優しく、かつ正確に添削してください。

必ず守ること:
- 入力テキストが英語かスペイン語（スペイン）かを自動判別し、その言語で文法チェックする。フロントから lang ヒント（en-US または es-ES）が付く場合は、その言語を優先して判定する。
- 時制のミス、文脈のミス、スペル・綴りミス（タイプミス）、冠詞・性数一致（スペイン語）を見逃さない。
- corrected は入力と同じ言語の全文（英語なら英語、スペイン語ならスペイン語）で返す。解説（tips）は常に日本語のみ。
- 「〜可能性があります」「〜かもしれません」など曖昧な表現は禁止。「〜です」「〜してください」の断定調のみ。
- 修正が複数ある場合、tips は必ず「修正点ごとに1件」の配列にすること（1つの長文にまとめない）。
- 各 tip は「誤り → 正しい形: 理由（1〜2行、断定調）」の形式を推奨（例: went → go: yesterday があるため過去形にします。）
- 修正点が3つあれば tips は最低3件入れる。見落とし禁止。最大8件まで。
- 修正候補語だけのリストや、提案語リストだけを先に出す形式は禁止。
- 問題がなければ corrected は原文のまま、has_issues は false、tips は1件のみ:
  - 英語のとき「修正の必要はありません。完璧な英文です！」
  - スペイン語のとき「修正の必要はありません。完璧なスペイン語です！」

出力は次のJSONオブジェクトのみ（前後に説明文を付けない）:
{
  "corrected": "修正後の全文（入力と同じ言語）",
  "tips": ["誤り → 正しい形: 日本語の解説1", "誤り → 正しい形: 日本語の解説2"],
  "has_issues": true または false,
  "detected_lang": "en" または "es"
}"""

PRONUNCIATION_SYSTEM_PROMPT = """あなたは日本人の中高生向け英語発音コーチです。
お手本の英文と、生徒の音読を音声認識（STT）したテキストを比較し、発音のワンポイントアドバイスを日本語で書いてください。

必ず守ること:
- 日本人の英語学習者が間違いやすい発音のクセ（LとRの混同、thがsやdになる、VがBになる、単語の末尾に余計な母音が付く など）に注目する
- STT 上でずれ・置き換え・欠落が見える部分を中心に解説する
- 次から意識すべき発音のコツを、親しみやすい日本語で2〜3行（短文）にまとめる
- 一致率の数値の復唱や長い講義は不要。励ましを1文含めてもよい
- 問題がほとんどなければ、うまくできた点を短く褒める

出力は次のJSONオブジェクトのみ（前後に説明文を付けない）:
{"advice": "日本語のアドバイス2〜3行"}"""


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


def normalize_study_lang(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"es", "es-es", "es_es", "spanish"}:
        return "es-ES"
    if value in {"en", "en-us", "en_us", "english"}:
        return "en-US"
    return TTS_DEFAULT_LANG


def grammar_user_message(text: str, lang: str) -> str:
    if lang == "es-ES":
        return f"[学習言語ヒント: スペイン語（スペイン / es-ES）]\n\n{text}"
    if lang == "en-US":
        return f"[学習言語ヒント: 英語（en-US）]\n\n{text}"
    return text


def perfect_grammar_tip(lang: str) -> str:
    if lang == "es-ES":
        return "修正の必要はありません。完璧なスペイン語です！"
    return "修正の必要はありません。完璧な英文です！"


GRAMMAR_TIPS_MAX = 8


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


def cache_key_for_text(text: str, lang: str = TTS_DEFAULT_LANG) -> str:
    digest = hashlib.sha256(f"{lang}\n{text}".encode("utf-8")).hexdigest()
    return digest[:32]


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
    lang = normalize_study_lang(payload.get("lang") or "")
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
                {"role": "system", "content": GRAMMAR_SYSTEM_PROMPT},
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
            fallback = (
                "スペイン語文を見直し、上の修正案を参考にしてください。"
                if lang == "es-ES"
                else "英文を見直し、上の修正案を参考にしてください。"
            )
            tips = [fallback]
        else:
            tips = [perfect_grammar_tip(lang)]

    detected_lang = str(data.get("detected_lang") or "").strip().lower()
    if detected_lang not in {"en", "es"}:
        detected_lang = "es" if lang == "es-ES" else "en"

    return jsonify(
        {
            "corrected": corrected,
            "tips": tips,
            "has_issues": has_issues,
            "source": text,
            "detected_lang": detected_lang,
            "lang": lang,
        }
    )


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

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

    try:
        completion = client.chat.completions.create(
            model=OCR_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all English text from this image.",
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
        return jsonify({"error": "No English text found in image"}), 422

    return jsonify({"text": extracted})


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

    cache_name = f"{cache_key_for_text(text, lang)}.mp3"
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

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    try:
        speech = client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        audio_bytes = speech.read()
    except Exception as exc:
        return jsonify({"error": f"TTS generation failed: {exc}"}), 502

    if use_cache:
        cache_path.write_bytes(audio_bytes)
        return jsonify(
            {
                "url": f"/static/audio/{cache_name}",
                "cached": False,
                "lang": lang,
                "voice": voice,
            }
        )

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
    if lang != "en-US":
        return jsonify({"error": "pronunciation advice is available for English only"}), 400

    accuracy_raw = payload.get("accuracy_percent")
    try:
        accuracy_percent = int(accuracy_raw)
    except (TypeError, ValueError):
        accuracy_percent = None

    client = get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY is not configured"}), 500

    user_message = (
        f"お手本の英文:\n{reference}\n\n"
        f"生徒の音読（STT）:\n{spoken}\n\n"
    )
    if accuracy_percent is not None:
        user_message += f"発音一致率: {accuracy_percent}%\n"

    try:
        data = create_json_chat_completion(
            client,
            get_ai_chat_model(),
            [
                {"role": "system", "content": PRONUNCIATION_SYSTEM_PROMPT},
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

    return jsonify(
        {
            "advice": advice,
            "model": get_ai_chat_model(),
            "lang": lang,
        }
    )


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
