import io
import logging
from copy import deepcopy
from pathlib import Path

import openpyxl
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

logger = logging.getLogger(__name__)

from news_app.access_control import (
    actor_id,
    attempt_login,
    copy_login_text,
    current_actor,
    delete_account,
    can_manage_class,
    deny_class,
    is_owner_session,
    issue_account,
    login_status_payload,
    managed_classes,
    public_accounts,
    require_teacher_login,
    resume_account,
    share_archives_enabled,
    stop_account,
    submission_allowed,
    update_access_settings,
    viewable_classes,
)
from news_app.admin_auth import (
    check_admin_password_attempt,
    clear_admin_session,
    configure_session_cookie,
)
from news_app.config import (
    AI_MODELS,
    CEFR_LEVELS,
    DISPLAY_LANGUAGES,
    VOCAB_MIN_CEFR_LEVELS,
    admin_password_matches,
    get_admin_password,
    get_openai_api_key,
    mask_api_key,
    resolve_ai_model,
    resolve_cefr_level,
    resolve_display_language,
    resolve_eval_ai_model,
    resolve_transcript_ai_model,
    resolve_vocab_min_cefr,
    save_openai_api_key,
)
from news_app.services.cnn10 import fetch_cnn10_episodes
from news_app.services.cnn10_highlight import find_title_segment_in_transcript
from news_app.services.cnn10_library import get_library_status, search_episodes, start_update_job
from news_app.services.cnn10_embeddings import get_embedding_status, semantic_search, start_embedding_job
from news_app.services.network import get_public_base_url
from news_app.services.docx_translate import (
    build_lesson_materials_docx,
    build_script_translation_docx,
    translation_rows,
)
from news_app.services.openai_translate import translate_script
from news_app.services.openai_vocab import extract_vocabulary_from_script
from news_app.services.openai_warmup import extract_warmup_from_script
from news_app.services.openai_postview import extract_postview_from_script
from news_app.services.openai_writing import extract_writing_topics_from_script
from news_app.services.storage import (
    DEFAULT_EVALUATION_CRITERIA,
    archive_class_current,
    copy_class_archive,
    current_lesson_identity,
    create_class,
    delete_class_archive,
    delete_submission,
    SAMPLE_CLASS_DISPLAY_NAME,
    SAMPLE_CLASS_NAME,
    find_class_by_name,
    get_active_class_id,
    get_archive_item,
    get_class,
    get_roster,
    get_submission,
    get_submissions,
    import_roster_from_excel,
    load_state,
    reset_class_current,
    restore_class_archive,
    set_archive_in_use,
    extract_score_breakdown,
    lesson_key,
    lesson_title_display,
    score_only_feedback,
    set_active_class,
    update_class_current,
    update_settings,
    update_submission_lesson_title,
    _normalize_script_ja_pairs,
    _normalize_vocabulary_data,
    _normalize_warmup_questions,
    _normalize_writing_topics,
    appearance_context,
    selected_display_questions,
)
from news_app.services.pdf_report import build_submissions_pdf
from news_app.services.youtube import extract_video_id, fetch_youtube_title, parse_time_to_seconds, seconds_to_display

admin_bp = Blueprint("news_admin", __name__)


@admin_bp.record_once
def _configure_admin_session(state):
    configure_session_cookie(state.app)


@admin_bp.route("/api/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    denied = attempt_login(payload)
    if denied:
        return denied
    role, actor = current_actor()
    return jsonify({"ok": True, "logged_in": True, "role": role, "teacher_id": actor if role == "teacher" else ""})


@admin_bp.route("/api/logout", methods=["POST"])
def admin_logout():
    clear_admin_session()
    return jsonify({"ok": True, "logged_in": False})


@admin_bp.route("/api/status", methods=["GET"])
def admin_status():
    if not get_admin_password():
        return jsonify({"ok": False, "logged_in": False, "error": "管理パスワードが設定されていません。"}), 503
    return jsonify(login_status_payload())


_OPEN_ADMIN_ENDPOINTS = frozenset(
    {
        "news_admin.admin_login",
        "news_admin.admin_logout",
        "news_admin.admin_status",
        "news_admin.web_app_manifest",
        "news_admin.admin_login_page",
    }
)

# 教員ログイン必須が OFF のときだけ、未ログインで使える CNN10 検索。
_CNN10_PUBLIC_ENDPOINTS = frozenset(
    {
        "news_admin.cnn10_episodes",
        "news_admin.cnn10_library_status",
        "news_admin.cnn10_library_search",
        "news_admin.cnn10_embeddings_status",
        "news_admin.cnn10_library_semantic_search",
    }
)

_OWNER_ONLY_ENDPOINTS = frozenset(
    {
        "news_admin.save_settings",
        "news_admin.appearance_settings",
        "news_admin.password_check",
        "news_admin.access_settings",
        "news_admin.teacher_account_issue",
        "news_admin.teacher_account_stop",
        "news_admin.teacher_account_resume",
        "news_admin.teacher_account_delete",
    }
)

_MANAGE_CLASS_ENDPOINTS = frozenset(
    {
        "news_admin.api_save_lesson",
        "news_admin.api_translate_lesson_script",
        "news_admin.api_export_lesson_script_translation_docx",
        "news_admin.api_extract_lesson_vocabulary",
        "news_admin.api_update_lesson_vocabulary_selection",
        "news_admin.api_toggle_vocabulary_scaffolding",
        "news_admin.api_toggle_translation_scaffolding",
        "news_admin.api_generate_warmup",
        "news_admin.api_update_warmup_selection",
        "news_admin.api_toggle_warmup_scaffolding",
        "news_admin.api_generate_postview",
        "news_admin.api_update_postview_selection",
        "news_admin.api_toggle_postview_scaffolding",
        "news_admin.api_toggle_postview_answers",
        "news_admin.api_generate_writing_topics",
        "news_admin.api_update_writing_selection",
        "news_admin.api_export_lesson_materials_docx",
        "news_admin.api_archive_lesson",
        "news_admin.api_reset_lesson",
        "news_admin.api_restore_archive_lesson",
        "news_admin.api_delete_archive_lesson",
        "news_admin.api_set_archive_in_use",
        "news_admin.api_select_class",
        "news_admin.upload_roster",
        "news_admin.get_roster_api",
        "news_admin.list_submissions",
        "news_admin.export_submissions",
    }
)

_VIEW_CLASS_ENDPOINTS = frozenset(
    {
        "news_admin.api_get_class",
        "news_admin.list_class_lessons",
        "news_admin.share_link",
        "news_admin.screen_link",
        "news_admin.screen_qr",
    }
)


def _wants_admin_json() -> bool:
    path = request.path or ""
    if "/admin/api/" in path:
        return True
    json_ok = request.accept_mimetypes["application/json"]
    html_ok = request.accept_mimetypes["text/html"]
    return json_ok > 0 and json_ok >= html_ok


def _request_class_id() -> str:
    if request.view_args and request.view_args.get("class_id"):
        return str(request.view_args.get("class_id") or "").strip()
    if request.method == "GET":
        return str(request.args.get("class_id") or "").strip()
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and data.get("class_id"):
        return str(data.get("class_id") or "").strip()
    if request.form:
        return str(request.form.get("class_id") or "").strip()
    return ""


def _owner_required():
    if is_owner_session():
        return None
    return jsonify({"ok": False, "error": "所有者だけが操作できます。"}), 403


@admin_bp.before_request
def require_admin_session():
    if request.method == "OPTIONS":
        return None
    endpoint = request.endpoint
    if endpoint in _OPEN_ADMIN_ENDPOINTS:
        return None

    if endpoint == "news_admin.admin_index":
        role, _actor = current_actor()
        if role:
            return None
        if not get_admin_password():
            return "管理パスワードが設定されていません。", 503
        if require_teacher_login():
            return redirect(url_for("news_admin.admin_login_page"))
        return None

    if endpoint in _CNN10_PUBLIC_ENDPOINTS and not require_teacher_login():
        return None

    role, _actor = current_actor()
    if not role:
        if not get_admin_password():
            body = {"ok": False, "error": "管理パスワードが設定されていません。"}
            if _wants_admin_json():
                return jsonify(body), 503
            return "管理パスワードが設定されていません。", 503
        if _wants_admin_json():
            return jsonify({"ok": False, "error": "ログインが必要です。"}), 401
        return redirect(url_for("news_admin.admin_login_page"))

    if endpoint in _OWNER_ONLY_ENDPOINTS:
        denied = _owner_required()
        if denied:
            return denied

    if endpoint in _MANAGE_CLASS_ENDPOINTS or endpoint in _VIEW_CLASS_ENDPOINTS:
        class_id = _request_class_id()
        if endpoint in {"news_admin.list_submissions", "news_admin.export_submissions"} and not class_id:
            return None
        if not class_id:
            class_id = get_active_class_id()
        if not class_id:
            return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400
        return deny_class(class_id, manage=endpoint in _MANAGE_CLASS_ENDPOINTS)
    return None


@admin_bp.route("/manifest.json")
def web_app_manifest():
    """管理画面用 PWA。start_url を /news/admin/ に固定する。"""
    response = send_from_directory(
        Path(current_app.static_folder) / "news" / "admin",
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _active_class_or_none():
    class_id = get_active_class_id()
    if not class_id:
        return None, None
    return class_id, get_class(class_id)


@admin_bp.route("/api/cnn10/episodes", methods=["GET"])
def cnn10_episodes():
    try:
        offset = int(request.args.get("offset") or 0)
        limit = int(request.args.get("limit") or 10)
        data = fetch_cnn10_episodes(offset=offset, limit=limit)
        return jsonify({"ok": True, **data})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@admin_bp.route("/api/youtube/highlight", methods=["POST"])
def youtube_highlight():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    snippets = data.get("snippets") or []
    if not title:
        return jsonify({"ok": False, "error": "タイトルが必要です。"}), 400
    if not isinstance(snippets, list) or not snippets:
        return jsonify({"ok": False, "error": "文字起こしデータが必要です。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": True,
                "highlight": {
                    "ok": False,
                    "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
                },
            }
        )

    state = load_state()
    model = resolve_transcript_ai_model(state.get("ai_transcript_model"))
    try:
        highlight = find_title_segment_in_transcript(
            title,
            snippets,
            model=model,
            api_key=api_key,
        )
    except ValueError as exc:
        highlight = {"ok": False, "error": str(exc)}
    except Exception as exc:
        highlight = {"ok": False, "error": f"区間推定に失敗しました: {exc}"}

    return jsonify({"ok": True, "highlight": highlight})


@admin_bp.route("/api/cnn10/library/status", methods=["GET"])
def cnn10_library_status():
    return jsonify({"ok": True, **get_library_status()})


@admin_bp.route("/api/cnn10/library/update", methods=["POST"])
def cnn10_library_update():
    data = request.get_json(silent=True) or {}
    mode = "full" if data.get("mode") == "full" else "diff"
    try:
        result = start_update_job(mode)
    except OSError as exc:
        return jsonify({"ok": False, "error": f"更新を開始できませんでした: {exc}"}), 500
    return jsonify({"ok": True, **result}), 202 if result.get("started") else 200


@admin_bp.route("/api/cnn10/library/search", methods=["GET"])
def cnn10_library_search():
    query = str(request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    return jsonify({"ok": True, **search_episodes(query, limit=limit)})


@admin_bp.route("/api/cnn10/library/embeddings/init", methods=["POST"])
def cnn10_embeddings_init():
    try:
        result = start_embedding_job()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except OSError as exc:
        return jsonify({"ok": False, "error": f"意味検索の準備を開始できませんでした: {exc}"}), 500
    return jsonify({"ok": True, **result}), 202 if result.get("started") else 200


@admin_bp.route("/api/cnn10/library/embeddings/status", methods=["GET"])
def cnn10_embeddings_status():
    return jsonify({"ok": True, **get_embedding_status()})


@admin_bp.route("/api/cnn10/library/search/semantic", methods=["GET"])
def cnn10_library_semantic_search():
    query = str(request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit") or 10)
    except ValueError:
        limit = 10
    try:
        since_year = int(request.args.get("since") or 0) or None
    except ValueError:
        since_year = None
    try:
        return jsonify({"ok": True, **semantic_search(query, limit=limit, since_year=since_year)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("cnn10 semantic search failed")
        return jsonify({"ok": False, "error": f"意味検索に失敗しました: {exc}"}), 502


@admin_bp.route("/login")
def admin_login_page():
    role, _actor = current_actor()
    if role:
        return redirect(url_for("news_admin.admin_index"))
    return render_template("news/admin_login.html", require_teacher_login=require_teacher_login())


@admin_bp.route("/")
def admin_index():
    role, actor = current_actor()
    state = load_state()
    state = {
        **state,
        "ai_model": resolve_ai_model(state.get("ai_model")),
        "ai_transcript_model": resolve_transcript_ai_model(state.get("ai_transcript_model")),
        "ai_eval_model": resolve_eval_ai_model(
            state.get("ai_eval_model"),
            fallback=resolve_ai_model(state.get("ai_model")),
        ),
        "default_cefr_level": resolve_cefr_level(state.get("default_cefr_level")),
    }
    classes = viewable_classes() if role else []
    submission_classes = managed_classes() if role else []
    class_id, cls = _active_class_or_none()
    managed_ids = {c["id"] for c in submission_classes}
    for item in classes:
        item["can_manage"] = item["id"] in managed_ids
    if class_id not in managed_ids:
        class_id, cls = ("", None)
        if submission_classes:
            class_id = submission_classes[0]["id"]
            cls = get_class(class_id)
    sample_readonly = False
    if not role:
        state = {
            **state,
            "openai_api_key": "",
        }
        cls = None
        class_id = ""
        classes = []
        submission_classes = []
        if not require_teacher_login():
            sample = find_class_by_name(SAMPLE_CLASS_NAME)
            if sample:
                preview = deepcopy(sample)
                preview["name"] = SAMPLE_CLASS_DISPLAY_NAME
                cls = preview
                class_id = preview["id"]
                listed = {
                    "id": preview["id"],
                    "name": SAMPLE_CLASS_DISPLAY_NAME,
                    "can_manage": False,
                }
                classes = [listed]
                submission_classes = [listed]
                sample_readonly = True
    current = (cls or {}).get("current") or {}
    api_key_configured = bool(get_openai_api_key()) and role == "owner"
    is_owner = role == "owner"

    return render_template(
        "news/admin.html",
        state=state,
        classes=classes,
        active_class_id=class_id,
        active_class=cls,
        current=current,
        cefr_levels=CEFR_LEVELS,
        vocab_min_cefr_levels=VOCAB_MIN_CEFR_LEVELS,
        display_languages=DISPLAY_LANGUAGES,
        ai_models=AI_MODELS,
        default_criteria=state.get("default_evaluation_criteria") or DEFAULT_EVALUATION_CRITERIA,
        start_time_display=seconds_to_display(int(current.get("start_seconds") or 0)),
        end_time_display=seconds_to_display(int(current.get("end_seconds") or 0)),
        api_key_configured=api_key_configured,
        api_key_masked=mask_api_key(state.get("openai_api_key") or "") if is_owner else "",
        is_owner=is_owner,
        is_logged_in=bool(role),
        actor_label=actor or "",
        submission_classes=submission_classes,
        require_teacher_login=require_teacher_login(),
        share_archives=share_archives_enabled() if role else False,
        sample_readonly=sample_readonly,
        sample_class_label=SAMPLE_CLASS_DISPLAY_NAME if sample_readonly else "",
        login_url=url_for("news_admin.admin_login_page"),
        **appearance_context(state),
    )


def _admin_password_denied():
    if not get_admin_password():
        return jsonify({"ok": False, "error": "管理パスワードが設定されていません。"}), 503
    return jsonify({"ok": False, "error": "管理設定のパスワードが違います。"}), 403


@admin_bp.route("/api/access-settings", methods=["GET", "POST"])
def access_settings():
    if request.method == "GET":
        return jsonify(
            {
                "ok": True,
                "require_teacher_login": require_teacher_login(),
                "share_archives": share_archives_enabled(),
                "accounts": public_accounts(),
                "login_url": request.url_root.rstrip("/") + url_for("news_admin.admin_login_page"),
            }
        )
    data = request.get_json(silent=True) or {}
    updated = update_access_settings(
        require_login=data.get("require_teacher_login") if "require_teacher_login" in data else None,
        share_archives=data.get("share_archives") if "share_archives" in data else None,
    )
    return jsonify({"ok": True, **updated})


@admin_bp.route("/api/teachers", methods=["POST"])
def teacher_account_issue():
    data = request.get_json(silent=True) or {}
    account, error = issue_account(str(data.get("id") or ""), data.get("password") if isinstance(data.get("password"), str) else "")
    if error:
        return jsonify({"ok": False, "error": error}), 400
    login_url = request.url_root.rstrip("/") + url_for("news_admin.admin_login_page")
    return jsonify(
        {
            "ok": True,
            "account": {
                "id": account["id"],
                "password": account.get("password") or "",
                "created_at": account["created_at"],
                "disabled": False,
            },
            "copy_text": copy_login_text(account["id"], account.get("password") or "", login_url),
            "accounts": public_accounts(),
            "login_url": login_url,
        }
    )


@admin_bp.route("/api/teachers/stop", methods=["POST"])
def teacher_account_stop():
    data = request.get_json(silent=True) or {}
    account, error = stop_account(str(data.get("id") or ""))
    if error:
        return jsonify({"ok": False, "error": error}), 404
    return jsonify({"ok": True, "accounts": public_accounts(), "id": account["id"], "disabled": True})


@admin_bp.route("/api/teachers/resume", methods=["POST"])
def teacher_account_resume():
    data = request.get_json(silent=True) or {}
    account, error = resume_account(str(data.get("id") or ""))
    if error:
        return jsonify({"ok": False, "error": error}), 404
    return jsonify({"ok": True, "accounts": public_accounts(), "id": account["id"], "disabled": False})


@admin_bp.route("/api/teachers/delete", methods=["POST"])
def teacher_account_delete():
    data = request.get_json(silent=True) or {}
    error = delete_account(str(data.get("id") or ""))
    if error:
        return jsonify({"ok": False, "error": error}), 404
    return jsonify({"ok": True, "accounts": public_accounts()})


@admin_bp.route("/api/password-check", methods=["POST"])
def password_check():
    data = request.get_json(silent=True) or {}
    denied = check_admin_password_attempt(
        data.get("admin_password"),
        matches=admin_password_matches,
        configured=get_admin_password,
    )
    if denied:
        return denied
    return jsonify({"ok": True})


@admin_bp.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json(silent=True) or {}
    try:
        openai_api_key = str(data.get("openai_api_key", "")).strip()
        if not openai_api_key:
            openai_api_key = (load_state().get("openai_api_key") or "").strip()
            if not openai_api_key:
                openai_api_key = get_openai_api_key()

        default_criteria = data.get("default_evaluation_criteria")
        kwargs = {
            "display_language": resolve_display_language(data.get("display_language")),
            "ai_model": resolve_ai_model(data.get("ai_model")),
            "ai_transcript_model": resolve_transcript_ai_model(data.get("ai_transcript_model")),
            "ai_eval_model": resolve_eval_ai_model(
                data.get("ai_eval_model"),
                fallback=resolve_ai_model(data.get("ai_model")),
            ),
            "default_cefr_level": resolve_cefr_level(data.get("default_cefr_level")),
            "openai_api_key": openai_api_key,
        }
        if "background_id" in data:
            kwargs["background_id"] = data.get("background_id")
        if "background_opacity" in data:
            kwargs["background_opacity"] = data.get("background_opacity")
        if isinstance(default_criteria, dict):
            kwargs["default_evaluation_criteria"] = default_criteria

        state = update_settings(**kwargs)

        if openai_api_key:
            save_openai_api_key(openai_api_key)

        return jsonify(
            {
                "ok": True,
                "state": {**state, "openai_api_key": mask_api_key(state.get("openai_api_key", ""))},
                "api_key_configured": bool(openai_api_key),
                **appearance_context(state),
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/appearance", methods=["GET", "POST"])
def appearance_settings():
    if request.method == "GET":
        return jsonify({"ok": True, **appearance_context()})

    data = request.get_json(silent=True) or {}
    try:
        updates = {}
        if "background_id" in data:
            updates["background_id"] = data.get("background_id")
        if "background_opacity" in data:
            updates["background_opacity"] = data.get("background_opacity")
        state = update_settings(**updates) if updates else load_state()
        return jsonify({"ok": True, **appearance_context(state)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/classes", methods=["GET"])
def api_list_classes():
    classes = viewable_classes()
    managed_ids = {c["id"] for c in managed_classes()}
    for item in classes:
        item["can_manage"] = item["id"] in managed_ids
    active = get_active_class_id()
    if active not in managed_ids:
        active = next(iter(managed_ids), "")
    return jsonify(
        {
            "ok": True,
            "classes": classes,
            "active_class_id": active,
            "share_archives": share_archives_enabled(),
        }
    )


@admin_bp.route("/api/classes", methods=["POST"])
def api_create_class():
    data = request.get_json(silent=True) or {}
    try:
        cls = create_class(str(data.get("name", "")).strip(), created_by=actor_id() or "owner")
        return jsonify({"ok": True, "class": cls, "active_class_id": cls["id"]})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/classes/<class_id>", methods=["GET"])
def api_get_class(class_id):
    """閲覧専用。現在のクラスは変えない。"""
    return jsonify(
        {
            "ok": True,
            "class": get_class(class_id),
            "can_manage": can_manage_class(class_id),
        }
    )


@admin_bp.route("/api/classes/select", methods=["POST"])
def api_select_class():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id", "")).strip()
    try:
        set_active_class(class_id)
        cls = get_class(class_id)
        return jsonify({"ok": True, "active_class_id": class_id, "class": cls})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@admin_bp.route("/api/class/lesson", methods=["POST"])
def api_save_lesson():
    """選択中クラスの動画・スクリプト・評価基準・タイマー設定を保存。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    url = (data.get("url") or "").strip()
    script = (data.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    try:
        video_id = extract_video_id(url) if url else ""
        if not video_id:
            return jsonify({"ok": False, "error": "YouTube URL または動画 ID を入力してください。"}), 400

        start_sec = parse_time_to_seconds(data.get("start_time", ""))
        end_sec = parse_time_to_seconds(data.get("end_time", ""))
        if start_sec >= end_sec:
            return jsonify({"ok": False, "error": "終了時間は開始時間より後にしてください。"}), 400

        criteria = data.get("evaluation_criteria")
        if not isinstance(criteria, dict):
            criteria = {}

        prep_sec = max(0, int(data.get("prep_timer_seconds") or 0))
        record_sec = max(0, int(data.get("record_timer_seconds") or 60))
        timers_visible = bool(data.get("timers_visible", True))
        subtitles_enabled = bool(data.get("subtitles_enabled", False))
        require_student_info = bool(data.get("require_student_info", False))
        vocabulary_scaffolding_enabled = bool(data.get("vocabulary_scaffolding_enabled", False))
        vocabulary_min_cefr = resolve_vocab_min_cefr(data.get("vocabulary_min_cefr"))
        translation_scaffolding_enabled = bool(data.get("translation_scaffolding_enabled", False))

        existing = (get_class(class_id) or {}).get("current") or {}
        existing_script = str(existing.get("script") or "").strip()
        script_ja = str(data.get("script_ja") if "script_ja" in data else existing.get("script_ja") or "").strip()
        if "script_ja_pairs" in data:
            script_ja_pairs = data.get("script_ja_pairs")
        else:
            script_ja_pairs = existing.get("script_ja_pairs") or []
        script_es = str(data.get("script_es") if "script_es" in data else existing.get("script_es") or "").strip()
        if "script_es_pairs" in data:
            script_es_pairs = data.get("script_es_pairs")
        else:
            script_es_pairs = existing.get("script_es_pairs") or []
        title = str(data.get("title") or "").strip()
        if not title:
            title = fetch_youtube_title(url or video_id)
        if "lesson_name" in data:
            lesson_name = str(data.get("lesson_name") or "").strip()
        else:
            lesson_name = str(existing.get("lesson_name") or "").strip()
        lesson_payload: dict = {
            "source_url": url,
            "video_id": video_id,
            "title": title,
            "lesson_name": lesson_name,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "script": script,
            "script_ja": script_ja,
            "script_ja_pairs": script_ja_pairs,
            "script_es": script_es,
            "script_es_pairs": script_es_pairs,
            "evaluation_criteria": criteria,
            "prep_timer_seconds": prep_sec,
            "record_timer_seconds": record_sec,
            "timers_visible": timers_visible,
            "subtitles_enabled": subtitles_enabled,
            "vocabulary_scaffolding_enabled": vocabulary_scaffolding_enabled,
            "vocabulary_min_cefr": vocabulary_min_cefr,
            "translation_scaffolding_enabled": translation_scaffolding_enabled,
        }
        if existing_script and existing_script != script:
            lesson_payload["vocabulary_data"] = []
            if "script_ja" not in data:
                lesson_payload["script_ja"] = ""
                lesson_payload["script_ja_pairs"] = []
            if "script_es" not in data:
                lesson_payload["script_es"] = ""
                lesson_payload["script_es_pairs"] = []

        cls = update_class_current(
            class_id,
            lesson_payload,
            require_student_info=require_student_info,
        )
        if title:
            update_submission_lesson_title(
                class_id,
                lesson_key(video_id, start_sec, end_sec),
                title,
            )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "message": f"「{cls['name']}」の授業設定を保存しました（スクリプト {len(script)} 文字）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/translate", methods=["POST"])
def api_translate_lesson_script():
    """指定した英語スクリプトの対訳を生成し、授業レコードに保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    current = cls.get("current") or {}
    script = str(data.get("script") or current.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
            }
        ), 400

    state = load_state()
    model = resolve_ai_model(state.get("ai_model"))
    target_lang = resolve_display_language(data.get("target_lang") or state.get("display_language"))
    if target_lang == "en":
        target_lang = "ja"
    try:
        translated = translate_script(script, api_key=api_key, model=model, target_lang=target_lang)
        script_translation = str(translated.get("script_translation") or "").strip()
        pairs = translated.get("pairs") or []
        if target_lang == "es":
            update_fields = {
                "script": script,
                "script_es": script_translation,
                "script_es_pairs": pairs,
            }
        else:
            update_fields = {
                "script": script,
                "script_ja": script_translation,
                "script_ja_pairs": pairs,
            }
        cls = update_class_current(class_id, update_fields)
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "target_lang": target_lang,
                "script_ja": script_translation if target_lang != "es" else str((cls.get("current") or {}).get("script_ja") or ""),
                "script_ja_pairs": pairs if target_lang != "es" else (cls.get("current") or {}).get("script_ja_pairs") or [],
                "script_es": script_translation if target_lang == "es" else str((cls.get("current") or {}).get("script_es") or ""),
                "script_es_pairs": pairs if target_lang == "es" else (cls.get("current") or {}).get("script_es_pairs") or [],
                "script_translation": script_translation,
                "pairs": pairs,
                "message": f"対訳を作成して保存しました（{len(script_translation)} 文字）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"対訳の作成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/translate/docx", methods=["POST"])
def api_export_lesson_script_translation_docx():
    """原文と和訳を Word（.docx）でダウンロードする。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    title = str(data.get("title") or "").strip()
    pairs = _normalize_script_ja_pairs(data.get("pairs"))
    script = str(data.get("script") or "").strip()
    script_ja = str(data.get("script_ja") or "").strip()

    cls = get_class(class_id) if class_id else None
    current = (cls or {}).get("current") or {}
    if not title:
        title = str(current.get("title") or "").strip()
    if not pairs:
        pairs = translation_rows(
            script or str(current.get("script") or ""),
            script_ja or str(current.get("script_ja") or ""),
            current.get("script_ja_pairs"),
        )

    if not pairs:
        return jsonify({"ok": False, "error": "原文と和訳がありません。先に和訳を作成してください。"}), 400

    try:
        buf = io.BytesIO(build_script_translation_docx(title=title, pairs=pairs))
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name="original_and_translation.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Word の作成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/vocabulary", methods=["POST"])
def api_extract_lesson_vocabulary():
    """英語スクリプトから語彙を AI 抽出し、授業レコードに保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    current = cls.get("current") or {}
    script = str(data.get("script") or current.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
            }
        ), 400

    state = load_state()
    model = resolve_ai_model(state.get("ai_model"))
    min_cefr = resolve_vocab_min_cefr(data.get("min_cefr") or current.get("vocabulary_min_cefr"))
    try:
        vocabulary_data = extract_vocabulary_from_script(
            script, api_key=api_key, model=model, min_cefr=min_cefr
        )
        cls = update_class_current(
            class_id,
            {
                "script": script,
                "vocabulary_data": vocabulary_data,
                "vocabulary_min_cefr": min_cefr,
            },
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "vocabulary_data": vocabulary_data,
                "vocabulary_min_cefr": min_cefr,
                "message": f"語彙 {len(vocabulary_data)} 件を抽出して保存しました（{min_cefr}以上）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"語彙抽出に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/vocabulary/selection", methods=["POST"])
def api_update_lesson_vocabulary_selection():
    """抽出語彙の表示/非表示（チェック状態）を保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    raw_items = data.get("vocabulary_data")
    if not isinstance(raw_items, list):
        return jsonify({"ok": False, "error": "語彙データが不正です。"}), 400

    if not get_class(class_id):
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    vocabulary_data = _normalize_vocabulary_data(raw_items)
    try:
        cls = update_class_current(class_id, {"vocabulary_data": vocabulary_data})
        selected_count = sum(1 for item in vocabulary_data if item.get("selected", True))
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "vocabulary_data": vocabulary_data,
                "message": f"語彙の表示設定を保存しました（表示 {selected_count} / {len(vocabulary_data)} 語）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/vocabulary/toggle", methods=["POST"])
def api_toggle_vocabulary_scaffolding():
    """生徒画面への語彙補助表示の on/off を切り替える。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    enabled = bool(data.get("vocabulary_scaffolding_enabled", False))
    try:
        cls = update_class_current(
            class_id,
            {"vocabulary_scaffolding_enabled": enabled},
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "vocabulary_scaffolding_enabled": enabled,
                "message": "語彙補助を有効にしました。" if enabled else "語彙補助を無効にしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/translation/toggle", methods=["POST"])
def api_toggle_translation_scaffolding():
    """生徒画面への和訳表示の on/off を切り替える。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    enabled = bool(data.get("translation_scaffolding_enabled", False))
    try:
        cls = update_class_current(
            class_id,
            {"translation_scaffolding_enabled": enabled},
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "translation_scaffolding_enabled": enabled,
                "message": "和訳を生徒画面に表示します。" if enabled else "和訳を生徒画面から非表示にしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/warmup", methods=["POST"])
def api_generate_warmup():
    """スクリプトからウォームアップ画像と質問5問を生成してレコードに保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    current = cls.get("current") or {}
    script = str(data.get("script") or current.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
            }
        ), 400

    state = load_state()
    model = resolve_ai_model(state.get("ai_model"))
    try:
        result = extract_warmup_from_script(script, api_key=api_key, model=model)
        cls = update_class_current(
            class_id,
            {
                "warmup_image_url": result["image_url"],
                "warmup_questions": result["questions"],
            },
        )
        has_image = bool(result["image_url"])
        q_count = len(result["questions"])
        if has_image:
            msg = f"イラストと質問 {q_count} 問を生成しました。"
        else:
            msg = (
                f"質問 {q_count} 問を生成しました。"
                "（イラスト生成はこのアカウントでは利用できないため省略されました）"
            )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "warmup_image_url": result["image_url"],
                "warmup_questions": result["questions"],
                "message": msg,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"ウォームアップの生成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/warmup/selection", methods=["POST"])
def api_update_warmup_selection():
    """ウォームアップ質問の表示/非表示（選択状態）を保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    raw_questions = data.get("warmup_questions")
    if not isinstance(raw_questions, list):
        return jsonify({"ok": False, "error": "質問データが不正です。"}), 400

    if not get_class(class_id):
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    warmup_questions = _normalize_warmup_questions(raw_questions)
    try:
        cls = update_class_current(class_id, {"warmup_questions": warmup_questions})
        selected_count = sum(1 for q in warmup_questions if q.get("selected", True))
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "warmup_questions": warmup_questions,
                "message": f"質問の表示設定を保存しました（表示 {selected_count} / {len(warmup_questions)} 問）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/warmup/toggle", methods=["POST"])
def api_toggle_warmup_scaffolding():
    """生徒画面へのウォームアップ表示の on/off を切り替える。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    enabled = bool(data.get("warmup_scaffolding_enabled", False))
    try:
        cls = update_class_current(
            class_id,
            {"warmup_scaffolding_enabled": enabled},
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "warmup_scaffolding_enabled": enabled,
                "message": "ウォームアップを有効にしました。" if enabled else "ウォームアップを無効にしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview", methods=["POST"])
def api_generate_postview():
    """スクリプトから視聴後の理解・会話質問5問を生成して保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    current = cls.get("current") or {}
    script = str(data.get("script") or current.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
            }
        ), 400

    state = load_state()
    model = resolve_ai_model(state.get("ai_model"))
    try:
        result = extract_postview_from_script(script, api_key=api_key, model=model)
        existing_manual = [
            q
            for q in _normalize_warmup_questions(current.get("postview_questions"))
            if q.get("manual")
        ]
        questions = result["questions"] + existing_manual
        cls = update_class_current(class_id, {"postview_questions": questions})
        q_count = len(result["questions"])
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "postview_questions": questions,
                "message": f"ディスカッション {q_count} 問と模範解答を生成しました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"ディスカッションの生成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview/selection", methods=["POST"])
def api_update_postview_selection():
    """ディスカッション質問の表示/非表示（選択状態）を保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    raw_questions = data.get("postview_questions")
    if not isinstance(raw_questions, list):
        return jsonify({"ok": False, "error": "質問データが不正です。"}), 400

    if not get_class(class_id):
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    postview_questions = _normalize_warmup_questions(raw_questions)
    try:
        cls = update_class_current(class_id, {"postview_questions": postview_questions})
        selected_count = sum(1 for q in postview_questions if q.get("selected", True))
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "postview_questions": postview_questions,
                "message": f"ディスカッションの表示設定を保存しました（表示 {selected_count} / {len(postview_questions)} 問）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview/toggle", methods=["POST"])
def api_toggle_postview_scaffolding():
    """生徒画面へのディスカッション表示の on/off を切り替える。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    enabled = bool(data.get("postview_scaffolding_enabled", False))
    try:
        cls = update_class_current(
            class_id,
            {"postview_scaffolding_enabled": enabled},
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "postview_scaffolding_enabled": enabled,
                "message": "ディスカッションを有効にしました。" if enabled else "ディスカッションを無効にしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview/answers", methods=["POST"])
def api_toggle_postview_answers():
    """生徒画面にディスカッションの模範解答を出すかどうかを保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    enabled = bool(data.get("postview_answers_visible", False))
    try:
        cls = update_class_current(
            class_id,
            {"postview_answers_visible": enabled},
        )
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "postview_answers_visible": enabled,
                "message": (
                    "生徒画面に模範解答を表示します。"
                    if enabled
                    else "生徒画面では模範解答を隠し、質問だけ表示します。"
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/writing", methods=["POST"])
def api_generate_writing_topics():
    """スクリプトから OREO ライティング／スピーチ用トピック5つを生成して保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    cls = get_class(class_id)
    if not cls:
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    current = cls.get("current") or {}
    script = str(data.get("script") or current.get("script") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "文字起こし（スクリプト）を入力してください。"}), 400

    api_key = get_openai_api_key()
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "OpenAI API キーが未設定です。管理画面の設定からキーを保存してください。",
            }
        ), 400

    state = load_state()
    model = resolve_ai_model(state.get("ai_model"))
    try:
        result = extract_writing_topics_from_script(script, api_key=api_key, model=model)
        existing_manual = [
            topic
            for topic in _normalize_writing_topics(current.get("writing_topics"))
            if topic.get("manual")
        ]
        topics = result["topics"] + existing_manual
        cls = update_class_current(class_id, {"writing_topics": topics})
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "writing_topics": cls["current"]["writing_topics"],
                "message": "ライティングトピックを5つ生成しました。スクリーンに出すものにチェックを入れてください。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"ライティングトピックの生成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/writing/selection", methods=["POST"])
def api_update_writing_selection():
    """ライティングトピックの選択（スクリーン表示）と文言の編集を保存する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択または作成してください。"}), 400

    raw_topics = data.get("writing_topics")
    if not isinstance(raw_topics, list):
        return jsonify({"ok": False, "error": "トピックデータが不正です。"}), 400

    if not get_class(class_id):
        return jsonify({"ok": False, "error": "クラスが見つかりません。"}), 404

    topics = _normalize_writing_topics(raw_topics)
    try:
        cls = update_class_current(class_id, {"writing_topics": topics})
        selected_count = sum(1 for topic in topics if topic["selected"])
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "writing_topics": cls["current"]["writing_topics"],
                "message": f"ライティングトピックを保存しました（スクリーン表示 {selected_count} / {len(topics)}）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/materials/docx", methods=["POST"])
def api_export_lesson_materials_docx():
    """文字起こし・和訳・語彙・ウォームアップ/ディスカッションを選んで Word 出力する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    include = data.get("include") if isinstance(data.get("include"), dict) else {}
    title = str(data.get("title") or "").strip()
    lesson_name = str(data.get("lesson_name") or "").strip()
    script = str(data.get("script") or "").strip()
    script_ja = str(data.get("script_ja") or "").strip()
    pairs = _normalize_script_ja_pairs(data.get("pairs"))

    cls = get_class(class_id) if class_id else None
    current = (cls or {}).get("current") or {}
    if not title:
        title = str(current.get("title") or "").strip()
    if not lesson_name:
        lesson_name = str(current.get("lesson_name") or "").strip()
    if not script:
        script = str(current.get("script") or "").strip()
    if not script_ja:
        script_ja = str(current.get("script_ja") or "").strip()
    if not pairs:
        pairs = translation_rows(script, script_ja, current.get("script_ja_pairs"))

    raw_vocab = data.get("vocabulary_data")
    if isinstance(raw_vocab, list):
        vocabulary = [
            item
            for item in _normalize_vocabulary_data(raw_vocab)
            if item.get("selected", True)
        ]
    else:
        vocabulary = [
            item
            for item in _normalize_vocabulary_data(current.get("vocabulary_data"))
            if item.get("selected", True)
        ]

    raw_warmup = data.get("warmup_questions")
    if isinstance(raw_warmup, list):
        warmup_questions = selected_display_questions(raw_warmup)
    else:
        warmup_questions = selected_display_questions(current.get("warmup_questions"))

    raw_postview = data.get("postview_questions")
    if isinstance(raw_postview, list):
        postview_questions = selected_display_questions(raw_postview)
    else:
        postview_questions = selected_display_questions(current.get("postview_questions"))

    try:
        buf = io.BytesIO(
            build_lesson_materials_docx(
                lesson_name=lesson_name,
                title=title,
                script=script,
                pairs=pairs,
                vocabulary=vocabulary,
                warmup_questions=warmup_questions,
                postview_questions=postview_questions,
                include=include,
            )
        )
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name="lesson_materials.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Word の作成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/archive", methods=["POST"])
def api_archive_lesson():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    try:
        title = str(data.get("title") or "").strip()
        lesson_name = str(data.get("lesson_name") or "").strip()
        current = (get_class(class_id) or {}).get("current") or {}
        if not title:
            title = str(current.get("title") or "").strip()
        if not title:
            title = fetch_youtube_title(current.get("source_url") or current.get("video_id") or "")
        if not lesson_name:
            lesson_name = str(current.get("lesson_name") or "").strip()
        cls = archive_class_current(class_id, title, lesson_name, created_by=actor_id() or "owner")
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "message": f"「{cls['name']}」の授業をアーカイブしました。新しい動画を設定できます。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"アーカイブに失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/reset", methods=["POST"])
def api_reset_lesson():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    try:
        cls = reset_class_current(class_id)
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "message": "現在の授業設定をリセットしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"リセットに失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/archive/restore", methods=["POST"])
def api_restore_archive_lesson():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    try:
        archive_index = int(data.get("archive_index", -1))
        cls = restore_class_archive(class_id, archive_index)
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "message": f"「{cls['name']}」の設定画面にアーカイブを戻しました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"復元に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/archive/delete", methods=["POST"])
def api_delete_archive_lesson():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    try:
        archive_index = int(data.get("archive_index", -1))
        cls = delete_class_archive(class_id, archive_index)
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "message": "アーカイブを削除しました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"削除に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/archive/copy", methods=["POST"])
def api_copy_archive_lesson():
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    target_class_id = str(data.get("target_class_id") or "").strip()
    try:
        archive_index = int(data.get("archive_index", -1))
        source_denied = deny_class(class_id, manage=False)
        if source_denied:
            return source_denied
        target_denied = deny_class(target_class_id, manage=True)
        if target_denied:
            return target_denied
        source_cls, target_cls = copy_class_archive(
            class_id, archive_index, target_class_id, created_by=actor_id() or "owner"
        )
        return jsonify(
            {
                "ok": True,
                "class": source_cls,
                "target_class": target_cls,
                "message": f"「{target_cls['name']}」へアーカイブをコピーしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"コピーに失敗しました: {exc}"}), 500


@admin_bp.route("/api/share-link", methods=["GET"])
def share_link():
    state = load_state()
    default_level = resolve_cefr_level(state.get("default_cefr_level"))
    level = resolve_cefr_level(request.args.get("level"), fallback=default_level)
    class_id = (request.args.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択してください。"}), 400

    base = get_public_base_url(request)
    link = f"{base}/news/?class={class_id}&level={level}"
    return jsonify({"ok": True, "link": link, "level": level, "class_id": class_id})


@admin_bp.route("/api/screen-link", methods=["GET"])
def screen_link():
    class_id = (request.args.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択してください。"}), 400

    archive_id = (request.args.get("archive_id") or "").strip()
    base = get_public_base_url(request)
    if archive_id:
        if not get_archive_item(class_id, archive_id):
            return jsonify({"ok": False, "error": "指定されたアーカイブが見つかりません。"}), 404
        link = f"{base}/news/screen/?class={class_id}&archive={archive_id}"
    else:
        link = f"{base}/news/screen/?class={class_id}"
    return jsonify({"ok": True, "link": link, "class_id": class_id, "archive_id": archive_id})


@admin_bp.route("/api/screen-qr", methods=["GET"])
def screen_qr():
    """教室スクリーンのリンクを QR（PNG data URI）で返す。archive_id なしは授業設定中のリンク。"""
    class_id = (request.args.get("class_id") or get_active_class_id()).strip()
    if not class_id:
        return jsonify({"ok": False, "error": "クラスを選択してください。"}), 400

    archive_id = (request.args.get("archive_id") or "").strip()
    base = get_public_base_url(request)
    in_use = False
    if archive_id:
        item = get_archive_item(class_id, archive_id)
        if not item:
            return jsonify({"ok": False, "error": "指定されたアーカイブが見つかりません。"}), 404
        link = f"{base}/news/screen/?class={class_id}&archive={archive_id}"
        in_use = item.get("in_use") is True
    else:
        link = f"{base}/news/screen/?class={class_id}"
    try:
        import segno

        qr_image = segno.make(link, error="m").png_data_uri(scale=10, border=3)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"QRの生成に失敗しました: {exc}"}), 500
    return jsonify(
        {
            "ok": True,
            "link": link,
            "qr": qr_image,
            "class_id": class_id,
            "archive_id": archive_id,
            "in_use": in_use,
        }
    )


@admin_bp.route("/api/class/archive/in-use", methods=["POST"])
def api_set_archive_in_use():
    """QR / リンクを配布中のアーカイブに「使用中」印を付け外しする（使用中は削除不可）。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    archive_id = str(data.get("archive_id") or "").strip()
    in_use = data.get("in_use") is True
    try:
        cls = set_archive_in_use(class_id, archive_id, in_use)
        return jsonify(
            {
                "ok": True,
                "class": cls,
                "in_use": in_use,
                "message": (
                    "使用中にしました。解除するまでこのアーカイブは削除できません。"
                    if in_use
                    else "使用中を解除しました。削除できるようになりました。"
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


# ── 名簿アップロード ──────────────────────────────────────────

@admin_bp.route("/api/roster/upload", methods=["POST"])
def upload_roster():
    class_id = request.form.get("class_id", "").strip()
    if not class_id:
        return jsonify({"ok": False, "error": "class_id が必要です。"}), 400
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "ファイルが選択されていません。"}), 400
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": ".xlsx または .xls ファイルを選択してください。"}), 400
    try:
        students = import_roster_from_excel(class_id, file.read())
        return jsonify({"ok": True, "students": students, "count": len(students)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"読み込みエラー: {exc}"}), 500


@admin_bp.route("/api/roster/<class_id>", methods=["GET"])
def get_roster_api(class_id):
    return jsonify({"ok": True, "students": get_roster(class_id)})


# ── 提出結果一覧 ──────────────────────────────────────────────

def _lesson_options_for_class(class_id: str) -> list[dict]:
    cls = get_class(class_id)
    if not cls:
        return []
    options = []
    seen = set()

    for item in cls.get("archive") or []:
        key = lesson_key(item.get("video_id", ""), item.get("start_seconds", 0), item.get("end_seconds", 0))
        if key and key not in seen:
            options.append(
                {
                    "key": key,
                    "title": lesson_title_display(item.get("title", ""), item.get("video_id", ""), "無題のアーカイブ"),
                }
            )
            seen.add(key)

    current = current_lesson_identity(cls)
    if current["lesson_video_id"] and current["lesson_key"]:
        title = current["lesson_title"] or "現在の授業"
        if current["lesson_key"] not in seen:
            options.insert(0, {"key": current["lesson_key"], "title": title})
            seen.add(current["lesson_key"])
    return options


def _submission_with_lesson_display(submission: dict) -> dict:
    cls = get_class(submission.get("class_id", ""))
    submission_key = submission.get("lesson_key") or ""
    lesson_title = ""

    if cls and submission_key:
        for item in cls.get("archive") or []:
            key = lesson_key(item.get("video_id", ""), item.get("start_seconds", 0), item.get("end_seconds", 0))
            if key == submission_key:
                lesson_title = lesson_title_display(item.get("title", ""), item.get("video_id", ""), "無題のアーカイブ")
                break
        if not lesson_title:
            current = current_lesson_identity(cls)
            if current["lesson_key"] == submission_key:
                lesson_title = current["lesson_title"]

    if not lesson_title:
        lesson_title = lesson_title_display(
            submission.get("lesson_title", ""),
            submission.get("lesson_video_id", ""),
            "未分類",
        )
    return {**submission, "lesson_title": lesson_title}


@admin_bp.route("/api/class/lessons", methods=["GET"])
def list_class_lessons():
    class_id = request.args.get("class_id") or ""
    if not class_id:
        return jsonify({"ok": True, "lessons": []})
    return jsonify({"ok": True, "lessons": _lesson_options_for_class(class_id)})


def _filter_managed_submissions(submissions: list[dict]) -> list[dict]:
    allowed = {c["id"] for c in managed_classes()}
    return [s for s in submissions if s.get("class_id") in allowed]


@admin_bp.route("/api/submissions", methods=["GET"])
def list_submissions():
    class_id = request.args.get("class_id") or None
    lesson_key_filter = request.args.get("lesson_key") or None
    submissions = []
    for submission in _filter_managed_submissions(get_submissions(class_id)):
        submission = _submission_with_lesson_display(submission)
        if lesson_key_filter and submission.get("lesson_key") != lesson_key_filter:
            continue
        scores = extract_score_breakdown(submission.get("feedback", ""))
        submissions.append(
            {
                **submission,
                **scores,
                "feedback": score_only_feedback(submission.get("feedback", "")),
            }
        )
    return jsonify({"ok": True, "submissions": submissions})


@admin_bp.route("/api/submissions/<submission_id>", methods=["DELETE"])
def delete_submission_api(submission_id):
    denied = submission_allowed(submission_id)
    if denied:
        return denied
    ok = delete_submission(submission_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "データが見つかりません。"}), 404


@admin_bp.route("/api/submissions/export", methods=["GET"])
def export_submissions():
    """提出結果を Excel でダウンロード。?class_id=xxx で絞り込み可。"""
    class_id = request.args.get("class_id") or None
    lesson_key_filter = request.args.get("lesson_key") or None
    submissions = _filter_managed_submissions(get_submissions(class_id))
    submissions = [_submission_with_lesson_display(s) for s in submissions]
    if lesson_key_filter:
        submissions = [s for s in submissions if s.get("lesson_key") == lesson_key_filter]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "提出結果"
    headers = [
        "提出日時",
        "授業クラス",
        "HRクラス",
        "出席番号",
        "名前",
        "動画タイトル",
        "内容理解",
        "構成",
        "英語表現",
        "即興要約",
        "合計",
        "レベル",
        "文字起こし",
        "AIフィードバック",
    ]
    ws.append(headers)

    for submission in submissions:
        scores = extract_score_breakdown(submission.get("feedback", ""))
        ws.append(
            [
                submission.get("submitted_at", ""),
                submission.get("class_name", ""),
                submission.get("student_hr_class", ""),
                submission.get("student_number", ""),
                submission.get("student_name", ""),
                submission.get("lesson_title", "") or "未分類",
                scores.get("content_score", ""),
                scores.get("organization_score", ""),
                scores.get("language_score", ""),
                scores.get("speaking_summary_score", ""),
                scores.get("total_score", ""),
                submission.get("level", ""),
                submission.get("transcript", ""),
                score_only_feedback(submission.get("feedback", "")),
            ]
        )

    col_widths = [20, 15, 12, 8, 12, 24, 8, 8, 10, 10, 8, 8, 60, 80]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"submissions_{class_id or 'all'}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _submission_for_pdf(submission: dict) -> dict:
    submission = _submission_with_lesson_display(submission)
    scores = extract_score_breakdown(submission.get("feedback", ""))
    return {
        **submission,
        **scores,
        "feedback": score_only_feedback(submission.get("feedback", "")),
    }


def _ascii_safe_filename(value: str, fallback: str = "report") -> str:
    """Content-Disposition に安全に載せられる ASCII のみのファイル名断片を作る。

    日本語などの非ASCII文字はヘッダーエンコードに失敗して 500/502 の原因になるため、
    ASCII 範囲の英数字・-・_ のみを残し、それ以外は取り除く。
    """
    ascii_only = "".join(ch for ch in str(value or "") if ch.isascii() and (ch.isalnum() or ch in ("-", "_")))
    ascii_only = ascii_only[:40]
    return ascii_only or fallback


def _pdf_response(submissions: list[dict], *, download_name: str, inline: bool = False):
    pdf_bytes = build_submissions_pdf(submissions)
    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    # download_name は ASCII のみのファイル名を渡す前提。send_file が
    # as_attachment に応じて Content-Disposition (inline/attachment) を
    # 安全に設定するため、ここで手動でヘッダーを上書きしない。
    return send_file(
        buf,
        as_attachment=not inline,
        download_name=download_name,
        mimetype="application/pdf",
    )


@admin_bp.route("/api/submissions/<submission_id>/pdf", methods=["GET"])
def export_submission_pdf(submission_id):
    """個別提出の評価帳票 PDF（ブラウザ表示用）。"""
    try:
        denied = submission_allowed(submission_id)
        if denied:
            return denied
        submission = get_submission(submission_id)
        safe_name = _ascii_safe_filename(submission.get("student_name"), fallback="student")
        return _pdf_response(
            [_submission_for_pdf(submission)],
            download_name=f"vibe_speak_news_{safe_name}.pdf",
            inline=True,
        )
    except Exception:
        logger.exception("個別PDFの生成に失敗しました: submission_id=%s", submission_id)
        return jsonify({"ok": False, "error": "PDFの生成に失敗しました。"}), 500


@admin_bp.route("/api/submissions/pdf", methods=["POST"])
def export_submissions_pdf_bulk():
    """選択した提出の評価帳票を1つの PDF にまとめてダウンロード。"""
    try:
        payload = request.get_json(silent=True) or {}
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return jsonify({"ok": False, "error": "提出が選択されていません。"}), 400

        wanted = {str(i) for i in ids if i}
        by_id = {}
        for submission in _filter_managed_submissions(get_submissions()):
            sid = submission.get("id")
            if sid in wanted:
                by_id[sid] = _submission_for_pdf(submission)
        if wanted - set(by_id):
            return jsonify({"ok": False, "error": "このクラスを操作する権限がありません。"}), 403

        ordered = [by_id[str(i)] for i in ids if str(i) in by_id]
        if not ordered:
            return jsonify({"ok": False, "error": "対象の提出データが見つかりません。"}), 404

        return _pdf_response(
            ordered,
            download_name=f"vibe_speak_news_reports_{len(ordered)}.pdf",
            inline=False,
        )
    except Exception:
        logger.exception("一括PDFの生成に失敗しました")
        return jsonify({"ok": False, "error": "PDFの生成に失敗しました。"}), 500
