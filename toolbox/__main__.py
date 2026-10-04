"""python -m toolbox create-user --role admin"""
from __future__ import annotations

import click

from toolbox.cli import create_user_record


@click.group()
def main():
    """Toolbox 管理コマンド"""


@main.command("create-user")
@click.option("--username", prompt=True)
@click.option("--role", type=click.Choice(["admin", "teacher"]), default="teacher")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_user(username, role, password):
    user = create_user_record(username, password, role)
    click.echo(f"作成しました: {user['username']} ({user['role']})")


if __name__ == "__main__":
    main()
