"""ルーブリック原文とレベル点数。評価の点数換算はサーバー側。"""
from __future__ import annotations

PROMPT_VERSION = "ms-eval-v2"
RUBRIC_VERSION = "s5-sem2-v1"
LEVEL_POINTS = {1: 10, 2: 20, 3: 25, 4: 30, 5: 35, 6: 40}

# 設計書 6.1。画像の欠けは確認済みの原文。
DESCRIPTORS = {
    "general_description": {
        1: "gave simple reasons; very little statements support the main idea",
        2: "gave simple reasons; a few statements support the main idea",
        3: "gave simple reasons and explanations; some statements support the main idea",
        4: "gave adequate reasons and explanations; most statements support the main idea",
        5: "gave adequate reasons and explanations; almost all the statements support the main idea",
        6: "adequate reasons and explanations were expounded well; all statements support the main idea",
    },
    "delivery": {
        1: "not fluent at all; pronunciation is unclear",
        2: "speaks with long pauses; pronunciation is clear a few times",
        3: "speaks slowly and with hesitation; pronunciation is clear most of the time",
        4: "speaks with some pauses and fillers; pronunciation is clear most of the time",
        5: "speaks in a natural pace with some hesitation; pronunciation is clear almost all the time",
        6: "speaks in a natural pace with little to no hesitation; pronunciation is clear all the time",
    },
    "language_use": {
        1: "used simple and/or limited language; message is incomprehensible due to errors",
        2: "used simple and/or limited language; language errors cause the message to be unclear",
        3: "used an adequate range of language; language errors cause the message to be unclear",
        4: "used an adequate range of language; language errors occur frequently, message is still clear",
        5: "used appropriate range of language; language errors occur minimally, message is still clear",
        6: "used extremely appropriate range of language; minimal to no language errors occur",
    },
    "topic_development": {
        1: "introduction, body, and conclusion are not expressed at all; cohesive devices are not used at all",
        2: "introduction, body, and conclusion are not expressed clearly; cohesive devices are not used appropriately",
        3: "introduction, body, and conclusion are not expressed clearly; a few cohesive devices are used appropriately",
        4: "introduction, body, and conclusion are expressed; some cohesive devices are used appropriately",
        5: "introduction, body, and conclusion are expressed; almost all cohesive devices are used appropriately",
        6: "introduction, body, and conclusion are expressed; all cohesive devices are used appropriately",
    },
}


def descriptor_text() -> str:
    lines = []
    titles = {
        "general_description": "General Description",
        "delivery": "Delivery（今回は判定しない。参考）",
        "language_use": "Language Use",
        "topic_development": "Topic Development",
    }
    for key, title in titles.items():
        lines.append(title)
        for level in range(1, 7):
            lines.append(f"  {level}: {DESCRIPTORS[key][level]}")
    return "\n".join(lines)
