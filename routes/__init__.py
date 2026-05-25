"""Blueprint 互換レイヤー（Render / 旧 app.py 向け）。"""

__all__ = ["student_bp", "admin_bp"]


def __getattr__(name: str):
    if name == "student_bp":
        from routes.student import student_bp

        return student_bp
    if name == "admin_bp":
        from routes.admin import admin_bp

        return admin_bp
    raise AttributeError(name)
