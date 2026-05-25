import logging

from flask import Blueprint, jsonify, session

from app.config import Config
from app.services.history_service import HistoryService

logger = logging.getLogger(__name__)

statistics_bp = Blueprint("statistics", __name__)
history_service = HistoryService(history_dir=Config.HISTORY_DIR, max_items=Config.MAX_HISTORY_ITEMS)


@statistics_bp.route("/statistics", methods=["GET"])
def statistics():
    """学習統計を取得"""
    try:
        user_id = session.get("user_id", "anonymous")
        stats = history_service.get_statistics(user_id)
        return jsonify(stats)
    except Exception as exc:
        logger.error("Error in statistics endpoint: %s", exc)
        return jsonify({"error": str(exc)}), 500
