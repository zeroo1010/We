"""نظام إدارة مخزن المعمل - واجهة مبسطة (Streamlit).

الصفحات (حسب ترتيب القائمة الجانبية):
    1. 🏠 الصفحة الرئيسية (Dashboard)     — الافتراضية بعد الدخول
    2. 📤 تسجيل سحب (Withdrawal Page)
    3. ➕ إدارة الأصناف (Item Management)
    4. 📊 التقارير والسجلات (Reports & Logs)
    5. 👤 إدارة المستخدمين (User Management) — للمدير فقط

المميزات:
    - نظام مستخدمين متعدد (ورقة Users) مع إضافة/حذف/تغيير كلمات المرور.
    - حقول إدخال فارغة بلا أرقام افتراضية أو نصوص إرشادية داخل الحقول.
    - طوابع زمنية مفصّلة بصيغة YYYY-MM-DD HH:MM:SS لكل عملية سحب.
    - كود الصنف وتاريخ الإضافة عند إضافة صنف جديد.
    - تمييز «اسم المسؤول» عن «اسم الساحب» في سجل السحوبات.
    - شارة المستخدم النشط أعلى الواجهة + زر تسجيل الخروج.
    - لوحة رئيسية بمؤشرات وآخر التحديثات وأزرار وصول سريع.
    - تخطيط متجاوب مع الهواتف المحمولة (عمود واحد + أهداف لمس أكبر).
    - عمل دون اتصال (Offline-First): الحفظ في قاعدة بيانات محلية SQLite عند
      انقطاع الإنترنت ودَفع تلقائي إلى Google Sheets فور عودة الاتصال، مع
      شارة حالة (Online / Offline / Syncing) أعلى الواجهة وفي القائمة الجانبية.

قاعدة البيانات: SQLite محلية (نسخة الديسك توب) — ملف data/warehouse.db.
"""
from __future__ import annotations

import html
import os
import subprocess
from datetime import date, datetime

import streamlit as st

from core import offline
from core.auth import current_username, is_admin, is_logged_in, login_form, logout
from core.config import load_config
from core.db import DataError, configure, ensure_schema, spreadsheet_info, to_number
from core.services import (
    add_stock_item,
    clear_test_data,
    delete_product,
    get_movements,
    get_products,
    get_withdrawals,
    record_movement,
    sell_draw_item,
    update_product,
)
from core.styles import header, inject_styles, metric_card
from core.users import (
    ROLE_ADMIN,
    ROLES,
    add_user,
    delete_user,
    get_users,
    reset_password,
    set_role,
)

# --------------------------------------------------------------------------- #
#                              إعداد الصفحة
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="مخزن المعمل",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed",  # مهيأ للهاتف: القائمة مطويوة
)
inject_styles()

# --------------------------------------------------------------------------- #
#     إصلاح تخطيط عام: حدود الشريط الجانبي + توافق RTL/LTR (يُحقن بعد الثيم)
# --------------------------------------------------------------------------- #
LAYOUT_FIX_CSS = """
<style>
/* ============ 1) تنظيف حدود الشريط الجانبي وإزالة الخطوط ============ */
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsed"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarHeader"],
[data-testid="stSidebarLogo"] {
    border-right: none !important;
    border-left: none !important;
    border-top: none !important;
    border-bottom: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* إزالة خطوط/حدود قائمة التنقل داخل الشريط الجانبي */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"],
[data-testid="stSidebarNavLinkContainer"] {
    border: none !important;
    border-top: none !important;
    border-bottom: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* الفواصل الداخلية تبقى ناعمة بلا ظلال */
[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid rgba(255, 255, 255, 0.16) !important;
    box-shadow: none !important;
    opacity: 1 !important;
    margin: 0.6rem 0 !important;
}

/* ============ 1ب) انتقال سلس لزر الطي/الفتح ============ */
[data-testid="stSidebarCollapseButton"] {
    outline: none !important;
    border: none !important;
    box-shadow: none !important;
    transition: all 0.25s ease !important;
}
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] > div {
    transition: background 0.25s ease, transform 0.25s ease,
        border-radius 0.25s ease, box-shadow 0.25s ease !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebarCollapseButton"] button:hover {
    transform: scale(1.06);
}
section[data-testid="stSidebar"] {
    transition: transform 0.3s ease-in-out, width 0.3s ease-in-out !important;
}

/* ============ 2) توافق RTL/LTR: flexbox للحاوية الرئيسية ============ */
.stApp,
.block-container {
    box-sizing: border-box;
    width: 100%;
}
.block-container {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.25rem;
}
.block-container > * {
    box-sizing: border-box;
    min-width: 0;
    max-width: 100%;
}
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[data-testid="stForm"],
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
}
[data-testid="stMetric"] { box-sizing: border-box; }

/* ============ 3) عرض كامل للعناصر ============ */
.stButton > button,
[data-testid="stButton"] > button,
.stDownloadButton > button,
[data-testid="stDownloadButton"] > button {
    width: 100%;
}

/* الجداول والنماذج بعرض كامل دائمًا لتفادي كسر التخطيط */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    width: 100% !important;
    max-width: 100% !important;
}
[data-testid="stForm"] {
    width: 100%;
}

/* ============ 4) إطارات واضحة لحقول الإدخال في كل التطبيق ============ */
div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"],
input,
textarea {
    border: 1.5px solid #4A5568 !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
    box-sizing: border-box !important;
}

/* منع تكرار الإطار: غلاف الحقل يحمل الإطار المرئي، والعنصر الداخلي شفاف */
div[data-baseweb] input,
div[data-baseweb] textarea {
    border: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
}

/* توهج قوي باللون الأساسي عند التركيز */
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.30) !important;
}
input:focus,
textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.30) !important;
    outline: none !important;
}

/* ============ 5) خانة الإجمالي (معطّلة للقراءة) بنفس مظهر الحقول العادية ============ */
div[data-baseweb="input"]:has(input:disabled),
div[data-baseweb="textarea"]:has(textarea:disabled) {
    background: #ffffff !important;
    border-color: #4A5568 !important;
    opacity: 1 !important;
}
div[data-baseweb="input"] input:disabled,
div[data-baseweb="textarea"] textarea:disabled {
    background: transparent !important;
    color: inherit !important;
    opacity: 1 !important;
    -webkit-text-fill-color: currentColor !important;
    cursor: default !important;
}
</style>
"""

st.markdown(LAYOUT_FIX_CSS, unsafe_allow_html=True)

PAGES = [
    "🏠 الصفحة الرئيسية (Dashboard)",
    "📤 تسجيل سحب (Withdrawal Page)",
    "➕ إدارة الأصناف (Item Management)",
    "📊 التقارير والسجلات (Reports & Logs)",
]
ADMIN_PAGES = ["👤 إدارة المستخدمين (User Management - Admin only)"]


# --------------------------------------------------------------------------- #
#                       التهيئة والاتصال بقاعدة البيانات
# --------------------------------------------------------------------------- #
def _bootstrap() -> None:
    if st.session_state.get("_db_ready"):
        return
    cfg = load_config()
    try:
        offline.configure(cfg)  # بيانات المزامنة الخلفية (بلا أي واجهة Streamlit)
        configure(cfg.database_path)
        ensure_schema(cfg.spreadsheet_key)  # يُؤجَّل تلقائيًا عند غياب الاتصال
        st.session_state["_db_ready"] = True
        st.session_state.pop("_db_error", None)
    except DataError as exc:
        st.session_state["_db_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تهيئة قاعدة البيانات المحلية: {exc}"


# --------------------------------------------------------------------------- #
#                  شارة حالة الاتصال والمزامنة (تتحدث تلقائيًا)
# --------------------------------------------------------------------------- #
def _render_sync_pill() -> None:
    st.markdown(offline.pill_html(), unsafe_allow_html=True)


@st.fragment(run_every=2)
def _sidebar_sync_status() -> None:
    """حالة المزامنة في القائمة الجانبية (تتحدث كل ثانيتين دون تدخل المستخدم)."""
    _render_sync_pill()


@st.fragment(run_every=2)
def _topbar_sync_status() -> None:
    """حالة المزامنة في الشريط العلوي (تتحدث كل ثانيتين دون تدخل المستخدم)."""
    _render_sync_pill()


@st.cache_resource(show_spinner=False)
def _app_version() -> str:
    """رقم نسخة التطبيق (commit git) للتحقق من أن النسخة المنشورة هي الأحدث."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        return "—"
    return "—"


def _sidebar() -> str:
    cfg = load_config()
    username = current_username()
    role = str(st.session_state.get("role", "")).strip()
    role_label = {"admin": "👑 مدير", "user": "👤 مستخدم"}.get(role.lower(), role)
    with st.sidebar:
        st.markdown(
            f"<div style='padding:14px 6px 6px;text-align:center;'>"
            f"<div style='font-size:34px;'>🏭</div>"
            f"<div style='font-weight:700;font-size:17px;color:#fff;'>{cfg.app_title}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if username:
            st.markdown(
                f'<div class="sidebar-user">'
                f'<div class="name">👤 المستخدم الحالي: {html.escape(username)}</div>'
                f'<div class="role">{html.escape(role_label)}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        # شارة حالة الاتصال/المزامنة (تتحدث تلقائيًا كل ثانيتين)
        _sidebar_sync_status()
        st.markdown("---")
        items = PAGES + (ADMIN_PAGES if is_admin() else [])

        # طلب تنقّل من أزرار الوصول السريع (يُستهلك قبل تركيب القائمة)
        pending = st.session_state.pop("pending_page", None)
        if pending in items:
            st.session_state["nav_page"] = pending
        # إسقاط أي صفحة غير صالحة (مثل صفحة المدير عند دخول مستخدم عادي)
        if st.session_state.get("nav_page") not in items:
            st.session_state.pop("nav_page", None)

        page = st.radio(
            "القائمة",
            items,
            index=0,
            label_visibility="collapsed",
            width="stretch",
            key="nav_page",
        )
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            logout()
        # زر إغلاق البرنامج (يظهر فقط في نسخة exe المكتبي)
        if os.environ.get("WAREHOUSE_DESKTOP") == "1":
            if st.button("⏻ إغلاق التطبيق", key="desktop_quit", use_container_width=True):
                os._exit(0)
        st.markdown("---")
        info = spreadsheet_info(cfg.spreadsheet_key)
        if info.get("url"):
            st.caption(f"🔗 مصدر البيانات: [{info['title']}]({info['url']})")
        elif info.get("title"):
            st.caption(f"💾 قاعدة البيانات المحلية: `{info['title']}`")
        st.caption(f"🔧 إصدار التطبيق: `{_app_version()}`")
    return page


def _topbar() -> None:
    """شريط علوي يعرض المستخدم النشط في أعلى كل صفحة (مع زر خروج وحالة المزامنة)."""
    username = current_username()
    if not username:
        return
    role = str(st.session_state.get("role", "")).strip()
    role_label = {"admin": "👑 مدير", "user": "👤 مستخدم"}.get(role.lower(), role)
    c_main, c_status, c_action = st.columns([3, 2, 1])
    with c_action:
        if st.button("🚪 تسجيل الخروج", key="topbar_logout", use_container_width=True):
            logout()
    with c_status:
        _topbar_sync_status()
    with c_main:
        st.markdown(
            f'<div class="user-bar" style="margin-bottom:0;">'
            f'<span class="who">👤 المستخدم الحالي: {html.escape(username)}'
            f'<span class="role-chip {"admin" if role.lower() == "admin" else ""}">'
            f"{html.escape(role_label)}</span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _guard() -> bool:
    """يعرض رسالة الخطأ ويمنع تنفيذ الصفحات عند فشل الاتصال."""
    err = st.session_state.get("_db_error")
    if not err:
        return True
    st.error(f"⚠️ {err}\n\nتعذّر تجهيز قاعدة البيانات المحلية في مجلد data بجانب التطبيق.")
    return False


def _go_to(page_label: str) -> None:
    """ينتقل إلى صفحة محددة عبر أزرار الوصول السريع."""
    st.session_state["pending_page"] = page_label
    st.rerun()


# --------------------------------------------------------------------------- #
#                    1) الصفحة الرئيسية (لوحة المعلومات)
def _remaining_quantity(wrow, movements, fallback=None):
    """الرصيد المتبقي بعد عملية سحب: balance_after من حركة «سحب» المطابقة أو الرصيد الحالي."""

    def _txt(value):
        s = str(value).strip()
        return "" if s.lower() in ("nan", "none", "nat") else s

    if movements is not None and not movements.empty:
        stamp = _txt(wrow.get("withdraw_date"))
        code = _txt(wrow.get("product_code"))
        matched = movements[
            (movements["product_code"].apply(_txt) == code)
            & (movements["movement_date"].apply(_txt) == stamp)
            & (movements["movement_type"].apply(_txt) == "سحب")
        ]
        if not matched.empty:
            return to_number(matched.iloc[-1]["balance_after"])
    if fallback is not None:
        return to_number(fallback)
    return None


def _product_note(value) -> str:
    s = str(value if value is not None else "").strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _unit_value(unit_raw):
    """قيمة الوحدة كرقم (لحساب الإجمالي بعد السحب) أو None إن لم تكن رقمية."""
    text = _product_note(unit_raw)
    if not text:
        return None
    value = to_number(text, -1.0)
    return value if value >= 0 else None


def _notes_by_code(products) -> dict:
    if products is None or getattr(products, "empty", True):
        return {}
    return {
        str(p.get("product_code", "") or "").strip(): _product_note(p.get("notes"))
        for p in products.to_dict("records")
    }


# --------------------------------------------------------------------------- #
def page_home() -> None:
    username = current_username()
    header(f"👤 مرحبا بك، {username}", "نظرة سريعة على حالة المخزن وآخر العمليات")

    products = get_products()
    withdrawals = get_withdrawals()

    total_items = len(products)
    total_ops = len(withdrawals)
    today = datetime.now().strftime("%Y-%m-%d")
    today_ops = (
        int(withdrawals["withdraw_date"].astype(str).str[:10].eq(today).sum())
        if not withdrawals.empty
        else 0
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("إجمالي الأصناف في المخزن", total_items, width="stretch")
    with m2:
        st.metric("إجمالي عمليات السحب", total_ops, width="stretch")
    with m3:
        st.metric("عمليات السحب اليوم", today_ops, width="stretch")

    st.write("")
    st.markdown("#### 🔎 بحث عن صنف")
    items = [] if products.empty else products.to_dict("records")
    options = {}
    seen_codes = set()
    for p in items:
        code_p = str(p.get("product_code", "") or "").strip()
        nm = str(p.get("product_name", "") or "").strip()
        code_key = code_p.lower()
        if not code_p and not nm:
            continue
        if code_p and code_key in seen_codes:
            continue
        if code_p:
            seen_codes.add(code_key)
        unit_p = str(p.get("unit", "") or "").strip()
        stock_p = to_number(p.get("current_stock"))
        label = f"{nm} [{code_p}] — رصيد {stock_p:g}"
        if unit_p:
            label += f" {unit_p}"
        while label in options:
            label += " "
        options[label] = code_p
    if not options:
        st.info("لا توجد أصناف مسجّلة في المخزن.")
    else:
        choice = st.selectbox(
            "اسم الصنف",
            options=list(options.keys()),
            index=None,
            placeholder="اختر صنفًا لعرض رصيده وعمليات السحب",
            key="home_product_select",
            width="stretch",
        )
        if choice is None:
            st.caption(
                "اختر صنفًا من القائمة لعرض رصيده الحالي وآخر عمليات السحب الخاصة به."
            )
        else:
            selected_code = options[choice]
            product = next(
                (
                    p
                    for p in items
                    if str(p.get("product_code", "") or "").strip().lower()
                    == selected_code.lower()
                ),
                {},
            )
            code_q = str(product.get("product_code", "") or "").strip()
            stock = to_number(product.get("current_stock"))
            min_stock = to_number(product.get("min_stock"))
            unit = str(product.get("unit", "") or "").strip()
            name = str(product.get("product_name", "") or "").strip()
            st.caption(f"{name} — [{code_q}]")
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                st.metric(
                    f"الرصيد الحالي{f' ({unit})' if unit else ''}",
                    f"{stock:g}",
                    width="stretch",
                )
            with q2:
                st.metric("الحد الأدنى", f"{min_stock:g}", width="stretch")
            with q3:
                st.metric(
                    "الحالة",
                    "⚠️ منخفض" if stock <= min_stock else "✅ جيد",
                    width="stretch",
                )
            unit_val = _unit_value(unit)
            with q4:
                st.metric(
                    "الإجمالي بعد السحب",
                    f"{stock * unit_val:g}" if unit_val is not None else "—",
                    width="stretch",
                )
            st.caption(
                "💡 الإجمالي بعد السحب = الرصيد الحالي × قيمة الوحدة"
                + ("" if unit_val is not None else " — (أدخل قيمة رقمية في خانة «الوحدة» ليظهر الحساب).")
            )

            p_notes = _product_note(product.get("notes"))
            if p_notes:
                st.info(f"📝 ملاحظات الصنف: {p_notes}")
            else:
                st.caption("📝 لا توجد ملاحظات مسجلة لهذا الصنف.")

            mine = (
                withdrawals[
                    withdrawals["product_code"]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    == code_q.lower()
                ]
                if not withdrawals.empty
                else withdrawals
            )
            if mine.empty:
                st.info("لا توجد عمليات سحب مسجّلة لهذا الصنف.")
            else:
                total_qty = sum(to_number(v) for v in mine["qty"])
                st.markdown(
                    f"**📋 آخر عمليات السحب لهذا الصنف** — إجمالي المسحوب: {total_qty:g} "
                    f"({len(mine)} عملية)"
                )
                recent_mine = mine.iloc[::-1].head(10).copy()
                movements = get_movements()
                remainings = []
                for _, row in recent_mine.iterrows():
                    rem = _remaining_quantity(row, movements, product.get("current_stock"))
                    remainings.append("" if rem is None else f"{rem:g}")
                recent_mine["remaining_quantity"] = remainings
                recent_mine["total_after_withdrawal"] = [
                    "" if rem_str == "" or unit_val is None else f"{to_number(rem_str) * unit_val:g}"
                    for rem_str in remainings
                ]
                recent_mine["product_notes"] = p_notes
                st.dataframe(
                    recent_mine[
                        [
                            "withdraw_date",
                            "qty",
                            "remaining_quantity",
                            "total_after_withdrawal",
                            "product_notes",
                            "withdrawn_by",
                            "supervisor_name",
                        ]
                    ].rename(
                        columns={
                            "withdraw_date": "التاريخ والوقت",
                            "qty": "الكمية المسحوبة",
                            "remaining_quantity": "الرصيد المتبقي",
                            "total_after_withdrawal": "الإجمالي بعد السحب",
                            "product_notes": "ملاحظات الصنف",
                            "withdrawn_by": "اسم الساحب",
                            "supervisor_name": "اسم المسؤول",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "💡 عمود «الإجمالي بعد السحب» = الرصيد المتبقي بعد العملية × قيمة الوحدة."
                    if unit_val is not None
                    else "⚠️ عمود «الإجمالي بعد السحب» يتطلب قيمة رقمية في خانة «الوحدة»."
                )

    st.write("")
    st.markdown("#### ⚠️ أصناف منخفضة المخزون (الرصيد 3 أو أقل)")
    if products.empty:
        st.info("لا توجد أصناف مسجّلة في المخزن.")
    else:
        low = products.copy()
        low["_stock_num"] = low["current_stock"].map(to_number)
        low = low[low["_stock_num"] <= 3].sort_values("_stock_num", kind="stable")
        if low.empty:
            st.success("✅ لا توجد أصناف منخفضة المخزون — جميع الأصناف ضمن الحدود الآمنة.")
        else:
            if "added_by" not in low.columns:
                low["added_by"] = ""
            view = low.rename(
                columns={
                    "product_name": "اسم الصنف",
                    "product_code": "الكود",
                    "current_stock": "الرصيد الحالي",
                    "unit": "الوحدة",
                    "notes": "ملاحظات الصنف",
                    "added_by": "أضافه",
                }
            )[
                ["اسم الصنف", "الكود", "الرصيد الحالي", "الوحدة", "ملاحظات الصنف", "أضافه"]
            ]
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.caption(f"عدد الأصناف التي رصيدها 3 أو أقل: {len(low)}")

    st.write("")
    st.markdown("#### 🕒 آخر التحديثات في المخزن")
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب بعد.")
    else:
        recent = withdrawals.tail(8).iloc[::-1]
        notes_map = _notes_by_code(products)
        for _, r in recent.iterrows():
            stamp = str(r.get("withdraw_date", "") or "").strip()
            item = str(r.get("product_name", "") or "").strip()
            code = str(r.get("product_code", "") or "").strip()
            recipient = str(r.get("withdrawn_by", "") or "").strip()
            supervisor = str(r.get("supervisor_name", "") or "").strip()
            p_notes = _product_note(notes_map.get(code))
            notes_line = (
                f'<div class="act-meta">📝 ملاحظات الصنف: {html.escape(p_notes)}</div>' if p_notes else ""
            )
            st.markdown(
                f'<div class="activity-card">'
                f'<div class="act-time">🕒 {html.escape(stamp)}</div>'
                f'<div class="act-title">{html.escape(item) or "—"} '
                f'<span class="act-code">[{html.escape(code)}]</span></div>'
                f'<div class="act-meta">👤 الساحب: {html.escape(recipient) or "—"}'
                f' &nbsp;•&nbsp; 🛡️ المسؤول: {html.escape(supervisor) or "—"}</div>'
                f"{notes_line}"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("#### ⚡ أزرار الوصول السريع")
    b1, b2 = st.columns(2)
    with b1:
        if st.button(
            "📤 تسجيل سحب جديد", type="primary", use_container_width=True, key="qa_withdraw"
        ):
            _go_to(PAGES[1])
    with b2:
        if st.button(
            "➕ إضافة صنف جديد", type="primary", use_container_width=True, key="qa_add_item"
        ):
            _go_to(PAGES[2])


# --------------------------------------------------------------------------- #
#                        2) صفحة تسجيل السحب
# --------------------------------------------------------------------------- #
def page_withdraw() -> None:
    header("📤 تسجيل سحب", "صرف صنف من المخزن — يُسجَّل الطابع الزمني تلقائيًا")

    products = get_products()
    available = products[products["current_stock"].apply(to_number) > 0] if not products.empty else products
    if available.empty:
        st.info("لا توجد أصناف متاحة في المخزون. أضف أصنافًا من صفحة «➕ إدارة الأصناف».")
        return

    c0, _ = st.columns([1, 3])
    with c0:
        code_filter = st.text_input("🔍 بحث بكود الصنف", placeholder="", width="stretch")
    if code_filter.strip():
        available = available[
            available["product_code"].astype(str).str.contains(code_filter.strip(), case=False, na=False)
        ]
        if available.empty:
            st.warning("لا يوجد صنف بهذا الكود.")
            return

    options = {
        f'[{r["product_code"]}] {r["product_name"]} — رصيد {to_number(r["current_stock"]):g} {str(r.get("unit", "") or "").strip()}'.strip(): str(
            r["product_code"]
        )
        for _, r in available.iterrows()
    }

    st.markdown("#### 📦 الصنف المراد سحبه")
    choice = st.selectbox(
        "اختر الصنف",
        options=list(options.keys()),
        width="stretch",
        placeholder="",
        key="withdraw_product_select",
    )
    code = options[choice]
    selected = next((r for _, r in available.iterrows() if str(r["product_code"]).strip() == code), None)
    p_notes = _product_note(None if selected is None else selected.get("notes"))
    if p_notes:
        st.info(f"📝 ملاحظات الصنف: {p_notes}")
    else:
        st.caption("📝 لا توجد ملاحظات مسجلة لهذا الصنف.")

    with st.form("withdraw_form", clear_on_submit=True):
        st.markdown("#### بيانات السحب")
        c1, c2 = st.columns(2)
        with c1:
            supervisor = st.text_input("اسم المسؤول / أمين المخزن *", placeholder="", width="stretch")
        with c2:
            person = st.text_input("اسم الساحب / المستلم *", placeholder="", width="stretch")
        q1, q2 = st.columns(2)
        with q1:
            qty = st.number_input(
                "الكمية المسحوبة", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch"
            )

        stamp_now = datetime.now()
        d1, h1, m1, a1 = st.columns(4)
        with d1:
            wdate = st.date_input("تاريخ السحب", value=stamp_now.date(), width="stretch")
        with h1:
            hour12 = st.selectbox(
                "الساعة",
                options=list(range(1, 13)),
                index=(stamp_now.hour % 12 or 12) - 1,
                width="stretch",
            )
        with m1:
            minute = st.selectbox(
                "الدقيقة",
                options=list(range(0, 60)),
                index=stamp_now.minute,
                format_func=lambda m: f"{m:02d}",
                width="stretch",
            )
        with a1:
            ampm = st.selectbox(
                "ص / م",
                options=["ص", "م"],
                index=0 if stamp_now.hour < 12 else 1,
                width="stretch",
            )
        st.caption(
            "اختر الوقت بنظام 12 ساعة (ص/م) — يُسجَّل الطابع الزمني بصيغة (YYYY-MM-DD HH:MM:SS)."
        )

        submitted = st.form_submit_button("📤 تسجيل السحب", type="primary", use_container_width=True)

    if submitted:
        code = options[choice]
        hour24 = (int(hour12) % 12) + (12 if ampm == "م" else 0)
        stamp = (
            f"{wdate.strftime('%Y-%m-%d')} {hour24:02d}:{int(minute):02d}:00"
            if wdate
            else ""
        )
        ok, msg = sell_draw_item(code, qty, person, stamp, supervisor)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    _render_recent_withdrawals(limit=5)


def _render_recent_withdrawals(limit: int = 5) -> None:
    st.write("")
    st.markdown("#### 🕒 آخر عمليات السحب")
    w = get_withdrawals()
    if w.empty:
        st.info("لا توجد عمليات سحب بعد.")
        return
    recent = w.tail(limit).iloc[::-1].copy()

    def _txt(value) -> str:
        s = str(value).strip()
        return "" if s.lower() in ("nan", "none", "nat") else s

    products = get_products()
    prod_map = {_txt(r["product_code"]): r for _, r in products.iterrows()} if not products.empty else {}
    movements = get_movements()

    manufacturers, suppliers, expiries, remainings, product_notes = [], [], [], [], []
    for _, row in recent.iterrows():
        code = _txt(row.get("product_code"))
        p = prod_map.get(code)
        manufacturers.append(_txt(p.get("manufacturer")) if p is not None else "")
        suppliers.append(_txt(p.get("supplier")) if p is not None else "")
        expiries.append(_txt(p.get("expiry_date")) if p is not None else "")
        product_notes.append(_txt(p.get("notes")) if p is not None else "")

        remaining = _remaining_quantity(
            row, movements, p["current_stock"] if p is not None else None
        )
        remainings.append("" if remaining is None else f"{remaining:g}")

    recent["manufacturer"] = manufacturers
    recent["supplier"] = suppliers
    recent["expiry_date"] = expiries
    recent["remaining_quantity"] = remainings
    recent["product_notes"] = product_notes

    st.dataframe(
        recent[
            [
                "withdraw_date",
                "product_code",
                "product_name",
                "qty",
                "remaining_quantity",
                "manufacturer",
                "supplier",
                "expiry_date",
                "product_notes",
                "supervisor_name",
                "withdrawn_by",
            ]
        ].rename(
            columns={
                "withdraw_date": "التاريخ والوقت",
                "product_code": "الكود",
                "product_name": "الصنف",
                "qty": "الكمية",
                "remaining_quantity": "الرصيد المتبقي",
                "manufacturer": "شركة الصنع",
                "supplier": "شركة التوريد",
                "expiry_date": "تاريخ الانتهاء",
                "product_notes": "ملاحظات الصنف",
                "supervisor_name": "اسم المسؤول",
                "withdrawn_by": "اسم الساحب",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------------- #
#                        3) صفحة إدارة الأصناف
# --------------------------------------------------------------------------- #
ITEMS_INPUT_LTR_CSS = """
<style>
/* حقول الإدخال في إدارة الأصناف: محاذاة النصوص لليسار لعرض الإنجليزي والمختلط بشكل صحيح */
div[data-baseweb="input"] input,
div[data-baseweb="input"] textarea,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="textarea"] input {
    text-align: left !important;
    direction: ltr !important;
}
</style>
"""


def _item_added_by(row) -> str:
    return str(row.get("added_by", "") or "").strip()


def _item_label(row) -> str:
    """عنصر القائمة المنسدلة: الاسم (الكود) — الرصيد — أضافه: المستخدم."""
    base = (
        f'{row["product_name"]} ({row["product_code"]}) '
        f"— رصيد {to_number(row['current_stock']):g}"
    )
    added = _item_added_by(row)
    return f"{base} — أضافه: {added}" if added else base


def page_items() -> None:
    header("➕ إدارة الأصناف", "إضافة صنف جديد أو تعديل بياناته أو حذفه من المخزون")
    st.markdown(ITEMS_INPUT_LTR_CSS, unsafe_allow_html=True)

    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف بعد — أضف أول صنف من تبويب «إضافة صنف».")
    else:
        view = products.copy()
        if "added_by" not in view.columns:
            view["added_by"] = ""
        st.markdown("#### 📦 كل الأصناف")
        st.dataframe(
            view[
                ["product_code", "product_name", "unit", "current_stock", "added_by"]
            ].rename(
                columns={
                    "product_code": "الكود",
                    "product_name": "اسم الصنف",
                    "unit": "الوحدة",
                    "current_stock": "الرصيد الحالي",
                    "added_by": "أضافه",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    tab_add, tab_edit, tab_delete = st.tabs(
        ["➕ إضافة صنف", "✏️ تعديل صنف", "🗑️ حذف صنف"]
    )

    with tab_add:
        _render_add_item()
    with tab_edit:
        _render_edit_item()
    with tab_delete:
        _render_delete_item()


def _total_text(qty, unit_raw) -> tuple:
    """(قيمة الإجمالي كنص، هل خانة الوحدة رقمية). الإجمالي = الكمية × الوحدة."""
    unit_text = str(unit_raw or "").strip()
    unit_num = to_number(unit_text, -1.0)
    if not unit_text or unit_num < 0:
        return "", False
    return f"{to_number(qty, 0.0) * unit_num:g}", True


def _render_total_field(total_key: str, qty, unit_raw) -> None:
    """خانة الإجمالي (معطّلة للقراءة فقط) تُحدَّث لحظيًا مع تغيّر الكمية أو الوحدة."""
    total_text, unit_is_number = _total_text(qty, unit_raw)
    st.session_state[total_key] = total_text
    st.text_input(
        "الإجمالي",
        key=total_key,
        disabled=True,
        placeholder="",
        width="stretch",
    )
    if not unit_is_number:
        st.caption("⚠️ أدخل رقمًا في خانة «الوحدة» ليُحسب الإجمالي = الكمية × الوحدة.")


def _render_add_item() -> None:
    if st.session_state.pop("_clear_add_form", False):
        for key in (
            "add_code",
            "add_name",
            "add_date",
            "add_qty",
            "add_unit",
            "add_total",
            "add_mfr",
            "add_sup",
            "add_expiry",
            "add_notes",
        ):
            st.session_state.pop(key, None)

    st.markdown("#### إضافة صنف جديد")
    c1, c2, c3 = st.columns(3)
    with c1:
        code = st.text_input("كود الصنف *", placeholder="", width="stretch", key="add_code")
    with c2:
        name = st.text_input("اسم الصنف *", placeholder="", width="stretch", key="add_name")
    with c3:
        date_added = st.date_input(
            "تاريخ الإضافة", value=date.today(), width="stretch", key="add_date"
        )
    c4, c5, c6 = st.columns(3)
    with c4:
        start_qty = st.number_input(
            "الكمية", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch",
            key="add_qty",
        )
    with c5:
        unit = st.text_input(
            "الوحدة (قطعة، كرتونة، لتر...)", placeholder="", width="stretch", key="add_unit"
        )
    with c6:
        _render_total_field("add_total", start_qty, unit)
    c7, c8, c9 = st.columns(3)
    with c7:
        manufacturer = st.text_input(
            "شركة الصنع", placeholder="", width="stretch", key="add_mfr"
        )
    with c8:
        supplier = st.text_input(
            "شركة التوريد / المرسل", placeholder="", width="stretch", key="add_sup"
        )
    with c9:
        expiry_date = st.date_input(
            "تاريخ الانتهاء", value=None, width="stretch", key="add_expiry"
        )
    notes = st.text_area("ملاحظات", placeholder="", height=90, width="stretch", key="add_notes")
    submitted = st.button(
        "➕ إضافة الصنف", type="primary", use_container_width=True, key="add_submit"
    )

    if submitted:
        ok, msg = add_stock_item(
            name,
            start_qty,
            unit,
            code=code,
            date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
            notes=notes,
            manufacturer=manufacturer,
            supplier=supplier,
            expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
        )
        if ok:
            st.success(msg)
            added_by = current_username()
            if added_by:
                st.caption(f"👤 الصنف أُضيف بواسطة: {added_by} — سيظهر بجنبه في كل الجداول.")
            saved_notes = str(notes or "").strip()
            if saved_notes:
                st.caption(f"📝 ملاحظات الصنف المحفوظة في قاعدة البيانات: {saved_notes}")
            st.session_state["_clear_add_form"] = True
            st.rerun()
        else:
            st.error(msg)


def _render_edit_item() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف لتعديلها.")
        return

    labels = {
        _item_label(r): str(r["product_code"])
        for _, r in products.iterrows()
    }
    choice = st.selectbox(
        "اختر الصنف المراد تعديله",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="edit_item_select",
    )
    if choice is None:
        st.caption("اختر صنفًا لعرض بياناته وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in products.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_unit = _product_note(product.get("unit"))
    cur_mfr = _product_note(product.get("manufacturer"))
    cur_sup = _product_note(product.get("supplier"))
    cur_notes = _product_note(product.get("notes"))
    cur_location = _product_note(product.get("storage_location"))
    cur_stock = to_number(product.get("current_stock"))
    cur_min = to_number(product.get("min_stock"))
    cur_added = _product_note(product.get("date_added"))

    expiry_raw = _product_note(product.get("expiry_date"))
    cur_expiry = None
    if expiry_raw:
        try:
            cur_expiry = datetime.strptime(expiry_raw[:10], "%Y-%m-%d").date()
        except ValueError:
            cur_expiry = None

    st.markdown("#### تعديل بيانات الصنف")
    code_line = f"كود الصنف: `{code}` (ثابت للحفاظ على ربط السحوبات السابقة)"
    if cur_added:
        code_line += f" — تاريخ الإضافة: {cur_added}"
    st.caption(code_line)
    c1, c2, c3 = st.columns(3)
    with c1:
        name_v = st.text_input(
            "اسم الصنف *", value=cur_name, placeholder="", width="stretch",
            key=f"edit_name_{code}",
        )
    with c2:
        unit_v = st.text_input(
            "الوحدة (قطعة، كرتونة، لتر...)", value=cur_unit, placeholder="", width="stretch",
            key=f"edit_unit_{code}",
        )
    with c3:
        location_v = st.text_input(
            "مكان التخزين", value=cur_location, placeholder="", width="stretch",
            key=f"edit_location_{code}",
        )
    q1, q2, q3 = st.columns(3)
    with q1:
        stock_v = st.number_input(
            "الرصيد الحالي",
            min_value=0.0,
            step=1.0,
            value=cur_stock,
            placeholder="",
            width="stretch",
            key=f"edit_stock_{code}",
        )
    with q2:
        min_v = st.number_input(
            "الحد الأدنى",
            min_value=0.0,
            step=1.0,
            value=cur_min,
            placeholder="",
            width="stretch",
            key=f"edit_min_{code}",
        )
    with q3:
        _render_total_field(f"edit_total_{code}", stock_v, unit_v)
    c4, c5, c6 = st.columns(3)
    with c4:
        mfr_v = st.text_input(
            "شركة الصنع", value=cur_mfr, placeholder="", width="stretch",
            key=f"edit_mfr_{code}",
        )
    with c5:
        sup_v = st.text_input(
            "شركة التوريد / المرسل", value=cur_sup, placeholder="", width="stretch",
            key=f"edit_sup_{code}",
        )
    with c6:
        expiry_v = st.date_input(
            "تاريخ الانتهاء",
            value=cur_expiry,
            width="stretch",
            key=f"edit_expiry_{code}",
        )
    notes_v = st.text_area(
        "ملاحظات", value=cur_notes, placeholder="", height=90, width="stretch",
        key=f"edit_notes_{code}",
    )
    submitted = st.button(
        "💾 حفظ التعديلات", type="primary", use_container_width=True,
        key=f"edit_submit_{code}",
    )

    if not submitted:
        return

    name_v = str(name_v or "").strip()
    if not name_v:
        st.error("اسم الصنف مطلوب.")
        return

    new_stock = to_number(stock_v, -1)
    if new_stock < 0:
        st.error("الرصيد الحالي يجب أن يكون صفرًا أو أكثر.")
        return

    updates = {
        "product_name": name_v,
        "unit": str(unit_v or "").strip(),
        "storage_location": str(location_v or "").strip(),
        "current_stock": new_stock,
        "min_stock": to_number(min_v, 0.0),
        "manufacturer": str(mfr_v or "").strip(),
        "supplier": str(sup_v or "").strip(),
        "expiry_date": expiry_v.strftime("%Y-%m-%d") if expiry_v else "",
        "notes": str(notes_v or "").strip(),
    }
    ok, msg = update_product(code, updates)
    if not ok:
        st.error(msg)
        return

    delta = new_stock - cur_stock
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_stock,
            person=current_username() or "تعديل صنف",
            movement_type="تعديل رصيد",
            notes=f"تعديل يدوي للرصيد من {cur_stock:g} إلى {new_stock:g}",
        )
    st.success(f"{msg} 🔄 التعديلات محفوظة في Google Sheets.")
    st.rerun()


def _render_delete_item() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف للحذف.")
        return

    labels = {
        _item_label(r): str(r["product_code"])
        for _, r in products.iterrows()
    }
    with st.form("delete_item_form"):
        st.markdown("#### حذف صنف نهائيًا")
        st.caption("سيُحذف الصنف من ورقة المخزون. سجل السحوبات السابقة يبقى محفوظًا.")
        choice = st.selectbox("اختر الصنف", options=list(labels.keys()), width="stretch", placeholder="")
        confirmed = st.checkbox("أؤكد رغبتي في حذف هذا الصنف نهائيًا", width="stretch")
        submitted = st.form_submit_button("🗑️ حذف الصنف", type="primary", use_container_width=True)

    if submitted:
        code = labels[choice]
        if not confirmed:
            st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
            return
        ok, msg = delete_product(code, force=True)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


# --------------------------------------------------------------------------- #
#                        4) صفحة التقارير والسجلات
# --------------------------------------------------------------------------- #
def page_reports() -> None:
    header("📊 التقارير والسجلات", "حالة المخزون وسجل السحوبات الكامل")

    products = get_products()
    withdrawals = get_withdrawals()

    total_items = len(products)
    total_withdrawals = len(withdrawals)
    total_stock = sum(to_number(v) for v in products["current_stock"]) if not products.empty else 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(metric_card("إجمالي الأصناف", total_items), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("إجمالي عمليات السحب", total_withdrawals, "purple"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("إجمالي رصيد المخزن", f"{total_stock:,.2f}", "good"), unsafe_allow_html=True)

    st.write("")
    st.markdown("#### 📦 حالة المخزون الحالية")
    if products.empty:
        st.info("لا توجد أصناف.")
    else:
        stock_view = products.copy()
        if "added_by" not in stock_view.columns:
            stock_view["added_by"] = ""
        stock_view["current_stock"] = stock_view["current_stock"].apply(to_number)
        stock_view["min_stock"] = stock_view["min_stock"].apply(to_number)
        stock_view["starting_stock"] = stock_view["starting_stock"].apply(to_number)
        stock_view["total_withdrawn"] = stock_view["total_withdrawn"].apply(to_number)
        stock_view["الحالة"] = stock_view.apply(
            lambda r: "⚠️ منخفض" if r["current_stock"] <= r["min_stock"] else "✅ جيد", axis=1
        )
        code_filter = st.text_input(
            "🔍 بحث بكود الصنف", key="stock_code_filter", placeholder="", width="stretch"
        )
        if code_filter.strip():
            stock_view = stock_view[
                stock_view["product_code"].astype(str).str.contains(
                    code_filter.strip(), case=False, na=False
                )
            ]
        # قيم التصفية الجديدة تُقرأ من الحالة قبل بناء الجدول، لأن حقولها تُنشأ أسفله
        mfr_filter = str(st.session_state.get("stock_mfr_filter", "")).strip()
        sup_filter = str(st.session_state.get("stock_sup_filter", "")).strip()
        exp_filter = str(st.session_state.get("stock_exp_filter", "")).strip()
        if mfr_filter:
            stock_view = stock_view[
                stock_view["manufacturer"].astype(str).str.contains(mfr_filter, case=False, na=False)
            ]
        if sup_filter:
            stock_view = stock_view[
                stock_view["supplier"].astype(str).str.contains(sup_filter, case=False, na=False)
            ]
        if exp_filter:
            stock_view = stock_view[
                stock_view["expiry_date"].astype(str).str.contains(exp_filter, case=False, na=False)
            ]
        st.dataframe(
            stock_view[
                [
                    "product_code",
                    "product_name",
                    "unit",
                    "starting_stock",
                    "total_withdrawn",
                    "current_stock",
                    "date_added",
                    "added_by",
                    "manufacturer",
                    "supplier",
                    "expiry_date",
                    "notes",
                    "الحالة",
                ]
            ].rename(
                columns={
                    "product_code": "الكود",
                    "product_name": "اسم الصنف",
                    "unit": "الوحدة",
                    "starting_stock": "الكمية الابتدائية",
                    "total_withdrawn": "إجمالي المسحوب",
                    "current_stock": "الرصيد الحالي",
                    "date_added": "تاريخ الإضافة",
                    "added_by": "أضافه",
                    "manufacturer": "شركة الصنع",
                    "supplier": "شركة التوريد",
                    "expiry_date": "تاريخ الانتهاء",
                    "notes": "ملاحظات الصنف",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.write("")
        st.caption("🔍 تصفية الجدول حسب بيانات الشركة والتاريخ (بحث جزئي مسموح):")
        f1, f2, f3 = st.columns(3)
        with f1:
            st.text_input(
                "🔍 بحث بشركة الصنع", key="stock_mfr_filter", placeholder="", width="stretch"
            )
        with f2:
            st.text_input(
                "🔍 بحث بشركة التوريد", key="stock_sup_filter", placeholder="", width="stretch"
            )
        with f3:
            st.text_input(
                "🔍 بحث بتاريخ الانتهاء", key="stock_exp_filter", placeholder="", width="stretch"
            )

    st.write("")
    st.markdown("#### 📜 سجل السحوبات الكامل")
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب بعد.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        supervisor_search = st.text_input("🔍 بحث باسم المسؤول", placeholder="", width="stretch")
    with c2:
        person = st.text_input("🔍 بحث باسم الساحب", placeholder="", width="stretch")
    with c3:
        item = st.text_input("🔍 بحث باسم الصنف", placeholder="", width="stretch")
    with c4:
        code_search = st.text_input("🔍 بحث بكود الصنف", placeholder="", width="stretch")
    with c5:
        start = st.date_input("من تاريخ", value=None, width="stretch")

    df = withdrawals.copy()
    if supervisor_search.strip():
        df = df[
            df["supervisor_name"].astype(str).str.contains(supervisor_search.strip(), case=False, na=False)
        ]
    if person.strip():
        df = df[df["withdrawn_by"].astype(str).str.contains(person.strip(), case=False, na=False)]
    if item.strip():
        df = df[df["product_name"].astype(str).str.contains(item.strip(), case=False, na=False)]
    if code_search.strip():
        df = df[
            df["product_code"].astype(str).str.contains(code_search.strip(), case=False, na=False)
        ]
    if start:
        df = df[df["withdraw_date"].astype(str).str[:10] >= start.strftime("%Y-%m-%d")]

    notes_map = _notes_by_code(products)
    log_view = df.iloc[::-1].copy()
    log_view["product_notes"] = [
        _product_note(notes_map.get(str(c).strip())) for c in log_view["product_code"]
    ]
    view = log_view[
        [
            "withdraw_date",
            "product_code",
            "product_name",
            "qty",
            "product_notes",
            "supervisor_name",
            "withdrawn_by",
        ]
    ].rename(
        columns={
            "withdraw_date": "التاريخ والوقت",
            "product_code": "الكود",
            "product_name": "الصنف",
            "qty": "الكمية",
            "product_notes": "ملاحظات الصنف",
            "supervisor_name": "اسم المسؤول",
            "withdrawn_by": "اسم الساحب",
        }
    )
    total_qty = sum(to_number(v) for v in df["qty"])
    st.caption(f"عدد العمليات: {len(df)} — إجمالي الكميات المسحوبة: {total_qty:g}")
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ تصدير السجل CSV",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name="withdrawals_log.csv",
        mime="text/csv",
        use_container_width=True,
    )


# --------------------------------------------------------------------------- #
#                       5) صفحة إدارة المستخدمين (للأدمن)
# --------------------------------------------------------------------------- #
def _users_dataframe():
    users = get_users()
    if users.empty:
        return users
    view = users.copy()
    view["الحالة"] = view["role"].apply(lambda r: "👑 مدير" if str(r).strip().lower() == ROLE_ADMIN else "👤 مستخدم")
    cols = ["username"]
    if "created_at" in view.columns:
        cols.append("created_at")
    cols.append("الحالة")
    return view[cols].rename(
        columns={"username": "اسم المستخدم", "created_at": "تاريخ الإنشاء"}
    )


def page_users() -> None:
    header("👥 إدارة المستخدمين", "إضافة وحذف المستخدمين وعرضهم وتغيير كلمات المرور")
    if not is_admin():
        st.error("هذه الصفحة متاحة لحساب المدير فقط.")
        return

    users = get_users()
    usernames = [str(u).strip() for u in users["username"]] if not users.empty else []

    tab_add, tab_del, tab_list, tab_reset = st.tabs(
        ["➕ إضافة مستخدم جديد", "🗑️ حذف مستخدم", "📋 عرض المستخدمين", "🔑 تغيير كلمة المرور"]
    )

    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            st.markdown("#### إضافة مستخدم جديد")
            c1, c2, c3 = st.columns(3)
            with c1:
                new_username = st.text_input("اسم المستخدم *", placeholder="", width="stretch")
            with c2:
                new_password = st.text_input("كلمة المرور *", type="password", placeholder="", width="stretch")
            with c3:
                new_role = st.selectbox(
                    "الصلاحية",
                    options=ROLES,
                    format_func=lambda r: "👑 مدير" if r == ROLE_ADMIN else "👤 مستخدم",
                    width="stretch",
                    placeholder="",
                )
            submitted = st.form_submit_button("➕ إضافة المستخدم", type="primary", use_container_width=True)
        if submitted:
            ok, msg = add_user(new_username, new_password, new_role)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()

    with tab_del:
        if not usernames:
            st.info("لا يوجد مستخدمون للحذف.")
        else:
            with st.form("delete_user_form"):
                st.markdown("#### حذف مستخدم")
                st.caption("لا يمكن حذف آخر حساب مدير في النظام.")
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
                confirmed = st.checkbox("أؤكد حذف هذا المستخدم نهائيًا", width="stretch")
                submitted = st.form_submit_button("🗑️ حذف المستخدم", type="primary", use_container_width=True)
            if submitted:
                if not target:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                elif not confirmed:
                    st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
                else:
                    ok, msg = delete_user(target)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

    with tab_list:
        st.markdown("#### قائمة المستخدمين الحاليين")
        view = _users_dataframe()
        if view is None or view.empty:
            st.info("لا يوجد مستخدمون.")
        else:
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.caption(f"عدد المستخدمين: {len(view)}")

    with tab_reset:
        if not usernames:
            st.info("لا يوجد مستخدمون.")
        else:
            with st.form("reset_password_form"):
                st.markdown("#### تغيير كلمة مرور مستخدم")
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
                c1, c2 = st.columns(2)
                with c1:
                    new_password = st.text_input(
                        "كلمة المرور الجديدة *", type="password", placeholder="", width="stretch"
                    )
                with c2:
                    confirm_password = st.text_input(
                        "تأكيد كلمة المرور *", type="password", placeholder="", width="stretch"
                    )
                submitted = st.form_submit_button("🔑 تغيير كلمة المرور", type="primary", use_container_width=True)
            if submitted:
                if not target:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                elif new_password != confirm_password:
                    st.error("كلمتا المرور غير متطابقتين.")
                else:
                    ok, msg = reset_password(target, new_password)
                    st.success(msg) if ok else st.error(msg)

    st.write("")
    st.markdown("#### ⚙️ صلاحية المستخدم")
    if usernames:
        with st.form("set_role_form"):
            c1, c2 = st.columns(2)
            with c1:
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
            with c2:
                role = st.selectbox(
                    "الصلاحية",
                    options=ROLES,
                    format_func=lambda r: "👑 مدير" if r == ROLE_ADMIN else "👤 مستخدم",
                    width="stretch",
                    placeholder="",
                )
            submitted = st.form_submit_button("💾 حفظ الصلاحية", use_container_width=True)
        if submitted:
            if not target:
                st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
            else:
                ok, msg = set_role(target, role)
                st.success(msg) if ok else st.error(msg)

    # ------------------------------------------------------------------ #
    #               تصفير البيانات التجريبية (إجراء خطر — للمدير فقط)
    # ------------------------------------------------------------------ #
    st.write("")
    st.markdown("#### 🧹 تصفير البيانات التجريبية")
    st.caption(
        "يحذف كل صفوف الأصناف وسجل السحوبات من قاعدة البيانات المحلية نهائيًا."
    )
    confirmed = st.checkbox(
        "تأكيد مسح كافة البيانات التجريبية",
        key="confirm_clear_test_data",
        width="stretch",
    )
    if st.button(
        "🧹 تصفير البيانات التجريبية",
        type="primary",
        use_container_width=True,
        disabled=not confirmed,
        key="clear_test_data_btn",
    ):
        ok, msg = clear_test_data()
        if ok:
            st.success("تم مسح جميع البيانات التجريبية بنجاح والمخزن جاهز للعمل")
        else:
            st.error(msg)
    if not confirmed:
        st.caption("⚠️ حدّد مربع التأكيد أعلاه لتفعيل زر التصفير.")


# --------------------------------------------------------------------------- #
#                                  التشغيل
# --------------------------------------------------------------------------- #
def main() -> None:
    cfg = load_config()
    try:
        offline.configure(cfg)      # يلتقط بيانات المزامنة للخيط الخلفي
        offline.ensure_worker()     # خيط مزامنة تلقائي: يدفع الطابور ويسحب البيانات في الخلفية
        offline.flush_if_pending()  # دفعة فورية عند فتح التطبيق (سريعة)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تجهيز نظام المزامنة المحلية: {exc}"
    try:
        configure(cfg.database_path)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تجهيز مسار قاعدة البيانات: {exc}"

    if not is_logged_in():
        login_form()
        return

    _bootstrap()
    page = _sidebar()
    if not _guard():
        return
    _topbar()

    if page == PAGES[0]:
        page_home()
    elif page == PAGES[1]:
        page_withdraw()
    elif page == PAGES[2]:
        page_items()
    elif page == ADMIN_PAGES[0]:
        page_users()
    else:
        page_reports()


if __name__ == "__main__":
    main()
