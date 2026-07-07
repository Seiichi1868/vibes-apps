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

logger = logging.getLogger(__name__)

gtec_bp = Blueprint("gtec", __name__)


@gtec_bp.route("/gtec")
def index():
    return render_template("gtec/index.html")


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
