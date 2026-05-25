from flask import Blueprint, jsonify

from flask_app.utils.language_utils import languages_response

languages_bp = Blueprint("languages", __name__)


@languages_bp.route("/languages", methods=["GET"])
def get_languages():
    """サポートされている学習言語のリストを返す"""
    data = languages_response()
    return jsonify(data["languages"])
