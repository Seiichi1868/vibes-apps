"""tú形から él/ella/usted形を自動導出する。

スペイン語の直説法現在形では、ほぼ全ての動詞で tú形の末尾の "s" を
1文字取れば él/ella/usted形になる。再帰動詞は代名詞 te→se も同時に置換する。

進行形（estás→está）・近接未来（vas→va）も同じ規則が使える。
点過去は tú形が -ste で終わるため s 除去では導出できず、
既存の pret_yo / pret_tu から文法規則で変換する。
"""

PERSON_IDS = ("tu", "el_ella_usted")
PERSON_MODES = ("tu", "el_ella_usted", "mix")
DEFAULT_PERSON_MODE = "tu"
DEFAULT_PERSON_FILTER = "all"

PERSON_MODE_LABELS = {
    "tu": "tú形のみ（既定）",
    "el_ella_usted": "él/ella/usted形のみ",
    "mix": "ミックス（ランダム）",
}

PERSON_BADGE_LABELS = {
    "tu": "tú",
    "el_ella_usted": "él/ella/usted",
}

PERSON_FILTER_LABELS = {
    "all": "すべて（ミックス）",
    "tu": "tú形だけ復習",
    "el_ella_usted": "él/ella/usted形だけ復習",
}

EL_ELLA_USTED_HINT = (
    "スペイン語では、彼・彼女・あなた（丁寧形）のいずれでも"
    "3人称単数の活用形は同じです。"
)


def tu_form_to_el(tu_form: str) -> str:
    """tú形の文字列から él/ella/usted形を返す。

    例: hablas→habla, vienes→viene, estás→está,
        te quedas→se queda, te sientes→se siente
    """
    text = (tu_form or "").strip()
    if not text:
        return text

    lower = text.lower()
    if lower.startswith("te "):
        rest = text[3:]
        prefix = "Se " if text[:1].isupper() else "se "
        text = prefix + rest
        lower = text.lower()

    # ser: eres → es（末尾 s 除去だと ere になる）
    if lower == "eres":
        return "Es" if text[:1].isupper() else "es"

    if text.endswith("s") or text.endswith("S"):
        text = text[:-1]
    return text


def tu_sentence_to_el(sentence: str) -> str:
    """tú形の完全文から él/ella/usted形の完全文を返す。

    進行形・近接未来・再帰の後置代名詞（-te → -se）にも対応する。
    """
    raw = (sentence or "").strip()
    if not raw:
        return raw
    ending = ""
    if raw.endswith("."):
        ending = "."
        raw = raw[:-1]

    tokens = raw.split()
    converted = [_token_tu_to_el(tok) for tok in tokens]
    text = " ".join(converted) + ending
    if text[:1].islower():
        text = text[:1].upper() + text[1:]
    return text


def _token_tu_to_el(token: str) -> str:
    lower = token.lower()
    if lower == "te":
        return "Se" if token[:1].isupper() else "se"
    if lower == "eres":
        return "Es" if token[:1].isupper() else "es"
    if lower.endswith("te") and len(lower) > 2:
        stem = token[:-2]
        se = "Se" if token[-2:-1].isupper() else "se"
        return stem + se
    if token.endswith("s") or token.endswith("S"):
        return token[:-1]
    return token


def pret_tu_to_el(pret_tu: str, pret_yo: str, stem_change: str | None, infinitive: str) -> str:
    """点過去の tú形（と yo形）から él/ella/usted形を返す。

    -ar 規則動詞は -aste → -ó（yo形の c/z・gu/g・qu/c 表記ゆれを回避できる）。
    -er/-ir と不規則は yo形の語尾規則で変換する。
    """
    tu = (pret_tu or "").strip()
    yo = (pret_yo or "").strip()
    if tu.endswith("aste"):
        return tu[:-4] + "ó"

    if yo == "fui":
        return "fue"
    if yo == "hice":
        return "hizo"
    if yo in ("vi", "di"):
        return yo + "o"
    if yo.endswith("aí"):
        return yo[:-2] + "ayó"
    if yo.endswith("eí") or yo.endswith("oí"):
        return yo[:-2] + "eyó" if yo.endswith("eí") else yo[:-2] + "oyó"
    if yo.endswith("e") and not yo.endswith("é"):
        return yo[:-1] + "o"
    if yo.endswith("í"):
        stem = yo[:-1]
        bare = infinitive[:-2] if infinitive.endswith("se") else infinitive
        if bare.endswith("ir"):
            change = stem_change or ""
            if change in ("e>i", "e>ie"):
                stem = _replace_last_vowel(stem, "e", "i")
            elif change in ("o>ue", "o>u"):
                stem = _replace_last_vowel(stem, "o", "u")
        return stem + "ió"
    if yo.endswith("é"):
        return yo[:-1] + "ó"
    return tu_form_to_el(tu)


def _replace_last_vowel(text: str, old: str, new: str) -> str:
    idx = text.rfind(old)
    if idx < 0:
        return text
    return text[:idx] + new + text[idx + len(old) :]


def resolve_person(person_mode: str | None, person_filter: str | None) -> str:
    """管理画面の人称モードと、ミックス時の生徒フィルターから出題人称を1つ決める。"""
    mode = person_mode if person_mode in PERSON_MODES else DEFAULT_PERSON_MODE
    filt = person_filter if person_filter in ("tu", "el_ella_usted", "all") else DEFAULT_PERSON_FILTER
    if mode == "mix":
        if filt in PERSON_IDS:
            return filt
        return "mix"
    return mode


def person_badge_text(*, tu_mastered: bool, el_mastered: bool, threshold: int, tu_count: int, el_count: int) -> str:
    """tú と él の連続カウントを、それぞれ独立した習得状況として返す。"""

    def side(label: str, mastered: bool, count: int) -> str:
        if mastered:
            return f"{label}✓"
        return f"{label} {count}/{threshold}"

    return (
        f"{side('tú', tu_mastered, tu_count)} / "
        f"{side('él', el_mastered, el_count)}"
    )
