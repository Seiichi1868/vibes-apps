"""#29 gustar 専用の特殊構文モード（開発指示書 6-2）。

gustar型構文は「好きな対象」が主語になるため、他のドリル対象動詞のような
「動詞語尾のyo→tú活用変換」は成立しない。人称を変える際に変わるのは
間接目的代名詞（me→te / me→le）のみで、動詞（gusta/gustan）自体は変化しない。

データはメインの動詞データとは分離し、このモジュール単体で管理する。
"""

GUSTAR_EXAMPLES = [
    {"id": "g1", "subject_type": "singular", "topic_ja": "コーヒーが好き", "yo_sentence": "Me gusta el café.", "tu_sentence": "Te gusta el café."},
    {"id": "g2", "subject_type": "singular", "topic_ja": "チョコレートが好き", "yo_sentence": "Me gusta el chocolate.", "tu_sentence": "Te gusta el chocolate."},
    {"id": "g3", "subject_type": "singular", "topic_ja": "音楽が好き", "yo_sentence": "Me gusta la música.", "tu_sentence": "Te gusta la música."},
    {"id": "g4", "subject_type": "singular", "topic_ja": "映画（1つの作品）が好き", "yo_sentence": "Me gusta el cine.", "tu_sentence": "Te gusta el cine."},
    {"id": "g5", "subject_type": "singular", "topic_ja": "サッカーが好き", "yo_sentence": "Me gusta el fútbol.", "tu_sentence": "Te gusta el fútbol."},
    {"id": "g6", "subject_type": "plural", "topic_ja": "本が好き", "yo_sentence": "Me gustan los libros.", "tu_sentence": "Te gustan los libros."},
    {"id": "g7", "subject_type": "plural", "topic_ja": "花が好き", "yo_sentence": "Me gustan las flores.", "tu_sentence": "Te gustan las flores."},
    {"id": "g8", "subject_type": "plural", "topic_ja": "犬が好き", "yo_sentence": "Me gustan los perros.", "tu_sentence": "Te gustan los perros."},
    {"id": "g9", "subject_type": "plural", "topic_ja": "映画（複数）が好き", "yo_sentence": "Me gustan las películas.", "tu_sentence": "Te gustan las películas."},
    {"id": "g10", "subject_type": "plural", "topic_ja": "猫が好き", "yo_sentence": "Me gustan los gatos.", "tu_sentence": "Te gustan los gatos."},
    {"id": "g11", "subject_type": "infinitive", "topic_ja": "旅行するのが好き", "yo_sentence": "Me gusta viajar.", "tu_sentence": "Te gusta viajar."},
    {"id": "g12", "subject_type": "infinitive", "topic_ja": "料理するのが好き", "yo_sentence": "Me gusta cocinar.", "tu_sentence": "Te gusta cocinar."},
    {"id": "g13", "subject_type": "infinitive", "topic_ja": "踊るのが好き", "yo_sentence": "Me gusta bailar.", "tu_sentence": "Te gusta bailar."},
    {"id": "g14", "subject_type": "infinitive", "topic_ja": "読書するのが好き", "yo_sentence": "Me gusta leer.", "tu_sentence": "Te gusta leer."},
]


def _el_from_tu(tu_sentence: str) -> str:
    """Te gusta… → Le gusta…（代名詞だけ置換）。"""
    if tu_sentence.startswith("Te "):
        return "Le " + tu_sentence[3:]
    return tu_sentence.replace(" te ", " le ").replace("Te ", "Le ")


for _item in GUSTAR_EXAMPLES:
    _item["el_ella_usted_sentence"] = _el_from_tu(_item["tu_sentence"])

GUSTAR_HINT = "gustarは活用しません。gusta/gustanのままで、代名詞（me→te / me→le）だけを変えましょう。"
GUSTAR_HINT_TU = "gustarは活用しません。gusta/gustanのままで、me→teだけを変えましょう。"
GUSTAR_HINT_EL = "gustarは活用しません。gusta/gustanのままで、me→leだけを変えましょう。"
