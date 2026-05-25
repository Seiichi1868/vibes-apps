import json
import logging
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from app.config import Config
from app.services.ai_service import AIService
from app.services.analysis_service import AnalysisService
from app.services.gate_service import gate_access_allowed, gate_auth_error
from app.services.history_service import HistoryService
from app.services.speech_service import SpeechService
from app.utils.audio_utils import allowed_file, convert_to_wav

logger = logging.getLogger(__name__)

transcription_bp = Blueprint("transcription", __name__)
speech_service = SpeechService()
analysis_service = AnalysisService()
ai_service = AIService()
history_service = HistoryService(history_dir=Config.HISTORY_DIR, max_items=Config.MAX_HISTORY_ITEMS)


@transcription_bp.route("/pronunciation-advice", methods=["POST"])
def pronunciation_advice():
    if not gate_access_allowed():
        return gate_auth_error()

    payload = request.get_json(silent=True) or {}
    reference = (payload.get("reference") or "").strip()
    spoken = (payload.get("spoken") or "").strip()
    lang_raw = payload.get("lang") or ""

    if not reference:
        return jsonify({"error": "reference is required"}), 400
    if not spoken:
        return jsonify({"error": "spoken is required"}), 400

    accuracy_raw = payload.get("accuracy_percent")
    try:
        accuracy_percent = int(accuracy_raw)
    except (TypeError, ValueError):
        accuracy_percent = None

    try:
        return jsonify(
            ai_service.generate_pronunciation_advice(
                reference, spoken, lang_raw, accuracy_percent
            )
        )
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from pronunciation model"}), 502
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logger.error("Pronunciation advice failed: %s", exc)
        return jsonify({"error": f"Pronunciation advice failed: {exc}"}), 502


@transcription_bp.route("/transcribe", methods=["POST"])
def transcribe():
    """音声をテキストに変換（Google Cloud STT 設定時）"""
    temp_files = []
    try:
        if "audio" not in request.files:
            return jsonify({"error": "No audio file provided"}), 400

        audio_file = request.files["audio"]
        language_code = request.form.get("language", "ja-JP")
        expected_text = request.form.get("expected_text", "")

        if audio_file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(audio_file.filename, current_app.config["ALLOWED_EXTENSIONS"]):
            return jsonify({"error": "Invalid file type"}), 400

        filename = secure_filename(audio_file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{timestamp}_{filename}")
        audio_file.save(temp_path)
        temp_files.append(temp_path)

        wav_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{timestamp}_converted.wav")
        if not convert_to_wav(temp_path, wav_path):
            return jsonify({"error": "Failed to convert audio file"}), 500
        temp_files.append(wav_path)

        transcript, confidence = speech_service.transcribe(wav_path, language_code)

        analysis = None
        feedback = None
        if expected_text:
            analysis = analysis_service.analyze_pronunciation(
                expected_text, transcript, language_code
            )
            try:
                feedback = ai_service.generate_feedback(expected_text, transcript, language_code)
            except Exception as exc:
                logger.warning("Feedback generation failed: %s", exc)

            user_id = session.get("user_id", "anonymous")
            history_service.save(
                user_id,
                {
                    "language": language_code,
                    "text": expected_text,
                    "similarity": analysis["similarity"],
                    "evaluation": analysis["evaluation"],
                },
            )

        return jsonify(
            {
                "transcript": transcript,
                "confidence": round(confidence * 100, 2),
                "analysis": analysis,
                "feedback": feedback,
            }
        )

    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        logger.error("Error in transcribe endpoint: %s", exc)
        return jsonify({"error": str(exc)}), 500

    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as exc:
                logger.error("Error deleting temporary file: %s", exc)
