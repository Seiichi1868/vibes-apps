import logging

from flask import Blueprint, Response, jsonify, request

from flask_app.services.gate_service import gate_access_allowed, gate_auth_error
from flask_app.services.tts_service import TTSService
from flask_app.utils.language_utils import is_tts_enabled, normalize_study_lang

logger = logging.getLogger(__name__)

tts_bp = Blueprint("tts", __name__)
tts_service = TTSService()


@tts_bp.route("/generate-tts", methods=["POST"])
def generate_tts():
    if not gate_access_allowed():
        return gate_auth_error()
    if not is_tts_enabled():
        return jsonify({"error": "TTS is disabled", "code": "TTS_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang = normalize_study_lang(payload.get("lang") or "")
    voice = tts_service.voice_for_lang(lang, generate=True)

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 4000:
        return jsonify({"error": "text is too long"}), 400

    try:
        url, cached = tts_service.resolve_audio(text, lang, voice)
    except Exception as exc:
        logger.error("TTS generation failed: %s", exc)
        return jsonify({"error": f"TTS generation failed: {exc}"}), 502

    return jsonify({"url": url, "cached": cached, "lang": lang, "voice": voice})


@tts_bp.route("/tts", methods=["POST"])
def tts():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    lang = normalize_study_lang(payload.get("lang") or "")
    voice = tts_service.voice_for_lang(lang, generate=False)
    use_cache = bool(payload.get("cache", False))

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 4000:
        return jsonify({"error": "text is too long"}), 400

    from flask_app.utils.audio_utils import cache_key_for_text

    cache_file = f"{cache_key_for_text(text, lang, voice)}.mp3"
    cache_path = tts_service.cache_dir / cache_file

    if use_cache and cache_path.is_file():
        return jsonify(
            {
                "url": f"/static/audio/{cache_file}",
                "cached": True,
                "lang": lang,
                "voice": voice,
            }
        )

    try:
        if use_cache:
            url, cached = tts_service.resolve_audio(text, lang, voice)
            return jsonify({"url": url, "cached": cached, "lang": lang, "voice": voice})

        audio_bytes = tts_service.synthesize(text, lang, voice)
    except Exception as exc:
        logger.error("TTS failed: %s", exc)
        return jsonify({"error": f"TTS generation failed: {exc}"}), 502

    return Response(
        audio_bytes,
        mimetype="audio/mpeg",
        headers={"Content-Disposition": "inline"},
    )
