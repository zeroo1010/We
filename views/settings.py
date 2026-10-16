"""صفحة الإعدادات: حالة الاتصال، إعداد الأسرار، أدوات."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.config import SHEETS, load_config
from core.gsheets import DataError, clear_cache, ensure_schema, get_spreadsheet, read_sheet
from core.services import get_orders, get_products, today_str
from core.styles import header


def render() -> None:
    header("⚙️ الإعدادات", "إعدادات الاتصال بـGoogle Sheets وأدوات النظام")

    cfg = load_config()

    st.markdown("### 🔌 حالة الاتصال")
    if not cfg.spreadsheet_key:
        st.error(
            "لم يتم ضبط مفتاح Google Sheet. أضف `spreadsheet_key` في `.streamlit/secrets.toml` "
            "ثم أعد تشغيل التطبيق."
        )
        _render_help()
        return

    col1, col2 = st.columns(2)
    with col1:
        st.write("**مفتاح الملف:**")
        masked = cfg.spreadsheet_key[:6] + "..." + cfg.spreadsheet_key[-4:] if len(cfg.spreadsheet_key) > 12 else "—"
        st.code(masked)
    with col2:
        method = "Streamlit Secrets [gcp_service_account]" if cfg.service_account_info else f"ملف: {cfg.service_account_file}"
        st.write("**طريقة الاعتماد:**")
        st.code(method)

    if st.button("🔍 اختبار الاتصال", type="primary"):
        try:
            ensure_schema(cfg.spreadsheet_key)
            ss = get_spreadsheet(cfg.spreadsheet_key)
            st.success(f"تم الاتصال بنجاح بالملف: {ss.title}")
        except DataError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"فشل الاتصال: {exc}")

    if st.button("🧱 إنشاء/فحص أوراق البيانات (Sheets)"):
        try:
            ensure_schema(cfg.spreadsheet_key)
            st.success("تم التأكد من وجود كل الأوراق المطلوبة: " + ", ".join(SHEETS.values()))
        except Exception as exc:  # noqa: BLE001
            st.error(f"تعذر إنشاء الأوراق: {exc}")

    st.write("")
    st.markdown("### 📊 ملخص البيانات الحالية")
    try:
        counts = {
            "Products (الأصناف)": len(get_products()),
            "Orders (الطلبات)": len(get_orders()),
            "Order_Items (أصناف الطلبات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["order_items"])),
            "Withdrawals (السحوبات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["withdrawals"])),
            "Stock_Movements (الحركات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["stock_movements"])),
        }
        st.dataframe(
            pd.DataFrame({"الورقة": list(counts.keys()), "عدد الصفوف": list(counts.values())}),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"تعذر قراءة الملخص: {exc}")

    st.write("")
    st.markdown("### 🛠️ أدوات")
    if st.button("♻️ تحديث الاتصال (مسح الكاش)"):
        clear_cache()
        st.success("تم مسح الكاش. أعد تحميل الصفحة.")

    st.caption(f"تاريخ النظام: {today_str()}")

    _render_help()


def _render_help() -> None:
    with st.expander("📘 طريقة الإعداد (Google Sheets + Service Account)"):
        st.markdown(
            """
1. أنشئ مشروعًا على [Google Cloud Console](https://console.cloud.google.com/).
2. فعّل **Google Sheets API** و**Google Drive API**.
3. من **IAM & Admin → Service Accounts** أنشئ حساب خدمة، ثم أنشئ مفتاح **JSON** ونزّله.
4. افتح Google Sheet، من مشاركة أضف بريد الـService Account (`...@....iam.gserviceaccount.com`) كـ**Editor**.
5. انسخ مفتاح الملف من الرابط: `docs.google.com/spreadsheets/d/<KEY>/edit`.
6. محليًا: ضع JSON باسم `service_account.json` بجانب `app.py`، وعدّل `.streamlit/secrets.toml`.
7. على Streamlit Cloud: أضف محتوى JSON داخل `[gcp_service_account]` في Secrets.
            """
        )
        st.code(
            '[gsheets]\nspreadsheet_key = "1AbC..."\n\n'
            '[auth]\nusername = "admin"\npassword = "change-me"\napp_title = "نظام إدارة مخزن المعمل"',
            language="toml",
        )