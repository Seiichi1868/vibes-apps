"""アップロード音声・動画を Whisper 向けに正規化する（news_app 独自実装）。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ffmpeg_ready = False


def _ensure_ffmpeg() -> bool:
    """pydub が ffmpeg を使えるようにする。システムに無ければ imageio-ffmpeg を使う。"""
    global _ffmpeg_ready
    if _ffmpeg_ready:
        return True
    try:
        from pydub import AudioSegment
        from pydub.utils import which
    except Exception as exc:  # noqa: BLE001
        logger.warning("pydub unavailable: %s", exc)
        return False

    if which("ffmpeg"):
        _ffmpeg_ready = True
        return True
    try:
        import imageio_ffmpeg

        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffmpeg = ffmpeg_path
        _ffmpeg_ready = True
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffmpeg not available for news transcription: %s", exc)
        return False


def audio_duration_sec(path: Path) -> float | None:
    if not _ensure_ffmpeg():
        return None
    try:
        from pydub import AudioSegment

        return max(0.0, len(AudioSegment.from_file(path)) / 1000.0)
    except Exception:  # noqa: BLE001
        return None


def prepare_for_whisper(src_path: Path, max_seconds: int) -> Path:
    """可能なら 16kHz モノラル MP3 に変換する。失敗時は元ファイルを返す。"""
    if not _ensure_ffmpeg():
        return src_path
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(src_path)
        duration_sec = len(audio) / 1000.0
        if duration_sec > max_seconds:
            logger.info(
                "trimming upload audio from %.1fs to %ds for whisper",
                duration_sec,
                max_seconds,
            )
            audio = audio[: max_seconds * 1000]
        audio = audio.set_channels(1).set_frame_rate(16000)
        out_path = src_path.with_suffix(".whisper.mp3")
        audio.export(out_path, format="mp3", bitrate="64k")
        return out_path
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("news audio convert skipped (%s): %s", src_path.name, exc)
        return src_path
