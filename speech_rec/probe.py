"""音声ファイルを Whisper に送り、単語時刻と間の指標を表示する。

使い方: python -m speech_rec.probe <音声ファイル>
"""
from __future__ import annotations

import sys
from pathlib import Path

from speech_rec.jobs import WHISPER_HINT, _parse
from speech_rec.metrics import measure
from speech_rec.openai_client import transcribe_words
from speech_rec.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("使い方: python -m speech_rec.probe <音声ファイル>", file=sys.stderr)
        return 2
    settings = get_settings()
    prompt = WHISPER_HINT if settings.get("whisper_hint") else ""
    result = transcribe_words(Path(args[0]), language="en", prompt=prompt)
    text, words, duration = _parse(result)
    row = measure(
        words,
        speak_sec=60,
        grace_sec=float(settings["score_config"].get("grace_sec") or 3),
        pause_gap_sec=float(settings.get("pause_gap_sec") or 0.8),
        exclude_fillers=bool(settings["score_config"].get("exclude_nonlexical_fillers", True)),
    )
    print(f"duration_sec={duration}")
    print(
        f"words_counted={row['words_counted']} pause_n={row['pause_n']} "
        f"pause_max={row['pause_max']} silent_ratio={row['silent_ratio']}"
    )
    for word, start, end in words:
        print(f"{start:7.2f}-{end:7.2f}  {word}")
    print("---")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
