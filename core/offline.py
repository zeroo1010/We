"""محرك العمل دون اتصال (Offline-First) والمزامنة التلقائية مع Google Sheets.

كيف يعمل:
- كشف الاتصال: فحص سريع (TCP إلى Google) مع نتائج مخزّنة لبضع ثوانٍ.
- التخزين المحلي: كل عملية كتابة تُحفظ فورًا في طابور SQLite
  (data/offline.db) وتُطبَّق على نسخة محلية (Snapshot) من كل ورقة،
  فتبقى قراءات التطبيق متسقة حتى أثناء العمل دون اتصال.
- المزامنة التلقائية: خيط خلفي (وأيضًا عند كل تشغيل للصفحة) يدفع العمليات
  المعلّقة إلى Google Sheets بالترتيب نفسه — بلا أي زر أو تدخل من المستخدم.
- الحالة (Online / Offline / Syncing) تُعرض عبر `status_info()` / `pill_html()`.

ملاحظات:
- الوحدة لا تستدعي أي واجهة Streamlit داخل الخيط الخلفي (لذلك تُلتقط
  بيانات الاعتماد والمسارات عند التشغيل عبر `configure`).
- `core.gsheets` يستدعي هذه الوحدة، لذا لا تُستورد `gsheets` هنا في المقام
  الأول (فقط داخل الدوال عند الحاجة لتفادي الدوران المتبادل).
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

FORCE_OFFLINE_ENV = "POLIO_FORCE_OFFLINE"
_DB_FILENAME = "offline.db"
_PROBE_HOSTS = ("www.googleapis.com", "docs.google.com")
_PROBE_TTL = 4.0          # صلاحية نتيجة فحص الاتصال بالثواني
_WORKER_INTERVAL = 3.0    # فترة استيقاظ خيط المزامنة الخلفي
_MAX_BACKOFF = 90.0       # أقصى تأخير قبل إعادة محاولة المزامنة بعد خطأ API

# --------------------------------------------------------------------------- #
#                          حالة مشتركة (مقفلة)
# --------------------------------------------------------------------------- #
_cfg_lock = threading.Lock()
_state_lock = threading.Lock()
_probe_lock = threading.Lock()
_pull_lock = threading.Lock()

_key: str = ""
_sa_info: Optional[Dict[str, Any]] = None
_sa_file: str = ""
_db_path: str = os.path.join("data", _DB_FILENAME)
_configured: bool = False

_probe_value: Optional[bool] = None
_probe_ts: float = 0.0

_flushing: bool = False
_last_sync: str = ""
_last_error: str = ""
_schema_pending: bool = False
_remote_version: int = 0
_retry_after: float = 0.0

_client_cache: Any = None
_worksheet_cache: Dict[str, Any] = {}

_ddl_done = False


class SyncConfigError(Exception):
    """تعذّر إعداد المزامنة (مفتاح الشيت أو بيانات اعتماد Google)."""


# --------------------------------------------------------------------------- #
#                             التهيئة والإعدادات
# --------------------------------------------------------------------------- #
def configure(cfg: Any = None, database_path: str = "") -> None:
    """يلتقط مفتاح الشيت وبيانات الاعتماد ومسار قاعدة البيانات المحلية.

    يُستدعى من سياق التشغيل الرئيسي (السكربت) قبل أي قراءة أو كتابة، وتستخدمه
    وحدات المزامنة الخلفية لاحقًا دون استدعاء أي واجهة Streamlit.
    """
    global _key, _sa_info, _sa_file, _db_path, _configured
    with _cfg_lock:
        old_key = _key
        _key = str(getattr(cfg, "spreadsheet_key", "") or "").strip()
        _sa_info = dict(getattr(cfg, "service_account_info", None) or {}) or None
        _sa_file = str(getattr(cfg, "service_account_file", "") or "").strip()
        path = database_path or str(getattr(cfg, "database_path", "") or "")
        base_dir = os.path.dirname(path.strip()) if path.strip() else "data"
        base_dir = base_dir or "data"
        _db_path = os.path.join(base_dir, _DB_FILENAME)
        _configured = True
        if old_key != _key:
            _reset_client()
    _bind_data_key(_key)


def _bind_data_key(key: str) -> None:
    """يربط البيانات المحلية (نسخة + ذاكرة دخول + طابور) بمفتاح الشيت الحالي.

    عند تغيّر المفتاح (مثلاً: برنامج مربوط بملف شيت آخر) تُمسح البيانات المحلية
    القديمة كليًا حتى لا تُخلط حسابات/بيانات شيت بآخر ولا يُدفع طابور شيت قديم
    إلى شيت جديد.
    """
    key = str(key or "").strip()
    if not key:
        return
    stored = _meta_get("data_key")
    if stored == key:
        return
    if stored is not None:
        with _connect() as con:
            con.execute("DELETE FROM snapshot")
            con.execute("DELETE FROM auth_cache")
            con.execute("DELETE FROM outbox")
            con.execute("DELETE FROM meta WHERE key LIKE 'initial_pull_done:%'")
            con.commit()
    _meta_set("data_key", key)


def spreadsheet_key() -> str:
    with _cfg_lock:
        return _key


def db_path() -> str:
    with _cfg_lock:
        return _db_path


# --------------------------------------------------------------------------- #
#                            كشف الاتصال بالإنترنت
# --------------------------------------------------------------------------- #
def _probe(timeout: float = 2.0) -> bool:
    for host in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, 443), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def is_online(timeout: float = 2.0) -> bool:
    """هل يمكن الوصول إلى Google الآن؟ (نتيجة مخزّنة لبضع ثوانٍ)."""
    global _probe_value, _probe_ts
    if os.getenv(FORCE_OFFLINE_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    now = time.monotonic()
    with _probe_lock:
        if _probe_value is not None and now - _probe_ts < _PROBE_TTL:
            return _probe_value
    value = _probe(timeout)
    with _probe_lock:
        _probe_value, _probe_ts = value, now
    return value


def mark_online() -> None:
    """يُحدّث نتيجة الفحص يدويًا (بعد نجاح اتصال بـ Google)."""
    global _probe_value, _probe_ts
    with _probe_lock:
        _probe_value, _probe_ts = True, time.monotonic()


def mark_offline() -> None:
    """يُعلّم الاتصال مفقودًا فورًا (بعد خطأ شبكة) دون انتظار انتهاء الصلاحية."""
    global _probe_value, _probe_ts
    with _probe_lock:
        _probe_value, _probe_ts = False, time.monotonic()


_NETWORK_NAME_MARKERS = (
    "connectionerror",
    "timeout",
    "transporterror",
    "sslerror",
    "maxretries",
    "newconnection",
    "gaierror",
    "proxyerror",
    "readtimeout",
    "connecttimeout",
    "incompleteread",
    "brokenpipe",
)
_NETWORK_TEXT_MARKERS = (
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection refused",
    "failed to establish a new socket",
    "name or service not known",
    "temporary failure in name resolution",
    "getaddrinfo",
    "network is unreachable",
    "no route to host",
    "max retries exceeded",
    "ssl",
    "proxy",
    "remote end closed connection",
    "cannot connect to host",
)


def is_network_error(exc: BaseException) -> bool:
    """هل الخطأ ناتج عن انقطاع الشبكة (لا خطأ من Google نفسه)؟"""
    seen: set = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        name = type(cur).__name__.lower()
        text = str(cur).lower()
        if any(marker in name for marker in _NETWORK_NAME_MARKERS):
            return True
        if any(marker in text for marker in _NETWORK_TEXT_MARKERS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def fell_offline(exc: BaseException) -> bool:
    """خطأ يستوجب حفظ العملية محليًا بدل إسقاطها."""
    return is_network_error(exc) or not is_online()


def use_local() -> bool:
    """اقرأ من النسخة المحلية إذا كنا دون اتصال أو ما زالت هناك عمليات معلّقة.

    (قراءة محلية أثناء وجود عمليات معلّقة تضمن اتساق «اقرأ ما كتبت» حتى
    اكتمال دفعها إلى Google Sheets في الخلفية.)
    """
    if not is_online():
        return True
    return pending_count() > 0


# --------------------------------------------------------------------------- #
#                        قاعدة البيانات المحلية (SQLite)
# --------------------------------------------------------------------------- #
def _new_connection() -> sqlite3.Connection:
    path = db_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    global _ddl_done
    if not _ddl_done:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet TEXT NOT NULL,
                op TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_sheet ON outbox(sheet);
            CREATE TABLE IF NOT EXISTS snapshot (
                sheet TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_cache (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                updated_at TEXT NOT NULL
            );
            """
        )
        con.commit()
        _ddl_done = True
    return con


@contextlib.contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """اتصال SQLite مؤقت (يُفلتَق بانتهائه) — آمن عبر الخيوط المختلفة."""
    con = _new_connection()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
#                        تطبيع القيم (يطابق طبقة gsheets)
# --------------------------------------------------------------------------- #
def _norm(value: Any) -> Any:
    """يُعيد القيمة بالصيغة التي تخزنها Google Sheets (نصوص موحّدة)."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    try:
        if not isinstance(value, (list, dict, set)) and pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _norm_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k): _norm(v) for k, v in dict(row).items()}


def _eq(value: Any, target: Any) -> bool:
    return str(value if value is not None else "").strip().lower() == str(
        target if target is not None else ""
    ).strip().lower()


# --------------------------------------------------------------------------- #
#                       النسخة المحلية من الأوراق (Snapshot)
# --------------------------------------------------------------------------- #
def _load_rows(sheet: str, create: bool = False) -> Optional[List[Dict[str, Any]]]:
    """صفوف الورقة محليًا، أو None إذا لم تكن هناك نسخة محلية بعد."""
    with _connect() as con:
        row = con.execute("SELECT payload FROM snapshot WHERE sheet = ?", (sheet,)).fetchone()
    if row is None:
        return [] if create else None
    data = _loads(row["payload"], [])
    return [dict(r) for r in data] if isinstance(data, list) else []


def _save_rows(sheet: str, rows: List[Dict[str, Any]]) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO snapshot(sheet, payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(sheet) DO UPDATE SET payload = excluded.payload, "
            "updated_at = excluded.updated_at",
            (sheet, _dumps(rows), _now()),
        )
        con.commit()
        if sheet == _users_sheet():
            _sync_auth_cache_rows(con, rows)


def read_snapshot(sheet: str) -> Optional[pd.DataFrame]:
    """النسخة المحلية من الورقة كـDataFrame (None إن لم توجد بعد)."""
    rows = _load_rows(sheet)
    if rows is None:
        return None
    return pd.DataFrame(rows)


def save_snapshot(sheet: str, df: Any) -> None:
    """حفظ نسخة محلية بعد نجاح قراءة Google Sheets."""
    try:
        if df is None:
            rows: List[Dict[str, Any]] = []
        elif getattr(df, "empty", False):
            rows = []
        else:
            rows = [_norm_row(r) for r in df.to_dict("records")]
        _save_rows(sheet, rows)
    except Exception:  # noqa: BLE001 — فشل النسخة المحلية لا يعطّل القراءة
        pass


def _matches(row: Dict[str, Any], match_col: str, match_value: Any) -> bool:
    return _eq(row.get(str(match_col), ""), match_value)


def _apply_local(sheet: str, op: str, payload: Dict[str, Any]) -> None:
    """يطبَّق العمل على النسخة المحلية لتبقى القراءات متسقة فورًا."""
    rows = _load_rows(sheet, create=(op == "append"))
    if rows is None:
        return  # لا توجد نسخة محلية لهذه الورقة بعد — تُطبَّق لاحقًا عند المزامنة
    if op == "append":
        row = payload.get("row") or {}
        rows.append(_norm_row(row))
    elif op == "update":
        match_col = str(payload.get("match_col", ""))
        updates = _norm_row(payload.get("updates") or {})
        for r in rows:
            if _matches(r, match_col, payload.get("match_value")):
                r.update(updates)
    elif op == "delete":
        match_col = str(payload.get("match_col", ""))
        if payload.get("clear"):
            for r in rows:
                if _matches(r, match_col, payload.get("match_value")):
                    for col in list(r.keys()):
                        r[col] = ""
        elif payload.get("single"):
            for i, r in enumerate(rows):
                if _matches(r, match_col, payload.get("match_value")):
                    del rows[i]
                    break
        else:
            rows = [r for r in rows if not _matches(r, match_col, payload.get("match_value"))]
    elif op == "clear_all":
        rows = []
    elif op == "sync":
        match_col = str(payload.get("match_col", ""))
        expected = payload.get("expected") or {}
        try:
            from core.gsheets import SCHEMA

            allowed = set(SCHEMA.get(sheet, []))
        except Exception:  # noqa: BLE001
            allowed = set(expected.keys())
        for r in rows:
            if _matches(r, match_col, payload.get("match_value")):
                for col, value in expected.items():
                    if not allowed or col in allowed:
                        r[str(col)] = _norm(value)
    _save_rows(sheet, rows)


def local_count(sheet: str, match_col: str, match_value: Any) -> int:
    rows = _load_rows(sheet)
    if not rows:
        return 0
    return sum(1 for r in rows if _matches(r, str(match_col), match_value))


def local_match(sheet: str, match_col: str, match_value: Any) -> bool:
    return local_count(sheet, match_col, match_value) > 0


def local_row_count(sheet: str) -> int:
    """عدد صفوف البيانات محليًا (الصفوف غير الفارغة)."""
    rows = _load_rows(sheet)
    if not rows:
        return 0
    return sum(1 for r in rows if any(str(v).strip() for v in r.values()))


def local_sync(sheet: str, match_col: str, match_value: Any, expected: Dict[str, Any]) -> int:
    """يصحّح القيم غير المطابقة في النسخة المحلية ويرجع عدد الخلايا المُصلحة."""
    rows = _load_rows(sheet)
    if not rows:
        return 0
    try:
        from core.gsheets import SCHEMA

        allowed = set(SCHEMA.get(sheet, []))
    except Exception:  # noqa: BLE001
        allowed = set(expected.keys())
    fixed = 0
    for r in rows:
        if not _matches(r, match_col, match_value):
            continue
        for col, value in expected.items():
            if allowed and col not in allowed:
                continue
            want = str(_norm(value)).strip()
            if str(r.get(col, "")).strip() != want:
                r[str(col)] = _norm(value)
                fixed += 1
    if fixed:
        _save_rows(sheet, rows)
    return fixed


# --------------------------------------------------------------------------- #
#                    ذاكرة الدخول المحلية (يعمل دون اتصال)
# --------------------------------------------------------------------------- #
def _users_sheet() -> str:
    """اسم ورقة المستخدمين (يُحلّ عند الحاجة لتفادي استيراد دائري)."""
    from core.config import SHEETS

    return str(SHEETS.get("users", "Users"))


def _sync_auth_cache_rows(con: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    """حدّث ذاكرة الدخول المحلية لتعكس ورقة المستخدمين (تُستدعى مع كل حفظ للنسخة).

    تُخزَّن تجزئات كلمات المرور (PBKDF2) فقط — بلا نص صريح — وتُستخدم للدخول
    دون اتصال عندما لا تتوفر نسخة كاملة من ورقة المستخدمين.
    """
    entries = []
    for row in rows:
        username = str(row.get("username", "")).strip()
        password_hash = str(row.get("password_hash", "")).strip()
        if not username or not password_hash:
            continue
        role = str(row.get("role", "")).strip() or "user"
        entries.append((username, password_hash, role, _now()))
    con.execute("DELETE FROM auth_cache")
    if entries:
        con.executemany(
            "INSERT OR REPLACE INTO auth_cache(username, password_hash, role, updated_at) "
            "VALUES (?, ?, ?, ?)",
            entries,
        )
    con.commit()


def get_cached_user(username: str) -> Optional[Dict[str, Any]]:
    """مستخدم من ذاكرة الدخول المحلية (للدخول دون اتصال) أو None."""
    name = str(username or "").strip()
    if not name:
        return None
    with _connect() as con:
        row = con.execute(
            "SELECT username, password_hash, role FROM auth_cache WHERE username = ?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return {
        "username": str(row["username"]),
        "password_hash": str(row["password_hash"]),
        "role": str(row["role"] or "user"),
    }


def auth_cache_count() -> int:
    """عدد الحسابات المخزّنة محليًا في ذاكرة الدخول."""
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM auth_cache").fetchone()
    return int(row["n"] if row else 0)


# --------------------------------------------------------------------------- #
#                    القيم الوصفية (meta) — علامات المزامنة
# --------------------------------------------------------------------------- #
def _meta_get(name: str) -> Optional[str]:
    with _connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (name,)).fetchone()
    return str(row["value"]) if row is not None else None


def _meta_set(name: str, value: str) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (name, str(value)),
        )
        con.commit()


# --------------------------------------------------------------------------- #
#                              طابور العمليات
# --------------------------------------------------------------------------- #
def enqueue(sheet: str, op: str, payload: Dict[str, Any]) -> int:
    """يخزّن العملية في الطابور المحلي ويُطبّقها على النسخة المحلية."""
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO outbox(sheet, op, payload, created_at, attempts) VALUES (?, ?, ?, ?, 0)",
            (sheet, op, _dumps(payload), _now()),
        )
        con.commit()
        op_id = int(cur.lastrowid or 0)
    _apply_local(sheet, op, payload)
    return op_id


def remember(sheet: str, op: str, payload: Dict[str, Any]) -> None:
    """يُحدّث النسخة المحلية بعد نجاح الكتابة مباشرة على Google Sheets."""
    _apply_local(sheet, op, payload)


def pending_ops() -> List[Dict[str, Any]]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, sheet, op, payload, attempts FROM outbox ORDER BY id"
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "sheet": str(r["sheet"]),
            "op": str(r["op"]),
            "payload": _loads(r["payload"], {}),
            "attempts": int(r["attempts"] or 0),
        }
        for r in rows
    ]


def pending_count() -> int:
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()
    return int(row["n"] if row else 0)


def _delete_op(op_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM outbox WHERE id = ?", (op_id,))
        con.commit()


def _bump_attempt(op_id: int, error: str) -> int:
    with _connect() as con:
        con.execute(
            "UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
            (str(error)[:500], op_id),
        )
        row = con.execute("SELECT attempts FROM outbox WHERE id = ?", (op_id,)).fetchone()
        con.commit()
    return int(row["attempts"] if row else 1)


# --------------------------------------------------------------------------- #
#                        تنفيذ العمليات على Google Sheets
# --------------------------------------------------------------------------- #
def _stringify(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _schema_headers(sheet: str) -> List[str]:
    from core.gsheets import SCHEMA

    return list(SCHEMA[sheet])


def _reset_client() -> None:
    global _client_cache, _worksheet_cache
    _client_cache = None
    _worksheet_cache = {}


def _client() -> Any:
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    import gspread
    from google.oauth2.service_account import Credentials

    info = _sa_info
    sa_file = _sa_file
    key = spreadsheet_key()
    if not key:
        raise SyncConfigError(
            "لم يتم إعداد مفتاح Google Sheet في الإعدادات (secrets.toml → [gsheets] spreadsheet_key)."
        )
    creds = None
    if info:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        candidates = [p for p in (sa_file, "credentials.json", "service_account.json") if p]
        found = next((p for p in candidates if os.path.exists(p)), None)
        if found:
            creds = Credentials.from_service_account_file(found, scopes=SCOPES)
    if creds is None:
        raise SyncConfigError(
            "لم يتم العثور على بيانات اعتماد Google. ضع ملف service_account.json "
            "بجانب app.py أو أضف [gcp_service_account] في secrets.toml."
        )
    _client_cache = gspread.authorize(creds)
    return _client_cache


def _spreadsheet() -> Any:
    key = spreadsheet_key()
    if not key:
        raise SyncConfigError("مفتاح Google Sheet غير مُعد.")
    return _client().open_by_key(key)


def _worksheet(sheet: str) -> Any:
    cached = _worksheet_cache.get(sheet)
    if cached is not None:
        return cached
    from gspread.exceptions import WorksheetNotFound

    ss = _spreadsheet()
    headers = _schema_headers(sheet)
    try:
        ws = ss.worksheet(sheet)
    except WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet, rows=1000, cols=max(len(headers), 5))
        ws.append_row(headers, value_input_option="RAW")
    _worksheet_cache[sheet] = ws
    return ws


def _find_row(ws: Any, headers: List[str], match_col: str, match_value: Any) -> Any:
    if match_col not in headers:
        return None
    try:
        return ws.find(str(match_value), in_column=headers.index(match_col) + 1)
    except Exception:  # noqa: BLE001
        return None


def _apply_remote(ws: Any, sheet: str, op: str, payload: Dict[str, Any]) -> None:
    """ينفّذ العملية على Google Sheets بنفس دلالة core.gsheets."""
    headers = _schema_headers(sheet)
    if op == "append":
        row = payload.get("row") or {}
        ws.append_row([_stringify(row.get(h, "")) for h in headers], value_input_option="RAW")
        return
    if op == "update":
        cell = _find_row(ws, headers, str(payload.get("match_col", "")), payload.get("match_value"))
        if cell is None:
            return
        for col, value in (payload.get("updates") or {}).items():
            if col in headers:
                ws.update_cell(cell.row, headers.index(col) + 1, _stringify(value))
        return
    if op == "delete":
        match_col = str(payload.get("match_col", ""))
        match_value = payload.get("match_value")
        col_idx = headers.index(match_col) if match_col in headers else None
        rows = ws.get_all_values()
        width = max((len(r) for r in rows), default=0)
        targets: List[int] = []
        if col_idx is not None:
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > col_idx and _eq(row[col_idx], match_value):
                    targets.append(i)
                    if payload.get("single"):
                        break
        if not targets:
            return
        if payload.get("clear"):
            letter = ""
            n = width
            while n > 0:
                n, rem = divmod(n - 1, 26)
                letter = chr(65 + rem) + letter
            ws.batch_clear([f"A{i}:{letter or 'A'}{i}" for i in targets])
        else:
            for i in sorted(targets, reverse=True):
                ws.delete_rows(i)
        return
    if op == "clear_all":
        total = len(ws.get_all_values())
        if total > 1:
            ws.delete_rows(2, total)
        return
    if op == "sync":
        cell = _find_row(ws, headers, str(payload.get("match_col", "")), payload.get("match_value"))
        if cell is None:
            return
        current = ws.row_values(cell.row)
        for col, value in (payload.get("expected") or {}).items():
            if col not in headers:
                continue
            idx = headers.index(col)
            raw = current[idx] if idx < len(current) else ""
            want = str(_stringify(value)).strip()
            if str(raw).strip() != want:
                ws.update_cell(cell.row, idx + 1, want)
        return


def _ensure_remote_schema() -> None:
    """يضمن وجود الأوراق ورؤوس الأعمدة (يدعو من الخيط الخلفي عند توفر الاتصال)."""
    from core.gsheets import SCHEMA

    ss = _spreadsheet()
    existing = {ws.title: ws for ws in ss.worksheets()}
    for sheet_name, headers in SCHEMA.items():
        if sheet_name not in existing:
            ws = ss.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 5))
            ws.append_row(headers, value_input_option="RAW")
            _worksheet_cache[sheet_name] = ws
        else:
            ws = existing[sheet_name]
            try:
                first = ws.row_values(1)
            except Exception:  # noqa: BLE001
                first = []
            if [str(c).strip() for c in first] != headers:
                if not first:
                    ws.append_row(headers, value_input_option="RAW")
                else:
                    ws.update(range_name="A1", values=[headers])


# --------------------------------------------------------------------------- #
#                          دفع العمليات (المزامنة)
# --------------------------------------------------------------------------- #
def remote_version() -> int:
    """عدّاد يرتفع بعد كل دفع ناجح (لإبطال كاش القراءة في Streamlit)."""
    return _remote_version


def set_schema_pending(value: bool = True) -> None:
    global _schema_pending
    _schema_pending = bool(value)


def schema_pending() -> bool:
    return _schema_pending


def _get_flush_lock() -> threading.Lock():
    """قفل دفع واحد لكل عملية Python (يبقى صحيحًا حتى بعد إعادة تحميل الوحدة)."""
    lock = getattr(sys, "_polio_sync_flush_lock", None)
    if lock is None:
        lock = threading.Lock()
        setattr(sys, "_polio_sync_flush_lock", lock)
    return lock


def flush() -> Dict[str, Any]:
    """يدفع كل العمليات المعلّقة إلى Google Sheets بالترتيب. آمن متعدد الخيوط."""
    global _flushing, _last_sync, _last_error, _remote_version, _retry_after
    flush_lock = _get_flush_lock()
    if not flush_lock.acquire(blocking=False):
        return {"skipped": True}
    try:
        ops = pending_ops()
        if not ops:
            with _state_lock:
                _last_error = ""
            return {"synced": 0}
        if not is_online():
            return {"offline": True}
        now = time.monotonic()
        with _state_lock:
            if now < _retry_after:
                return {"backoff": True}
        with _state_lock:
            _flushing = True
        try:
            if _schema_pending:
                try:
                    _ensure_remote_schema()
                    set_schema_pending(False)
                except Exception as exc:  # noqa: BLE001
                    if fell_offline(exc):
                        mark_offline()
                        return {"offline": True}
                    raise
            synced = 0
            for op in ops:
                try:
                    ws = _worksheet(op["sheet"])
                    _apply_remote(ws, op["sheet"], op["op"], op["payload"])
                    _delete_op(op["id"])
                    synced += 1
                except Exception as exc:  # noqa: BLE001
                    if fell_offline(exc):
                        mark_offline()
                        with _state_lock:
                            _last_error = ""
                        break
                    attempts = _bump_attempt(op["id"], f"{type(exc).__name__}: {exc}")
                    delay = min(_MAX_BACKOFF, 5.0 * attempts)
                    with _state_lock:
                        _last_error = (
                            f"تعذّرت مزامنة ورقة «{op['sheet']}» ({op['op']}): "
                            f"{type(exc).__name__}: {exc}"
                        )
                        _retry_after = time.monotonic() + delay
                    break
            if synced:
                with _state_lock:
                    _remote_version += 1
                    _last_sync = _now()
                    if not pending_ops():
                        _last_error = ""
            return {"synced": synced}
        finally:
            with _state_lock:
                _flushing = False
    finally:
        flush_lock.release()


def flush_if_pending() -> Dict[str, Any]:
    """دفع سريع عند الحاجة (يُستدعى مع كل تشغيل للصفحة) دون انتظار الخيط."""
    if pending_count() <= 0:
        return {"synced": 0}
    if not is_online():
        return {"offline": True}
    return flush()


# --------------------------------------------------------------------------- #
#                     السحب الأولي من Google Sheets
# --------------------------------------------------------------------------- #
def _pull_meta_key() -> str:
    return f"initial_pull_done:{spreadsheet_key()}"


def has_snapshot(sheet: str) -> bool:
    """هل توجد نسخة محلية (حتى لو فارغة) لهذه الورقة؟"""
    return _load_rows(sheet) is not None


def _fetch_remote_rows(sheet_name: str) -> List[Dict[str, Any]]:
    """يقرأ الورقة كاملًا من Google Sheets ويُطبّعها على المخطط (بلا كاش Streamlit)."""
    from core.gsheets import SCHEMA

    ws = _worksheet(sheet_name)
    try:
        records = ws.get_all_records(default_blank="", numericise_ignore=["all"])
    except Exception:  # noqa: BLE001 — مسار احتياطي: قراءة خام
        values = ws.get_all_values()
        if len(values) <= 1:
            records = []
        else:
            header = values[0]
            records = [dict(zip(header, row)) for row in values[1:]]
    headers = SCHEMA[sheet_name]
    return [{h: _norm(rec.get(h, "")) for h in headers} for rec in records]


def initial_pull(force: bool = False) -> Dict[str, Any]:
    """السحب الأولي: تعبئة النسخة المحلية بكل الأوراق من Google Sheets.

    يُنفَّذ عند أول تشغيل متصل (وكلما غابت نسخة محلية لورقة جديدة). بعد نجاحه
    يصبح كل محتوى الشيت متاحًا للقراءة والدخول دون اتصال.
    """
    global _remote_version, _last_sync
    if not is_online():
        return {"offline": True}
    if not spreadsheet_key():
        return {"no_key": True}
    if not _pull_lock.acquire(blocking=False):
        return {"skipped": True, "busy": True}
    try:
        from core.gsheets import SCHEMA

        if not force:
            missing = [name for name in SCHEMA if not has_snapshot(name)]
            if _meta_get(_pull_meta_key()) and not missing:
                return {"skipped": True, "already": True}
        pulled = 0
        failed: List[str] = []
        for sheet_name in SCHEMA:
            if not is_online():
                return {"offline": True, "pulled": pulled}
            try:
                rows = _fetch_remote_rows(sheet_name)
            except Exception as exc:  # noqa: BLE001
                if fell_offline(exc):
                    mark_offline()
                    return {"offline": True, "pulled": pulled}
                failed.append(sheet_name)  # خطأ في ورقة محددة: تجاهلها وتابع البقية
                continue
            _save_rows(sheet_name, rows)
            pulled += 1
        if not failed:
            # لا تُعلَّم المزامنة مكتملة إلا بسحب كل الأوراق (تُعاد المحاولة لاحقًا)
            _meta_set(_pull_meta_key(), _now())
        with _state_lock:
            _remote_version += 1
            _last_sync = _now()
        return {"pulled": pulled, "failed": failed}
    finally:
        _pull_lock.release()


# --------------------------------------------------------------------------- #
#                     خيط المزامنة الخلفي (تلقائي ومستمر)
# --------------------------------------------------------------------------- #
def ensure_worker() -> None:
    """يبدأ خيط مزامنة خلفيًا واحدًا للعملية (آمن عبر إعادة تحميل Streamlit)."""
    existing = getattr(sys, "_polio_sync_worker", None)
    if existing is not None and getattr(existing, "is_alive", lambda: False)():
        return
    thread = threading.Thread(target=_worker_loop, name="gsheet-sync-worker", daemon=True)
    thread.start()
    setattr(sys, "_polio_sync_worker", thread)


def _worker_loop() -> None:
    while True:
        time.sleep(_WORKER_INTERVAL)
        try:
            if not is_online():
                continue
            now = time.monotonic()
            with _state_lock:
                if now < _retry_after:
                    continue
            if pending_count() > 0:
                flush()
            else:
                initial_pull()  # سحب أولي/ догоняющий عند الفراغ (رخيص عند الاكتمال)
        except Exception:  # noqa: BLE001 — الخيط الخلفي لا يُسقط التطبيق أبدًا
            continue


# --------------------------------------------------------------------------- #
#                     حالة الاتصال للعرض في الواجهة
# --------------------------------------------------------------------------- #
_STATUS_META = {
    "online": ("🟢", "Online · متصل", "متصل بالإنترنت — تمت مزامنة كل البيانات."),
    "offline": (
        "🟠",
        "Offline - Saving Locally · عدم الاتصال — الحفظ محليًا",
        "لا يوجد اتصال بالإنترنت — تُحفظ التغييرات محليًا وتُزامن تلقائيًا لاحقًا.",
    ),
    "syncing": ("🔵", "Syncing… · جارٍ المزامنة", "جارٍ دفع التغييرات المعلّقة إلى Google Sheets."),
    "error": (
        "🔴",
        "Sync Error · تعذّرت المزامنة",
        "تعذّر الوصول إلى Google Sheets — ستُعاد المحاولة تلقائيًا.",
    ),
}


def status_info() -> Dict[str, Any]:
    pending = pending_count()
    with _state_lock:
        flushing = _flushing
        last_sync = _last_sync
        last_error = _last_error
    if flushing:
        state = "syncing"
    elif not is_online():
        state = "offline"
    elif last_error:
        state = "error"
    elif pending > 0:
        state = "syncing"
    else:
        state = "online"
    icon, label, hint = _STATUS_META[state]
    return {
        "state": state,
        "icon": icon,
        "label": label,
        "hint": hint,
        "pending": pending,
        "last_sync": last_sync,
        "last_error": last_error,
    }


def pill_html() -> str:
    """شارة صغيرة (HTML) لحالة الاتصال/المزامنة لعرضها في الترويسة والقائمة."""
    info = status_info()
    count = int(info["pending"] or 0)
    extra = f" ({count})" if count else ""
    return (
        f'<span class="sync-pill {info["state"]}" title="{info["hint"]}">'
        f'<span class="sync-dot"></span>{info["icon"]} {info["label"]}{extra}</span>'
    )


__all__ = [
    "FORCE_OFFLINE_ENV",
    "SyncConfigError",
    "auth_cache_count",
    "configure",
    "db_path",
    "enqueue",
    "fell_offline",
    "flush",
    "flush_if_pending",
    "ensure_worker",
    "get_cached_user",
    "has_snapshot",
    "initial_pull",
    "is_network_error",
    "is_online",
    "local_count",
    "local_match",
    "local_row_count",
    "local_sync",
    "mark_offline",
    "mark_online",
    "pending_count",
    "pending_ops",
    "pill_html",
    "read_snapshot",
    "remote_version",
    "remember",
    "save_snapshot",
    "schema_pending",
    "set_schema_pending",
    "status_info",
    "use_local",
]
