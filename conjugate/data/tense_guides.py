"""時制ごとの解説。出題と同じ build_forms() から例文を取る。"""
import re

from conjugate.data.conjugations import TENSE_LABELS, TENSE_LABELS_ES, TENSE_ORDER, build_forms
from conjugate.data.verbs import VERBS_BY_ID

_INFINITIVE_MEANING = {
    verb["infinitive"]: verb["meaning_ja"]
    for verb in VERBS_BY_ID.values()
    if verb.get("infinitive") and verb.get("meaning_ja")
}
_INFINITIVE_PATTERN = re.compile(
    r"(?<![\wáéíóúüñÁÉÍÓÚÜÑ])("
    + "|".join(re.escape(inf) for inf in sorted(_INFINITIVE_MEANING, key=len, reverse=True))
    + r")(?![\wáéíóúüñÁÉÍÓÚÜÑ])"
)


def _with_verb_meanings(line: str) -> str:
    """解説文中の原形に、登録済みの日本語の意味を付ける。"""

    def repl(match: re.Match) -> str:
        infinitive = match.group(1)
        meaning = _INFINITIVE_MEANING.get(infinitive)
        if not meaning:
            return infinitive
        return f"{infinitive}（{meaning}）"

    text = _INFINITIVE_PATTERN.sub(repl, line)
    # 「ir だけ」のように原形の直後が日本語だと、意味を挟んだあとに空白が残る。
    return re.sub(r"） (?![→/])", "）", text)

PERSON_HEADERS_SG = ("yo", "tú", "él")
PERSON_HEADERS_PL = ("nosotros", "vosotros", "ellos")

_GUIDES = {
    "present": {
        "summary": "今していること、習慣、事実を表す基本の時制です。このアプリのスタート地点です。",
        "uses": [
            "今している動作（Hablo español. スペイン語を話す）",
            "習慣や繰り返し（Todos los días camino. 毎日歩く）",
            "変わらない事実や能力（Hablo español. / Escribo cartas.）",
        ],
        "howto": "原形の語尾 -ar / -er / -ir を外し、人称の語尾を付けます。e>ie や o>ue などの語幹変化は、nosotros / vosotros 以外で起きます。",
        "endings": [
            {"group": "-ar（hablar）", "forms": ["-o", "-as", "-a", "-amos", "-áis", "-an"]},
            {"group": "-er（comer）", "forms": ["-o", "-es", "-e", "-emos", "-éis", "-en"]},
            {"group": "-ir（escribir）", "forms": ["-o", "-es", "-e", "-imos", "-ís", "-en"]},
        ],
        "irregulars": [
            "ser → soy / eres / es",
            "ir → voy / vas / va",
            "estar → estoy / estás / está",
            "tener → tengo / tienes / tiene",
            "hacer → hago / haces / hace",
        ],
        "example_ids": [101, 51, 76, 21, 30],
        "tips": [
            "練習では yo形を見て、tú形または él/ella/usted形に言い換えます。",
            "tú形はだいたい él形に s を付けた形です（hablas → habla）。",
        ],
    },
    "progressive": {
        "summary": "「今まさに〜している」という途中の動作を表します。estar の活用＋現在分詞（-ando / -iendo）です。",
        "uses": [
            "今この瞬間の動作（Estoy comiendo. 今食べている）",
            "一時的に続いていること（Estás trabajando mucho. たくさん働いている）",
        ],
        "howto": "estar を人称に合わせて活用し、続けて現在分詞を置きます。-ar は -ando、-er/-ir は -iendo です。再帰動詞では分詞の後ろに me/te/se が付き、アクセントが必要になることがあります（quedándose）。",
        "endings": [
            {"group": "estar", "forms": ["estoy", "estás", "está", "estamos", "estáis", "están"]},
        ],
        "irregulars": [
            "ir → yendo",
            "leer → leyendo / caer → cayendo（母音＋iendo は yendo）",
            "sentir → sintiendo、dormir → durmiendo、pedir → pidiendo（e>i / o>u）",
            "poder → pudiendo",
        ],
        "example_ids": [51, 76, 28, 100],
        "tips": [
            "変わるのは estar の部分です（estoy → estás / está）。分詞は同じままです。",
            "再帰は Estoy quedándome. → Estás quedándote. のように代名詞も変わります。",
        ],
    },
    "near_future": {
        "summary": "「これから〜する」という近い未来です。ir の現在形＋ a ＋原形で作ります。",
        "uses": [
            "すぐ予定していること（Voy a estudiar. 勉強するつもりだ）",
            "これから起きそうなこと（Va a llover. 雨が降りそうだ）",
        ],
        "howto": "voy / vas / va ＋ a ＋ 原形。再帰動詞は原形の後ろに me/te/se を付けます（Voy a quedarme.）。",
        "endings": [
            {"group": "ir + a", "forms": ["voy a", "vas a", "va a", "vamos a", "vais a", "van a"]},
        ],
        "irregulars": [
            "動詞本体は原形のままなので、語幹変化や点過去の不規則は出ません。",
            "変わるのは ir だけです（voy → vas / va）。",
        ],
        "example_ids": [51, 76, 92, 100],
        "tips": [
            "Yo voy a hablar. → Vas a hablar. / Va a hablar.",
            "再帰は Voy a quedarme. → Vas a quedarte. / Va a quedarse.",
        ],
    },
    "preterite": {
        "summary": "点過去は「終わった一回の出来事」を区切って述べる過去です。昨日したこと、完了した動作に使います。",
        "uses": [
            "完了した一回の動作（Ayer hablé con Ana. 昨日アナと話した）",
            "連続する出来事の区切り（Llegué, comí y me fui. 着いて、食べて、帰った）",
            "回数や期間が区切られていること（Vivió allí tres años. そこに3年住んだ）",
        ],
        "howto": "原形の語尾を外して点過去の語尾を付けます。多くの頻出動詞は不規則なので、このアプリでは動詞ごとに確認済みの形を使います。",
        "endings": [
            {"group": "-ar（hablar）", "forms": ["-é", "-aste", "-ó", "-amos", "-asteis", "-aron"]},
            {"group": "-er/-ir（comer / escribir）", "forms": ["-í", "-iste", "-ió", "-imos", "-isteis", "-ieron"]},
        ],
        "irregulars": [
            "ir / ser → fui / fuiste / fue（同じ形）",
            "hacer → hice / hiciste / hizo",
            "tener → tuve / tuviste / tuvo",
            "estar → estuve / estuviste / estuvo",
            "dar → di / diste / dio",
            "poner → puse / pusiste / puso",
            "ver → vi / viste / vio",
            "decir → dije / dijiste / dijo",
        ],
        "example_ids": [51, 76, 1, 101, 92],
        "tips": [
            "tú形は -aste / -iste で終わります。él形は -ó / -ió、または不規則の -o（tuvo, hizo）。",
            "線過去と違い、「いつ終わったか」が意識できる過去です。",
        ],
        "contrast": {
            "title": "線過去との違い",
            "points": [
                "点過去: 一回で終わったこと（Ayer comí pizza.）",
                "線過去: 背景・習慣・途中だったこと（Cuando era niño, comía pizza.）",
            ],
        },
    },
    "imperfect": {
        "summary": "線過去は「続いていた過去」です。習慣、様子、背景、途中だった動作を線のように描きます。不規則は ir / ser / ver の3語だけです。",
        "uses": [
            "昔の習慣（Cuando era niño, jugaba al fútbol. 子どものころサッカーをしていた）",
            "過去の様子や背景（Hacía frío. 寒かった）",
            "別の動作の最中だったこと（Leía cuando llamaste. 君が電話したとき、読んでいた）",
        ],
        "howto": "語幹変化はしません。-ar は -aba、-er/-ir は -ía を付けます。yo と él/ella/usted は同じ形です。",
        "endings": [
            {"group": "-ar（hablar）", "forms": ["-aba", "-abas", "-aba", "-ábamos", "-abais", "-aban"]},
            {"group": "-er/-ir（comer / escribir）", "forms": ["-ía", "-ías", "-ía", "-íamos", "-íais", "-ían"]},
        ],
        "irregulars": [
            "ir → iba / ibas / iba",
            "ser → era / eras / era",
            "ver → veía / veías / veía（vía ではない）",
        ],
        "example_ids": [51, 76, 1, 101, 95, 100],
        "tips": [
            "練習では Hablaba. → Hablabas. / Hablaba. です。él形は yo形と同じ動詞になります。",
            "querer は現在形 quiere でも、線過去は quería（語幹変化なし）です。",
        ],
        "contrast": {
            "title": "点過去との違い",
            "points": [
                "線過去: 習慣・背景（Todos los días caminaba.）",
                "点過去: 一回の完了（Ayer caminé al parque.）",
            ],
        },
    },
}

_EXAMPLE_NOTES = {
    1: "ir は線過去も点過去も不規則です。点過去は ser と同じ fui。",
    101: "ser は線過去も点過去も不規則です。点過去は ir と同じ fui。",
    21: "-ir 規則動詞の代表例です。",
    28: "現在分詞は sintiendo（e>i）。線過去なら sentía で語幹変化しません。",
    30: "現在形は e>ie（quieres）でも、線過去は quería です。",
    51: "-ar 規則動詞の基本形です。",
    76: "-er 規則動詞の基本形です。",
    92: "点過去 hice / hiciste / hizo は不規則です。",
    95: "ver は線過去だけ veía 型の不規則です。",
    100: "再帰動詞。代名詞 me / te / se も一緒に変わります。",
}


def _example_row(verb_id: int, tense_id: str) -> dict:
    verb = VERBS_BY_ID[verb_id]
    forms = build_forms(verb)[tense_id]
    return {
        "id": verb["id"],
        "infinitive": verb["infinitive"],
        "meaning_ja": verb["meaning_ja"],
        "reflexive": bool(verb.get("reflexive")),
        "yo": forms["yo"],
        "tu": forms["tu"],
        "el": forms["el_ella_usted"],
        "note": _EXAMPLE_NOTES.get(verb_id, ""),
    }


def list_tense_guides() -> list[dict]:
    rows = []
    for tense_id in TENSE_ORDER:
        meta = _GUIDES[tense_id]
        rows.append(
            {
                "id": tense_id,
                "label": TENSE_LABELS[tense_id],
                "label_es": TENSE_LABELS_ES[tense_id],
                "summary": meta["summary"],
            }
        )
    return rows


def get_tense_guide(tense_id: str) -> dict | None:
    if tense_id not in _GUIDES:
        return None
    meta = _GUIDES[tense_id]
    idx = TENSE_ORDER.index(tense_id)
    prev_id = TENSE_ORDER[idx - 1] if idx > 0 else None
    next_id = TENSE_ORDER[idx + 1] if idx + 1 < len(TENSE_ORDER) else None
    return {
        "id": tense_id,
        "label": TENSE_LABELS[tense_id],
        "label_es": TENSE_LABELS_ES[tense_id],
        "summary": meta["summary"],
        "uses": meta["uses"],
        "howto": meta["howto"],
        "endings": meta["endings"],
        "person_headers_sg": PERSON_HEADERS_SG,
        "person_headers_pl": PERSON_HEADERS_PL,
        "irregulars": [_with_verb_meanings(line) for line in meta["irregulars"]],
        "examples": [_example_row(vid, tense_id) for vid in meta["example_ids"]],
        "tips": meta["tips"],
        "contrast": meta.get("contrast"),
        "prev": {"id": prev_id, "label": TENSE_LABELS[prev_id]} if prev_id else None,
        "next": {"id": next_id, "label": TENSE_LABELS[next_id]} if next_id else None,
        "all": list_tense_guides(),
    }
