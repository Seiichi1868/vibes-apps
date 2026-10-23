"""Render 統合サービスに載っているアプリと URL の対応。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformApp:
    id: str
    name: str
    description: str
    prefixes: tuple[str, ...]
    exact_paths: tuple[str, ...] = ()
    admin_bypass_prefixes: tuple[str, ...] = ()


PLATFORM_APPS: tuple[PlatformApp, ...] = (
    PlatformApp(
        id="vibespeak",
        name="音読 Speaking Lab",
        description="ブラウザ音読・教員管理（/ と /admin）",
        exact_paths=("/",),
        prefixes=("/admin", "/api"),
    ),
    PlatformApp(
        id="public",
        name="Public ゲート",
        description="高負荷時用の /public 入口",
        prefixes=("/public",),
    ),
    PlatformApp(
        id="news",
        name="Vibe Speak News",
        description="CNN10 などニュース授業（/news）",
        prefixes=("/news",),
    ),
    PlatformApp(
        id="debate",
        name="Parliamentary Debate",
        description="ディベート練習（/debate）",
        prefixes=("/debate",),
    ),
    PlatformApp(
        id="gtec",
        name="GTEC Speaking",
        description="GTEC 形式のスピーキング（/gtec）",
        prefixes=("/gtec",),
    ),
    PlatformApp(
        id="level_check",
        name="Speaking Level Check",
        description="レベルチェック（/level_check）",
        prefixes=("/level_check",),
    ),
    PlatformApp(
        id="conjugate",
        name="Spanish Lab Conjugate",
        description="スペイン語活用（/conjugate）",
        prefixes=("/conjugate",),
    ),
    PlatformApp(
        id="trigger",
        name="Speaking Lab Trigger",
        description="トリガー練習（/trigger）",
        prefixes=("/trigger",),
    ),
    PlatformApp(
        id="speech_rec",
        name="1分スピーチ（/rec）",
        description="録音・評価・出題（/rec）",
        prefixes=("/rec",),
    ),
    PlatformApp(
        id="toolbox",
        name="Toolbox",
        description="授業補助ツール一式（/toolbox）",
        prefixes=("/toolbox",),
        admin_bypass_prefixes=("/toolbox/admin",),
    ),
)


def get_app(app_id: str) -> PlatformApp | None:
    for app in PLATFORM_APPS:
        if app.id == app_id:
            return app
    return None
