import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class HistoryService:
    def __init__(self, history_dir: str | Path = "learning_history", max_items: int = 100):
        self.history_dir = Path(history_dir)
        self.max_items = max_items
        self.history_dir.mkdir(exist_ok=True)

    def save(self, user_id: str, session_data: dict) -> bool:
        try:
            user_file = self.history_dir / f"{user_id}.json"

            if user_file.exists():
                with open(user_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = []

            history.append({"timestamp": datetime.now().isoformat(), **session_data})
            history = history[-self.max_items :]

            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            logger.info("Learning history saved for user: %s", user_id)
            return True
        except Exception as exc:
            logger.error("Error saving learning history: %s", exc)
            return False

    def get_statistics(self, user_id: str) -> dict:
        try:
            user_file = self.history_dir / f"{user_id}.json"

            if not user_file.exists():
                return {
                    "total_sessions": 0,
                    "average_similarity": 0,
                    "recent_sessions": [],
                }

            with open(user_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            if not history:
                return {
                    "total_sessions": 0,
                    "average_similarity": 0,
                    "recent_sessions": [],
                }

            total_sessions = len(history)
            similarities = [s["similarity"] for s in history if "similarity" in s]
            average_similarity = sum(similarities) / len(similarities) if similarities else 0

            return {
                "total_sessions": total_sessions,
                "average_similarity": round(average_similarity, 2),
                "recent_sessions": history[-10:],
            }
        except Exception as exc:
            logger.error("Error getting learning statistics: %s", exc)
            return {
                "total_sessions": 0,
                "average_similarity": 0,
                "recent_sessions": [],
            }
