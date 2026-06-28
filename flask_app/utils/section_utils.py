import flask_app.state as state

SECTION_KEYS = ("sample", "compose", "grammar", "recorder", "result", "comparison")

DEFAULT_VISIBLE_SECTIONS: dict[str, bool] = {key: True for key in SECTION_KEYS}


def normalize_visible_sections(raw) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return dict(DEFAULT_VISIBLE_SECTIONS)

    normalized = dict(DEFAULT_VISIBLE_SECTIONS)
    for key in SECTION_KEYS:
        if key in raw:
            normalized[key] = bool(raw.get(key))
    return normalized


def get_visible_sections() -> dict[str, bool]:
    return dict(state.VISIBLE_SECTIONS)


def set_visible_sections(raw) -> dict[str, bool]:
    from flask_app.services.runtime_settings import update_runtime_settings

    normalized = normalize_visible_sections(raw)
    saved = update_runtime_settings(visible_sections=normalized)
    return normalize_visible_sections(saved.get("visible_sections"))


def sections_response() -> dict:
    visible = get_visible_sections()
    return {
        "ok": True,
        "visible_sections": visible,
        "sections": [
            {"id": key, "visible": visible[key]}
            for key in SECTION_KEYS
        ],
    }
