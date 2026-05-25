from app.api.admin import admin_bp
from app.api.gate import gate_bp
from app.api.grammar import grammar_bp
from app.api.languages import languages_bp
from app.api.ocr import ocr_bp
from app.api.practice import practice_bp
from app.api.statistics import statistics_bp
from app.api.transcription import transcription_bp
from app.api.tts import tts_bp

__all__ = [
    "admin_bp",
    "gate_bp",
    "grammar_bp",
    "ocr_bp",
    "transcription_bp",
    "tts_bp",
    "practice_bp",
    "statistics_bp",
    "languages_bp",
]
