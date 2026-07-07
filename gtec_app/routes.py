"""GTEC Speaking App — Flask Blueprint。

GET  /gtec          → メイン画面
POST /gtec/evaluate → 採点 API（テキスト＋秒数のみ受信、音声ファイル不要）
"""

import logging

import openai
from flask import Blueprint, jsonify, render_template, request

from gtec_app.evaluator import (
    evaluate_part_a,
    evaluate_part_b,
    evaluate_part_c,
    evaluate_part_d,
)
from gtec_app.settings import public_settings, resolve_background
from gtec_app.tts import synthesize_question

logger = logging.getLogger(__name__)

gtec_bp = Blueprint("gtec", __name__)


@gtec_bp.route("/gtec")
def index():
    settings = public_settings()
    return render_template("gtec/index.html", background=resolve_background(settings.get("background_id")))


@gtec_bp.route("/gtec/api/settings", methods=["GET"])
def get_settings():
    return jsonify(public_settings())


@gtec_bp.route("/gtec/api/tts", methods=["POST"])
def generate_tts():
    """Part B 質問読み上げ用 TTS（OpenAI・MP3）。"""
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 500:
        return jsonify({"error": "text is too long"}), 400

    try:
        path, cached = synthesize_question(text)
        return jsonify({
            "url": f"/static/audio/gtec/{path.name}",
            "cached": cached,
        })
    except openai.AuthenticationError:
        return jsonify({"error": "OpenAI APIキーが正しく設定されていません。"}), 500
    except Exception as exc:
        logger.exception("GTEC TTS failed: %s", exc)
        return jsonify({"error": f"音声生成に失敗しました: {exc}"}), 502


@gtec_bp.route("/gtec/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json(force=True, silent=True) or {}

    part = str(data.get("part", "")).upper()
    text = str(data.get("text", "")).strip()
    duration = float(data.get("duration", 0) or 0)

    if not text:
        return jsonify({"error": "文字起こしテキストがありません。もう一度お試しください。"}), 400

    try:
        if part == "A":
            result = evaluate_part_a(
                text,
                duration,
                str(data.get("target_text", "")),
            )
        elif part == "B":
            result = evaluate_part_b(
                text,
                duration,
                str(data.get("question", "")),
                str(data.get("context", "")),
            )
        elif part == "C":
            panels = data.get("panel_descriptions", [])
            if not isinstance(panels, list):
                panels = []
            result = evaluate_part_c(text, duration, panels)
        elif part == "D":
            result = evaluate_part_d(
                text,
                duration,
                str(data.get("topic", "")),
            )
        else:
            return jsonify({"error": f"不明なパート: {part}"}), 400

        return jsonify(result)

    except openai.AuthenticationError:
        logger.error("OpenAI auth error")
        return jsonify({"error": "OpenAI APIキーが正しく設定されていません。"}), 500
    except openai.RateLimitError:
        logger.warning("OpenAI rate limit")
        return jsonify({"error": "APIの使用制限に達しました。少し待ってから再試行してください。"}), 429
    except Exception as exc:
        logger.exception("Evaluation failed: %s", exc)
        return jsonify({"error": f"採点エラーが発生しました: {exc}"}), 500
