# -*- mode: python ; coding: utf-8 -*-
"""مواصفات بناء تطبيق «مخزن المعمل» (Streamlit + PyInstaller).

وضعان عبر متغير البيئة POLIO_BUILD_MODE:
- "onedir" (الافتراضي): مجلد dist\\PolioStock\\ يفتح فورًا (أسرع بكثير — بلا استخراج).
- "single": ملف exe واحد (أبطأ في أول فتحdue لاستخراج الحزمة، أسهل للتوزيع).

يُبنى عبر:  powershell -ExecutionPolicy Bypass -File build_exe.ps1
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

MODE = os.environ.get("POLIO_BUILD_MODE", "onedir").strip().lower()

datas = []
binaries = []
hiddenimports = [
    # حزمة التطبيق محليًا (تُحلل عبر الاستيراد الثابت داخل app.py أيضًا)
    "core",
    "core.auth",
    "core.config",
    "core.db",
    "core.gsheets",
    "core.offline",
    "core.services",
    "core.styles",
    "core.users",
]

# ملفات Streamlit الثابتة (واجهة المتصفح) + pyarrow (أساسية لعرض الجداول)
# + شهادات TLS + قاعدة المناطق الزمنية.
for pkg in ("streamlit", "pyarrow", "certifi", "tzdata"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:  # noqa: BLE001 — حزمة غير مثبتة: تجاهل
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# حزم Google (oauth2 / service account) وgspread كوحدات فرعية كاملة.
hiddenimports += collect_submodules("google")
hiddenimports += collect_submodules("gspread")

# ملفات البيانات: نقطة الدخول + إعدادات الثيم الافتراضية (تُنسخ بجانب الـexe
# عند أول تشغيل ويمكن للمستخدم تعديلها لاحقًا).
datas += [
    ("app.py", "."),
    (os.path.join(".streamlit", "config.toml"), ".streamlit"),
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe_kwargs = dict(
    name="PolioStock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,  # بدون نافذة سطر أوامر — يعمل كبرنامج سطح مكتب (السجلات في PolioStock.log)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if MODE == "single":
    # ملف واحد: يستخرج نفسه إلى %TEMP% عند كل تشغيل (أبطأ — للتوزيع السهل فقط)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        runtime_tmpdir=None,
        **exe_kwargs,
    )
else:
    # مجلد أسرع: كل الملفات جاهزة على القرص — بدء فوري بلا استخراج
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="PolioStock",
    )
