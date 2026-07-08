#!/usr/bin/env python3
"""GTEC Part C 4コマ漫画イラスト生成スクリプト（Gemini API）。

使い方:
  export GEMINI_API_KEY="your-api-key"
  python scripts/generate_gtec_part_c_images.py
  python scripts/generate_gtec_part_c_images.py --only 2 3

出力先:
  static/gtec/images/part-c-story-1.png 〜 part-c-story-4.png

問題1は既存イラストがある場合はスキップされます（--force で上書き）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "gtec" / "images"

STORIES = {
    1: {
        "title": "Lost pink purse",
        "prompt": (
            "Create a single horizontal 4-panel comic strip image for a Japanese high school "
            "English speaking test (GTEC style). Clean line art, soft colors, no speech text "
            "inside panels except minimal Japanese labels if needed. "
            "Panel 1: A male student in school uniform finds a pink clasp purse on the ground "
            "near a school gate. "
            "Panel 2: He brings the purse to the school staff room (職員室 sign). "
            "Panel 3: A female teacher in the staff room calls the owner on a desk phone. "
            "Panel 4: The owner, an older woman, thanks the student and receives the purse. "
            "Consistent characters across panels. White borders between panels."
        ),
    },
    2: {
        "title": "Birthday cake for mother",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Clean educational manga style, soft colors, consistent characters, white panel borders. "
            "Panel 1: A male student in casual clothes at home reads a recipe book, planning a birthday cake. "
            "Panel 2: He measures flour and eggs and mixes batter in a kitchen bowl. "
            "Panel 3: He takes a baked cake from the oven and decorates it with cream and strawberries. "
            "Panel 4: His mother blows out birthday candles on the cake and hugs him happily. "
            "Warm family atmosphere, NOT a lost-and-found story."
        ),
    },
    3: {
        "title": "Tree planting volunteer",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Clean educational manga style, soft colors, consistent characters, white panel borders. "
            "Panel 1: High school students wearing gloves gather at a city park for a tree-planting event. "
            "Panel 2: They dig holes and plant young saplings together. "
            "Panel 3: They water the new trees with watering cans. "
            "Panel 4: The students smile proudly in front of the newly planted trees. "
            "Outdoor volunteer activity, NOT a lost item or food-sharing story."
        ),
    },
    4: {
        "title": "Transfer student finds classroom",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Clean educational manga style, soft colors, consistent characters, white panel borders. "
            "Panel 1: A new male transfer student in school uniform stands in a hallway holding a schedule, looking confused. "
            "Panel 2: He politely asks a female teacher for directions to Room 302. "
            "Panel 3: The teacher smiles and points down the school corridor. "
            "Panel 4: He enters a classroom, bows, and introduces himself to classmates. "
            "First-day-at-school story, NOT a lost item or weather story."
        ),
    },
}


def generate_with_gemini(prompt: str, api_key: str) -> bytes:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise SystemExit(
            "google-genai が必要です: pip install google-genai\n" + str(exc)
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data

    raise RuntimeError("Gemini response did not include image data")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GTEC Part C story images via Gemini")
    parser.add_argument("--only", nargs="+", type=int, choices=[1, 2, 3, 4], help="Generate only these problem numbers")
    parser.add_argument("--force", action="store_true", help="Overwrite existing images")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts only")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: GEMINI_API_KEY または GOOGLE_API_KEY を設定してください。", file=sys.stderr)
        return 1

    targets = args.only or [1, 2, 3, 4]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for num in targets:
        out_path = OUT_DIR / f"part-c-story-{num}.png"
        story = STORIES[num]
        print(f"\n=== 問題{num}: {story['title']} ===")
        print(f"Output: {out_path}")

        if out_path.exists() and not args.force:
            print("Skip (already exists). Use --force to overwrite.")
            continue

        if args.dry_run:
            print(story["prompt"])
            continue

        try:
            image_bytes = generate_with_gemini(story["prompt"], api_key)
            out_path.write_bytes(image_bytes)
            print(f"Saved: {out_path} ({len(image_bytes)} bytes)")
        except Exception as exc:
            print(f"Failed problem {num}: {exc}", file=sys.stderr)
        time.sleep(2)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
