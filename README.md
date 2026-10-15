# نظام إدارة مخزن المعمل

نظام ويب كامل بلغة Python + Streamlit لإدارة طلبات المعمل وصرف الأصناف من المخزن على دفعات، مع حفظ كل البيانات في **Google Sheets** كقاعدة بيانات أساسية (لا تضيع البيانات عند إعادة تشغيل التطبيق).

---

## ✨ المميزات

- واجهة عربية كاملة **RTL** بتصميم عصري ومتجاوب (كمبيوتر وموبايل).
- قائمة جانبية: الرئيسية، طلبات المعمل، الأصناف، حركة المخزن، التقارير، الإعدادات، تسجيل الخروج.
- إنشاء طلبيات بأرقام تلقائية، وإضافة أصناف متعددة لكل طلبية.
- صرف الطلبية **على دفعات** مع تسجيل كل عملية سحب مستقلة (الكمية، التاريخ، اسم الساحب).
- حساب تلقائي: `المتبقي = المطلوب - إجمالي المسحوب`.
- خصم تلقائي من رصيد المخزن عند كل سحب.
- منع السحب بأكثر من الرصيد أو بأكثر من المتبقي في الطلبية.
- تنبيه عند وجود كميات متبقية من **طلبية سابقة** لنفس الصنف (دون خلط الطلبيات).
- تنبيه **"المخزون منخفض"** عند وصول الرصيد للحد الأدنى.
- صفحة تقارير شاملة (طلبات، سحوبات، حركة صنف، المتبقيات، الأصناف المنخفضة) مع بحث وتصفية بالتاريخ والتصدير CSV.
- معالجة أخطاء وتحقق من صحة البيانات.
- **عمل دون اتصال (Offline-First)**: حفظ كل الإضافات والتعديلات محليًا (SQLite) عند انقطاع الإنترنت، ومزامنتها تلقائيًا مع Google Sheets فور عودة الاتصال — بدون أي زر Sync، مع شارة حالة (Online / Offline / Syncing).

> الصفحة الرئيسية لا تحتوي على أي بطاقة أو قسم باسم "طلبات قيد الانتظار".

---

## 📂 بنية المشروع

```
.
├── app.py                        # نقطة الدخول + التوجيه بين الصفحات + تسجيل الدخول
├── requirements.txt
├── README.md
├── .streamlit/
│   ├── config.toml               # إعدادات الثيم
│   └── secrets.toml.example      # نموذج الأسرار (انسخه إلى secrets.toml)
├── core/
│   ├── config.py                 # قراءة الإعدادات من Secrets
│   ├── gsheets.py                # طبقة الوصول إلى Google Sheets + المخطط (Schema)
│   ├── offline.py                # العمل دون اتصال + طابور المزامنة التلقائية (SQLite)
│   ├── services.py               # منطق الأعمال (أصناف، طلبات، سحب، حركات)
│   ├── auth.py                   # تسجيل الدخول/الخروج
│   └── styles.py                 # تنسيقات CSS RTL
└── views/
    ├── dashboard.py              # الرئيسية (ملخصات إحصائية)
    ├── orders.py                 # طلبات المعمل + السحب + المتبقيات
    ├── products.py               # الأصناف
    ├── movements.py              # حركة المخزن
    ├── reports.py                # التقارير
    └── settings.py               # الإعدادات وحالة الاتصال
```

---

## 🔧 المتطلبات

- Python 3.9+
- حساب Google (لإنشاء Service Account و Google Sheet)

---

## 🗂️ أوراق بيانات Google Sheets

يقوم التطبيق بإنشائها وتجهيز رؤوس الأعمدة تلقائيًا عند أول تشغيل (من صفحة الإعدادات اضغط «إنشاء/فحص أوراق البيانات»):

| الورقة | الأعمدة |
|---|---|
| `Products` | product_code, product_name, unit, current_stock, min_stock, storage_location, notes, created_at |
| `Orders` | order_no, order_date, factory_name, responsible_person, status, notes, created_at |
| `Order_Items` | item_id, order_no, product_code, product_name, unit, required_qty, withdrawn_qty, last_withdraw_date, last_withdrawn_by, created_at |
| `Withdrawals` | withdrawal_id, order_no, item_id, product_code, product_name, qty, withdraw_date, withdrawn_by, notes, created_at |
| `Stock_Movements` | movement_no, movement_date, movement_type, order_no, product_code, product_name, qty, balance_after, person, notes, created_at |
| `Settings` | key, value |

> لا يتم حذف أي بيانات قديمة عند إنشاء طلبية أو عملية سحب؛ كل العمليات تُضاف كصفوف جديدة.

---

## 🔑 إعداد Google Sheets API و Service Account (خطوة بخطوة)

1. افتح [Google Cloud Console](https://console.cloud.google.com/) وأنشئ مشروعًا جديدًا.
2. من **APIs & Services → Library** فعّل:
   - **Google Sheets API**
   - **Google Drive API**
3. من **APIs & Services → Credentials → Create Credentials → Service Account**:
   - أدخل اسمًا للحساب (مثال: `warehouse-bot`) ثم أنشئه.
4. افتح الـService Account → تبويب **Keys → Add Key → Create new key → JSON**.
   - سيتم تنزيل ملف JSON (احفظه باسم `service_account.json` بجانب `app.py` محليًا).
   - انسخ البريد `client_email` من داخل الملف (شكله `xxx@project.iam.gserviceaccount.com`).
5. أنشئ Google Sheet جديدًا (أو استخدم موجودًا)، ثم اضغط **مشاركة / Share** وأضف بريد الـService Account مع صلاحية **Editor**.
6. انسخ **مفتاح الملف** من الرابط:
   `https://docs.google.com/spreadsheets/d/<SPREADSHEET_KEY>/edit`

---

## ⚙️ إعداد الأسرار (Secrets)

انسخ `.streamlit/secrets.toml.example` إلى `.streamlit/secrets.toml` وعدّل القيم:

```toml
[gsheets]
spreadsheet_key = "ضع_مفتاح_الملف_هنا"
service_account_file = "service_account.json"   # محليًا فقط

[auth]
username = "admin"
password = "غيّر_كلمة_المرور"
app_title = "نظام إدارة مخزن المعمل"
```

> ملف `secrets.toml` و `service_account.json` لا يجب رفعهما إلى Git. أضفهما إلى `.gitignore`.

---

## 📴 العمل دون اتصال والمزامنة التلقائية (Offline-First)

- عند انقطاع الإنترنت تُحفَظ كل عمليات الإضافة/التعديل/الحذف فورًا في قاعدة بيانات
  محلية SQLite (`data/offline.db`): طابور عمليات معلّقة + نسخة محلية من كل ورقة،
  فتبقى شاشات التطبيق تعمل بالكامل وتقرأ آخر ما كُتب («اقرأ ما كتبت»).
- عند عودة الاتصال يدفع **خيط خلفي تلقائي** (وأيضًا عند أي تفاعل مع التطبيق) كل
  العمليات المعلّقة إلى Google Sheets بالترتيب نفسه — **بلا أي زر Sync أو تدخل من
  المستخدم**، ولا تُفقد أي بيانات عند الأعطال (تبقى في الطابور وتُعاد المحاولة).
- شارة حالة صغيرة أعلى الواجهة وفي القائمة الجانبية تتحدث تلقائيًا كل ثانيتين:
  - 🟢 `Online` — متصل وتمت مزامنة كل البيانات.
  - 🟠 `Offline - Saving Locally` — عدم الاتصال، الحفظ محليًا (مع عدد العمليات المعلّقة).
  - 🔵 `Syncing…` — جارٍ دفع التغييرات المعلّقة إلى Google Sheets.
  - 🔴 `Sync Error` — تعذّر الوصول إلى Google Sheets (تُعاد المحاولة تلقائيًا مع تأجيل متزايد).
- **السحب الأولي**: عند أول تشغيل متصل (وكلما غابت نسخة محلية لورقة جديدة) يسحب
  المحرك **كل أوراق الشيت** (الأصناف/الطلبيات/السحوبات/…) إلى `data/offline.db`،
  فتتوفر كل البيانات القديمة للعمل دون اتصال مباشرة.
- **الدخول دون اتصال**: عند أي قراءة ناجحة لورقة المستخدمين تُخزَّن تجزئات كلمات
  المرور (PBKDF2 — لا نص صريح) في ذاكرة دخول محلية داخل `data/offline.db`،
  وعند عدم توفّر النسخة الكاملة يتحقق التطبيق من هذه الذاكرة — فيعمل تسجيل
  الدخول بنفس بيانات الاعتماد حتى دون إنترنت، وتتحدّث فورًا مع أي تغيير
  (إضافة مستخدم/تغيير كلمة مرور/حذف).
- للتجربة المحلية دون اتصال: ضع `POLIO_FORCE_OFFLINE=1` في متغيرات البيئة قبل التشغيل.

---

## 🖥️ التشغيل محليًا

```bash
# 1) إنشاء بيئة افتراضية (اختياري لكن مستحسن)
python -m venv .venv
.venv\Scripts\activate        # على Windows
# source .venv/bin/activate   # على Linux/Mac

# 2) تثبيت الحزم
pip install -r requirements.txt

# 3) ضع ملف service_account.json بجانب app.py، وعدّل .streamlit/secrets.toml

# 4) التشغيل
streamlit run app.py
```

ثم افتح المتصفح على `http://localhost:8501` وسجّل الدخول باسم المستخدم وكلمة المرور من `secrets.toml`.

---

## 📦 تجميع التطبيق (Windows)

يمكن توزيع التطبيق على أجهزة أخرى بدون تثبيت بايثون عبر تجميعه بـPyInstaller:

```powershell
# من داخل مجلد المشروع (يحتاج اتصال إنترنت لتثبيت الحزم أول مرة)
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

- المخرج (الافتراضي — **أسرع في الفتح**): مجلد `dist\PolioStock\` — انسخه كاملًا
  إلى الجهاز الهدف وشغّل `PolioStock\PolioStock.exe` (بدء فوري بلا استخراج).
- بديل ملف واحد أسهل للتوزيع وأبطأ عند كل تشغيل (يستخرج ~138 ميجا لحظيًا):
  `build_exe.ps1 -SingleExe` → `dist\PolioStock.exe`.
- **يشتغل كبرنامج سطح مكتب**: بدون نافذة سوداء، وتفتح نافذة تطبيق مستقلة (عبر Edge/Chrome بوضع `--app`) بدون شريط تبويبات.
- **إعادة تشغيل الملف** تفتح النافذة مباشرة دون تشغيل خادم ثانٍ؛ للإغلاق الكامل استخدم زر **«⏻ إغلاق التطبيق»** في الشريط الجانبي.
- سجل التشغيل والأخطاء: `PolioStock.log` بجانب الملف.
- **بعد نسخ المجلد** ضع ملفات الاعتماد **بجانب الملف التنفيذي** ثم شغّله:

  ```
  PolioStock\
  ├── PolioStock.exe
  ├── .streamlit\secrets.toml   ← مفتاح الشيت وإعدادات الدخول
  ├── service_account.json      ← (اختياري إن كانت بيانات الخدمة داخل secrets.toml)
  └── data\                     ← يُنشأ تلقائيًا (قاعدة العمل دون اتصال)
  ```

- أول تشغيل متصل يُنزّل بيانات الشيت محليًا في الخلفية (السحب الأولي) — الصفحة تفتح فورًا دون انتظاره.
- `app.spec` هو ملف إعدادات البناء (`POLIO_BUILD_MODE=single|onedir`).
- فحص سريع للحزمة (اختياري): `WAREHOUSE_SELFTEST=1 PolioStock.exe` — يطبع النتيجة في `PolioStock.log`.

---

## ☁️ التشغيل على Streamlit Cloud

1. ارفع المشروع إلى مستودع GitHub (بدون `secrets.toml` أو `service_account.json`).
2. من [share.streamlit.io](https://share.streamlit.io) اضغط **New app** واختر المستودع وملف `app.py`.
3. من **Settings → Secrets** الصق الإعدادات التالية:

```toml
[gsheets]
spreadsheet_key = "ضع_مفتاح_الملف_هنا"

[auth]
username = "admin"
password = "غيّر_كلمة_المرور"
app_title = "نظام إدارة مخزن المعمل"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "warehouse-bot@project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/warehouse-bot%40project.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

> انسخ قيم `[gcp_service_account]` حرفيًا من ملف JSON الذي نزّلته (مع الإبقاء على `\n` داخل `private_key`).

4. اضغط **Deploy**. عند أول تشغيل انتقل إلى صفحة **الإعدادات** واضغط «إنشاء/فحص أوراق البيانات».

---

## 🧭 طريقة الاستخدام

1. **الأصناف**: أضف الأصناف (الكود، الاسم، الوحدة، الرصيد الحالي، الحد الأدنى، مكان التخزين).
2. **طلبات المعمل → ➕ إضافة طلبية جديدة**: أدخل تاريخ الوصول، اسم المعمل/القسم، المسؤول، ملاحظات.
3. من شاشة تفاصيل الطلبية اضغط **➕ إضافة صنف** وأضف الأصناف المطلوبة.
   - إذا كان الصنف له كمية متبقية في طلبية سابقة سيظهر **تنبيه** برقم الطلبية القديمة وتاريخها وكمياتها.
4. **تسجيل السحب**: اختر الصنف، الكمية المسحوبة، اسم الساحب، تاريخ السحب (يمكن السحب على دفعات في تواريخ مختلفة).
5. عند اكتمال كل الأصناف اضغط **✅ إتمام الطلبية**.
6. تابع كل الحركات من **حركة المخزن**، والتقارير من صفحة **التقارير**.

---

## 📌 قواعد الحساب المطبّقة

- المتبقي في الطلبية = المطلوب − إجمالي المسحوب.
- رصيد المخزن ينخفض تلقائيًا عند كل سحب.
- لا يُسمح بسحب كمية أكبر من رصيد المخزن.
- لا يُسمح بسحب كمية أكبر من المتبقي في الطلبية.
- عند وصول الرصيد للحد الأدنى أو أقل يظهر تنبيه «المخزون منخفض».
- يتم حفظ تاريخ ووقت كل عملية سحب واسم الشخص الذي قام بالسحب.
- كل العمليات محفوظة في Google Sheets ولا تُحذف البيانات القديمة.