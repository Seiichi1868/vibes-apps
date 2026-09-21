"""動詞データ。開発指示書の100語に、DELE A2必須の抜けを追加したもの。

category:
  - motion_daily     移動・日常基本動作
  - emotion_state     感情・状態
  - communication     コミュニケーション
  - daily_activity    日常生活の活動

special: "gustar_type" が付いた動詞（#29 gustar）は通常のyo→tú活用ドリルの
対象から除外し、conjugate.data.gustar の専用モジュールで扱う。
"""

CATEGORY_LABELS = {
    "motion_daily": "移動・日常基本動作",
    "emotion_state": "感情・状態",
    "communication": "コミュニケーション",
    "daily_activity": "日常生活の活動",
}

CATEGORY_SHORT = {
    "motion_daily": "移動・日常",
    "emotion_state": "感情・状態",
    "communication": "会話",
    "daily_activity": "日常活動",
}

CATEGORY_ORDER = ["motion_daily", "emotion_state", "communication", "daily_activity"]

VERBS = [
    {"id": 1, "infinitive": "ir", "meaning_ja": "行く", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "vas", "irregular_tu": True},
    {"id": 2, "infinitive": "venir", "meaning_ja": "来る", "category": "motion_daily", "reflexive": False, "stem_change": "e>ie", "tu_present": "vienes", "irregular_tu": False},
    {"id": 3, "infinitive": "salir", "meaning_ja": "出る", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "sales", "irregular_tu": False},
    {"id": 4, "infinitive": "entrar", "meaning_ja": "入る", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "entras", "irregular_tu": False},
    {"id": 5, "infinitive": "llegar", "meaning_ja": "到着する", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "llegas", "irregular_tu": False},
    {"id": 6, "infinitive": "caminar", "meaning_ja": "歩く", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "caminas", "irregular_tu": False},
    {"id": 7, "infinitive": "correr", "meaning_ja": "走る", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "corres", "irregular_tu": False},
    {"id": 8, "infinitive": "pasar", "meaning_ja": "過ごす", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "pasas", "irregular_tu": False},
    {"id": 9, "infinitive": "quedar", "meaning_ja": "残る", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "quedas", "irregular_tu": False, "note": "quedarse(#100)と混同注意"},
    {"id": 10, "infinitive": "subir", "meaning_ja": "上がる", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "subes", "irregular_tu": False},
    {"id": 11, "infinitive": "bajar", "meaning_ja": "下がる", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "bajas", "irregular_tu": False},
    {"id": 12, "infinitive": "sentar", "meaning_ja": "座る", "category": "motion_daily", "reflexive": False, "stem_change": "e>ie", "tu_present": "sientas", "irregular_tu": False, "note": "実用上はsentarse(te sientas)が自然"},
    {"id": 13, "infinitive": "parar", "meaning_ja": "止まる", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "paras", "irregular_tu": False},
    {"id": 14, "infinitive": "seguir", "meaning_ja": "続ける", "category": "motion_daily", "reflexive": False, "stem_change": "e>i", "tu_present": "sigues", "irregular_tu": False},
    {"id": 15, "infinitive": "empezar", "meaning_ja": "始める", "category": "motion_daily", "reflexive": False, "stem_change": "e>ie", "tu_present": "empiezas", "irregular_tu": False},
    {"id": 16, "infinitive": "volver", "meaning_ja": "戻る", "category": "motion_daily", "reflexive": False, "stem_change": "o>ue", "tu_present": "vuelves", "irregular_tu": False},
    {"id": 17, "infinitive": "dejar", "meaning_ja": "置く", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "dejas", "irregular_tu": False},
    {"id": 105, "infinitive": "poner", "meaning_ja": "置く・つける", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "pones", "irregular_tu": False},
    {"id": 18, "infinitive": "caer", "meaning_ja": "落ちる", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "caes", "irregular_tu": False},
    {"id": 19, "infinitive": "llevar", "meaning_ja": "持っていく", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "llevas", "irregular_tu": False},
    {"id": 20, "infinitive": "traer", "meaning_ja": "持ってくる", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "traes", "irregular_tu": False},
    {"id": 21, "infinitive": "escribir", "meaning_ja": "書く", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "escribes", "irregular_tu": False},
    {"id": 22, "infinitive": "leer", "meaning_ja": "読む", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "lees", "irregular_tu": False},
    {"id": 23, "infinitive": "abrir", "meaning_ja": "開ける", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "abres", "irregular_tu": False},
    {"id": 24, "infinitive": "cerrar", "meaning_ja": "閉める", "category": "motion_daily", "reflexive": False, "stem_change": "e>ie", "tu_present": "cierras", "irregular_tu": False},
    {"id": 25, "infinitive": "cortar", "meaning_ja": "切る", "category": "motion_daily", "reflexive": False, "stem_change": None, "tu_present": "cortas", "irregular_tu": False},

    {"id": 26, "infinitive": "estar", "meaning_ja": "〜にある/いる", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "estás", "irregular_tu": True},
    {"id": 101, "infinitive": "ser", "meaning_ja": "〜である", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "eres", "irregular_tu": True},
    {"id": 102, "infinitive": "saber", "meaning_ja": "知る（事実・やり方）", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "sabes", "irregular_tu": False},
    {"id": 103, "infinitive": "conocer", "meaning_ja": "知っている（人・場所）", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "conoces", "irregular_tu": False},
    {"id": 27, "infinitive": "parecer", "meaning_ja": "思われる", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "pareces", "irregular_tu": False},
    {"id": 28, "infinitive": "sentir", "meaning_ja": "感じる", "category": "emotion_state", "reflexive": False, "stem_change": "e>ie", "tu_present": "sientes", "irregular_tu": False},
    {"id": 29, "infinitive": "gustar", "meaning_ja": "好きである", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": None, "irregular_tu": None, "special": "gustar_type", "note": "tú主語での活用不成立。出題対象から除外し専用モジュールで扱う"},
    {"id": 30, "infinitive": "querer", "meaning_ja": "欲しい/愛する", "category": "emotion_state", "reflexive": False, "stem_change": "e>ie", "tu_present": "quieres", "irregular_tu": False},
    {"id": 31, "infinitive": "amar", "meaning_ja": "愛する", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "amas", "irregular_tu": False},
    {"id": 32, "infinitive": "odiar", "meaning_ja": "憎む", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "odias", "irregular_tu": False},
    {"id": 33, "infinitive": "disfrutar", "meaning_ja": "楽しむ", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "disfrutas", "irregular_tu": False},
    {"id": 34, "infinitive": "preferir", "meaning_ja": "好む", "category": "emotion_state", "reflexive": False, "stem_change": "e>ie", "tu_present": "prefieres", "irregular_tu": False},
    {"id": 35, "infinitive": "necesitar", "meaning_ja": "必要とする", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "necesitas", "irregular_tu": False},
    {"id": 104, "infinitive": "deber", "meaning_ja": "〜すべきである", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "debes", "irregular_tu": False},
    {"id": 36, "infinitive": "desear", "meaning_ja": "望む", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "deseas", "irregular_tu": False},
    {"id": 37, "infinitive": "esperar", "meaning_ja": "期待する", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "esperas", "irregular_tu": False},
    {"id": 38, "infinitive": "creer", "meaning_ja": "信じる", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "crees", "irregular_tu": False},
    {"id": 39, "infinitive": "pensar", "meaning_ja": "考える", "category": "emotion_state", "reflexive": False, "stem_change": "e>ie", "tu_present": "piensas", "irregular_tu": False},
    {"id": 40, "infinitive": "recordar", "meaning_ja": "思い出す", "category": "emotion_state", "reflexive": False, "stem_change": "o>ue", "tu_present": "recuerdas", "irregular_tu": False},
    {"id": 41, "infinitive": "olvidar", "meaning_ja": "忘れる", "category": "emotion_state", "reflexive": False, "stem_change": None, "tu_present": "olvidas", "irregular_tu": False},
    {"id": 42, "infinitive": "sentirse", "meaning_ja": "感じる", "category": "emotion_state", "reflexive": True, "stem_change": "e>ie", "tu_present": "te sientes", "irregular_tu": False},
    {"id": 43, "infinitive": "preocuparse", "meaning_ja": "心配する", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te preocupas", "irregular_tu": False},
    {"id": 44, "infinitive": "alegrarse", "meaning_ja": "喜ぶ", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te alegras", "irregular_tu": False},
    {"id": 45, "infinitive": "enojarse", "meaning_ja": "怒る", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te enojas", "irregular_tu": False},
    {"id": 46, "infinitive": "cansarse", "meaning_ja": "疲れる", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te cansas", "irregular_tu": False},
    {"id": 47, "infinitive": "enfermarse", "meaning_ja": "病む", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te enfermas", "irregular_tu": False},
    {"id": 48, "infinitive": "mejorarse", "meaning_ja": "回復する", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te mejoras", "irregular_tu": False},
    {"id": 49, "infinitive": "empeorarse", "meaning_ja": "悪化する", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te empeoras", "irregular_tu": False, "note": "一般には非再帰empeorarの方が高頻度だが元データ通り再帰で実装"},
    {"id": 50, "infinitive": "aburrirse", "meaning_ja": "退屈する", "category": "emotion_state", "reflexive": True, "stem_change": None, "tu_present": "te aburres", "irregular_tu": False},

    {"id": 51, "infinitive": "hablar", "meaning_ja": "話す", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "hablas", "irregular_tu": False},
    {"id": 52, "infinitive": "decir", "meaning_ja": "言う", "category": "communication", "reflexive": False, "stem_change": "e>i", "tu_present": "dices", "irregular_tu": False},
    {"id": 53, "infinitive": "preguntar", "meaning_ja": "尋ねる", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "preguntas", "irregular_tu": False},
    {"id": 54, "infinitive": "responder", "meaning_ja": "答える", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "respondes", "irregular_tu": False},
    {"id": 55, "infinitive": "escuchar", "meaning_ja": "聞く", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "escuchas", "irregular_tu": False},
    {"id": 106, "infinitive": "entender", "meaning_ja": "理解する", "category": "communication", "reflexive": False, "stem_change": "e>ie", "tu_present": "entiendes", "irregular_tu": False},
    {"id": 107, "infinitive": "oír", "meaning_ja": "聞こえる", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "oyes", "irregular_tu": True},
    {"id": 56, "infinitive": "explicar", "meaning_ja": "説明する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "explicas", "irregular_tu": False},
    {"id": 57, "infinitive": "pedir", "meaning_ja": "頼む", "category": "communication", "reflexive": False, "stem_change": "e>i", "tu_present": "pides", "irregular_tu": False},
    {"id": 58, "infinitive": "contar", "meaning_ja": "数える・語る", "category": "communication", "reflexive": False, "stem_change": "o>ue", "tu_present": "cuentas", "irregular_tu": False},
    {"id": 59, "infinitive": "llamar", "meaning_ja": "呼ぶ", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "llamas", "irregular_tu": False, "note": "llamarse(#108)と混同注意"},
    {"id": 108, "infinitive": "llamarse", "meaning_ja": "〜という名前である", "category": "communication", "reflexive": True, "stem_change": None, "tu_present": "te llamas", "irregular_tu": False, "note": "llamar(#59)と混同注意"},
    {"id": 60, "infinitive": "gritar", "meaning_ja": "叫ぶ", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "gritas", "irregular_tu": False},
    {"id": 61, "infinitive": "susurrar", "meaning_ja": "囁く", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "susurras", "irregular_tu": False},
    {"id": 62, "infinitive": "saludar", "meaning_ja": "挨拶する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "saludas", "irregular_tu": False},
    {"id": 63, "infinitive": "discutir", "meaning_ja": "議論する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "discutes", "irregular_tu": False},
    {"id": 64, "infinitive": "argumentar", "meaning_ja": "論じる", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "argumentas", "irregular_tu": False},
    {"id": 65, "infinitive": "comunicar", "meaning_ja": "伝える", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "comunicas", "irregular_tu": False},
    {"id": 66, "infinitive": "informar", "meaning_ja": "情報を与える", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "informas", "irregular_tu": False},
    {"id": 67, "infinitive": "describir", "meaning_ja": "描写する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "describes", "irregular_tu": False},
    {"id": 68, "infinitive": "anunciar", "meaning_ja": "発表する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "anuncias", "irregular_tu": False},
    {"id": 69, "infinitive": "declarar", "meaning_ja": "宣言する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "declaras", "irregular_tu": False},
    {"id": 70, "infinitive": "afirmar", "meaning_ja": "断言する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "afirmas", "irregular_tu": False},
    {"id": 71, "infinitive": "negar", "meaning_ja": "否定する", "category": "communication", "reflexive": False, "stem_change": "e>ie", "tu_present": "niegas", "irregular_tu": False},
    {"id": 72, "infinitive": "aceptar", "meaning_ja": "受け入れる", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "aceptas", "irregular_tu": False},
    {"id": 73, "infinitive": "rechazar", "meaning_ja": "拒否する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "rechazas", "irregular_tu": False},
    {"id": 74, "infinitive": "prometer", "meaning_ja": "約束する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "prometes", "irregular_tu": False},
    {"id": 75, "infinitive": "agradecer", "meaning_ja": "感謝する", "category": "communication", "reflexive": False, "stem_change": None, "tu_present": "agradeces", "irregular_tu": False},

    {"id": 76, "infinitive": "comer", "meaning_ja": "食べる", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "comes", "irregular_tu": False},
    {"id": 77, "infinitive": "beber", "meaning_ja": "飲む", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "bebes", "irregular_tu": False},
    {"id": 111, "infinitive": "tomar", "meaning_ja": "取る・飲む", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "tomas", "irregular_tu": False},
    {"id": 78, "infinitive": "dormir", "meaning_ja": "眠る", "category": "daily_activity", "reflexive": False, "stem_change": "o>ue", "tu_present": "duermes", "irregular_tu": False},
    {"id": 79, "infinitive": "jugar", "meaning_ja": "遊ぶ", "category": "daily_activity", "reflexive": False, "stem_change": "u>ue", "tu_present": "juegas", "irregular_tu": False},
    {"id": 80, "infinitive": "trabajar", "meaning_ja": "働く", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "trabajas", "irregular_tu": False},
    {"id": 81, "infinitive": "estudiar", "meaning_ja": "勉強する", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "estudias", "irregular_tu": False},
    {"id": 110, "infinitive": "vivir", "meaning_ja": "住む", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "vives", "irregular_tu": False},
    {"id": 82, "infinitive": "cocinar", "meaning_ja": "料理する", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "cocinas", "irregular_tu": False},
    {"id": 83, "infinitive": "limpiar", "meaning_ja": "掃除する", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "limpias", "irregular_tu": False},
    {"id": 84, "infinitive": "lavar", "meaning_ja": "洗う", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "lavas", "irregular_tu": False},
    {"id": 85, "infinitive": "comprar", "meaning_ja": "買う", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "compras", "irregular_tu": False},
    {"id": 114, "infinitive": "buscar", "meaning_ja": "探す", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "buscas", "irregular_tu": False},
    {"id": 86, "infinitive": "vender", "meaning_ja": "売る", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "vendes", "irregular_tu": False},
    {"id": 87, "infinitive": "conducir", "meaning_ja": "運転する", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "conduces", "irregular_tu": False},
    {"id": 88, "infinitive": "viajar", "meaning_ja": "旅行する", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "viajas", "irregular_tu": False},
    {"id": 89, "infinitive": "volar", "meaning_ja": "飛ぶ", "category": "daily_activity", "reflexive": False, "stem_change": "o>ue", "tu_present": "vuelas", "irregular_tu": False},
    {"id": 90, "infinitive": "nadar", "meaning_ja": "泳ぐ", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "nadas", "irregular_tu": False},
    {"id": 91, "infinitive": "tener", "meaning_ja": "持つ", "category": "daily_activity", "reflexive": False, "stem_change": "e>ie", "tu_present": "tienes", "irregular_tu": False},
    {"id": 92, "infinitive": "hacer", "meaning_ja": "する・作る", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "haces", "irregular_tu": False},
    {"id": 109, "infinitive": "dar", "meaning_ja": "与える", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "das", "irregular_tu": False},
    {"id": 93, "infinitive": "saltar", "meaning_ja": "跳ぶ", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "saltas", "irregular_tu": False},
    {"id": 94, "infinitive": "mover", "meaning_ja": "動かす", "category": "daily_activity", "reflexive": False, "stem_change": "o>ue", "tu_present": "mueves", "irregular_tu": False},
    {"id": 95, "infinitive": "ver", "meaning_ja": "見る", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "ves", "irregular_tu": False},
    {"id": 96, "infinitive": "comenzar", "meaning_ja": "始める", "category": "daily_activity", "reflexive": False, "stem_change": "e>ie", "tu_present": "comienzas", "irregular_tu": False},
    {"id": 97, "infinitive": "terminar", "meaning_ja": "終える", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "terminas", "irregular_tu": False},
    {"id": 98, "infinitive": "poder", "meaning_ja": "できる", "category": "daily_activity", "reflexive": False, "stem_change": "o>ue", "tu_present": "puedes", "irregular_tu": False},
    {"id": 99, "infinitive": "cambiar", "meaning_ja": "変える", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "cambias", "irregular_tu": False},
    {"id": 100, "infinitive": "quedarse", "meaning_ja": "滞在する", "category": "daily_activity", "reflexive": True, "stem_change": None, "tu_present": "te quedas", "irregular_tu": False, "note": "quedar(#9)と混同注意"},
    {"id": 112, "infinitive": "levantarse", "meaning_ja": "起きる", "category": "daily_activity", "reflexive": True, "stem_change": None, "tu_present": "te levantas", "irregular_tu": False},
    {"id": 113, "infinitive": "nacer", "meaning_ja": "生まれる", "category": "daily_activity", "reflexive": False, "stem_change": None, "tu_present": "naces", "irregular_tu": False},
]

VERBS_BY_ID = {v["id"]: v for v in VERBS}


def drillable_verbs() -> list[dict]:
    """通常のyo→tú活用ドリル対象（gustar等の特殊構文を除く）。"""
    return [v for v in VERBS if not v.get("special")]


def verbs_by_category(category_ids: list[str]) -> list[dict]:
    wanted = set(category_ids or [])
    return [v for v in drillable_verbs() if v["category"] in wanted]
