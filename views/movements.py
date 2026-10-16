"""صفحة حركة المخزن: عرض كل الحركات والتصفية والتصدير."""
from __future__ import annotations

import streamlit as st

from core.gsheets import to_number
from core.services import get_movements
from core.styles import header


def render() -> None:
    header("🔄 حركة المخزن", "سجل كل عمليات السحب والإضافات على المخزن")

    moves = get_movements()
    if moves.empty:
        st.info("لا توجد حركات مسجلة بعد. تُسجَّل الحركات تلقائيًا عند صرف الأصناف.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        search = st.text_input("🔍 بحث بصنف / طلبية / رقم حركة")
    with c2:
        person = st.text_input("👤 بحث باسم الشخص")
    with c3:
        mtype = st.selectbox("نوع الحركة", ["الكل"] + sorted(moves["movement_type"].astype(str).unique().tolist()))

    df = moves.copy()
    if mtype != "الكل":
        df = df[df["movement_type"].astype(str) == mtype]
    if search.strip():
        s = search.strip()
        mask = (
            df["movement_no"].astype(str).str.contains(s, case=False, na=False)
            | df["order_no"].astype(str).str.contains(s, case=False, na=False)
            | df["product_code"].astype(str).str.contains(s, case=False, na=False)
            | df["product_name"].astype(str).str.contains(s, case=False, na=False)
        )
        df = df[mask]
    if person.strip():
        df = df[df["person"].astype(str).str.contains(person.strip(), case=False, na=False)]

    view = df.iloc[::-1].rename(
        columns={
            "movement_no": "رقم الحركة",
            "movement_date": "التاريخ والوقت",
            "movement_type": "النوع",
            "order_no": "رقم الطلبية",
            "product_code": "كود الصنف",
            "product_name": "اسم الصنف",
            "qty": "الكمية",
            "balance_after": "الرصيد بعد",
            "person": "الشخص",
            "notes": "ملاحظات",
        }
    )
    st.caption(f"عدد الحركات: {len(df)}")
    st.dataframe(view, use_container_width=True, hide_index=True)

    total_out = sum(to_number(v) for v in df[df["qty"].apply(to_number) > 0]["qty"])
    total_in = abs(sum(to_number(v) for v in df[df["qty"].apply(to_number) < 0]["qty"]))
    m1, m2 = st.columns(2)
    m1.metric("إجمالي الكميات المسحوبة", f"{total_out:g}")
    m2.metric("إجمالي الكميات المُرجعة", f"{total_in:g}")

    st.download_button(
        "⬇️ تصدير الحركات CSV",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name="stock_movements.csv",
        mime="text/csv",
    )