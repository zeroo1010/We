"""إدارة المستخدمين: تخزين في ورقة Users داخل Google Sheets مع تشفير كلمات المرور."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core import offline
from core.config import SHEETS, load_config
from core.gsheets import DataError, append_row, delete_row, read_sheet, update_row

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = [ROLE_ADMIN, ROLE_USER]

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "adminpassword"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _key() -> str:
    cfg = load_config()
    if not cfg.spreadsheet_key:
        raise DataError("لم يتم إعداد مفتاح Google Sheet في الإعدادات (secrets.toml).")
    return cfg.spreadsheet_key


def hash_password(password: str, salt: str = "") -> str:
    """تجزئة كلمة المرور باستخدام PBKDF2-SHA256 مع ملح."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, salt, digest = str(stored_hash).split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), 100_000)
    return hmac.compare_digest(check.hex(), digest)


def get_users() -> pd.DataFrame:
    return read_sheet(_key(), SHEETS["users"])


def bootstrap_default_admin() -> Optional[str]:
    """إنشاء حساب Admin افتراضي إن كانت ورقة المستخدمين فارغة.

    لا يُنشئ الحساب أثناء القراءة المحلية (دون اتصال أو عمليات معلّقة) حتى
    لا يُضاف حساب افتراضي افتراضيًا إلى الشيت الحقيقي عند عودة الاتصال.
    """
    users = get_users()
    if not users.empty:
        return None
    if offline.use_local():
        return None
    append_row(
        _key(),
        SHEETS["users"],
        {
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
            "role": ROLE_ADMIN,
            "created_at": _now(),
        },
    )
    return f"تم إنشاء حساب المدير الافتراضي: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}"


def find_user(username: str) -> Optional[Dict[str, Any]]:
    users = get_users()
    if users.empty:
        return None
    match = users[users["username"].astype(str).str.strip().str.lower() == str(username).strip().lower()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = find_user(username)
    if not user:
        # دون اتصال (أو قبل توفّر نسخة محلية): الاعتماد على ذاكرة الدخول المحلية
        user = offline.get_cached_user(username)
    if not user:
        return None
    if verify_password(password, str(user.get("password_hash", ""))):
        return user
    return None


def add_user(username: str, password: str, role: str = ROLE_USER) -> Tuple[bool, str]:
    username = str(username or "").strip()
    if not username:
        return False, "اسم المستخدم مطلوب."
    if len(str(password or "")) < 4:
        return False, "كلمة المرور يجب أن تكون 4 أحرف على الأقل."
    if role not in ROLES:
        return False, "الدور غير صالح."
    if find_user(username):
        return False, f"اسم المستخدم «{username}» موجود مسبقًا."
    append_row(
        _key(),
        SHEETS["users"],
        {
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "created_at": _now(),
        },
    )
    return True, f"تم إضافة المستخدم «{username}»."


def delete_user(username: str) -> Tuple[bool, str]:
    users = get_users()
    if users.empty:
        return False, "لا يوجد مستخدمون."
    user = find_user(username)
    if not user:
        return False, "المستخدم غير موجود."
    admins = users[users["role"].astype(str).str.strip().str.lower() == ROLE_ADMIN]
    if str(user.get("role", "")).lower() == ROLE_ADMIN and len(admins) <= 1:
        return False, "لا يمكن حذف آخر حساب مدير في النظام."
    ok = delete_row(_key(), SHEETS["users"], "username", str(user["username"]))
    return (ok, f"تم حذف المستخدم «{username}»." if ok else "تعذر حذف المستخدم.")


def reset_password(username: str, new_password: str) -> Tuple[bool, str]:
    if len(str(new_password or "")) < 4:
        return False, "كلمة المرور يجب أن تكون 4 أحرف على الأقل."
    user = find_user(username)
    if not user:
        return False, "المستخدم غير موجود."
    ok = update_row(
        _key(),
        SHEETS["users"],
        "username",
        str(user["username"]),
        {"password_hash": hash_password(new_password)},
    )
    return (ok, f"تم تغيير كلمة مرور «{username}»." if ok else "تعذر تغيير كلمة المرور.")


def set_role(username: str, role: str) -> Tuple[bool, str]:
    if role not in ROLES:
        return False, "الدور غير صالح."
    user = find_user(username)
    if not user:
        return False, "المستخدم غير موجود."
    users = get_users()
    admins = users[users["role"].astype(str).str.strip().str.lower() == ROLE_ADMIN]
    if (
        str(user.get("role", "")).lower() == ROLE_ADMIN
        and role != ROLE_ADMIN
        and len(admins) <= 1
    ):
        return False, "لا يمكن إزالة دور المدير عن آخر حساب مدير."
    ok = update_row(_key(), SHEETS["users"], "username", str(user["username"]), {"role": role})
    return (ok, "تم تحديث دور المستخدم." if ok else "تعذر تحديث الدور.")


def list_users() -> List[Dict[str, Any]]:
    users = get_users()
    if users.empty:
        return []
    return users.to_dict("records")