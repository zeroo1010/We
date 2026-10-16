"""مصادقة متعددة المستخدمين عبر ورقة Google Sheets (مع ذاكرة دخول محلية دون اتصال)."""
from __future__ import annotations

import hmac
import logging

import streamlit as st

from core import offline
from core.config import SHEETS, load_config

LOGGER = logging.getLogger(__name__)


def _has_local_users() -> bool:
    """هل توجد حسابات على هذا الجهاز (ذاكرة دخول أو نسخة ورقة المستخدمين)؟"""
    if offline.auth_cache_count() > 0:
        return True
    try:
        snapshot = offline.read_snapshot(SHEETS["users"])
    except Exception:  # noqa: BLE001
        return False
    return snapshot is not None and not bool(getattr(snapshot, "empty", True))


def _check(username: str, password: str):
    """يتحقق من بيانات الدخول.

    يعيد (مستخدم, رسالة خطأ) — رسالة الخطأ فارغة عند النجاح، وتساعد المستخدم
    على معرفة سبب الرفض (إعدادات ناقصة / لا اتصال وبدون حسابات محلية / بيانات
    غير صحيحة).
    """
    from core.users import authenticate, bootstrap_default_admin

    cfg = load_config()
    if not cfg.spreadsheet_key:
        return None, (
            "لم يتم إعداد مفتاح الجدول (Google Sheet). "
            "ضع ملف الإعدادات بجانب البرنامج: `.streamlit/secrets.toml` "
            "← [gsheets] spreadsheet_key."
        )
    user = None
    google_error = ""
    try:
        bootstrap_default_admin()
        user = authenticate(username, password)
    except Exception as exc:  # noqa: BLE001
        google_error = str(exc)
        LOGGER.warning("login: google sheets error: %s", exc)
    if user:
        return user, ""
    # مسار احتياطي لحساب الأسرار المفرد (قبل تفعيل ورقة Users)
    if hmac.compare_digest(username, cfg.username) and hmac.compare_digest(password, cfg.password):
        return {"username": cfg.username, "role": "admin"}, ""
    # تفسير سبب الرفض
    if google_error:
        return None, (
            "تعذر الوصول إلى بيانات المستخدمين من Google Sheets — "
            f"تحقق من `service_account.json` ومن مشاركة الملف مع حساب الخدمة. "
            f"(التفاصيل: {google_error})"
        )
    if not offline.is_online() and not _has_local_users():
        return None, (
            "لا توجد حسابات محفوظة على هذا الجهاز (قد يكون هذا أول تشغيل أو أول "
            "تشغيل دون اتصال). شغّل البرنامج متصلًا بالإنترنت أول مرة لتنزيل "
            "حسابات الموقع، ثم أعد المحاولة."
        )
    LOGGER.warning("login: invalid credentials for user %r", username)
    return None, "اسم المستخدم أو كلمة المرور غير صحيحة."


def is_logged_in() -> bool:
    return bool(st.session_state.get("logged_in"))


def login_form() -> None:
    cfg = load_config()
    st.markdown(
        """
        <style>
        .login-wrap { max-width: 420px; margin: 6vh auto 0; }
        .login-card { background:#fff; border-radius:18px; padding:30px;
            box-shadow:0 12px 40px rgba(15,43,70,.12); direction:rtl; }
        .login-card h2 { text-align:center; color:#0f2b46; margin-bottom:4px; }
        .login-card p { text-align:center; color:#64748b; font-size:14px; margin-top:0; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="login-card"><h2>🔐 {cfg.app_title}</h2><p>سجّل الدخول للمتابعة</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(offline.pill_html(), unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("اسم المستخدم", value="", placeholder="", width="stretch")
        password = st.text_input("كلمة المرور", type="password", value="", placeholder="", width="stretch")
        submitted = st.form_submit_button("تسجيل الدخول", use_container_width=True, type="primary")
    if submitted:
        user, error = _check(username.strip(), password)
        if user:
            active = str(user.get("username", username.strip()))
            st.session_state["logged_in"] = True
            st.session_state["username"] = active
            st.session_state["user"] = active
            st.session_state["role"] = str(user.get("role", "user"))
            # كل دخول جديد يبدأ من الصفحة الرئيسية (لوحة المعلومات)
            st.session_state.pop("nav_page", None)
            st.session_state.pop("pending_page", None)
            st.rerun()
        else:
            st.error(error or "اسم المستخدم أو كلمة المرور غير صحيحة.")
    st.markdown("</div>", unsafe_allow_html=True)


def logout() -> None:
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user", None)
    st.session_state.pop("role", None)
    st.session_state.pop("pending_page", None)
    st.rerun()


def current_username() -> str:
    """اسم المستخدم النشط حاليًا (يتماشى مع `st.session_state['username']`)."""
    return str(
        st.session_state.get("username")
        or st.session_state.get("user")
        or ""
    ).strip()


def is_admin() -> bool:
    return str(st.session_state.get("role", "")).lower() == "admin"