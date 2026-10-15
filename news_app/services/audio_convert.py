"""アップロード音声・動画を Whisper 向けに正規化する（news_app 独自実装）。"""
from __future__ import annotations

import array
import logging
import shutil
import subprocess
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

_ffmpeg_ready = False
_MIN_AUDIBLE_RMS = 40


def _ffmpeg_exe() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffmpeg not available for news transcription: %s", exc)
        return None


def _ensure_ffmpeg() -> bool:
    """pydub が ffmpeg を使えるようにする。システムに無ければ imageio-ffmpeg を使う。"""
    global _ffmpeg_ready
    if _ffmpeg_ready:
        return True
    exe = _ffmpeg_exe()
    if not exe:
        return False
    try:
        from pydub import AudioSegment

        AudioSegment.converter = exe
        AudioSegment.ffmpeg = exe
        _ffmpeg_ready = True
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("pydub unavailable: %s", exc)
        return False


def audio_duration_sec(path: Path) -> float | None:
    wav_duration = _wav_duration_sec(path)
    if wav_duration is not None:
        return wav_duration
    if not _ensure_ffmpeg():
        return None
    try:
        from pydub import AudioSegment

        return max(0.0, len(AudioSegment.from_file(path)) / 1000.0)
    except Exception:  # noqa: BLE001
        return None


def _wav_duration_sec(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate() or 0
            if rate <= 0:
                return None
            return handle.getnframes() / float(rate)
    except Exception:  # noqa: BLE001
        return None


def _wav_rms(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
                return 0.0
            pending = handle.getnframes()
            total = 0
            count = 0
            while pending > 0:
                chunk = handle.readframes(min(pending, 16000))
                pending -= len(chunk) // 2
                samples = array.array("h")
                samples.frombytes(chunk)
                if not samples:
                    continue
                total += sum(sample * sample for sample in samples)
                count += len(samples)
            if count <= 0:
                return 0.0
            return (total / count) ** 0.5
    except Exception:  # noqa: BLE001
        return 0.0


def _extract_wav(src_path: Path, dest: Path, max_seconds: int, *, ignore_editlist: bool) -> None:
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is unavailable")
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error"]
    if ignore_editlist:
        # iPhone の MOV/MP4 は edit list で音声が先頭数秒に切られることがある。
        cmd.extend(["-ignore_editlist", "1"])
    cmd.extend(
        [
            "-i",
            str(src_path),
            "-vn",
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            str(max_seconds),
            "-c:a",
            "pcm_s16le",
            str(dest),
        ]
    )
    subprocess.run(cmd, check=True, capture_output=True, timeout=max(90, max_seconds * 2))


def _extract_with_pydub(src_path: Path, max_seconds: int) -> Path | None:
    if not _ensure_ffmpeg():
        return None
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(src_path)
        if len(audio) > max_seconds * 1000:
            audio = audio[: max_seconds * 1000]
        audio = audio.set_channels(1).set_frame_rate(16000)
        out_path = src_path.with_suffix(".whisper.wav")
        audio.export(out_path, format="wav")
        return out_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("pydub extract skipped (%s): %s", src_path.name, exc)
        return None


def prepare_for_whisper(src_path: Path, max_seconds: int) -> Path:
    """16kHz モノラル WAV にする。iPhone 動画は edit list を無視して全長を取る。"""
    candidates: list[tuple[float, float, Path]] = []
    for ignore_editlist in (True, False):
        dest = src_path.with_name(f"whisper-edit{int(ignore_editlist)}.wav")
        try:
            _extract_wav(src_path, dest, max_seconds, ignore_editlist=ignore_editlist)
        except Exception as exc:  # noqa: BLE001
            logger.info("ffmpeg extract failed (ignore_editlist=%s): %s", ignore_editlist, exc)
            continue
        duration = _wav_duration_sec(dest) or 0.0
        rms = _wav_rms(dest)
        logger.info(
            "extracted upload audio ignore_editlist=%s duration=%.1fs rms=%.0f",
            ignore_editlist,
            duration,
            rms,
        )
        candidates.append((duration, rms, dest))

    audible = [item for item in candidates if item[0] >= 0.4 and item[1] >= _MIN_AUDIBLE_RMS]
    pool = audible or candidates
    if pool:
        duration, rms, path = max(pool, key=lambda item: (item[0], item[1]))
        if duration >= 0.4 and rms >= _MIN_AUDIBLE_RMS:
            return path
        if duration >= 0.4 and not audible:
            fallback = _extract_with_pydub(src_path, max_seconds)
            if fallback is not None:
                fb_duration = _wav_duration_sec(fallback) or 0.0
                fb_rms = _wav_rms(fallback)
                if fb_duration > duration and fb_rms >= _MIN_AUDIBLE_RMS:
                    return fallback
            raise ValueError(
                "動画から音声を読み取れませんでした。カメラのマイクがオンの録画か、ボイスメモを選んでください。"
            )

    fallback = _extract_with_pydub(src_path, max_seconds)
    if fallback is not None and (_wav_duration_sec(fallback) or 0) >= 0.4:
        return fallback
    logger.warning("news audio convert skipped (%s)", src_path.name)
    return src_path
