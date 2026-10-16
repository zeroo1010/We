"""إعدادات النظام: القراءة من Streamlit Secrets مع قيم افتراضية آمنة."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import streamlit as st


SHEETS = {
    "products": "Products",
    "orders": "Orders",
    "order_items": "Order_Items",
    "withdrawals": "Withdrawals",
    "stock_movements": "Stock_Movements",
    "settings": "Settings",
    "users": "Users",
}


@dataclass
class AppConfig:
    spreadsheet_key: str = ""
    service_account_file: str = "service_account.json"
    service_account_info: Optional[Dict[str, Any]] = None
    username: str = "admin"
    password: str = "admin123"
    app_title: str = "نظام إدارة مخزن المعمل"
    database_path: str = "data/warehouse.db"


def _secret(section: str, key: str, default: Any = None) -> Any:
    try:
        value = st.secrets[section][key]
        return value
    except Exception:
        return default


def load_config() -> AppConfig:
    cfg = AppConfig()

    cfg.spreadsheet_key = str(
        _secret("gsheets", "spreadsheet_key", os.getenv("GSHEETS_KEY", "")) or ""
    ).strip()
    cfg.service_account_file = str(
        _secret("gsheets", "service_account_file", os.getenv("GSHEETS_SA_FILE", "service_account.json"))
    )

    try:
        cfg.service_account_info = dict(st.secrets["gcp_service_account"])
    except Exception:
        cfg.service_account_info = None

    cfg.username = str(_secret("auth", "username", "admin"))
    cfg.password = str(_secret("auth", "password", "admin123"))
    cfg.app_title = str(_secret("auth", "app_title", "نظام إدارة مخزن المعمل"))

    return cfg


def secrets_available() -> bool:
    try:
        st.secrets.get("gsheets", None)
        return True
    except Exception:
        return False