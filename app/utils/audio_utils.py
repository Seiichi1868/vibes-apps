import hashlib
import logging

from pydub import AudioSegment

logger = logging.getLogger(__name__)


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def convert_to_wav(input_path: str, output_path: str) -> bool:
    """音声ファイルをWAV形式に変換"""
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(16000)
        audio.export(output_path, format="wav")
        logger.info("Successfully converted %s to %s", input_path, output_path)
        return True
    except Exception as exc:
        logger.error("Error converting audio file: %s", exc)
        return False


def cache_key_for_text(text: str, lang: str, voice: str) -> str:
    digest = hashlib.sha256(f"{lang}\n{voice}\n{text}".encode("utf-8")).hexdigest()
    return digest[:32]
