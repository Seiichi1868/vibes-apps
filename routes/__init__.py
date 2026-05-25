"""Blueprint 互換レイヤー（Render / 旧 app.py 向け）。

実装は ``app.api`` / ``app.views`` にあり、ここでは再エクスポートのみ行う。
"""
from routes.admin import admin_bp
from routes.student import student_bp

__all__ = ["student_bp", "admin_bp"]
