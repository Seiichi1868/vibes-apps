"""ツールのメタ情報を1か所にまとめる。追加時はここ＋ tools/<id>/ を足す。"""
from __future__ import annotations

from copy import deepcopy

TOOLS: list[dict] = [
    {
        "id": "timer",
        "name": "タイマー",
        "description": "カウントダウン。表示モードで大きな数字。",
        "icon": "timer",
        "scene": "運営",
        "route": "toolbox.timer_page",
        "path": "/toolbox/timer",
        "uses_ai": False,
        "default_enabled": True,
    },
    {
        "id": "random_pick",
        "name": "ランダム指名",
        "description": "出席番号だけで指名。欠席と重複を除く。",
        "icon": "dice",
        "scene": "運営",
        "route": "toolbox.random_pick_page",
        "path": "/toolbox/random-pick",
        "uses_ai": False,
        "default_enabled": True,
    },
    {
        "id": "random_seats",
        "name": "ランダム座席表",
        "description": "出席番号を座席にランダム配置。",
        "icon": "seats",
        "scene": "運営",
        "route": "toolbox.random_seats_page",
        "path": "/toolbox/random-seats",
        "uses_ai": False,
        "default_enabled": True,
    },
    {
        "id": "talk_check",
        "name": "スピーチ理解度チェック",
        "description": "スピーチを録音し、理解度チェックの質問を作る。",
        "icon": "mic",
        "scene": "展開",
        "route": "toolbox.talk_check_page",
        "path": "/toolbox/talk-check",
        "uses_ai": True,
        "default_enabled": True,
    },
]

SCENE_TABS = [
    {"id": "all", "label": "すべて"},
    {"id": "導入", "label": "導入"},
    {"id": "展開", "label": "展開"},
    {"id": "まとめ", "label": "まとめ"},
    {"id": "運営", "label": "授業運営"},
]


def get_tool(tool_id: str) -> dict | None:
    for tool in TOOLS:
        if tool["id"] == tool_id:
            return deepcopy(tool)
    return None


def all_tools() -> list[dict]:
    return [deepcopy(tool) for tool in TOOLS]
