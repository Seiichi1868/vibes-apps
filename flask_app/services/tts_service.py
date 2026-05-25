import logging
import os

from openai import OpenAI

from flask_app.config import Config
from flask_app.state import TTS_GENERATE_VOICE_BY_LANG, TTS_VOICE_BY_LANG
from flask_app.utils.audio_utils import cache_key_for_text

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.client = self._get_client()
        self.cache_dir = Config.AUDIO_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_client() -> OpenAI | None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return OpenAI(api_key=api_key)

    def synthesize(self, text: str, lang: str, voice: str) -> bytes:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        speech = self.client.audio.speech.create(
            model=Config.TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        return speech.read()

    def resolve_audio(self, text: str, lang: str, voice: str) -> tuple[str, bool]:
        cache_name = f"{cache_key_for_text(text, lang, voice)}.mp3"
        cache_path = self.cache_dir / cache_name
        if cache_path.is_file():
            return f"/static/audio/{cache_name}", True

        audio_bytes = self.synthesize(text, lang, voice)
        cache_path.write_bytes(audio_bytes)
        return f"/static/audio/{cache_name}", False

    def voice_for_lang(self, lang: str, *, generate: bool = False) -> str:
        mapping = TTS_GENERATE_VOICE_BY_LANG if generate else TTS_VOICE_BY_LANG
        return mapping.get(lang, mapping[Config.TTS_DEFAULT_LANG])

    def generate_audio(self, text: str, language_code: str = "ja-JP", output_path: str | None = None):
        """テキストから音声を生成（OpenAI TTS）"""
        voice = self.voice_for_lang(language_code, generate=True)
        audio_bytes = self.synthesize(text, language_code, voice)
        if output_path:
            with open(output_path, "wb") as out:
                out.write(audio_bytes)
            return output_path
        return audio_bytes
