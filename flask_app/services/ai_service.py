import base64
import json
import logging
import os

from openai import OpenAI

from flask_app.config import Config
from flask_app.utils.language_utils import (
    grammar_fallback_tip,
    grammar_system_prompt,
    grammar_user_message,
    lang_id_from_api,
    normalize_grammar_tips,
    normalize_study_lang,
    ocr_system_prompt,
    ocr_user_prompt,
    perfect_grammar_tip,
    pronunciation_reference_label,
    pronunciation_system_prompt,
)
from flask_app.utils.openai_utils import create_json_chat_completion, get_ai_chat_model
from flask_app.utils.text_utils import clean_ocr_text

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self):
        self.client = self._get_client()

    @staticmethod
    def _get_client() -> OpenAI | None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return OpenAI(api_key=api_key)

    def check_grammar(self, text: str, lang_raw: str) -> dict:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        lang = normalize_study_lang(lang_raw)
        lang_id = lang_id_from_api(lang)

        data = create_json_chat_completion(
            self.client,
            get_ai_chat_model(),
            [
                {"role": "system", "content": grammar_system_prompt(lang)},
                {"role": "user", "content": grammar_user_message(text, lang)},
            ],
            temperature=0.2,
        )

        corrected = str(data.get("corrected") or text).strip()
        tips = normalize_grammar_tips(data.get("tips"))
        has_issues = bool(data.get("has_issues", corrected != text))

        if not tips:
            tips = [grammar_fallback_tip(lang) if has_issues else perfect_grammar_tip(lang)]

        tips_english = ""
        if lang_id == "ja":
            tips_english = str(data.get("tips_english") or "").strip()
            if not tips_english and not has_issues:
                tips_english = "No corrections needed. Your Japanese is perfect!"

        detected_lang = str(data.get("detected_lang") or "").strip().lower()
        if detected_lang not in {"en", "es", "ja", "ro"}:
            detected_lang = lang_id

        from flask_app.utils.language_utils import get_ai_mode

        response = {
            "corrected": corrected,
            "tips": tips,
            "has_issues": has_issues,
            "source": text,
            "detected_lang": detected_lang,
            "lang": lang,
            "lang_id": lang_id,
            "active_model": get_ai_chat_model(),
            "ai_mode": get_ai_mode(),
        }
        if tips_english:
            response["tips_english"] = tips_english
        return response

    def extract_text_from_image(self, image_bytes: bytes, mime: str, lang_raw: str) -> dict:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        lang = normalize_study_lang(lang_raw)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

        completion = self.client.chat.completions.create(
            model=Config.OCR_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": ocr_system_prompt(lang)},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ocr_user_prompt(lang)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        extracted = clean_ocr_text(completion.choices[0].message.content or "")
        if not extracted:
            raise ValueError("No text found in image")
        return {"text": extracted, "lang": lang}

    def generate_pronunciation_advice(
        self,
        reference: str,
        spoken: str,
        lang_raw: str,
        accuracy_percent: int | None = None,
    ) -> dict:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        lang = normalize_study_lang(lang_raw)
        user_message = (
            f"{pronunciation_reference_label(lang)}:\n{reference}\n\n"
            f"生徒の音読（STT）:\n{spoken}\n\n"
        )
        if accuracy_percent is not None:
            user_message += f"発音一致率: {accuracy_percent}%\n"

        data = create_json_chat_completion(
            self.client,
            get_ai_chat_model(),
            [
                {"role": "system", "content": pronunciation_system_prompt(lang)},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )

        advice = str(data.get("advice") or "").strip()
        if not advice:
            raise ValueError("Empty advice from pronunciation model")

        lang_id = lang_id_from_api(lang)
        response = {
            "advice": advice,
            "model": get_ai_chat_model(),
            "lang": lang,
            "lang_id": lang_id,
        }
        if lang_id == "ja":
            advice_english = str(data.get("advice_english") or "").strip()
            if advice_english:
                response["advice_english"] = advice_english
        return response

    def generate_feedback(self, expected_text: str, actual_text: str, language_code: str = "ja-JP") -> str:
        """OpenAI による発音フィードバック（Anthropic 未設定時の代替）"""
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        prompt = f"""あなたは発音指導の専門家です。以下の音読結果を分析し、具体的で建設的なフィードバックを日本語で提供してください。

【読むべきテキスト】
{expected_text}

【実際に読まれたテキスト】
{actual_text}

学習言語: {language_code}

フィードバックは300文字以内で、学習者を励ましながらも具体的な改善点を示してください。"""

        completion = self.client.chat.completions.create(
            model=Config.MODEL_ECONOMY,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content or ""

    def generate_practice_text(
        self,
        language_code: str = "ja-JP",
        difficulty: str = "medium",
        topic: str = "general",
    ) -> str:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        prompt = (
            f"Generate a short practice reading passage in language {language_code}. "
            f"Difficulty: {difficulty}. Topic: {topic}. "
            "Return only the passage text, about 50 words."
        )
        completion = self.client.chat.completions.create(
            model=Config.MODEL_ECONOMY,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return (completion.choices[0].message.content or "").strip()
