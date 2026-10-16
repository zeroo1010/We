"""طبقة الوصول إلى Google Sheets: إنشاء الأوراق، قراءة/كتابة، وتخزين مؤقت بسيط."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from core import offline
from core.config import SHEETS, AppConfig, load_config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SCHEMA: Dict[str, List[str]] = {
    SHEETS["products"]: [
        "product_code",
        "product_name",
        "unit",
        "current_stock",
        "min_stock",
        "storage_location",
        "notes",
        "created_at",
        "starting_stock",
        "total_withdrawn",
        "date_added",
        "manufacturer",
        "supplier",
        "expiry_date",
        "added_by",
    ],
    SHEETS["orders"]: [
        "order_no",
        "order_date",
        "factory_name",
        "responsible_person",
        "status",
        "notes",
        "created_at",
    ],
    SHEETS["order_items"]: [
        "item_id",
        "order_no",
        "product_code",
        "product_name",
        "unit",
        "required_qty",
        "withdrawn_qty",
        "last_withdraw_date",
        "last_withdrawn_by",
        "created_at",
    ],
    SHEETS["withdrawals"]: [
        "withdrawal_id",
        "order_no",
        "item_id",
        "product_code",
        "product_name",
        "qty",
        "withdraw_date",
        "withdrawn_by",
        "notes",
        "created_at",
        "supervisor_name",
    ],
    SHEETS["stock_movements"]: [
        "movement_no",
        "movement_date",
        "movement_type",
        "order_no",
        "product_code",
        "product_name",
        "qty",
        "balance_after",
        "person",
        "notes",
        "created_at",
    ],
    SHEETS["settings"]: ["key", "value"],
    SHEETS["users"]: [
        "username",
        "password_hash",
        "role",
        "created_at",
    ],
}


class DataError(Exception):
    """خطأ عام في طبقة البيانات."""


def _client_from_config(cfg: AppConfig) -> gspread.Client:
    if cfg.service_account_info:
        creds = Credentials.from_service_account_info(cfg.service_account_info, scopes=SCOPES)
    else:
        candidates = [
            cfg.service_account_file,
            "credentials.json",
            "service_account.json",
        ]
        found = next((p for p in candidates if p and os.path.exists(p)), None)
        if not found:
            raise DataError(
                "لم يتم العثور على بيانات اعتماد Google. ضع ملف credentials.json "
                "(أو service_account.json) بجانب app.py، أو أضف [gcp_service_account] في secrets.toml."
            )
        creds = Credentials.from_service_account_file(found, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_spreadsheet(key: str) -> gspread.Spreadsheet:
    cfg = load_config()
    client = _client_from_config(cfg)
    try:
        return client.open_by_key(key)
    except SpreadsheetNotFound as exc:
        raise DataError(
            "لم يتم العثور على الملف. تأكد من مفتاح الـSheet ومن مشاركته مع بريد الـService Account."
        ) from exc
    except APIError as exc:
        raise DataError(f"خطأ من Google API: {exc}") from exc


@st.cache_resource(show_spinner=False)
def get_worksheet(key: str, sheet_name: str) -> gspread.Worksheet:
    ss = get_spreadsheet(key)
    try:
        return ss.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(SCHEMA[sheet_name]), 5))
        ws.append_row(SCHEMA[sheet_name])
        return ws


def ensure_schema(key: str) -> None:
    """التأكد من وجود كل الأوراق ورؤوس الأعمدة.

    عند غياب الاتصال تُؤجَّل العملية (تُنفَّذها المزامنة الخلفية لاحقًا).
    """
    key = str(key or "").strip()
    if not key:
        raise DataError(
            "لم يتم إعداد مفتاح Google Sheet في الإعدادات (secrets.toml)."
        )
    if not offline.is_online():
        offline.set_schema_pending(True)
        return
    try:
        _ensure_schema_online(key)
    except Exception as exc:  # noqa: BLE001
        if offline.fell_offline(exc):
            offline.mark_offline()
            offline.set_schema_pending(True)
            return
        if isinstance(exc, DataError):
            raise
        raise DataError(f"تعذر تجهيز أوراق Google Sheets: {exc}") from exc


def _ensure_schema_online(key: str) -> None:
    ss = get_spreadsheet(key)
    existing = {ws.title: ws for ws in ss.worksheets()}
    for sheet_name, headers in SCHEMA.items():
        if sheet_name not in existing:
            ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 5))
            ws.append_row(headers)
        else:
            ws = existing[sheet_name]
            try:
                first = ws.row_values(1)
            except Exception:
                first = []
            if [c.strip() for c in first] != headers:
                if not first:
                    ws.append_row(headers)
                else:
                    ws.update(range_name="A1", values=[headers])


def _finalize(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """يُوحّد أعمدة DataFrame مع المخطط (يضمن وجود كل الأعمدة بالترتيب)."""
    expected = SCHEMA[sheet_name]
    if df is None:
        return pd.DataFrame(columns=expected)
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    if df.empty:
        return df.reindex(columns=expected)
    return df[expected]


def read_sheet(key: str, sheet_name: str) -> pd.DataFrame:
    """قراءة ورقة: من Google Sheets عند توفر الاتصال، أو من النسخة المحلية دون اتصال."""
    if offline.use_local():
        local = offline.read_snapshot(sheet_name)
        if local is not None:
            return _finalize(local, sheet_name)
        if not offline.is_online():
            # دون اتصال وبدون نسخة محلية بعد: ورقة فارغة بدل محاولة اتصال ميؤوس منها
            return _finalize(None, sheet_name)
    try:
        df = _read_sheet_cached(key, sheet_name, _cache_buster())
    except Exception as exc:  # noqa: BLE001
        if offline.fell_offline(exc):
            offline.mark_offline()
            local = offline.read_snapshot(sheet_name)
            if local is not None:
                return _finalize(local, sheet_name)
            if not offline.is_online():
                return _finalize(None, sheet_name)
        raise
    offline.save_snapshot(sheet_name, df)
    return df


@st.cache_data(show_spinner=False, ttl=20)
def _read_sheet_cached(key: str, sheet_name: str, _buster: int) -> pd.DataFrame:
    ws = get_worksheet(key, sheet_name)
    try:
        records = ws.get_all_records(default_blank="", numericise_ignore=["all"])
    except Exception:
        values = ws.get_all_values()
        if len(values) <= 1:
            records = []
        else:
            header = values[0]
            records = [dict(zip(header, row)) for row in values[1:]]
    return _finalize(pd.DataFrame(records), sheet_name)


def _cache_buster() -> int:
    """مفتاح كاش القراءة: يتغيّر بعد أي كتابة أو بعد مزامنة الخلفية للطابور."""
    try:
        session_version = int(st.session_state.get("_data_version", 0))
    except Exception:  # noqa: BLE001 — قد يُستدعى خارج سياق السكربت
        session_version = 0
    return session_version + offline.remote_version()


@st.cache_resource(show_spinner=False)
def spreadsheet_info(key: str) -> Dict[str, str]:
    """عنوان ورابط ملف Google Sheets الذي يقرأ منه التطبيق ويكتب إليه."""
    try:
        ss = get_spreadsheet(key)
        return {"title": str(ss.title), "url": str(ss.url)}
    except Exception:
        return {"title": "", "url": ""}


def _eq(value: Any, target: str) -> bool:
    """مطابقة قيمة خلية مع قيمة مطلوبة بغض النظر عن الحروف الكبيرة/الصغيرة."""
    return str(value).strip().lower() == target.strip().lower()


def invalidate_cache() -> None:
    """يُبطل كاش القراءة بعد أي كتابة حتى تظهر البيانات الجديدة فورًا."""
    try:
        st.session_state["_data_version"] = _cache_buster() + 1
    except Exception:  # noqa: BLE001 — آمن عند الاستدعاء من خيط خلفي
        pass
    try:
        _read_sheet_cached.clear()
    except Exception:  # noqa: BLE001
        pass


def append_row(key: str, sheet_name: str, row: Dict[str, Any]) -> None:
    payload = {"row": dict(row)}
    if offline.use_local():
        offline.enqueue(sheet_name, "append", payload)
        return
    headers = SCHEMA[sheet_name]
    values = [_stringify(row.get(h, "")) for h in headers]
    retries = 0
    while True:
        try:
            ws = get_worksheet(key, sheet_name)
            ws.append_row(values, value_input_option="RAW")
            break
        except Exception as exc:
            if offline.fell_offline(exc):
                offline.mark_offline()
                offline.enqueue(sheet_name, "append", payload)
                return
            retries += 1
            if retries >= 3:
                raise DataError(f"تعذر حفظ البيانات في ورقة {sheet_name}: {exc}") from exc
    offline.remember(sheet_name, "append", payload)
    invalidate_cache()


def update_row(key: str, sheet_name: str, match_col: str, match_value: str, updates: Dict[str, Any]) -> bool:
    payload = {"match_col": match_col, "match_value": match_value, "updates": dict(updates)}
    if offline.use_local():
        offline.enqueue(sheet_name, "update", payload)
        return offline.local_match(sheet_name, match_col, match_value)
    headers = SCHEMA[sheet_name]
    try:
        ws = get_worksheet(key, sheet_name)
        try:
            cell = ws.find(str(match_value), in_column=headers.index(match_col) + 1)
        except Exception:
            cell = None
        if cell is None:
            return False
        row_idx = cell.row
        for col_name, value in updates.items():
            if col_name in headers:
                ws.update_cell(row_idx, headers.index(col_name) + 1, _stringify(value))
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            offline.enqueue(sheet_name, "update", payload)
            return offline.local_match(sheet_name, match_col, match_value)
        raise
    offline.remember(sheet_name, "update", payload)
    invalidate_cache()
    return True


def append_rows(key: str, sheet_name: str, rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        append_row(key, sheet_name, row)


def delete_row(key: str, sheet_name: str, match_col: str, match_value: str) -> bool:
    payload = {"match_col": match_col, "match_value": match_value, "single": True}
    if offline.use_local():
        offline.enqueue(sheet_name, "delete", payload)
        return offline.local_match(sheet_name, match_col, match_value)
    headers = SCHEMA[sheet_name]
    try:
        ws = get_worksheet(key, sheet_name)
        try:
            cell = ws.find(str(match_value), in_column=headers.index(match_col) + 1)
        except Exception:
            cell = None
        if cell is None:
            return delete_rows_where(key, sheet_name, match_col, str(match_value)) > 0
        ws.delete_rows(cell.row)
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            offline.enqueue(sheet_name, "delete", payload)
            return offline.local_match(sheet_name, match_col, match_value)
        raise
    offline.remember(sheet_name, "delete", payload)
    invalidate_cache()
    return True


def _column_index(ws: gspread.Worksheet, sheet_name: str, match_col: str) -> int:
    headers = [str(h).strip() for h in ws.row_values(1)]
    if match_col in headers:
        return headers.index(match_col)
    return SCHEMA[sheet_name].index(match_col)


def delete_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    """حذف كل الصفوف التي تطابق القيمة من Google Sheets، وإرجاع عددها."""
    payload = {"match_col": match_col, "match_value": match_value}
    if offline.use_local():
        found = offline.local_count(sheet_name, match_col, match_value)
        offline.enqueue(sheet_name, "delete", payload)
        return found
    try:
        ws = get_worksheet(key, sheet_name)
        col_idx = _column_index(ws, sheet_name, match_col)
        target = str(match_value).strip()
        rows = ws.get_all_values()
        to_delete: List[int] = []
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > col_idx and _eq(row[col_idx], target):
                to_delete.append(i)
        for row_idx in sorted(to_delete, reverse=True):
            ws.delete_rows(row_idx)
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            found = offline.local_count(sheet_name, match_col, match_value)
            offline.enqueue(sheet_name, "delete", payload)
            return found
        raise
    offline.remember(sheet_name, "delete", payload)
    if to_delete:
        invalidate_cache()
    return len(to_delete)


def _col_letter(col: int) -> str:
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters or "A"


def count_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    """عدّ الصفوف المطابقة: مباشرة من Google Sheets، أو من النسخة المحلية دون اتصال."""
    if offline.use_local():
        return offline.local_count(sheet_name, match_col, match_value)
    try:
        ws = get_worksheet(key, sheet_name)
        col_idx = _column_index(ws, sheet_name, match_col)
        target = str(match_value).strip()
        rows = ws.get_all_values()
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            return offline.local_count(sheet_name, match_col, match_value)
        raise
    total = 0
    for row in rows[1:]:
        if len(row) > col_idx and _eq(row[col_idx], target):
            total += 1
    return total


def sync_row(
    key: str,
    sheet_name: str,
    match_col: str,
    match_value: str,
    expected: Dict[str, Any],
) -> int:
    """يتحقق من مطابقة صف في الشيت للقيم المتوقعة ويصحح الخلايا غير المطابقة عبر Google Sheets API."""
    payload = {"match_col": match_col, "match_value": match_value, "expected": dict(expected)}
    if offline.use_local():
        return offline.local_sync(sheet_name, match_col, match_value, expected)
    try:
        ws = get_worksheet(key, sheet_name)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return 0
        headers = [str(h).strip() for h in rows[0]]
        col_idx = _column_index(ws, sheet_name, match_col)
        target = str(match_value).strip()
        row_no = 0
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > col_idx and _eq(row[col_idx], target):
                row_no = i
                break
        if not row_no:
            return 0
        current = rows[row_no - 1]
        fixed = 0
        for col, value in expected.items():
            if col not in headers:
                continue
            idx = headers.index(col)
            raw = current[idx] if idx < len(current) else ""
            want = str(_stringify(value)).strip()
            if str(raw).strip() != want:
                ws.update_cell(row_no, idx + 1, want)
                fixed += 1
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            return offline.local_sync(sheet_name, match_col, match_value, expected)
        raise
    if fixed:
        offline.remember(sheet_name, "sync", payload)
        invalidate_cache()
    return fixed


def clear_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    """إفراغ الصفوف المطابقة في Google Sheets (خيار أخير إن تعذّر حذف الصفوف)."""
    payload = {"match_col": match_col, "match_value": match_value, "clear": True}
    if offline.use_local():
        found = offline.local_count(sheet_name, match_col, match_value)
        if found:
            offline.enqueue(sheet_name, "delete", payload)
        return found
    try:
        ws = get_worksheet(key, sheet_name)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return 0
        col_idx = _column_index(ws, sheet_name, match_col)
        target = str(match_value).strip()
        width = max(len(r) for r in rows)
        ranges = [
            f"A{i}:{_col_letter(width)}{i}"
            for i, row in enumerate(rows[1:], start=2)
            if len(row) > col_idx and str(row[col_idx]).strip() == target
        ]
        if not ranges:
            return 0
        ws.batch_clear(ranges)
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            found = offline.local_count(sheet_name, match_col, match_value)
            if found:
                offline.enqueue(sheet_name, "delete", payload)
            return found
        raise
    offline.remember(sheet_name, "delete", payload)
    invalidate_cache()
    return len(ranges)


def clear_sheet_rows(key: str, sheet_name: str) -> int:
    """يحذف كل صفوف البيانات مع الإبقاء على صف العناوين (الصف 1)، ويُرجع عدد الصفوف المحذوفة."""
    if offline.use_local():
        found = offline.local_row_count(sheet_name)
        offline.enqueue(sheet_name, "clear_all", {})
        return found
    try:
        ws = get_worksheet(key, sheet_name)
        values = ws.get_all_values()
        total = len(values)
        if total <= 1:
            return 0
        ws.delete_rows(2, total)  # الصف 2 حتى الأخير، مع الإبقاء على العناوين
    except Exception as exc:
        if offline.fell_offline(exc):
            offline.mark_offline()
            found = offline.local_row_count(sheet_name)
            offline.enqueue(sheet_name, "clear_all", {})
            return found
        raise
    offline.remember(sheet_name, "clear_all", {})
    invalidate_cache()
    return total - 1


def _stringify(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def to_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def clear_cache() -> None:
    get_spreadsheet.clear()
    get_worksheet.clear()