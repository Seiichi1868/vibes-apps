"""ログイン用パスワード変更の認証アプリ（TOTP）。"""
from __future__ import annotations

import pyotp
import segno

ISSUER = "Toolbox"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(username: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def qr_data_uri(uri: str) -> str:
    return segno.make(uri, error="m").svg_data_uri(scale=4)


def verify_code(secret: str, code: str) -> bool:
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) != 6 or not secret:
        return False
    return bool(pyotp.TOTP(secret).verify(digits, valid_window=1))
