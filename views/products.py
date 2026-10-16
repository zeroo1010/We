"""صفحة الأصناف: إضافة، تعديل، بحث، تفاصيل."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from core.gsheets import to_number
from core.services import (
    add_product,
    delete_product,
    find_product,
    get_order_items,
    get_products,
    get_withdrawals,
    update_product,
)
from core.styles import alert, header


def _products_table(df):
    view = df.copy()
    view["الرصيد"] = view["current_stock"].apply(to_number)
    view["حالة"] = view.apply(
        lambda r: "منخفض" if to_number(r["current_stock"]) <= to_number(r["min_stock"]) else "جيد",
        axis=1,
    )
    return view[
        [
            "product_code",
            "product_name",
            "unit",
            "الرصيد",
            "min_stock",
            "storage_location",
            "manufacturer",
            "supplier",
            "expiry_date",
            "حالة",
        ]
    ].rename(
        columns={
            "product_code": "الكود",
            "product_name": "اسم الصنف",
            "unit": "الوحدة",
            "min_stock": "الحد الأدنى",
            "storage_location": "مكان التخزين",
            "manufacturer": "شركة الصنع",
            "supplier": "شركة التوريد",
            "expiry_date": "تاريخ الانتهاء",
        }
    )


def render() -> None:
    header("🧱 الأصناف", "إدارة أصناف المخزن والأرصدة")

    tab_list, tab_add, tab_edit = st.tabs(["📋 قائمة الأصناف", "➕ إضافة صنف", "✏️ تعديل صنف"])

    with tab_add:
        _render_add_form()

    with tab_list:
        _render_list()

    with tab_edit:
        _render_edit()


def _render_add_form() -> None:
    with st.form("add_product_form", clear_on_submit=True):
        st.markdown("#### ➕ إضافة صنف جديد")
        c1, c2 = st.columns(2)
        with c1:
            code = st.text_input("كود الصنف *")
            name = st.text_input("اسم الصنف *")
            unit = st.text_input("الوحدة (كجم، لتر، قطعة...)")
            manufacturer = st.text_input("شركة الصنع", placeholder="")
        with c2:
            current_stock = st.number_input("الرصيد الحالي", min_value=0.0, step=1.0, value=None, placeholder="")
            min_stock = st.number_input("الحد الأدنى", min_value=0.0, step=1.0, value=None, placeholder="")
            location = st.text_input("مكان التخزين")
            supplier = st.text_input("شركة التوريد / المرسل", placeholder="")
        expiry_date = st.date_input("تاريخ الانتهاء", value=None)
        notes = st.text_area("ملاحظات", height=70)
        submitted = st.form_submit_button("حفظ الصنف", type="primary", use_container_width=True)

    if submitted:
        ok, msg = add_product(
            {
                "product_code": code,
                "product_name": name,
                "unit": unit,
                "current_stock": current_stock,
                "min_stock": min_stock,
                "storage_location": location,
                "notes": notes,
                "manufacturer": manufacturer,
                "supplier": supplier,
                "expiry_date": expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
            }
        )
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def _render_list() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف بعد. أضف صنفًا من التبويب المجاور.")
        return

    search = st.text_input("🔍 البحث بالكود أو الاسم أو مكان التخزين")
    df = products
    if search.strip():
        s = search.strip()
        mask = (
            df["product_code"].astype(str).str.contains(s, case=False, na=False)
            | df["product_name"].astype(str).str.contains(s, case=False, na=False)
            | df["storage_location"].astype(str).str.contains(s, case=False, na=False)
        )
        df = df[mask]

    # قيم التصفية الجديدة تُقرأ قبل بناء الجدول لأن حقولها تُنشأ أسفله
    mfr_search = str(st.session_state.get("list_mfr_search", "")).strip()
    sup_search = str(st.session_state.get("list_sup_search", "")).strip()
    exp_search = str(st.session_state.get("list_exp_search", "")).strip()
    if mfr_search:
        df = df[df["manufacturer"].astype(str).str.contains(mfr_search, case=False, na=False)]
    if sup_search:
        df = df[df["supplier"].astype(str).str.contains(sup_search, case=False, na=False)]
    if exp_search:
        df = df[df["expiry_date"].astype(str).str.contains(exp_search, case=False, na=False)]

    st.caption(f"عدد الأصناف: {len(df)}")
    st.dataframe(_products_table(df), use_container_width=True, hide_index=True)

    st.write("")
    st.caption("🔍 تصفية حسب بيانات الشركة والتاريخ (بحث جزئي مسموح):")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.text_input("🔍 بحث بشركة الصنع", key="list_mfr_search", placeholder="")
    with s2:
        st.text_input("🔍 بحث بشركة التوريد", key="list_sup_search", placeholder="")
    with s3:
        st.text_input("🔍 بحث بتاريخ الانتهاء", key="list_exp_search", placeholder="")

    st.write("")
    st.markdown("### 🔎 تفاصيل صنف")
    codes = df["product_code"].astype(str).tolist()
    if not codes:
        return
    selected = st.selectbox("اختر صنفًا لعرض تفاصيله", options=[""] + codes)
    if not selected:
        return
    product = find_product(selected)
    if not product:
        st.warning("الصنف غير موجود.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("الرصيد الحالي", f'{to_number(product["current_stock"]):g}')
    c2.metric("الحد الأدنى", f'{to_number(product["min_stock"]):g}')
    c3.metric("الوحدة", product.get("unit") or "-")
    if to_number(product["current_stock"]) <= to_number(product["min_stock"]):
        alert("⚠️ <strong>المخزون منخفض</strong> — الرصيد الحالي أقل من أو يساوي الحد الأدنى.")

    items = get_order_items()
    related = items[items["product_code"].astype(str).str.strip() == str(selected).strip()] if not items.empty else items
    st.markdown("#### 📦 الطلبات المرتبطة بهذا الصنف")
    if related.empty:
        st.info("لا توجد طلبات مرتبطة بهذا الصنف.")
    else:
        view = related[
            ["order_no", "required_qty", "withdrawn_qty", "_remaining", "last_withdraw_date", "last_withdrawn_by"]
        ].rename(
            columns={
                "order_no": "رقم الطلبية",
                "required_qty": "المطلوب",
                "withdrawn_qty": "المسحوب",
                "_remaining": "المتبقي",
                "last_withdraw_date": "آخر سحب (تاريخ ووقت)",
                "last_withdrawn_by": "آخر ساحب",
            }
        )
        st.dataframe(view, use_container_width=True, hide_index=True)

    withdrawals = get_withdrawals()
    w = withdrawals[withdrawals["product_code"].astype(str).str.strip() == str(selected).strip()] if not withdrawals.empty else withdrawals
    st.markdown("#### 📤 سجل عمليات السحب لهذا الصنف")
    if w.empty:
        st.info("لا توجد عمليات سحب لهذا الصنف.")
    else:
        total = sum(to_number(v) for v in w["qty"])
        st.caption(f"إجمالي الكمية المسحوبة من هذا الصنف: {total:g}")
        st.dataframe(
            w[["withdrawal_id", "order_no", "qty", "withdraw_date", "withdrawn_by"]].rename(
                columns={
                    "withdrawal_id": "رقم السحب",
                    "order_no": "رقم الطلبية",
                    "qty": "الكمية",
                    "withdraw_date": "التاريخ والوقت",
                    "withdrawn_by": "الساحب",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def _render_edit() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف للتعديل.")
        return
    codes = products["product_code"].astype(str).tolist()
    code = st.selectbox("اختر الصنف", options=[""] + codes, key="edit_product_select")
    if not code:
        return
    product = find_product(code)
    if not product:
        return

    with st.form("edit_product_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("اسم الصنف", value=str(product.get("product_name", "")))
            unit = st.text_input("الوحدة", value=str(product.get("unit", "")))
            location = st.text_input("مكان التخزين", value=str(product.get("storage_location", "")))
        with c2:
            current_stock = st.number_input(
                "الرصيد الحالي", min_value=0.0, step=1.0, value=to_number(product.get("current_stock"))
            )
            min_stock = st.number_input(
                "الحد الأدنى", min_value=0.0, step=1.0, value=to_number(product.get("min_stock"))
            )
        notes = st.text_area("ملاحظات", value=str(product.get("notes", "")), height=70)
        submitted = st.form_submit_button("حفظ التعديلات", type="primary", use_container_width=True)

    if submitted:
        ok, msg = update_product(
            code,
            {
                "product_name": name,
                "unit": unit,
                "storage_location": location,
                "current_stock": current_stock,
                "min_stock": min_stock,
                "notes": notes,
            },
        )
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    st.markdown("---")
    st.markdown("##### 🗑️ حذف الصنف")
    st.caption("حذف الصنف يزيله من قائمة المخزن. سجل الطلبات والسحوبات السابقة يبقى محفوظًا.")
    confirm_key = f"confirm_delete_{code}"
    if not st.session_state.get(confirm_key):
        if st.button("🗑️ حذف الصنف", key=f"delete_btn_{code}"):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        st.warning(f"هل أنت متأكد من حذف الصنف «{product.get('product_name')}» (كود {code})؟")
        d1, d2 = st.columns(2)
        with d1:
            if st.button("✅ نعم، احذف", type="primary", key=f"confirm_yes_{code}"):
                ok, msg = delete_product(code, force=True)
                st.session_state.pop(confirm_key, None)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with d2:
            if st.button("↩️ إلغاء", key=f"confirm_no_{code}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()