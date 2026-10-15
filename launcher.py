"""نقطة تشغيل التطبيق كبرنامج سطح مكتب (PyInstaller + Streamlit).

ماذا يفعل:
- يفتح التطبيق كنافذة برنامج مستقلة (عبر Edge/Chrome بوضع --app) بدون
  شريط تبويبات، ولا تظهر نافذة سطر أوامر سوداء.
- يحدّد مجلد العمل ليكون مجلد الـexe نفسه، فتُحفظ كل الملفات القابلة للتعديل
  بجانبه: `.streamlit/secrets.toml` (الأسرار) + `service_account.json` +
  `data/offline.db` (قاعدة البيانات المحلية للعمل دون اتصال) +
  `PolioStock.log` (سجل التشغيل والأخطاء).
- ينسخ إعدادات الثيم الافتراضية إلى `.streamlit/config.toml` بجانب الـexe إن لم تكن موجودة.
- يشغّل خادم Streamlit داخليًا على 127.0.0.1 ثم يفتح نافذة التطبيق.
- إذا كان التطبيق يعمل بالفعل (إعادة تشغيل الملف) يفتح نافذة فقط دون تشغيل خادم ثانٍ.
- زر «إغلاق التطبيق» داخل الشريط الجانبي يوقف الخادم بالكامل.

متغيرات بيئة اختيارية:
- WAREHOUSE_PORT  : رقم المنفذ (الافتراضي 8501).
- POLIO_FORCE_OFFLINE=1 : إجبار التطبيق على وضع العمل دون اتصال (للتجربة).
- WAREHOUSE_SELFTEST=1 : فحص سريع للحزمة (وجود كل الوحدات) ثم الخروج.
"""
from __future__ import annotations

import importlib
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_dir() -> str:
    """مجلد الملفات المجمَّعة (يُستخرج مؤقتًا عند تشغيل الـexe)."""
    return str(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    """مجلد الـexe نفسه — مكان الأسرار وقاعدة البيانات المحلية."""
    if _frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _setup_output(base: str) -> None:
    """يضمن وجود stdout/stderr (البناء بدون نافذة سطر أوامر يلغيهما).

    يوجّه الإخراج إلى `PolioStock.log` بجانب الـexe ليُتاح تشخيص الأخطاء،
    ويفرض ترميز UTF-8 لعرض النص العربي بأمان على أي صفحة شيفرة.
    """
    log_path = os.path.join(base, "PolioStock.log")
    for attr in ("stdout", "stderr"):
        stream = getattr(sys, attr, None)
        if stream is None or getattr(stream, "closed", False):
            try:
                setattr(sys, attr, open(log_path, "a", encoding="utf-8", errors="replace", buffering=1))
            except OSError:
                pass
        else:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _pick_port(preferred: int) -> int:
    """أول منفذ متاح ابتداءً من المنفذ المطلوب."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def _already_running(preferred: int) -> str | None:
    """رابط الخادم إن كان تطبيقنا يعمل بالفعل على المنفذ المفضل.

    يُفحص المنفذ المفضل فقط (لا مسح للمنافذ) — مسح المنافذ يستغرق أحيانًا
    ثوانٍ على بعض الأجهزة بسبب تعليق محاولات الاتصال الفاشلة.
    """
    url = f"http://127.0.0.1:{preferred}"
    try:
        with urllib.request.urlopen(f"{url}/_stcore/health", timeout=0.4):
            return url
    except Exception:  # noqa: BLE001
        return None


def _install_default_config(base: str, bundle: str) -> None:
    """ينسخ إعدادات الثيم الافتراضية بجانب الـexe إن لم يكن هناك إعدادات مستخدم."""
    src = os.path.join(bundle, ".streamlit", "config.toml")
    dst_dir = os.path.join(base, ".streamlit")
    dst = os.path.join(dst_dir, "config.toml")
    if not os.path.isfile(src) or os.path.isfile(dst):
        return
    try:
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copyfile(src, dst)
    except OSError:
        pass


def _browser_candidates() -> list[str]:
    """مسارات Edge وChrome على Windows (أو غيرهما على أنظمة أخرى)."""
    if os.name != "nt":
        return [
            "/usr/bin/microsoft-edge",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
    candidates: list[str] = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(env, "")
        if not root:
            continue
        candidates.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
        candidates.append(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
    return candidates


def _open_app_window(url: str) -> None:
    """يفتح نافذة تطبيق (بدون تبويبات) بنفس شكل برامج سطح المكتب."""
    for exe in _browser_candidates():
        if not exe or not os.path.isfile(exe):
            continue
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=1360,860", "--no-first-run"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            continue
    webbrowser.open(url)


def _open_window_when_ready(url: str, timeout: float = 240.0) -> None:
    """يفتح نافذة التطبيق فور استجابة الخادم (أول تشغيل للـexe قد يستغرق وقتًا)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                break
        except Exception:  # noqa: BLE001 — الخادم لم يبدأ بعد
            time.sleep(0.7)
    _open_app_window(url)


def _selftest(bundle: str) -> int:
    """يتحقق من وجود كل الوحدات والملفات داخل الحزمة ثم يخرج (لتشخيص مشاكل البناء)."""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))

    for name in (
        "streamlit.web.cli",
        "core.config",
        "core.gsheets",
        "core.offline",
        "core.services",
        "core.auth",
        "core.users",
        "core.styles",
        "core.db",
        "gspread",
        "pandas",
        "pyarrow",
        "google.oauth2.service_account",
        "google.auth.transport.requests",
        "certifi",
        "requests",
        "watchdog",
        "altair",
        "tzdata",
    ):
        try:
            importlib.import_module(name)
            check(name, True)
        except Exception as exc:  # noqa: BLE001
            check(name, False, str(exc))

    try:
        import streamlit

        static = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        check("streamlit static/index.html", os.path.isfile(static))
    except Exception as exc:  # noqa: BLE001
        check("streamlit static/index.html", False, str(exc))

    check("app.py", os.path.isfile(os.path.join(bundle, "app.py")))
    check(".streamlit/config.toml", os.path.isfile(os.path.join(bundle, ".streamlit", "config.toml")))

    failed = [item for item in results if not item[1]]
    for name, ok, detail in results:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name} {detail}")
    print(f"SELFTEST_{'OK' if not failed else 'FAILED'} ({len(results) - len(failed)}/{len(results)})", flush=True)
    return 0 if not failed else 1


def main() -> None:
    multiprocessing.freeze_support()

    bundle = _bundle_dir()
    base = _base_dir()
    os.chdir(base)  # كل الملفات القابلة للتعديل تُنشأ بجانب الـexe
    if bundle not in sys.path:
        sys.path.insert(0, bundle)

    _setup_output(base)
    _install_default_config(base, bundle)

    # داخل حزمة PyInstaller لا يمرّ مسار streamlit عبر site-packages،
    # فيظنّ أنه وضع التطوير ويمنع تغيير المنفذ — نعطّله هنا.
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    # يُبلّغ التطبيق بأنه يعمل كبرنامج سطح مكتب (زر الإغلاق في الشريط الجانبي)
    os.environ.setdefault("WAREHOUSE_DESKTOP", "1")

    preferred = int(os.environ.get("WAREHOUSE_PORT", "8501"))

    if os.environ.get("WAREHOUSE_SELFTEST"):
        raise SystemExit(_selftest(bundle))

    # إذا كان التطبيق يعمل بالفعل: افتح نافذة فقط (بدون خادم ثانٍ)
    existing = _already_running(preferred)
    if existing:
        print(f"التطبيق يعمل بالفعل — فتح النافذة فقط: {existing}", flush=True)
        _open_app_window(existing)
        return

    port = _pick_port(preferred)
    url = f"http://127.0.0.1:{port}"

    print("=" * 64)
    print("  نظام إدارة مخزن المعمل — نسخة مكتبي (تعمل دون اتصال)")
    print(f"  الرابط: {url}")
    print("  ستفتح نافذة التطبيق تلقائيًا بعد جاهزية الخادم…")
    print("  للإغلاق: استخدم زر «إغلاق التطبيق» في الشريط الجانبي")
    print(f"  سجل التشغيل: {os.path.join(base, 'PolioStock.log')}")
    print("=" * 64, flush=True)

    threading.Thread(target=_open_window_when_ready, args=(url,), daemon=True).start()

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        os.path.join(bundle, "app.py"),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
    ]
    stcli.main()


if __name__ == "__main__":
    main()
