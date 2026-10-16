"""طبقة تهيئة قاعدة البيانات الموحدة لواجهة app.py.

المخزن الأساسي هو Google Sheets (التفاصيل في core/gsheets.py)، ويوفر هذا
الوحدة الدوال التي تستدعيها الواجهة: تهيئة الاتصال، تجهيز المخطط، ومعلومات
الملف، مع تمرير الأخطاء بنفس نوع `DataError`.
"""
from __future__ import annotations

from typing import Dict

from core.gsheets import (
    DataError,
    ensure_schema as _ensure_schema,
    spreadsheet_info as _spreadsheet_info,
    to_number,
)

_DB_PATH = ""


def configure(database_path: str = "") -> None:
    """يُسجّل مسار قاعدة البيانات المحلية (اختياري) — القراءة والكتابة عبر Google Sheets."""
    global _DB_PATH
    _DB_PATH = str(database_path or "").strip()


def database_path() -> str:
    """آخر مسار سُجّل عبر `configure` (فارغ عند العمل عبر Google Sheets فقط)."""
    return _DB_PATH


def ensure_schema(spreadsheet_key: str) -> None:
    """يضمن وجود أوراق Google Sheets ورؤوس الأعمدة قبل أي قراءة أو كتابة."""
    key = str(spreadsheet_key or "").strip()
    if not key:
        raise DataError(
            "لم يتم إعداد مفتاح Google Sheet في الإعدادات (secrets.toml → [gsheets] spreadsheet_key)."
        )
    _ensure_schema(key)


def spreadsheet_info(spreadsheet_key: str) -> Dict[str, str]:
    """عنوان ورابط ملف Google Sheets (قيم فارغة عند تعذّر الاتصال)."""
    return _spreadsheet_info(str(spreadsheet_key or "").strip())


__all__ = ["DataError", "configure", "database_path", "ensure_schema", "spreadsheet_info", "to_number"]
