"""صفحة طلبات المعمل: إنشاء الطلبات، الأصناف، السحب، التفاصيل."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core.gsheets import to_number
from core.services import (
    add_order_item,
    complete_order,
    create_order,
    delete_order,
    find_product,
    get_order,
    get_orders,
    get_products,
    get_withdrawals,
    order_items,
    previous_pending_for_product,
    reopen_order,
    now_str,
    today_str,
    withdraw,
)
from core.styles import alert, header

STATUS_OPEN = "مفتوحة"
STATUS_DONE = "مكتملة"


def render() -> None:
    selected = st.session_state.get("selected_order")
    if selected and get_order(selected):
        _render_details(selected)
    else:
        st.session_state.pop("selected_order", None)
        _render_list()


# --------------------------------------------------------------------------- #
#                                  القائمة
# --------------------------------------------------------------------------- #
def _render_list() -> None:
    header("📋 طلبات المعمل", "إدارة طلبات المعمل وصرف الأصناف على دفعات")

    top1, top2 = st.columns([3, 1])
    with top2:
        if st.button("➕ إضافة طلبية جديدة", type="primary", use_container_width=True):
            st.session_state["show_new_order"] = not st.session_state.get("show_new_order", False)

    if st.session_state.get("show_new_order"):
        _render_new_order_form()

    orders = get_orders()
    if orders.empty:
        st.info("لا توجد طلبات بعد. اضغط «➕ إضافة طلبية جديدة» للبدء.")
        return

    st.write("")
    c1, c2 = st.columns([2, 1])
    with c1:
        search = st.text_input("🔍 بحث برقم الطلبية أو المعمل أو المسؤول")
    with c2:
        status_filter = st.selectbox("الحالة", ["الكل", STATUS_OPEN, STATUS_DONE])

    df = orders.copy()
    if status_filter != "الكل":
        df = df[df["status"].astype(str) == status_filter]
    if search.strip():
        s = search.strip()
        mask = (
            df["order_no"].astype(str).str.contains(s, case=False, na=False)
            | df["factory_name"].astype(str).str.contains(s, case=False, na=False)
            | df["responsible_person"].astype(str).str.contains(s, case=False, na=False)
        )
        df = df[mask]

    st.caption(f"عدد الطلبات: {len(df)}")
    if df.empty:
        st.info("لا توجد نتائج مطابقة.")
        return

    rows = []
    for _, o in df.iloc[::-1].iterrows():
        oi = order_items(o["order_no"])
        req = oi["_required"].sum() if not oi.empty else 0
        wd = oi["_withdrawn"].sum() if not oi.empty else 0
        rows.append(
            {
                "رقم الطلبية": o["order_no"],
                "التاريخ": o.get("order_date", ""),
                "المعمل/القسم": o.get("factory_name", ""),
                "المسؤول": o.get("responsible_person", ""),
                "الحالة": o.get("status", ""),
                "عدد الأصناف": len(oi),
                "المطلوب": f"{req:g}",
                "المسحوب": f"{wd:g}",
                "المتبقي": f"{max(req - wd, 0):g}",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.write("")
    st.markdown("### 🔎 عرض تفاصيل طلبية")
    codes = orders["order_no"].astype(str).tolist()[::-1]
    choice = st.selectbox("اختر رقم الطلبية", options=[""] + codes, key="open_order_select")
    if choice and st.button("عرض التفاصيل", type="primary"):
        st.session_state["selected_order"] = choice
        st.rerun()


def _render_new_order_form() -> None:
    with st.form("new_order_form", clear_on_submit=True):
        st.markdown("#### ➕ طلبية جديدة")
        st.caption("رقم الطلبية يتم توليده تلقائيًا عند الحفظ.")
        c1, c2 = st.columns(2)
        with c1:
            order_date = st.date_input("تاريخ وصول الطلبية", value=date.today())
            factory = st.text_input("اسم المعمل أو القسم *")
        with c2:
            responsible = st.text_input("اسم المسؤول عن الطلبية *")
            notes = st.text_area("ملاحظات (اختياري)", height=70)
        submitted = st.form_submit_button("إنشاء الطلبية", type="primary", use_container_width=True)

    if submitted:
        ok, msg, order_no = create_order(
            order_date.strftime("%Y-%m-%d") if order_date else today_str(),
            factory,
            responsible,
            notes,
        )
        if ok:
            st.session_state["show_new_order"] = False
            st.session_state["selected_order"] = order_no
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


# --------------------------------------------------------------------------- #
#                                التفاصيل
# --------------------------------------------------------------------------- #
def _render_details(order_no: str) -> None:
    order = get_order(order_no)
    if not order:
        st.session_state.pop("selected_order", None)
        st.rerun()

    if st.button("⬅️ رجوع إلى قائمة الطلبات"):
        st.session_state.pop("selected_order", None)
        st.rerun()

    status = str(order.get("status", STATUS_OPEN))
    badge = "badge-done" if status == STATUS_DONE else "badge-open"
    header(f"🧾 الطلبية {order_no}", f"تفاصيل أصناف الطلبية وسجل السحب")
    st.markdown(
        f'<span class="badge {badge}">{status}</span>', unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("تاريخ الطلبية", str(order.get("order_date", "-")))
    c2.metric("المعمل / القسم", str(order.get("factory_name", "-")))
    c3.metric("المسؤول", str(order.get("responsible_person", "-")))
    items = order_items(order_no)
    req = items["_required"].sum() if not items.empty else 0
    wd = items["_withdrawn"].sum() if not items.empty else 0
    c4.metric("المتبقي الكلي", f"{max(req - wd, 0):g}")
    if str(order.get("notes", "")).strip():
        st.caption(f"ملاحظات: {order['notes']}")

    st.write("")
    b1, b2, b3 = st.columns([1, 1, 1])
    with b1:
        if st.button("➕ إضافة صنف", type="primary", use_container_width=True):
            st.session_state["show_add_item"] = not st.session_state.get("show_add_item", False)

    if st.session_state.get("show_add_item"):
        _render_add_item_form(order_no)

    st.markdown("#### 📦 أصناف الطلبية")
    if items.empty:
        st.info("لا توجد أصناف في هذه الطلبية. أضف صنفًا من الزر أعلاه.")
    else:
        view = items[
            [
                "product_code",
                "product_name",
                "unit",
                "required_qty",
                "withdrawn_qty",
                "_remaining",
                "last_withdrawn_by",
                "last_withdraw_date",
            ]
        ].rename(
            columns={
                "product_code": "كود الصنف",
                "product_name": "اسم الصنف",
                "unit": "الوحدة",
                "required_qty": "المطلوب",
                "withdrawn_qty": "المسحوب",
                "_remaining": "المتبقي",
                "last_withdrawn_by": "الساحب",
                "last_withdraw_date": "آخر سحب (تاريخ ووقت)",
            }
        )
        st.dataframe(view, use_container_width=True, hide_index=True)

    pending = items[items["_remaining"] > 0] if not items.empty else items
    if not items.empty:
        w1, w2 = st.columns([1, 1])
        with w1:
            if not pending.empty and st.button(
                "📤 تسجيل سحب", type="primary", use_container_width=True, key="toggle_withdraw"
            ):
                st.session_state["show_withdraw"] = not st.session_state.get("show_withdraw", False)
                st.session_state.pop("withdraw_item_id", None)

        if pending.empty:
            st.success("تم صرف كل الأصناف المطلوبة في هذه الطلبية.")
        else:
            _render_item_withdraw_buttons(order_no, pending)
            if st.session_state.get("show_withdraw") or "withdraw_item_id" in st.session_state:
                selected_item = st.session_state.get("withdraw_item_id")
                _render_withdraw_form(order_no, pending, selected_item)

    st.write("")
    actions = st.columns([1, 1, 3])
    with actions[0]:
        if status == STATUS_DONE:
            if st.button("🔓 إعادة فتح الطلبية", use_container_width=True):
                ok, msg = reopen_order(order_no)
                (st.success if ok else st.error)(msg)
                st.rerun()
        else:
            if st.button("✅ إتمام الطلبية", type="primary", use_container_width=True):
                ok, msg = complete_order(order_no)
                (st.success if ok else st.error)(msg)
                st.rerun()
    with actions[1]:
        _render_delete_order(order_no)

    _render_withdrawals_log(order_no)


def _render_delete_order(order_no: str) -> None:
    confirm_key = f"confirm_del_order_{order_no}"
    if not st.session_state.get(confirm_key):
        if st.button("🗑️ حذف الطلبية", use_container_width=True, key=f"del_order_{order_no}"):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        if st.button("⚠️ تأكيد الحذف", type="primary", use_container_width=True, key=f"del_ok_{order_no}"):
            ok, msg = delete_order(order_no)
            st.session_state.pop(confirm_key, None)
            st.session_state.pop("selected_order", None)
            (st.success if ok else st.error)(msg)
            st.rerun()


def _render_add_item_form(order_no: str) -> None:
    products = get_products()
    codes = products["product_code"].astype(str).tolist() if not products.empty else []

    with st.form("add_item_form", clear_on_submit=True):
        st.markdown("##### ➕ إضافة صنف إلى الطلبية")
        c1, c2, c3 = st.columns(3)
        with c1:
            manual_code = st.text_input("كود الصنف")
        with c2:
            name = st.text_input("اسم الصنف (اختياري)")
        with c3:
            required = st.number_input("الكمية المطلوبة", min_value=0.0, step=1.0, value=None, placeholder="")
        pick = st.selectbox("أو اختر صنفًا من القائمة", options=[""] + codes)
        submitted = st.form_submit_button("إضافة الصنف", type="primary", use_container_width=True)

    code = manual_code.strip() or pick
    if submitted:
        if not code:
            st.error("أدخل كود الصنف أو اختر صنفًا.")
            return
        if not name.strip():
            p = find_product(code)
            if p:
                name = p["product_name"]
        unit = ""
        p = find_product(code)
        if p:
            unit = p.get("unit", "")

        pending = previous_pending_for_product(code, order_no)
        ok, msg = add_order_item(order_no, code, name, required, unit)
        if ok:
            st.success(msg)
            if pending:
                _show_pending_alert(code, pending)
        else:
            st.error(msg)
        if ok:
            st.session_state["show_add_item"] = False


def _show_pending_alert(code: str, pending) -> None:
    lines = [
        f"⚠️ <strong>يوجد متبقي من طلبيات سابقة لنفس الصنف ({code}).</strong><br>"
        "لن يتم خلط الطلبية القديمة بالجديدة؛ كل طلبية تحتفظ ببياناتها."
    ]
    rows = []
    for p in pending:
        rows.append(
            {
                "رقم الطلبية القديمة": p["order_no"],
                "تاريخها": p["order_date"],
                "المعمل": p["factory_name"],
                "المطلوب": f'{p["required_qty"]:g}',
                "إجمالي المسحوب": f'{p["withdrawn_qty"]:g}',
                "المتبقي": f'{p["remaining_qty"]:g}',
            }
        )
    alert("<br>".join(lines))
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_withdraw_form(order_no: str, pending: pd.DataFrame, selected_item: str | None = None) -> None:
    options = {
        f'{r["product_name"]} ({r["product_code"]}) — متبقي {r["_remaining"]:g}': r["item_id"]
        for _, r in pending.iterrows()
    }
    keys = list(options.keys())
    default_idx = 0
    if selected_item:
        for i, k in enumerate(keys):
            if options[k] == selected_item:
                default_idx = i
                break
    with st.form("withdraw_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            choice = st.selectbox("الصنف", options=keys, index=default_idx)
        with c2:
            qty = st.number_input("الكمية المسحوبة", min_value=0.0, step=1.0, value=None, placeholder="")
        with c3:
            person = st.text_input("اسم الشخص الذي قام بالسحب")
        t1, t2, t3 = st.columns(3)
        with t1:
            wdate = st.date_input("تاريخ السحب", value=date.today())
        with t2:
            wtime = st.time_input("وقت السحب", value=datetime.now().time().replace(second=0, microsecond=0))
        with t3:
            st.caption("يُسجَّل كل سحب كعملية مستقلة بالتاريخ والوقت الكامل.")
        notes = st.text_input("ملاحظات (اختياري)")
        submitted = st.form_submit_button("تسجيل السحب", type="primary", use_container_width=True)

    if submitted:
        item_id = options[choice]
        stamp = f"{wdate.strftime('%Y-%m-%d')} {wtime.strftime('%H:%M:%S')}" if wdate and wtime else now_str()
        ok, msg = withdraw(
            order_no,
            item_id,
            qty,
            person,
            stamp,
            notes,
        )
        if ok:
            st.session_state.pop("withdraw_item_id", None)
            st.session_state["show_withdraw"] = False
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def _render_item_withdraw_buttons(order_no: str, pending: pd.DataFrame) -> None:
    st.markdown("###### 📤 سحب سريع من صنف")
    st.caption("اضغط «سحب» بجانب الصنف لفتح نموذج السحب مع اختياره تلقائيًا.")
    cols = st.columns(min(len(pending), 3))
    for i, (_, r) in enumerate(pending.iterrows()):
        with cols[i % len(cols)]:
            if st.button(
                f'📤 سحب: {r["product_name"]} (متبقي {r["_remaining"]:g})',
                key=f'quick_withdraw_{r["item_id"]}',
                use_container_width=True,
            ):
                st.session_state["withdraw_item_id"] = r["item_id"]
                st.session_state["show_withdraw"] = True
                st.rerun()


def _render_withdrawals_log(order_no: str) -> None:
    st.markdown("#### 📜 سجل السحب الخاص بالطلبية")
    w = get_withdrawals()
    if not w.empty:
        w = w[w["order_no"].astype(str) == str(order_no)]
    if w is None or w.empty:
        st.info("لا توجد عمليات سحب مسجلة لهذه الطلبية بعد.")
        return
    st.dataframe(
        w[["withdrawal_id", "product_name", "qty", "withdraw_date", "withdrawn_by"]].rename(
            columns={
                "withdrawal_id": "رقم السحب",
                "product_name": "الصنف",
                "qty": "الكمية",
                "withdraw_date": "التاريخ والوقت",
                "withdrawn_by": "الساحب",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )