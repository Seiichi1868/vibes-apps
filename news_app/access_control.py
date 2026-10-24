"""教員アカウントと公開範囲。データは NEWS_DATA_DIR の JSON（flock）。

他アプリは import しない。字幕取得のサービスには触らない。
"""
from __future__ import annotations

import fcntl
import hmac
import json
import os
import re
import threading
import time
from pathlib import Path

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from news_app.admin_auth import (
    SESSION_KEY,
    clear_admin_session,
    clear_failures,
    client_ip,
    establish_admin_session,
    is_admin_session,
    is_locked,
    limiter_denied_response,
    record_failure,
)
from news_app.config import admin_password_matches, get_admin_password
from news_app.services.storage import get_class, get_submission, list_classes

OWNER = "owner"
ROLE_OWNER = "owner"
ROLE_TEACHER = "teacher"
SESSION_ROLE = "news_admin_role"
SESSION_ACTOR = "news_admin_actor"
SESSION_REV = "news_admin_rev"

MIN_ID_LEN = 2
MAX_ID_LEN = 40
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 80
_ID_RE = re.compile(r"^[^\s/\\]{2,40}$")

_guard = threading.Lock()
_locks: dict[str, "_ProcessFileLock"] = {}


class _ProcessFileLock:
    def __init__(self, path: Path):
        self._path = path
        self._thread = threading.RLock()
        self._fh = None
        self._depth = 0

    def __enter__(self):
        self._thread.acquire()
        try:
            if self._depth == 0:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = self._path.open("a+")
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            self._depth += 1
        except Exception:
            self._thread.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._depth -= 1
            if self._depth <= 0:
                self._depth = 0
                handle = self._fh
                self._fh = None
                if handle is not None:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()
        finally:
            self._thread.release()
        return False


def _named_lock(path: Path) -> _ProcessFileLock:
    key = str(path)
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _ProcessFileLock(path)
            _locks[key] = lock
        return lock


def _store_path() -> Path:
    root = Path(os.environ.get("NEWS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))).expanduser()
    return root / "teacher_access.json"


def _default_store() -> dict:
    return {"require_teacher_login": False, "share_archives": False, "accounts": []}


def _with_store(mutator):
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _named_lock(path.with_name(path.name + ".lock")):
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                data = {}
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        data.setdefault("require_teacher_login", False)
        data.setdefault("share_archives", False)
        if not isinstance(data.get("accounts"), list):
            data["accounts"] = []
        result = mutator(data)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return result


def load_access() -> dict:
    def read(data):
        return {
            "require_teacher_login": bool(data.get("require_teacher_login")),
            "share_archives": bool(data.get("share_archives")),
            "accounts": list(data.get("accounts") or []),
        }

    return _with_store(read)


def require_teacher_login() -> bool:
    return bool(load_access()["require_teacher_login"])


def share_archives_enabled() -> bool:
    return bool(load_access()["share_archives"])


def update_access_settings(*, require_login=None, share_archives=None) -> dict:
    def apply(data):
        if require_login is not None:
            data["require_teacher_login"] = bool(require_login)
        if share_archives is not None:
            data["share_archives"] = bool(share_archives)
        return {
            "require_teacher_login": bool(data.get("require_teacher_login")),
            "share_archives": bool(data.get("share_archives")),
        }

    return _with_store(apply)


def _find_account(data: dict, account_id: str) -> dict | None:
    for account in data.get("accounts") or []:
        if isinstance(account, dict) and account.get("id") == account_id:
            return account
    return None


def validate_account_id(account_id: str) -> str | None:
    account_id = (account_id or "").strip()
    if account_id.lower() == OWNER:
        return "このIDは使えません。"
    if not _ID_RE.match(account_id) or len(account_id) < MIN_ID_LEN or len(account_id) > MAX_ID_LEN:
        return "アカウントIDは2〜40文字で、空白やスラッシュは使えません。"
    return None


def validate_password(password: str) -> str | None:
    password = password if isinstance(password, str) else ""
    if len(password) < MIN_PASSWORD_LEN or len(password) > MAX_PASSWORD_LEN:
        return "パスワードは8〜80文字にしてください。"
    if password.strip() != password or not password.strip():
        return "パスワードの前後に空白は使えません。"
    return None


def issue_account(account_id: str, password: str) -> tuple[dict | None, str | None]:
    account_id = (account_id or "").strip()
    error = validate_account_id(account_id) or validate_password(password if isinstance(password, str) else "")
    if error:
        return None, error

    def add(data):
        if _find_account(data, account_id):
            return None, "同じIDのアカウントが既にあります。"
        account = {
            "id": account_id,
            "password_hash": generate_password_hash(password),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "disabled": False,
            "rev": 1,
        }
        data["accounts"].append(account)
        shown = dict(account)
        shown["password"] = password
        return shown, None

    return _with_store(add)


def _set_disabled(account_id: str, disabled: bool) -> tuple[dict | None, str | None]:
    def apply(data):
        account = _find_account(data, (account_id or "").strip())
        if not account:
            return None, "アカウントが見つかりません。"
        account["disabled"] = disabled
        account["rev"] = int(account.get("rev") or 1) + 1
        return account, None

    return _with_store(apply)


def stop_account(account_id: str):
    return _set_disabled(account_id, True)


def resume_account(account_id: str):
    return _set_disabled(account_id, False)


def delete_account(account_id: str) -> str | None:
    def apply(data):
        account_id_clean = (account_id or "").strip()
        accounts = data.get("accounts") or []
        kept = [a for a in accounts if not (isinstance(a, dict) and a.get("id") == account_id_clean)]
        if len(kept) == len(accounts):
            return "アカウントが見つかりません。"
        data["accounts"] = kept
        return None

    return _with_store(apply)


def public_accounts() -> list[dict]:
    """所有者向け一覧。保存済みパスワードは返さない。"""
    rows = []
    for account in load_access()["accounts"]:
        if not isinstance(account, dict):
            continue
        rows.append(
            {
                "id": account.get("id") or "",
                "created_at": account.get("created_at") or "",
                "disabled": bool(account.get("disabled")),
                "rev": int(account.get("rev") or 1),
                "has_password": bool(account.get("password_hash") or account.get("password")),
            }
        )
    return rows


def _account_by_id(account_id: str) -> dict | None:
    found = {}

    def read(data):
        account = _find_account(data, account_id)
        found["account"] = dict(account) if account else None
        return None

    _with_store(read)
    return found.get("account")


def establish_owner_session() -> None:
    establish_admin_session()
    session[SESSION_ROLE] = ROLE_OWNER
    session[SESSION_ACTOR] = OWNER
    session[SESSION_REV] = 0
    session.modified = True


def establish_teacher_session(account: dict) -> None:
    establish_admin_session()
    session[SESSION_ROLE] = ROLE_TEACHER
    session[SESSION_ACTOR] = account.get("id") or ""
    session[SESSION_REV] = int(account.get("rev") or 1)
    session.modified = True


def current_actor() -> tuple[str | None, str | None]:
    """有効なセッションなら (role, actor_id)。教員の停止・削除・rev 不一致は即無効。"""
    if not is_admin_session():
        return None, None
    role = session.get(SESSION_ROLE)
    actor = session.get(SESSION_ACTOR)
    if role == ROLE_TEACHER:
        account = _account_by_id(str(actor or ""))
        try:
            rev = int(session.get(SESSION_REV) or 0)
        except (TypeError, ValueError):
            rev = 0
        if (
            not account
            or account.get("disabled")
            or int(account.get("rev") or 1) != rev
        ):
            clear_admin_session()
            return None, None
        return ROLE_TEACHER, str(account.get("id") or "")
    if role == ROLE_OWNER or (role is None and session.get(SESSION_KEY)):
        return ROLE_OWNER, OWNER
    clear_admin_session()
    return None, None


def is_owner_session() -> bool:
    role, _actor = current_actor()
    return role == ROLE_OWNER


def actor_id() -> str:
    _role, actor = current_actor()
    return actor or ""


def _password_matches(account: dict, provided: str) -> bool:
    hashed = account.get("password_hash")
    if isinstance(hashed, str) and hashed:
        return check_password_hash(hashed, provided)
    plain = account.get("password")
    if isinstance(plain, str) and plain:
        return hmac.compare_digest(provided, plain)
    return False


def _migrate_plaintext_password(account_id: str, password: str) -> None:
    def apply(data):
        account = _find_account(data, account_id)
        if not account or account.get("password_hash"):
            return None
        account["password_hash"] = generate_password_hash(password)
        account.pop("password", None)
        return None

    _with_store(apply)


def attempt_login(payload: dict) -> tuple | None:
    """失敗時は (response, status)。成功時は None でセッション確立済み。"""
    payload = payload or {}
    teacher_id = str(payload.get("teacher_id") or payload.get("account_id") or "").strip()
    provided = payload.get("password")
    if provided is None:
        provided = payload.get("admin_password")
    provided = "" if provided is None else str(provided)

    ip = client_ip()
    if is_locked(ip):
        return limiter_denied_response()

    if teacher_id:
        account = _account_by_id(teacher_id)
        matches = bool(account and not account.get("disabled") and _password_matches(account, provided))
        if matches and account and not account.get("password_hash") and account.get("password"):
            _migrate_plaintext_password(teacher_id, provided)
            account = _account_by_id(teacher_id) or account
        if not matches:
            record_failure(ip)
            if is_locked(ip):
                return limiter_denied_response()
            return jsonify({"ok": False, "error": "アカウントIDまたはパスワードが違います。"}), 403
        clear_failures(ip)
        establish_teacher_session(account)
        return None

    if not get_admin_password():
        return jsonify({"ok": False, "error": "管理パスワードが設定されていません。"}), 503
    if not admin_password_matches(provided):
        record_failure(ip)
        if is_locked(ip):
            return limiter_denied_response()
        return jsonify({"ok": False, "error": "管理パスワードが違います。"}), 403
    clear_failures(ip)
    establish_owner_session()
    return None


def class_creator(cls: dict | None) -> str:
    if not isinstance(cls, dict):
        return OWNER
    return str(cls.get("created_by") or OWNER).strip() or OWNER


def can_view_class(class_id: str) -> bool:
    role, actor = current_actor()
    if role == ROLE_OWNER:
        return get_class(class_id) is not None
    if role != ROLE_TEACHER:
        return False
    cls = get_class(class_id)
    if not cls:
        return False
    if class_creator(cls) == actor:
        return True
    return share_archives_enabled()


def can_manage_class(class_id: str) -> bool:
    """授業の変更と、提出・名簿など生徒情報。共有トグルでは開かない。"""
    role, actor = current_actor()
    if role == ROLE_OWNER:
        return get_class(class_id) is not None
    if role != ROLE_TEACHER:
        return False
    cls = get_class(class_id)
    return bool(cls) and class_creator(cls) == actor


def viewable_classes() -> list[dict]:
    role, actor = current_actor()
    classes = list_classes()
    if role == ROLE_OWNER:
        return classes
    if role != ROLE_TEACHER:
        return []
    if share_archives_enabled():
        return classes
    return [c for c in classes if (c.get("created_by") or OWNER) == actor]


def managed_classes() -> list[dict]:
    role, actor = current_actor()
    classes = list_classes()
    if role == ROLE_OWNER:
        return classes
    if role != ROLE_TEACHER:
        return []
    return [c for c in classes if (c.get("created_by") or OWNER) == actor]


def deny_class(class_id: str, *, manage: bool) -> tuple | None:
    if not class_id or not get_class(class_id):
        return jsonify({"ok": False, "error": "指定されたクラスが見つかりません。"}), 404
    allowed = can_manage_class(class_id) if manage else can_view_class(class_id)
    if allowed:
        return None
    return jsonify({"ok": False, "error": "このクラスを操作する権限がありません。"}), 403


def submission_allowed(submission_id: str) -> tuple | None:
    submission = get_submission(submission_id)
    if not submission:
        return jsonify({"ok": False, "error": "データが見つかりません。"}), 404
    return deny_class(str(submission.get("class_id") or ""), manage=True)


def login_status_payload() -> dict:
    role, actor = current_actor()
    logged_in = role is not None
    return {
        "ok": True,
        "logged_in": logged_in,
        "role": role or "",
        "teacher_id": actor if role == ROLE_TEACHER else "",
        "require_teacher_login": require_teacher_login(),
        "share_archives": share_archives_enabled() if role == ROLE_OWNER else False,
    }


def copy_login_text(account_id: str, password: str, login_url: str) -> str:
    return f"ID: {account_id}\nパスワード: {password}\nログインURL: {login_url}"
