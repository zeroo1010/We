"""الصفحة الرئيسية: ملخصات وإحصائيات."""
from __future__ import annotations

import streamlit as st

from core.services import (
    dashboard_metrics,
    get_movements,
    get_orders,
    get_order_items,
    low_stock_products,
    product_notes_map,
)
from core.styles import metric_card


def render() -> None:
    st.markdown("## 📊 نظرة عامة")

    try:
        m = dashboard_metrics()
    except Exception as exc:  # noqa: BLE001
        st.error(f"تعذر تحميل البيانات: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("إجمالي عدد الأصناف", m["total_products"]), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("إجمالي رصيد المخزن", f'{m["total_stock"]:,.2f}'), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("عدد الطلبات", m["total_orders"], "purple"), unsafe_allow_html=True)
    with c4:
        st.markdown(
            metric_card("أصناف وصلت للحد الأدنى", m["low_stock_count"], "warn"),
            unsafe_allow_html=True,
        )

    st.write("")
    left, right = st.columns(2)

    with left:
        st.markdown("### ⚠️ أصناف منخفضة المخزون")
        low = low_stock_products()
        if low.empty:
            st.success("لا توجد أصناف منخفضة المخزون حاليًا.")
        else:
            st.dataframe(
                low[["product_code", "product_name", "current_stock", "min_stock", "unit", "notes"]].rename(
                    columns={
                        "product_code": "الكود",
                        "product_name": "الصنف",
                        "current_stock": "الرصيد",
                        "min_stock": "الحد الأدنى",
                        "unit": "الوحدة",
                        "notes": "ملاحظات الصنف",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("### 🕒 آخر حركات المخزن")
        moves = get_movements()
        if moves.empty:
            st.info("لا توجد حركات مسجلة بعد.")
        else:
            notes_map = product_notes_map()
            recent = moves.tail(8).iloc[::-1].copy()
            recent["_product_notes"] = recent["product_code"].map(
                lambda c: notes_map.get(str(c).strip(), "")
            )
            st.dataframe(
                recent[["movement_no", "movement_date", "product_name", "qty", "person", "_product_notes"]].rename(
                    columns={
                        "movement_no": "الحركة",
                        "movement_date": "التاريخ والوقت",
                        "product_name": "الصنف",
                        "qty": "الكمية",
                        "person": "الشخص",
                        "_product_notes": "ملاحظات الصنف",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.write("")
    st.markdown("### 📦 أحدث الطلبات")
    orders = get_orders()
    if orders.empty:
        st.info("لا توجد طلبات بعد. ابدأ بإنشاء طلبية من صفحة طلبات المعمل.")
        return
    items = get_order_items()
    latest = orders.tail(6).iloc[::-1].copy()
    summary = []
    for _, o in latest.iterrows():
        oi = items[items["order_no"].astype(str) == str(o["order_no"])]
        total_req = oi["_required"].sum() if not oi.empty else 0
        total_wd = oi["_withdrawn"].sum() if not oi.empty else 0
        summary.append(
            {
                "رقم الطلبية": o["order_no"],
                "التاريخ": o.get("order_date", ""),
                "المعمل/القسم": o.get("factory_name", ""),
                "المسؤول": o.get("responsible_person", ""),
                "الحالة": o.get("status", ""),
                "أصناف": len(oi),
                "المطلوب": f"{total_req:g}",
                "المسحوب": f"{total_wd:g}",
                "المتبقي": f"{max(total_req - total_wd, 0):g}",
            }
        )
    st.dataframe(summary, use_container_width=True, hide_index=True)