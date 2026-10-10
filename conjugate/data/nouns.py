"""名詞の単語練習。カテゴリー単位で4択にする。"""

NOUN_CATEGORY_ORDER = ("vegetables",)

NOUN_CATEGORY_LABELS = {
    "vegetables": "野菜",
}

# 添付の野菜表。冠詞付き。キャベツとじゃがいもは地域による言い方を併記する。
# zanahoria は女性名詞なので la（表の el は直してある）。
NOUNS = [
    {
        "id": "veg-zanahoria",
        "category": "vegetables",
        "ja": "にんじん",
        "es": "la zanahoria",
        "reading": "ラ サナオリア",
    },
    {
        "id": "veg-espinaca",
        "category": "vegetables",
        "ja": "ほうれんそう",
        "es": "la espinaca",
        "reading": "ラ エスピナカ",
    },
    {
        "id": "veg-repollo",
        "category": "vegetables",
        "ja": "キャベツ",
        "es": "el repollo / la col",
        "reading": "エル レポージョ / ラ コル",
    },
    {
        "id": "veg-tomate",
        "category": "vegetables",
        "ja": "トマト",
        "es": "el tomate",
        "reading": "エル トマテ",
    },
    {
        "id": "veg-pepino",
        "category": "vegetables",
        "ja": "きゅうり",
        "es": "el pepino",
        "reading": "エル ペピノ",
    },
    {
        "id": "veg-berenjena",
        "category": "vegetables",
        "ja": "なす",
        "es": "la berenjena",
        "reading": "ラ ベレンヘナ",
    },
    {
        "id": "veg-calabaza",
        "category": "vegetables",
        "ja": "かぼちゃ",
        "es": "la calabaza",
        "reading": "ラ カラバサ",
    },
    {
        "id": "veg-papa",
        "category": "vegetables",
        "ja": "じゃがいも",
        "es": "la papa / la patata",
        "reading": "ラ パパ（中南米） / ラ パタタ（スペイン）",
    },
    {
        "id": "veg-lechuga",
        "category": "vegetables",
        "ja": "レタス",
        "es": "la lechuga",
        "reading": "ラ レチュガ",
    },
    {
        "id": "veg-pimiento",
        "category": "vegetables",
        "ja": "ピーマン",
        "es": "el pimiento",
        "reading": "エル ピミエント",
    },
]


def nouns_in_category(category: str) -> list[dict]:
    return [n for n in NOUNS if n["category"] == category]


def noun_categories() -> list[dict]:
    return [
        {
            "id": cat,
            "label": NOUN_CATEGORY_LABELS[cat],
            "count": len(nouns_in_category(cat)),
        }
        for cat in NOUN_CATEGORY_ORDER
        if nouns_in_category(cat)
    ]
