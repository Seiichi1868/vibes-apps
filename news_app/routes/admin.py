import io
import logging

import openpyxl
from flask import Blueprint, jsonify, render_template, request, send_file, url_for

logger = logging.getLogger(__name__)

from news_app.config import (
    AI_MODELS,
    CEFR_LEVELS,
    DISPLAY_LANGUAGES,
    VOCAB_MIN_CEFR_LEVELS,
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
from news_app.services.storage import (
    DEFAULT_EVALUATION_CRITERIA,
    archive_class_current,
    copy_class_archive,
    current_lesson_identity,
    create_class,
    delete_class_archive,
    delete_submission,
    get_active_class_id,
    get_class,
    get_roster,
    get_submission,
    get_submissions,
    import_roster_from_excel,
    list_classes,
    load_state,
    reset_class_current,
    restore_class_archive,
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
    appearance_context,
    selected_display_questions,
)
from news_app.services.pdf_report import build_submissions_pdf
from news_app.services.youtube import extract_video_id, fetch_youtube_title, parse_time_to_seconds, seconds_to_display

admin_bp = Blueprint("news_admin", __name__)


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


@admin_bp.route("/")
def admin_index():
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
    class_id, cls = _active_class_or_none()
    current = (cls or {}).get("current") or {}
    api_key_configured = bool(get_openai_api_key())
    classes = list_classes()

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
        api_key_masked=mask_api_key(state.get("openai_api_key") or get_openai_api_key()),
        **appearance_context(state),
    )


@admin_bp.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json(silent=True) or {}
    try:
        if str(data.get("admin_password") or "") != "2479":
            return jsonify({"ok": False, "error": "管理設定のパスワードが違います。"}), 403

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
    return jsonify({"ok": True, "classes": list_classes(), "active_class_id": get_active_class_id()})


@admin_bp.route("/api/classes", methods=["POST"])
def api_create_class():
    data = request.get_json(silent=True) or {}
    try:
        cls = create_class(str(data.get("name", "")).strip())
        return jsonify({"ok": True, "class": cls, "active_class_id": cls["id"]})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


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
        lesson_payload: dict = {
            "source_url": url,
            "video_id": video_id,
            "title": title,
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
                "message": "導入補助を有効にしました。" if enabled else "導入補助を無効にしました。",
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
                "message": f"事後質問 {q_count} 問を生成しました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"事後質問の生成に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview/selection", methods=["POST"])
def api_update_postview_selection():
    """事後質問の表示/非表示（選択状態）を保存する。"""
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
                "message": f"事後質問の表示設定を保存しました（表示 {selected_count} / {len(postview_questions)} 問）。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/postview/toggle", methods=["POST"])
def api_toggle_postview_scaffolding():
    """生徒画面への事後質問表示の on/off を切り替える。"""
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
                "message": "事後質問を有効にしました。" if enabled else "事後質問を無効にしました。",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"設定の保存に失敗しました: {exc}"}), 500


@admin_bp.route("/api/class/lesson/materials/docx", methods=["POST"])
def api_export_lesson_materials_docx():
    """文字起こし・和訳・語彙・事前/事後質問を選んで Word 出力する。"""
    data = request.get_json(silent=True) or {}
    class_id = str(data.get("class_id") or get_active_class_id()).strip()
    include = data.get("include") if isinstance(data.get("include"), dict) else {}
    title = str(data.get("title") or "").strip()
    script = str(data.get("script") or "").strip()
    script_ja = str(data.get("script_ja") or "").strip()
    pairs = _normalize_script_ja_pairs(data.get("pairs"))

    cls = get_class(class_id) if class_id else None
    current = (cls or {}).get("current") or {}
    if not title:
        title = str(current.get("title") or "").strip()
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
        current = (get_class(class_id) or {}).get("current") or {}
        if not title:
            title = str(current.get("title") or "").strip()
        if not title:
            title = fetch_youtube_title(current.get("source_url") or current.get("video_id") or "")
        cls = archive_class_current(class_id, title)
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
        source_cls, target_cls = copy_class_archive(class_id, archive_index, target_class_id)
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

    base = get_public_base_url(request)
    link = f"{base}/news/screen/?class={class_id}"
    return jsonify({"ok": True, "link": link, "class_id": class_id})


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


@admin_bp.route("/api/submissions", methods=["GET"])
def list_submissions():
    class_id = request.args.get("class_id") or None
    lesson_key_filter = request.args.get("lesson_key") or None
    submissions = []
    for submission in get_submissions(class_id):
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
    ok = delete_submission(submission_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "データが見つかりません。"}), 404


@admin_bp.route("/api/submissions/export", methods=["GET"])
def export_submissions():
    """提出結果を Excel でダウンロード。?class_id=xxx で絞り込み可。"""
    class_id = request.args.get("class_id") or None
    lesson_key_filter = request.args.get("lesson_key") or None
    submissions = get_submissions(class_id)
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
        submission = get_submission(submission_id)
        if not submission:
            return jsonify({"ok": False, "error": "データが見つかりません。"}), 404
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
        for submission in get_submissions():
            sid = submission.get("id")
            if sid in wanted:
                by_id[sid] = _submission_for_pdf(submission)

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
