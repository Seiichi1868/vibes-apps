"""GTEC 問題セット（各パート 問題1〜4）の永続化。"""

import json
import os
import re
import threading
from copy import deepcopy
from pathlib import Path

_lock = threading.Lock()
DATA_DIR = Path(
    os.environ.get("GTEC_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
).expanduser()
PROBLEMS_FILE = DATA_DIR / "gtec_problems.json"

PARTS = ("a", "b", "c", "d")
PROBLEM_NUMS = (1, 2, 3, 4)
PROBLEMS_VERSION = 2

DEFAULT_ACTIVE = {part: 1 for part in PARTS}

DEFAULT_SETS: dict[str, dict[str, dict]] = {
    "a": {
        "1": {
            "text": (
                "Good morning, everyone! This is your Student Council with an important announcement. "
                "We are excited to invite all students to our annual Quiz Competition. "
                "The event will take place this Friday afternoon at three o'clock in the school gymnasium. "
                "Students will form teams of three and compete in categories including science, history, and popular culture. "
                "Registration forms are available at the front office. "
                "Please sign up by Wednesday at noon. We look forward to seeing you there!"
            ),
        },
        "2": {
            "text": (
                "Attention, students. The school library will extend its opening hours during the exam period. "
                "From Monday to Friday, the library will be open from eight in the morning until eight in the evening. "
                "On Saturdays, it will close at five o'clock. "
                "Please remember to bring your student ID card when you enter the library. "
                "Food and drinks are not allowed inside the reading area. "
                "We hope these extended hours will help you prepare for your exams."
            ),
        },
        "3": {
            "text": (
                "Dear students and parents, we are pleased to announce our school trip to Kyoto this spring. "
                "The trip will take place on April twentieth and twenty-first. "
                "Students will visit famous temples, a traditional market, and a science museum. "
                "The cost is twelve thousand yen per student, including transportation and accommodation. "
                "Permission slips must be returned to your homeroom teacher by March fifteenth. "
                "Please contact the school office if you have any questions."
            ),
        },
        "4": {
            "text": (
                "Hello, everyone. Sports Day will be held next month on the school grounds. "
                "The event will start at nine o'clock in the morning and finish at three in the afternoon. "
                "Students should wear their gym uniforms and bring a water bottle and a hat. "
                "Lunch boxes will be available for purchase at the cafeteria, or you may bring your own lunch. "
                "In case of rain, the event will be postponed to the following Saturday. "
                "Let's work together to make this Sports Day enjoyable for everyone!"
            ),
        },
    },
    "b": {
        "1": {
            "schedule": [
                {"time": "9:00 AM", "activity": "Tennis Practice", "place": "Sports Hall"},
                {"time": "12:00 PM", "activity": "Lunch", "place": "Cafeteria"},
                {"time": "2:00 PM – 4:00 PM", "activity": "Study Group", "place": "Library"},
                {"time": "5:00 PM", "activity": "Movie", "place": "Cinema"},
            ],
            "questions": [
                {"text": "What time does Akiko start tennis practice?", "context": "Akiko's Saturday schedule"},
                {"text": "Where will Akiko have lunch?", "context": "Akiko's Saturday schedule"},
                {"text": "How many hours will the study group last?", "context": "Akiko's Saturday schedule"},
                {"text": "What will Akiko do at five o'clock?", "context": "Akiko's Saturday schedule"},
            ],
        },
        "2": {
            "schedule": [
                {"time": "10:00 AM", "activity": "Swimming", "place": "City Pool"},
                {"time": "1:00 PM", "activity": "Lunch with Family", "place": "Restaurant"},
                {"time": "3:00 PM", "activity": "Piano Lesson", "place": "Music School"},
                {"time": "6:30 PM", "activity": "Homework", "place": "Home"},
            ],
            "questions": [
                {"text": "Where does Ken go swimming?", "context": "Ken's Sunday schedule"},
                {"text": "What time does Ken have lunch?", "context": "Ken's Sunday schedule"},
                {"text": "Where does Ken take his piano lesson?", "context": "Ken's Sunday schedule"},
                {"text": "What will Ken do at six thirty in the evening?", "context": "Ken's Sunday schedule"},
            ],
        },
        "3": {
            "schedule": [
                {"time": "3:30 PM", "activity": "Basketball Club", "place": "Gym"},
                {"time": "5:00 PM", "activity": "Snack", "place": "School Store"},
                {"time": "5:30 PM", "activity": "English Conversation", "place": "Room 201"},
                {"time": "7:00 PM", "activity": "Go Home", "place": "Station"},
            ],
            "questions": [
                {"text": "What club does Maria belong to?", "context": "Maria's after-school schedule"},
                {"text": "Where does Maria buy a snack?", "context": "Maria's after-school schedule"},
                {"text": "What time does Maria's English class start?", "context": "Maria's after-school schedule"},
                {"text": "Where does Maria go at seven o'clock?", "context": "Maria's after-school schedule"},
            ],
        },
        "4": {
            "schedule": [
                {"time": "8:00 AM", "activity": "Visit Grandparents", "place": "Grandparents' House"},
                {"time": "11:00 AM", "activity": "Shopping", "place": "Shopping Mall"},
                {"time": "2:00 PM", "activity": "Cooking Class", "place": "Community Center"},
                {"time": "4:30 PM", "activity": "Return Home", "place": "Home"},
            ],
            "questions": [
                {"text": "Where does Tom go at eight in the morning?", "context": "Tom's holiday schedule"},
                {"text": "Where will Tom go shopping?", "context": "Tom's holiday schedule"},
                {"text": "What activity does Tom do at two o'clock?", "context": "Tom's holiday schedule"},
                {"text": "What time does Tom return home?", "context": "Tom's holiday schedule"},
            ],
        },
    },
    "c": {
        "1": {
            "storyImage": "gtec/images/part-c-story-1.png",
            "panels": [
                {
                    "description": "A student finds a pink purse lying on the ground near the school gate.",
                    "example": "One day, a student was walking to school when he noticed a pink purse on the ground near the school gate.",
                },
                {
                    "description": "The student picks up the purse and brings it to the staff room.",
                    "example": "He picked it up and took it to the staff room to turn it in.",
                },
                {
                    "description": "A teacher in the staff room calls the owner of the purse on the phone.",
                    "example": "A teacher in the staff room called the owner of the purse on the phone.",
                },
                {
                    "description": "The owner comes to the school, receives the purse, and thanks the student warmly.",
                    "example": "The owner came to the school, got her purse back, and thanked the student warmly.",
                },
            ],
        },
        "2": {
            "storyImage": "gtec/images/part-c-story-2.png",
            "panels": [
                {
                    "description": "A student decides to bake a birthday cake for his mother and reads a recipe book in the kitchen.",
                    "example": "One Saturday, a student decided to bake a birthday cake for his mother and read a recipe book in the kitchen.",
                },
                {
                    "description": "He measures flour and eggs and mixes the batter in a bowl.",
                    "example": "He measured flour and eggs and mixed the batter in a large bowl.",
                },
                {
                    "description": "He takes the cake out of the oven and decorates it with cream and strawberries.",
                    "example": "He took the cake out of the oven and decorated it with cream and strawberries.",
                },
                {
                    "description": "His mother blows out the candles on the cake and hugs him with a big smile.",
                    "example": "His mother blew out the candles on the cake and hugged him with a big smile.",
                },
            ],
        },
        "3": {
            "storyImage": "gtec/images/part-c-story-3.png",
            "panels": [
                {
                    "description": "Students wearing gloves gather at a city park for a tree-planting volunteer event.",
                    "example": "On Sunday morning, students wearing gloves gathered at a city park for a tree-planting volunteer event.",
                },
                {
                    "description": "They dig holes in the ground and plant young trees together.",
                    "example": "They dug holes in the ground and planted young trees together.",
                },
                {
                    "description": "They water the saplings with watering cans.",
                    "example": "They watered the saplings with watering cans.",
                },
                {
                    "description": "The students smile proudly in front of the newly planted trees.",
                    "example": "The students smiled proudly in front of the newly planted trees.",
                },
            ],
        },
        "4": {
            "storyImage": "gtec/images/part-c-story-4.png",
            "panels": [
                {
                    "description": "A new transfer student stands in the school hallway holding his schedule, looking confused.",
                    "example": "On his first day, a new transfer student stood in the school hallway holding his schedule and looking confused.",
                },
                {
                    "description": "He politely asks a teacher where Room 302 is.",
                    "example": "He politely asked a teacher where Room 302 was.",
                },
                {
                    "description": "The teacher smiles and points down the corridor toward the classroom.",
                    "example": "The teacher smiled and pointed down the corridor toward the classroom.",
                },
                {
                    "description": "He enters the classroom, bows, and introduces himself to the class.",
                    "example": "He entered the classroom, bowed, and introduced himself to the class.",
                },
            ],
        },
    },
    "d": {
        "1": {
            "topic": "Should students be allowed to use smartphones at school? State your opinion clearly and support it with reasons and specific examples.",
            "topicJa": "学校でのスマートフォン使用を許可すべきか？自分の意見を明確に述べ、理由と具体例を挙げて説明してください。",
        },
        "2": {
            "topic": "Should school uniforms be mandatory for all students? State your opinion clearly and support it with reasons and specific examples.",
            "topicJa": "生徒全員に制服を義務付けるべきか？自分の意見を明確に述べ、理由と具体例を挙げて説明してください。",
        },
        "3": {
            "topic": "Should high school students have part-time jobs? State your opinion clearly and support it with reasons and specific examples.",
            "topicJa": "高校生はアルバイトをすべきか？自分の意見を明確に述べ、理由と具体例を挙げて説明してください。",
        },
        "4": {
            "topic": "Should plastic shopping bags be banned in Japan? State your opinion clearly and support it with reasons and specific examples.",
            "topicJa": "日本ではレジ袋を禁止すべきか？自分の意見を明確に述べ、理由と具体例を挙げて説明してください。",
        },
    },
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clamp_problem_num(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return n if n in PROBLEM_NUMS else 1


def _normalize_schedule(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "time": str(item.get("time", "")).strip(),
            "activity": str(item.get("activity", "")).strip(),
            "place": str(item.get("place", "")).strip(),
        })
    return out[:8]


def _normalize_questions(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        out.append({
            "text": text,
            "context": str(item.get("context", "")).strip(),
        })
    return out[:8]


def _normalize_panels(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "description": str(item.get("description", "")).strip(),
            "example": str(item.get("example", "")).strip(),
        })
    return out[:4]


def _normalize_story_image(path: str | None, fallback: str) -> str:
    value = str(path or "").strip().lstrip("/")
    if value.startswith("static/"):
        value = value[len("static/"):]
    if re.match(r"^gtec/images/part-c-story-\d+\.png$", value):
        return value
    return fallback


def _normalize_part_set(part: str, num: int, raw: dict | None) -> dict:
    default = deepcopy(DEFAULT_SETS[part][str(num)])
    if not isinstance(raw, dict):
        return default

    if part == "a":
        text = str(raw.get("text", default.get("text", ""))).strip()
        return {"text": text or default["text"]}

    if part == "b":
        schedule = _normalize_schedule(raw.get("schedule", default.get("schedule")))
        questions = _normalize_questions(raw.get("questions", default.get("questions")))
        return {
            "schedule": schedule or default["schedule"],
            "questions": questions or default["questions"],
        }

    if part == "c":
        panels = _normalize_panels(raw.get("panels", default.get("panels")))
        return {
            "storyImage": _normalize_story_image(raw.get("storyImage"), default["storyImage"]),
            "panels": panels or default["panels"],
        }

    if part == "d":
        topic = str(raw.get("topic", default.get("topic", ""))).strip()
        topic_ja = str(raw.get("topicJa", default.get("topicJa", ""))).strip()
        return {
            "topic": topic or default["topic"],
            "topicJa": topic_ja or default["topicJa"],
        }

    return default


def _normalize(raw: dict | None) -> dict:
    data = {
        "version": PROBLEMS_VERSION,
        "active": deepcopy(DEFAULT_ACTIVE),
        "sets": deepcopy(DEFAULT_SETS),
    }
    if not isinstance(raw, dict):
        return data

    stored_version = raw.get("version", 1)
    try:
        stored_version = int(stored_version)
    except (TypeError, ValueError):
        stored_version = 1

    active = raw.get("active")
    if isinstance(active, dict):
        for part in PARTS:
            if part in active:
                data["active"][part] = _clamp_problem_num(active[part])

    sets = raw.get("sets")
    if isinstance(sets, dict):
        for part in PARTS:
            part_sets = sets.get(part)
            if not isinstance(part_sets, dict):
                continue
            for num in PROBLEM_NUMS:
                key = str(num)
                if key in part_sets:
                    # 問題1はカスタム保存を尊重。問題2〜4はバージョン更新時に新デフォルトへ。
                    if part == "c" and num > 1 and stored_version < PROBLEMS_VERSION:
                        continue
                    data["sets"][part][key] = _normalize_part_set(part, num, part_sets[key])

    return data


def load_problems() -> dict:
    _ensure_data_dir()
    with _lock:
        if not PROBLEMS_FILE.is_file():
            return _normalize(None)
        try:
            with PROBLEMS_FILE.open(encoding="utf-8") as handle:
                return _normalize(json.load(handle))
        except (json.JSONDecodeError, OSError):
            return _normalize(None)


def save_problems(data: dict) -> dict:
    _ensure_data_dir()
    normalized = _normalize(data)
    with _lock:
        with PROBLEMS_FILE.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
    return normalized


def public_problems() -> dict:
    """生徒画面向け。画像パスを /static/... 形式に変換。"""
    data = load_problems()
    sets = deepcopy(data["sets"])
    for num in PROBLEM_NUMS:
        key = str(num)
        part_c = sets.get("c", {}).get(key)
        if part_c and part_c.get("storyImage"):
            part_c["storyImage"] = f"/static/{part_c['storyImage']}"
    return {"active": data["active"], "sets": sets}


def get_active_problem_set(part: str) -> dict:
    part = part.lower()
    if part not in PARTS:
        return {}
    data = load_problems()
    num = data["active"].get(part, 1)
    return deepcopy(data["sets"][part][str(num)])
