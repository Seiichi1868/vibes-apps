"""Whisper API（OpenAI）による音声文字起こし。

スペイン語（tú形の短文）以外は受け付けない。
language="es" に加え、プロンプトエコーの除去と非ラテン文字の再試行で
誤認識を抑える。

Whisper の prompt は「直前の文字起こし」として扱われるため、
例文を入れると短い発話でその例文自体が返ることがある。
"""
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

# 指示だけ。例文は入れない（短い音声でエコーされるため）
SPANISH_PROMPT = "Transcripción en español."
SPANISH_RETRY_PROMPT = "Idioma: español."

# 過去のプロンプト例文。本番でエコーされていたため除去対象に残す
_PROMPT_ECHO_PHRASES = (
    "puedes",
    "hablas",
    "estas comiendo",
    "vas a estudiar",
    "te gusta el cafe",
    "pudiste",
    "estas vendiendo",
    "vas a poder",
    "tu puedes",
    "tu hablas",
    "transcripcion en espanol",
    "idioma espanol",
    "espanol solamente",
    "transcribe solo espanol",
    "frases cortas en forma de tu",
)

# アラビア語・ヘブライ語・キリル・日中韓など、スペイン語に現れない文字
_NON_SPANISH_SCRIPT = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0870-\u089F"
    r"\u0590-\u05FF"
    r"\u0400-\u04FF"
    r"\u3040-\u30FF\u31F0-\u31FF"
    r"\u4E00-\u9FFF"
    r"\uAC00-\uD7AF]"
)
_ACCENT_MAP = str.maketrans(
    "áéíóúÁÉÍÓÚñÑ",
    "aeiouAEIOUnN",
)


def _get_client():
    from openai import OpenAI

    from conjugate.config import WHISPER_MAX_RETRIES, WHISPER_TIMEOUT_SEC, get_openai_api_key

    api_key = get_openai_api_key()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=WHISPER_TIMEOUT_SEC, max_retries=WHISPER_MAX_RETRIES)


def _is_non_spanish_script(text: str) -> bool:
    if not text:
        return False
    hits = _NON_SPANISH_SCRIPT.findall(text)
    if not hits:
        return False
    return len(hits) >= 2 or (len(hits) / max(1, len(text)) >= 0.15)


def _norm_for_echo(text: str) -> str:
    s = unicodedata.normalize("NFC", text or "").strip().lower()
    s = s.translate(_ACCENT_MAP)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


_PROMPT_ECHO_NORMS = tuple(_norm_for_echo(p) for p in _PROMPT_ECHO_PHRASES if _norm_for_echo(p))


def _sentence_chunks(text: str) -> list[str]:
    parts = re.split(r"[.!?¡¿;:]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _is_echo_sentence(sentence: str) -> bool:
    norm = _norm_for_echo(sentence)
    return bool(norm) and norm in _PROMPT_ECHO_NORMS


def looks_like_prompt_echo(text: str) -> bool:
    """短い発話なのにプロンプト例文が複数つながった結果かどうか。"""
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _norm_for_echo(raw)
    hits = sum(1 for phrase in _PROMPT_ECHO_NORMS if phrase and phrase in norm)
    if hits >= 3:
        return True
    chunks = _sentence_chunks(raw)
    echo_count = sum(1 for chunk in chunks if _is_echo_sentence(chunk))
    return echo_count >= 2


def strip_prompt_echo(text: str) -> str:
    """プロンプト由来の例文が混ざっていれば取り除き、実際の発話だけ残す。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    if not looks_like_prompt_echo(raw):
        return raw
    kept = [chunk for chunk in _sentence_chunks(raw) if not _is_echo_sentence(chunk)]
    if not kept:
        return ""
    return ". ".join(kept)


def keep_spanish_transcript(text: str) -> str:
    """Web Speech 等の結果からも、スペイン語以外の文字起こしを落とす。"""
    cleaned = (text or "").strip()
    if _is_non_spanish_script(cleaned):
        return ""
    return cleaned


def sanitize_transcript(text: str) -> str:
    return strip_prompt_echo(keep_spanish_transcript(text))


def glossary_sentences(question: dict, target: str) -> list[str]:
    """この問題の活用形だけを並べた短い用語集。正解文そのものはプロンプトにしない。"""
    sentences: list[str] = []
    if question.get("kind") == "gustar":
        keys = ("yo_sentence", "tu_sentence", "el_ella_usted_sentence")
        raw_items = [question.get(key) for key in keys]
    else:
        infinitive = (question.get("infinitive") or "").strip()
        forms = (question.get("forms") or {}).get(target) or {}
        raw_items = [infinitive, forms.get("yo"), forms.get("tu"), forms.get("el_ella_usted")]
    for raw in raw_items:
        text = (raw or "").strip().rstrip(".")
        if text and text not in sentences:
            sentences.append(text)
    return sentences


def _contains_phrase(norm_text: str, norm_phrase: str) -> bool:
    if not norm_phrase:
        return False
    return f" {norm_phrase} " in f" {norm_text} "


def looks_like_glossary_echo(text: str, glossary: list[str]) -> bool:
    """用語集の文が2つ以上そのまま返ってきたら、無音時のエコーとみなす。"""
    norm = _norm_for_echo(text)
    if not norm:
        return False
    hits = 0
    for sentence in glossary:
        phrase = _norm_for_echo(sentence)
        if len(phrase) >= 3 and _contains_phrase(norm, phrase):
            hits += 1
    return hits >= 2


def _transcribe_once(client, file_path: Path, model: str, prompt: str) -> str:
    kwargs = {
        "model": model,
        "language": "es",
    }
    if prompt:
        kwargs["prompt"] = prompt
    if model == "whisper-1":
        kwargs["temperature"] = 0
    with open(file_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(file=audio_file, **kwargs)
    return (getattr(result, "text", "") or "").strip()


def transcribe_audio(
    file_path: Path,
    model: str = "whisper-1",
    language: str = "es",
    glossary: list[str] | None = None,
) -> str:
    del language  # 常にスペイン語。呼び出し側の上書きは受け付けない。
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEYが設定されていないため、文字起こしできません。")

    terms = [item for item in (glossary or []) if (item or "").strip()]
    prompt = ". ".join(terms) + "." if len(terms) >= 2 else SPANISH_PROMPT
    raw = _transcribe_once(client, file_path, model, prompt)
    if _is_non_spanish_script(raw):
        logger.warning("Non-Spanish script detected, retrying as Spanish-only: %s", raw[:80])
        raw = _transcribe_once(client, file_path, model, SPANISH_RETRY_PROMPT)
        if _is_non_spanish_script(raw):
            logger.warning("Retry still non-Spanish; dropping transcript: %s", raw[:80])
            return ""

    if terms and looks_like_glossary_echo(raw, terms):
        logger.warning("Glossary echo detected, retrying without prompt: %s", raw[:80])
        raw = _transcribe_once(client, file_path, model, "")
        if _is_non_spanish_script(raw) or looks_like_glossary_echo(raw, terms):
            return ""

    text = sanitize_transcript(raw)
    if looks_like_prompt_echo(raw) or not text:
        logger.warning("Prompt-like transcript detected, retrying without examples: %s", raw[:80])
        retry_raw = _transcribe_once(client, file_path, model, "")
        if terms and looks_like_glossary_echo(retry_raw, terms):
            return ""
        retry_text = sanitize_transcript(retry_raw)
        if retry_text:
            return retry_text
        if _is_non_spanish_script(retry_raw):
            return ""
    return text
