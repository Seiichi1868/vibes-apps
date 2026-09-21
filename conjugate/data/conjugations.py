"""5文型（現在形／進行形／近接未来／点過去／線過去）の yo形・tú形・él/ella/usted形 文生成。

`tu_present` は verbs.py に既に格納されているため、残りの文型に必要な
「現在分詞（gerundio）」「点過去（yo/tú）」の語幹を動詞ごとに手動で保持する。
線過去は不規則が ir / ser / ver の3語だけなので、原形から規則的に生成する。

不規則活用・語幹変化はスペイン語文法上、人称・時制ごとに現れ方が異なるため
（例: sentir の現在形は e>ie だが現在分詞は e>i、poder は -er 動詞だが
現在分詞が pudiendo になる、など）、自動生成ではなく検証済みの値を
直接テーブル化することで正確性を優先している。

各エントリの値は「素の活用形」（代名詞・大文字化・句点なし）。
再帰動詞の me/te は build_forms() が一括で付与する。
"""
from conjugate.data.persons import pret_tu_to_el, tu_form_to_el
from conjugate.data.verbs import drillable_verbs

TENSE_LABELS = {
    "present": "現在形",
    "progressive": "進行形",
    "near_future": "近接未来形",
    "preterite": "点過去形",
    "imperfect": "線過去形",
}

TENSE_LABELS_ES = {
    "present": "presente",
    "progressive": "estar + gerundio",
    "near_future": "ir a + infinitivo",
    "preterite": "pretérito indefinido",
    "imperfect": "pretérito imperfecto",
}

TENSE_ORDER = ["present", "progressive", "near_future", "preterite", "imperfect"]

# id -> (yo_present_base, gerundio_base, pret_yo_base, pret_tu_base)
CONJ_EXTRA: dict[int, tuple[str, str, str, str]] = {
    1: ("voy", "yendo", "fui", "fuiste"),
    2: ("vengo", "viniendo", "vine", "viniste"),
    3: ("salgo", "saliendo", "salí", "saliste"),
    4: ("entro", "entrando", "entré", "entraste"),
    5: ("llego", "llegando", "llegué", "llegaste"),
    6: ("camino", "caminando", "caminé", "caminaste"),
    7: ("corro", "corriendo", "corrí", "corriste"),
    8: ("paso", "pasando", "pasé", "pasaste"),
    9: ("quedo", "quedando", "quedé", "quedaste"),
    10: ("subo", "subiendo", "subí", "subiste"),
    11: ("bajo", "bajando", "bajé", "bajaste"),
    12: ("siento", "sentando", "senté", "sentaste"),
    13: ("paro", "parando", "paré", "paraste"),
    14: ("sigo", "siguiendo", "seguí", "seguiste"),
    15: ("empiezo", "empezando", "empecé", "empezaste"),
    16: ("vuelvo", "volviendo", "volví", "volviste"),
    17: ("dejo", "dejando", "dejé", "dejaste"),
    18: ("caigo", "cayendo", "caí", "caíste"),
    19: ("llevo", "llevando", "llevé", "llevaste"),
    20: ("traigo", "trayendo", "traje", "trajiste"),
    21: ("escribo", "escribiendo", "escribí", "escribiste"),
    22: ("leo", "leyendo", "leí", "leíste"),
    23: ("abro", "abriendo", "abrí", "abriste"),
    24: ("cierro", "cerrando", "cerré", "cerraste"),
    25: ("corto", "cortando", "corté", "cortaste"),
    26: ("estoy", "estando", "estuve", "estuviste"),
    27: ("parezco", "pareciendo", "parecí", "pareciste"),
    28: ("siento", "sintiendo", "sentí", "sentiste"),
    30: ("quiero", "queriendo", "quise", "quisiste"),
    31: ("amo", "amando", "amé", "amaste"),
    32: ("odio", "odiando", "odié", "odiaste"),
    33: ("disfruto", "disfrutando", "disfruté", "disfrutaste"),
    34: ("prefiero", "prefiriendo", "preferí", "preferiste"),
    35: ("necesito", "necesitando", "necesité", "necesitaste"),
    36: ("deseo", "deseando", "deseé", "deseaste"),
    37: ("espero", "esperando", "esperé", "esperaste"),
    38: ("creo", "creyendo", "creí", "creíste"),
    39: ("pienso", "pensando", "pensé", "pensaste"),
    40: ("recuerdo", "recordando", "recordé", "recordaste"),
    41: ("olvido", "olvidando", "olvidé", "olvidaste"),
    42: ("siento", "sintiendo", "sentí", "sentiste"),
    43: ("preocupo", "preocupando", "preocupé", "preocupaste"),
    44: ("alegro", "alegrando", "alegré", "alegraste"),
    45: ("enojo", "enojando", "enojé", "enojaste"),
    46: ("canso", "cansando", "cansé", "cansaste"),
    47: ("enfermo", "enfermando", "enfermé", "enfermaste"),
    48: ("mejoro", "mejorando", "mejoré", "mejoraste"),
    49: ("empeoro", "empeorando", "empeoré", "empeoraste"),
    50: ("aburro", "aburriendo", "aburrí", "aburriste"),
    51: ("hablo", "hablando", "hablé", "hablaste"),
    52: ("digo", "diciendo", "dije", "dijiste"),
    53: ("pregunto", "preguntando", "pregunté", "preguntaste"),
    54: ("respondo", "respondiendo", "respondí", "respondiste"),
    55: ("escucho", "escuchando", "escuché", "escuchaste"),
    56: ("explico", "explicando", "expliqué", "explicaste"),
    57: ("pido", "pidiendo", "pedí", "pediste"),
    58: ("cuento", "contando", "conté", "contaste"),
    59: ("llamo", "llamando", "llamé", "llamaste"),
    60: ("grito", "gritando", "grité", "gritaste"),
    61: ("susurro", "susurrando", "susurré", "susurraste"),
    62: ("saludo", "saludando", "saludé", "saludaste"),
    63: ("discuto", "discutiendo", "discutí", "discutiste"),
    64: ("argumento", "argumentando", "argumenté", "argumentaste"),
    65: ("comunico", "comunicando", "comuniqué", "comunicaste"),
    66: ("informo", "informando", "informé", "informaste"),
    67: ("describo", "describiendo", "describí", "describiste"),
    68: ("anuncio", "anunciando", "anuncié", "anunciaste"),
    69: ("declaro", "declarando", "declaré", "declaraste"),
    70: ("afirmo", "afirmando", "afirmé", "afirmaste"),
    71: ("niego", "negando", "negué", "negaste"),
    72: ("acepto", "aceptando", "acepté", "aceptaste"),
    73: ("rechazo", "rechazando", "rechacé", "rechazaste"),
    74: ("prometo", "prometiendo", "prometí", "prometiste"),
    75: ("agradezco", "agradeciendo", "agradecí", "agradeciste"),
    76: ("como", "comiendo", "comí", "comiste"),
    77: ("bebo", "bebiendo", "bebí", "bebiste"),
    78: ("duermo", "durmiendo", "dormí", "dormiste"),
    79: ("juego", "jugando", "jugué", "jugaste"),
    80: ("trabajo", "trabajando", "trabajé", "trabajaste"),
    81: ("estudio", "estudiando", "estudié", "estudiaste"),
    82: ("cocino", "cocinando", "cociné", "cocinaste"),
    83: ("limpio", "limpiando", "limpié", "limpiaste"),
    84: ("lavo", "lavando", "lavé", "lavaste"),
    85: ("compro", "comprando", "compré", "compraste"),
    86: ("vendo", "vendiendo", "vendí", "vendiste"),
    87: ("conduzco", "conduciendo", "conduje", "condujiste"),
    88: ("viajo", "viajando", "viajé", "viajaste"),
    89: ("vuelo", "volando", "volé", "volaste"),
    90: ("nado", "nadando", "nadé", "nadaste"),
    91: ("tengo", "teniendo", "tuve", "tuviste"),
    92: ("hago", "haciendo", "hice", "hiciste"),
    93: ("salto", "saltando", "salté", "saltaste"),
    94: ("muevo", "moviendo", "moví", "moviste"),
    95: ("veo", "viendo", "vi", "viste"),
    96: ("comienzo", "comenzando", "comencé", "comenzaste"),
    97: ("termino", "terminando", "terminé", "terminaste"),
    98: ("puedo", "pudiendo", "pude", "pudiste"),
    99: ("cambio", "cambiando", "cambié", "cambiaste"),
    100: ("quedo", "quedando", "quedé", "quedaste"),
}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def selectable_tenses(enabled: list[str] | None) -> list[str]:
    """生徒が選べる文型。管理画面で有効なものに加え、点過去と線過去は常に選べる。"""
    selected = set(enabled or [])
    return [t for t in TENSE_ORDER if t in selected or t in ("preterite", "imperfect")]


def default_selected_tenses(enabled: list[str] | None) -> list[str]:
    """練習開始時にチェックを入れる文型。点過去が有効なら線過去も入れる。"""
    selected = set(enabled or [])
    if "preterite" in selected:
        selected.add("imperfect")
    return [t for t in TENSE_ORDER if t in selected]


def _imperfect_bases(bare_infinitive: str) -> tuple[str, str, str]:
    """線過去の yo / tú / él 素形。語幹変化は起きない。"""
    bare = (bare_infinitive or "").strip().lower()
    irregular = {
        "ir": ("iba", "ibas", "iba"),
        "ser": ("era", "eras", "era"),
        "ver": ("veía", "veías", "veía"),
    }
    if bare in irregular:
        return irregular[bare]
    if bare.endswith("ar"):
        stem = bare[:-2]
        return stem + "aba", stem + "abas", stem + "aba"
    if bare.endswith("er") or bare.endswith("ir"):
        stem = bare[:-2]
        return stem + "ía", stem + "ías", stem + "ía"
    return bare, bare, bare


def _gerundio_with_clitic_accent(gerundio: str) -> str:
    """再帰代名詞を後置する際、元の強勢位置を保つためのアクセント付与。

    例: cerrando -> cerrándo(me), sintiendo -> sintiéndo(te), cayendo -> cayéndo(se)
    """
    if gerundio.endswith("ando"):
        return gerundio[:-4] + "ándo"
    if gerundio.endswith("iendo"):
        return gerundio[:-5] + "iéndo"
    if gerundio.endswith("yendo"):
        return gerundio[:-5] + "yéndo"
    return gerundio


def build_forms(verb: dict) -> dict:
    """指定した動詞について、各文型の yo形/tú形/él/ella/usted形 完全文を返す。

    戻り値: {tense: {"yo": "Yo hablo.", "tu": "Hablas.", "el_ella_usted": "Habla."}}
    él/ella/usted形は JSON に手入力せず、tú形（点過去は yo/tú、線過去は原形）から自動導出する。
    """
    vid = verb["id"]
    if vid not in CONJ_EXTRA:
        raise KeyError(f"動詞ID {vid} の活用データがありません")
    yo_present, gerundio, pret_yo, pret_tu = CONJ_EXTRA[vid]

    infinitive = verb["infinitive"]
    reflexive = bool(verb.get("reflexive"))
    tu_present = verb["tu_present"]
    el_present = tu_form_to_el(tu_present)
    pret_el = pret_tu_to_el(pret_tu, pret_yo, verb.get("stem_change"), infinitive)

    # verbs.py の再帰動詞は原形に "-se" を含む（sentirse, quedarse等）ため、
    # 代名詞を付け直す前提の「素の原形」を別途用意する。
    bare_infinitive = infinitive[:-2] if reflexive and infinitive.endswith("se") else infinitive

    forms = {}

    # 現在形
    yo_sentence = f"Yo {'me ' if reflexive else ''}{yo_present}."
    tu_sentence = _cap(f"{tu_present}.")
    el_sentence = _cap(f"{el_present}.")
    forms["present"] = {"yo": yo_sentence, "tu": tu_sentence, "el_ella_usted": el_sentence}

    # 進行形（estoy/estás/está + 現在分詞。再帰代名詞は分詞末尾に付く＝アクセント付与が必要）
    gerundio_with_clitic = _gerundio_with_clitic_accent(gerundio) if reflexive else gerundio
    yo_sentence = f"Estoy {gerundio_with_clitic}{'me' if reflexive else ''}."
    tu_sentence = f"Estás {gerundio_with_clitic}{'te' if reflexive else ''}."
    el_sentence = f"Está {gerundio_with_clitic}{'se' if reflexive else ''}."
    forms["progressive"] = {"yo": yo_sentence, "tu": tu_sentence, "el_ella_usted": el_sentence}

    # 近接未来（voy a/vas a/va a + 原形。再帰代名詞は原形末尾に付く）
    yo_sentence = f"Voy a {bare_infinitive}{'me' if reflexive else ''}."
    tu_sentence = f"Vas a {bare_infinitive}{'te' if reflexive else ''}."
    el_sentence = f"Va a {bare_infinitive}{'se' if reflexive else ''}."
    forms["near_future"] = {"yo": yo_sentence, "tu": tu_sentence, "el_ella_usted": el_sentence}

    # 点過去（活用した動詞の前に代名詞）
    yo_sentence = _cap(f"{'me ' if reflexive else ''}{pret_yo}.")
    tu_sentence = _cap(f"{'te ' if reflexive else ''}{pret_tu}.")
    el_sentence = _cap(f"{'se ' if reflexive else ''}{pret_el}.")
    forms["preterite"] = {"yo": yo_sentence, "tu": tu_sentence, "el_ella_usted": el_sentence}

    # 線過去（規則活用。yo と él は同形）
    imp_yo, imp_tu, imp_el = _imperfect_bases(bare_infinitive)
    yo_sentence = _cap(f"{'me ' if reflexive else ''}{imp_yo}.")
    tu_sentence = _cap(f"{'te ' if reflexive else ''}{imp_tu}.")
    el_sentence = _cap(f"{'se ' if reflexive else ''}{imp_el}.")
    forms["imperfect"] = {"yo": yo_sentence, "tu": tu_sentence, "el_ella_usted": el_sentence}

    return forms


def derived_person_rows() -> list[dict]:
    """管理画面の目視確認用。ドリル対象動詞の tú / él・ella・usted を全時制で返す。"""
    rows = []
    for verb in drillable_verbs():
        forms = build_forms(verb)
        row = {
            "id": verb["id"],
            "infinitive": verb["infinitive"],
            "meaning_ja": verb["meaning_ja"],
            "category": verb["category"],
            "reflexive": bool(verb.get("reflexive")),
            "tu_present": verb["tu_present"],
            "el_present": tu_form_to_el(verb["tu_present"]),
            "tenses": forms,
        }
        rows.append(row)
    return rows


def gustar_derived_rows() -> list[dict]:
    from conjugate.data.gustar import GUSTAR_EXAMPLES

    rows = []
    for item in GUSTAR_EXAMPLES:
        rows.append(
            {
                "id": item["id"],
                "topic_ja": item["topic_ja"],
                "yo_sentence": item["yo_sentence"],
                "tu_sentence": item["tu_sentence"],
                "el_ella_usted_sentence": item["el_ella_usted_sentence"],
            }
        )
    return rows
