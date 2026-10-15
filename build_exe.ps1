<#
.SYNOPSIS
    يبني تطبيق «مخزن المعمل» باستخدام PyInstaller.

.DESCRIPTION
    1) يثبّت حزم requirements.txt و PyInstaller.
    2) يبني التطبيق — الوضع الافتراضي مجلد dist\PolioStock\ يفتح فورًا
       (أسرع بكثير من ملف واحد لأنه بلا استخراج عند كل تشغيل).

.PARAMETER SingleExe
    بديل التوزيع السهل: ملف exe واحد (أبطأ في الفتح — يستخرج نفسه كل مرة).

.PARAMETER Python
    أمر بايثون المستخدم (الافتراضي: python).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build_exe.ps1
    powershell -ExecutionPolicy Bypass -File build_exe.ps1 -SingleExe
#>
param(
    [switch]$SingleExe,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "==> [1/3] تثبيت المتطلبات و PyInstaller ..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "فشل تثبيت الحزم." }

Write-Host "==> [2/3] تنظيف مخرجات بناء سابقة ..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

$env:POLIO_BUILD_MODE = if ($SingleExe) { "single" } else { "onedir" }
$label = if ($SingleExe) { "ملف exe واحد (أبطأ عند الفتح)" } else { "مجلد (أسرع — افتراضي)" }
Write-Host "==> [3/3] البناء ($label) ..."
& $Python -m PyInstaller --noconfirm --clean app.spec
if ($LASTEXITCODE -ne 0) { throw "فشل بناء التطبيق." }

$out = if ($SingleExe) { Join-Path $root "dist\PolioStock.exe" } else { Join-Path $root "dist\PolioStock\PolioStock.exe" }
if (-not (Test-Path $out)) { throw "لم يتم العثور على الملف الناتج: $out" }

Write-Host ""
Write-Host "=== تم البناء بنجاح ===" -ForegroundColor Green
Write-Host "الملف: $out"
Write-Host ""
Write-Host "للتشغيل: ضع بيانات الاعتماد بجانب الملف ثم شغّله:"
Write-Host "  - .streamlit\secrets.toml   (مفتاح الشيت وإعدادات الدخول)"
Write-Host "  - service_account.json      (اختياري — بيانات الخدمة قد تكون في secrets.toml)"
Write-Host "سيُنشأ مجلد data\ تلقائيًا لقاعدة البيانات المحلية (العمل دون اتصال)."
if (-not $SingleExe) {
    Write-Host "ملاحظة: للتوزيع انسخ مجلد PolioStock كاملًا (لا يُنقل الملف وحده)."
}
