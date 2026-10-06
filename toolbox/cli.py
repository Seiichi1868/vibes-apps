"""Flask CLI: flask --app wsgi:application toolbox create-user --role admin"""
from __future__ import annotations

import getpass
import re

import click
from werkzeug.security import generate_password_hash

from toolbox.config import MIN_PASSWORD_LEN, ensure_dirs
from toolbox.storage import get_user, new_id, now_iso, save_user

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def create_user_record(username: str, password: str, role: str) -> dict:
    name = (username or "").strip()
    if not USERNAME_RE.match(name):
        raise click.ClickException("ユーザー名は英数字とアンダースコア、3〜32文字です。")
    if role not in ("admin", "teacher"):
        raise click.ClickException("role は admin または teacher です。")
    if len(password) < MIN_PASSWORD_LEN:
        raise click.ClickException(f"パスワードは{MIN_PASSWORD_LEN}文字以上にしてください。")
    if get_user(username=name):
        raise click.ClickException("同じユーザー名がすでにあります。")
    ensure_dirs()
    user = {
        "id": new_id(),
        "username": name,
        "password_hash": generate_password_hash(password),
        "role": role,
        "is_active": True,
        "created_at": now_iso(),
        "last_login_at": None,
    }
    save_user(user)
    return user


def register(app) -> None:
    @app.cli.group("toolbox")
    def toolbox_cli():
        """Toolbox 管理コマンド"""

    @toolbox_cli.command("create-user")
    @click.option("--username", prompt=True, help="ログイン用ユーザー名")
    @click.option("--role", type=click.Choice(["admin", "teacher"]), default="teacher")
    @click.option("--password", default=None, help="4文字以上。省略時は非表示で入力")
    def create_user(username: str, role: str, password: str | None):
        if not password:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Password (again): ")
            if password != confirm:
                raise click.ClickException("パスワードが一致しません。")
        user = create_user_record(username, password, role)
        click.echo(f"作成しました: {user['username']} ({user['role']})")
