"""やわらかい2〜3音のベル風チャイムを WAV として生成する。"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "toolbox" / "sounds" / "timer_end.wav"
SAMPLE_RATE = 44100
DURATION = 2.0


def _tone(freq: float, t: float, attack: float = 0.02) -> float:
    env = min(1.0, t / attack) * math.exp(-2.6 * t)
    wave_sum = (
        math.sin(2 * math.pi * freq * t)
        + 0.35 * math.sin(2 * math.pi * freq * 2 * t)
        + 0.12 * math.sin(2 * math.pi * freq * 3 * t)
    )
    return env * wave_sum


def generate(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(SAMPLE_RATE * DURATION)
    notes = [(659.25, 0.0), (783.99, 0.18), (987.77, 0.38)]
    frames = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        sample = 0.0
        for freq, start in notes:
            if t >= start:
                sample += _tone(freq, t - start)
        sample = max(-1.0, min(1.0, sample * 0.22))
        frames.append(struct.pack("<h", int(sample * 32767)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(frames))
    return path


if __name__ == "__main__":
    out = generate()
    print(f"wrote {out}")
