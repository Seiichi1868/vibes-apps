"""統合サービス上のアプリ稼働状態（メンテナンス）を一元管理する。"""

from platform_ops.registry import PLATFORM_APPS, get_app
from platform_ops.runtime import (
    MAINTENANCE_MESSAGE,
    is_path_operational,
    list_apps_with_status,
    maintenance_response,
    set_app_operational,
)

__all__ = [
    "PLATFORM_APPS",
    "MAINTENANCE_MESSAGE",
    "get_app",
    "is_path_operational",
    "list_apps_with_status",
    "maintenance_response",
    "set_app_operational",
]
