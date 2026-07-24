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
PROBLEMS_VERSION = 9
PART_A_DEFAULTS_VERSION = 6
PART_B_1_DEFAULTS_VERSION = 8
PART_B_2_DEFAULTS_VERSION = 9
PART_C_DEFAULTS_VERSION = 4

DEFAULT_ACTIVE = {part: 1 for part in PARTS}

DEFAULT_SETS: dict[str, dict[str, dict]] = {
    "a": {
        "1": {
            "text": (
                "One day, a robot called Max suddenly stopped working. "
                "No one knew how to fix him. "
                "\"Should I wait until technology improves?\" the robot asked himself. "
                "\"If I wait long enough, someone will be able to help me!\" "
                "Years later, the technology to repair Max was finally ready. "
                "He asked an engineer to fix him, but the engineer said no. "
                "No one needed an old robot like Max anymore."
            ),
        },
        "2": {
            "text": (
                "Now, let me introduce a special speaker – Nancy Watkinson. "
                "Ms. Watkinson is well-known for two things. "
                "She is a scientist who researches insects and a writer of exciting mystery novels. "
                "As many of you know, her latest book, \"Never Count Down to Zero,\" was just named "
                "Entertainment Book of the Year. "
                "Today, she will tell us about her research and her novels. "
                "Let's give her a big hand."
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
            "heading": "Question 1–4",
            "instructionJa": (
                "あなたは自分の予定について外国人の友だちと話しています。"
                "友だちから4つ質問されますので、画面上の予定表をもとに、質問に英語で答えなさい。"
            ),
            "randomQuestions": False,
            "selectedQuestions": [1, 2, 3, 4],
            "schedule": [
                {"date": "4/29", "activity": "", "publicHoliday": True},
                {"date": "4/30", "activity": "School and music club", "publicHoliday": False},
                {"date": "5/1", "activity": "School and music club", "publicHoliday": False},
                {"date": "5/2", "activity": "School and music club", "publicHoliday": False},
                {"date": "5/3", "activity": "Camping", "publicHoliday": True},
                {"date": "5/4", "activity": "Camping", "publicHoliday": True},
                {"date": "5/5", "activity": "Camping", "publicHoliday": True},
                {"date": "5/6", "activity": "", "publicHoliday": True},
            ],
            "questions": [
                {
                    "text": "On which days are you going to be free?",
                    "context": (
                        "The schedule runs from April 29 to May 6. "
                        "The student is free on April 29 and May 6."
                    ),
                    "examples": [
                        "I'm free on April 29th and May 6th.",
                        "I'll have two free days, which are April 29th and May 6th.",
                    ],
                },
                {
                    "text": (
                        "What is your special activity during the public holidays, "
                        "and on which days is it?"
                    ),
                    "context": (
                        "The special activity is camping from May 3 through May 5 "
                        "during the public holidays."
                    ),
                    "examples": [
                        "I'm going to go camping from May 3rd to 5th.",
                        "I'm planning to go on a camping trip from May 3rd to May 5th.",
                    ],
                },
                {
                    "text": "How many days are you going to go camping?",
                    "context": "The camping trip lasts for three days, from May 3 through May 5.",
                    "examples": ["I'm going to go camping for three days."],
                },
                {
                    "text": "What are you going to do on May 1st?",
                    "context": "The schedule shows school and music club on May 1.",
                    "examples": [
                        "I'm going to go to school and join my music club on May 1st."
                    ],
                },
                {
                    "text": "When are you going to start your camping trip?",
                    "context": "The camping trip starts on May 3.",
                    "examples": ["My camping trip starts on May 3rd."],
                },
                {
                    "text": "Which days on your schedule are public holidays?",
                    "context": "The public holidays are April 29 and May 3, 4, 5, and 6.",
                    "examples": [
                        "April 29th, May 3rd, 4th, 5th, and 6th are public holidays."
                    ],
                },
                {
                    "text": "On which days do you have school and music club?",
                    "context": "School and music club run from April 30 through May 2.",
                    "examples": [
                        "I have school and music club from April 30th to May 2nd."
                    ],
                },
                {
                    "text": "Are you busy on May 6th?",
                    "context": "The student is free on May 6.",
                    "examples": ["No, I'm free on May 6th."],
                },
                {
                    "text": "Do you have school on any public holidays?",
                    "context": "The student does not have school on any public holiday.",
                    "examples": ["No, I don't have school on any public holidays."],
                },
                {
                    "text": "What is your last day of school before the camping trip?",
                    "context": "The last school day before camping is May 2.",
                    "examples": [
                        "My last day of school before the camping trip is May 2nd."
                    ],
                },
            ],
        },
        "2": {
            "heading": "Question 1–4",
            "instructionJa": (
                "あなたは留学先の街にある公園のまわりをサイクリングする計画をたてました。"
                "友だちからその計画について4つ質問されますので、画面上のサイクリングマップを"
                "もとに、質問に英語で答えなさい。"
            ),
            "informationImage": "gtec/images/part-b-park-map.png",
            "randomQuestions": False,
            "selectedQuestions": [1, 2, 3, 4],
            "schedule": [],
            "questions": [
                {
                    "text": "What places will you stop at while cycling around the park?",
                    "context": "The cycling plan stops at the castle and the restaurant.",
                    "examples": [
                        "I will stop at a castle and a restaurant.",
                        "I'm going to go to a castle and then a restaurant.",
                    ],
                },
                {
                    "text": "Where is the bike rental shop?",
                    "context": (
                        "The bike rental shop is at the corner of Green Road and "
                        "4th Street, next to a hamburger restaurant."
                    ),
                    "examples": [
                        "It's on the corner of Green Road and 4th Street.",
                        "It's on 4th Street, next to a hamburger restaurant.",
                    ],
                },
                {
                    "text": "Where is the restaurant?",
                    "context": "The restaurant is on Park Road between two trees.",
                    "examples": ["It is on Park Road between two trees."],
                },
                {
                    "text": "Where is the bike rental shop?",
                    "context": (
                        "The bike rental shop is on Green Road at the corner of "
                        "Green Road and 4th Street."
                    ),
                    "examples": [
                        "It is on Green Road at the corner of Green Road and 4th Street."
                    ],
                },
                {
                    "text": "What places can you visit after renting a bike?",
                    "context": "The route visits the castle and the restaurant.",
                    "examples": ["I can visit the castle and the restaurant."],
                },
                {
                    "text": "How do you get from the bike rental shop to the restaurant?",
                    "context": (
                        "Go along Green Road, go up 5th Street, and turn right "
                        "onto Park Road."
                    ),
                    "examples": [
                        "Go along Green Road, go up 5th Street, and turn right onto Park Road."
                    ],
                },
                {
                    "text": "How do you get from the restaurant to the castle?",
                    "context": (
                        "Go along Park Road, turn right onto 4th Street, and then "
                        "turn right onto Green Road."
                    ),
                    "examples": [
                        "Go along Park Road, turn right onto 4th Street, and then turn right onto Green Road."
                    ],
                },
                {
                    "text": "What is next to the bike rental shop?",
                    "context": "The hamburger shop is next to the bike rental shop.",
                    "examples": ["The hamburger shop is next to it."],
                },
                {
                    "text": "How many restrooms are there on the map, and where are they?",
                    "context": (
                        "There are two restrooms. One is next to the restaurant, "
                        "and the other is near 5th Street."
                    ),
                    "examples": [
                        "There are two restrooms. One is next to the restaurant and the other is near 5th Street."
                    ],
                },
                {
                    "text": (
                        "If you want to visit the castle and then have lunch, "
                        "what route will you take from the bike rental shop?"
                    ),
                    "context": (
                        "First go to the castle on Green Road. Then ride around "
                        "the park to the restaurant on Park Road."
                    ),
                    "examples": [
                        "First, I will go to the castle on Green Road. Then I will ride around the park and go to the restaurant on Park Road."
                    ],
                },
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
                    "description": "A young man plans a tree-planting project at his desk with a map, a brochure, and a calendar.",
                    "example": "One day, a young man planned a tree-planting project at his desk with a map, a brochure, and a calendar.",
                },
                {
                    "description": "He goes to a park and plants a young sapling in the ground with a trowel.",
                    "example": "He went to a park and planted a young sapling in the ground with a trowel.",
                },
                {
                    "description": "Later, he waters the growing tree, which is supported by a wooden stake.",
                    "example": "Later, he watered the growing tree, which was supported by a wooden stake.",
                },
                {
                    "description": "The tree has grown well; he gives a thumbs-up while an older man claps beside a community tree-planting sign.",
                    "example": "The tree had grown well, and he gave a thumbs-up while an older man clapped beside a community tree-planting sign.",
                },
            ],
        },
        "4": {
            "storyImage": "gtec/images/part-c-story-4.png",
            "panels": [
                {
                    "description": "A student in a school uniform stands in the hallway looking confused at his schedule.",
                    "example": "One morning, a student in a school uniform stood in the hallway looking confused at his schedule.",
                },
                {
                    "description": "He asks a staff member where Room 302 is, near a door marked Room 201.",
                    "example": 'He asked a staff member, "Room 302?" near a door marked Room 201.',
                },
                {
                    "description": "The staff member smiles and points down the corridor to show him the way.",
                    "example": "The staff member smiled and pointed down the corridor to show him the way.",
                },
                {
                    "description": "He arrives late to the classroom and bows apologetically while the teacher and classmates look at him.",
                    "example": "He arrived late to the classroom and bowed apologetically while the teacher and classmates looked at him.",
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
        normalized = {
            "activity": str(item.get("activity", "")).strip(),
        }
        if "date" in item:
            normalized.update({
                "date": str(item.get("date", "")).strip(),
                "publicHoliday": bool(item.get("publicHoliday", False)),
            })
        else:
            normalized.update({
                "time": str(item.get("time", "")).strip(),
                "place": str(item.get("place", "")).strip(),
            })
        out.append(normalized)
    return out[:8]


def _normalize_selected_questions(items, question_count: int) -> list[int]:
    selected = []
    if isinstance(items, list):
        for item in items:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= question_count and number not in selected:
                selected.append(number)
            if len(selected) == 4:
                break
    for number in range(1, question_count + 1):
        if len(selected) == min(4, question_count):
            break
        if number not in selected:
            selected.append(number)
    return selected


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
            "examples": [
                str(example).strip()
                for example in item.get("examples", [])
                if str(example).strip()
            ][:4] if isinstance(item.get("examples"), list) else [],
        })
    return out[:20]


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


def _normalize_part_b_image(path: str | None, fallback: str = "") -> str:
    value = str(path or "").strip().lstrip("/")
    if value.startswith("static/"):
        value = value[len("static/"):]
    if re.match(r"^gtec/images/part-b-[a-z0-9-]+\.png$", value):
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
        questions = questions or default["questions"]
        return {
            "heading": str(raw.get("heading", default.get("heading", ""))).strip(),
            "instructionJa": str(
                raw.get("instructionJa", default.get("instructionJa", ""))
            ).strip(),
            "informationImage": _normalize_part_b_image(
                raw.get("informationImage"),
                default.get("informationImage", ""),
            ),
            "randomQuestions": bool(
                raw.get("randomQuestions", default.get("randomQuestions", False))
            ),
            "selectedQuestions": _normalize_selected_questions(
                raw.get(
                    "selectedQuestions",
                    default.get("selectedQuestions", [1, 2, 3, 4]),
                ),
                len(questions),
            ),
            "schedule": schedule or default["schedule"],
            "questions": questions,
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
                    # 更新した既定問題は、旧バージョンの保存内容より優先する。
                    if part == "a" and num in (1, 2) and stored_version < PART_A_DEFAULTS_VERSION:
                        continue
                    if part == "b" and num == 1 and stored_version < PART_B_1_DEFAULTS_VERSION:
                        continue
                    if part == "b" and num == 2 and stored_version < PART_B_2_DEFAULTS_VERSION:
                        continue
                    if part == "c" and num > 1 and stored_version < PART_C_DEFAULTS_VERSION:
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
        part_b = sets.get("b", {}).get(key)
        if part_b and part_b.get("informationImage"):
            part_b["informationImage"] = f"/static/{part_b['informationImage']}"
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
