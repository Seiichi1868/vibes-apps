from pathlib import Path

from flask_app.config import Config


def allowed_file(filename: str, allowed_extensions: set[str] | None = None) -> bool:
    """許可されたファイル拡張子かチェック"""
    extensions = allowed_extensions or Config.ALLOWED_EXTENSIONS
    return "." in filename and filename.rsplit(".", 1)[1].lower() in extensions


def resolve_image_mime(file_storage) -> str:
    mime = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if mime in Config.OCR_ALLOWED_MIME:
        return mime
    ext = Path(file_storage.filename or "").suffix.lower()
    return Config.OCR_MIME_BY_EXT.get(ext, "image/jpeg")
