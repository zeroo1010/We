"""صفحة التقارير: تقارير الطلبات والسحوبات وحركة الأصناف والمتبقيات."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core.gsheets import to_number
from core.services import (
    get_movements,
    get_order_items,
    get_orders,
    get_products,
    get_withdrawals,
    low_stock_products,
    product_notes_map,
)
from core.styles import header


def _to_date(value: str):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value).strip()[:19], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _date_filter(df: pd.DataFrame, col: str, start, end) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    parsed = df[col].apply(_to_date)
    mask = parsed.apply(lambda d: d is not None and start <= d <= end)
    return df[mask]


def render() -> None:
    header("📈 التقارير", "تقارير تفصيلية عن الطلبات والسحوبات والمخزون")

    tabs = st.tabs(
        [
            "📋 تقرير الطلبات",
            "📤 تقرير السحوبات",
            "📦 حركة صنف",
            "⏳ المتبقي من الطلبات القديمة",
            "⚠️ الأصناف منخفضة المخزون",
        ]
    )
    with tabs[0]:
        _orders_report()
    with tabs[1]:
        _withdrawals_report()
    with tabs[2]:
        _product_movement_report()
    with tabs[3]:
        _pending_report()
    with tabs[4]:
        _low_stock_report()


def _orders_report() -> None:
    orders = get_orders()
    if orders.empty:
        st.info("لا توجد طلبات.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        start = st.date_input("من تاريخ", value=date.today().replace(day=1), key="ord_start")
    with c2:
        end = st.date_input("إلى تاريخ", value=date.today(), key="ord_end")
    with c3:
        q = st.text_input("رقم الطلبية / المعمل", key="ord_q")

    df = _date_filter(orders, "order_date", start, end)
    if q.strip():
        s = q.strip()
        df = df[
            df["order_no"].astype(str).str.contains(s, case=False, na=False)
            | df["factory_name"].astype(str).str.contains(s, case=False, na=False)
        ]

    items = get_order_items()
    rows = []
    for _, o in df.iloc[::-1].iterrows():
        oi = items[items["order_no"].astype(str) == str(o["order_no"])] if not items.empty else items
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
                "إجمالي المطلوب": f"{req:g}",
                "إجمالي المسحوب": f"{wd:g}",
                "إجمالي المتبقي": f"{max(req - wd, 0):g}",
            }
        )
    st.caption(f"عدد الطلبات: {len(rows)}")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        st.download_button(
            "⬇️ تصدير CSV",
            data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
            file_name="orders_report.csv",
            mime="text/csv",
            key="ord_dl",
        )


def _withdrawals_report() -> None:
    w = get_withdrawals()
    if w.empty:
        st.info("لا توجد عمليات سحب.")
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start = st.date_input("من تاريخ", value=date.today().replace(day=1), key="wd_start")
    with c2:
        end = st.date_input("إلى تاريخ", value=date.today(), key="wd_end")
    with c3:
        person = st.text_input("اسم الساحب", key="wd_person")
    with c4:
        prod = st.text_input("اسم/كود الصنف", key="wd_prod")

    df = _date_filter(w, "withdraw_date", start, end)
    if person.strip():
        df = df[df["withdrawn_by"].astype(str).str.contains(person.strip(), case=False, na=False)]
    if prod.strip():
        s = prod.strip()
        df = df[
            df["product_name"].astype(str).str.contains(s, case=False, na=False)
            | df["product_code"].astype(str).str.contains(s, case=False, na=False)
        ]

    notes_map = product_notes_map()
    view = df.iloc[::-1].copy()
    view["_product_notes"] = view["product_code"].map(lambda c: notes_map.get(str(c).strip(), ""))
    view = view.rename(
        columns={
            "withdrawal_id": "رقم السحب",
            "order_no": "رقم الطلبية",
            "product_code": "الكود",
            "product_name": "الصنف",
            "qty": "الكمية",
            "withdraw_date": "التاريخ والوقت",
            "withdrawn_by": "الساحب",
            "_product_notes": "ملاحظات الصنف",
        }
    )[
        ["رقم السحب", "رقم الطلبية", "الكود", "الصنف", "الكمية", "التاريخ والوقت", "الساحب", "ملاحظات الصنف"]
    ]
    total = sum(to_number(v) for v in df["qty"])
    st.caption(f"عدد العمليات: {len(df)} — إجمالي الكميات المسحوبة: {total:g}")
    st.dataframe(view, use_container_width=True, hide_index=True)
    if not df.empty:
        st.download_button(
            "⬇️ تصدير CSV",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name="withdrawals_report.csv",
            mime="text/csv",
            key="wd_dl",
        )


def _product_movement_report() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف.")
        return
    codes = products["product_code"].astype(str).tolist()
    code = st.selectbox("اختر الصنف", options=[""] + codes, key="pm_code")
    if not code:
        return
    product = products[products["product_code"].astype(str) == code].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("الرصيد الحالي", f'{to_number(product["current_stock"]):g}')
    c2.metric("الحد الأدنى", f'{to_number(product["min_stock"]):g}')
    c3.metric("الوحدة", product.get("unit") or "-")

    moves = get_movements()
    if not moves.empty:
        moves = moves[moves["product_code"].astype(str).str.strip() == code]
    if moves is None or moves.empty:
        st.info("لا توجد حركات لهذا الصنف.")
        return
    notes_map = product_notes_map()
    view = moves.iloc[::-1].copy()
    view["_product_notes"] = view["product_code"].map(lambda c: notes_map.get(str(c).strip(), ""))
    view = view[
        ["movement_no", "movement_date", "movement_type", "order_no", "qty", "balance_after", "person", "_product_notes"]
    ].rename(
        columns={
            "movement_no": "رقم الحركة",
            "movement_date": "التاريخ والوقت",
            "movement_type": "النوع",
            "order_no": "رقم الطلبية",
            "qty": "الكمية",
            "balance_after": "الرصيد بعد",
            "person": "الشخص",
            "_product_notes": "ملاحظات الصنف",
        }
    )
    st.dataframe(view, use_container_width=True, hide_index=True)


def _pending_report() -> None:
    items = get_order_items()
    if items.empty:
        st.info("لا توجد أصناف في الطلبات.")
        return
    orders = get_orders()
    pending = items[items["_remaining"] > 0].copy()
    if pending.empty:
        st.success("لا توجد كميات متبقية من الطلبات.")
        return

    c1, c2 = st.columns(2)
    with c1:
        prod = st.text_input("اسم/كود الصنف", key="pend_prod")
    with c2:
        order_q = st.text_input("رقم الطلبية", key="pend_order")
    if prod.strip():
        s = prod.strip()
        pending = pending[
            pending["product_name"].astype(str).str.contains(s, case=False, na=False)
            | pending["product_code"].astype(str).str.contains(s, case=False, na=False)
        ]
    if order_q.strip():
        pending = pending[pending["order_no"].astype(str).str.contains(order_q.strip(), case=False, na=False)]

    notes_map = product_notes_map()
    rows = []
    for _, it in pending.iterrows():
        o = orders[orders["order_no"].astype(str) == str(it["order_no"])]
        rows.append(
            {
                "رقم الطلبية": it["order_no"],
                "تاريخها": o.iloc[0].get("order_date", "") if not o.empty else "",
                "المعمل/القسم": o.iloc[0].get("factory_name", "") if not o.empty else "",
                "الحالة": o.iloc[0].get("status", "") if not o.empty else "",
                "الكود": it["product_code"],
                "الصنف": it["product_name"],
                "المطلوب": f'{to_number(it["required_qty"]):g}',
                "المسحوب": f'{to_number(it["withdrawn_qty"]):g}',
                "المتبقي": f'{to_number(it["_remaining"]):g}',
                "ملاحظات الصنف": notes_map.get(str(it["product_code"]).strip(), ""),
            }
        )
    st.caption(f"عدد الأصناف ذات المتبقي: {len(rows)}")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        st.download_button(
            "⬇️ تصدير CSV",
            data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
            file_name="pending_report.csv",
            mime="text/csv",
            key="pend_dl",
        )


def _low_stock_report() -> None:
    low = low_stock_products()
    if low.empty:
        st.success("لا توجد أصناف منخفضة المخزون.")
        return
    view = low[
        ["product_code", "product_name", "unit", "current_stock", "min_stock", "storage_location", "notes"]
    ].rename(
        columns={
            "product_code": "الكود",
            "product_name": "الصنف",
            "unit": "الوحدة",
            "current_stock": "الرصيد الحالي",
            "min_stock": "الحد الأدنى",
            "storage_location": "مكان التخزين",
            "notes": "ملاحظات الصنف",
        }
    )
    st.caption(f"عدد الأصناف: {len(low)}")
    st.dataframe(view, use_container_width=True, hide_index=True)