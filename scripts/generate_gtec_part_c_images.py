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
        "title": "Lost blue umbrella in park",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Panel 1: A student finds a blue umbrella on a park bench. "
            "Panel 2: He brings it to a park office lost-and-found counter. "
            "Panel 3: A staff member makes a found-item announcement. "
            "Panel 4: The owner retrieves the umbrella and thanks the student. "
            "Clean educational manga style, soft colors, consistent characters."
        ),
    },
    3: {
        "title": "Sharing umbrella in rain",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Panel 1: A student waits at a bus stop in the rain without an umbrella. "
            "Panel 2: A classmate arrives with an umbrella and offers to share. "
            "Panel 3: They walk to school together under one umbrella in the rain. "
            "Panel 4: They arrive at school smiling. "
            "Clean educational manga style, soft colors, consistent characters."
        ),
    },
    4: {
        "title": "Sharing lunch",
        "prompt": (
            "Create a single horizontal 4-panel comic strip for a Japanese high school English test. "
            "Panel 1: A student realizes he forgot his lunchbox and looks worried. "
            "Panel 2: He sits alone in the school cafeteria looking sad. "
            "Panel 3: A friend offers to share her lunch. "
            "Panel 4: They eat lunch together happily in the cafeteria. "
            "Clean educational manga style, soft colors, consistent characters."
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
