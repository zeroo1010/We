"""تنسيقات CSS للواجهة العربية RTL."""
from __future__ import annotations

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif !important;
    direction: rtl;
}

.stApp { background: #f6f8fb; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f2b46 0%, #123a5c 100%);
    direction: rtl;
}
[data-testid="stSidebar"] * { color: #e8f1f8 !important; }
[data-testid="stSidebar"] .stButton button {
    width: 100%;
    text-align: start;
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 15px;
    font-weight: 600;
    color: #e8f1f8;
    transition: background .15s ease;
}
[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,0.12); }
[data-testid="stSidebar"] .nav-active button {
    background: #2563eb !important;
    color: #fff !important;
}

.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px; }

h1, h2, h3, h4 { color: #0f2b46; font-weight: 700; }

.app-header {
    background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
    color: #fff;
    padding: 22px 26px;
    border-radius: 16px;
    margin-bottom: 18px;
    box-shadow: 0 8px 24px rgba(37,99,235,0.18);
}
.app-header h1 { color: #fff; margin: 0; font-size: 24px; }
.app-header p { margin: 6px 0 0; opacity: .9; font-size: 14px; }

.metric-card {
    background: #fff;
    border-radius: 14px;
    padding: 18px 20px;
    box-shadow: 0 4px 14px rgba(15,43,70,0.07);
    border-inline-start: 5px solid #2563eb;
    height: 100%;
}
.metric-card .label { color: #64748b; font-size: 14px; font-weight: 600; }
.metric-card .value { color: #0f2b46; font-size: 30px; font-weight: 700; margin-top: 6px; }
.metric-card.warn { border-inline-start-color: #f59e0b; }
.metric-card.good { border-inline-start-color: #10b981; }
.metric-card.purple { border-inline-start-color: #8b5cf6; }

div[data-testid="stForm"], div[data-testid="stExpander"] {
    background: #fff; border-radius: 14px; padding: 8px;
    box-shadow: 0 2px 10px rgba(15,43,70,0.05);
}
.stDataFrame, [data-testid="stTable"] { border-radius: 12px; overflow: hidden; }
.stButton button[kind="primary"] { border-radius: 10px; font-weight: 700; }
.stButton button { border-radius: 10px; }

.badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 700;
}
.badge-open { background: #dbeafe; color: #1e40af; }
.badge-done { background: #d1fae5; color: #065f46; }

.user-bar {
    display: flex; align-items: center; justify-content: space-between;
    direction: rtl; gap: 10px; flex-wrap: wrap;
    background: #fff; border: 1px solid #e2e8f0;
    border-inline-start: 5px solid #2563eb;
    border-radius: 14px; padding: 10px 16px; margin-bottom: 14px;
    box-shadow: 0 4px 14px rgba(15,43,70,.07);
}
.user-bar .who { font-size: 15px; font-weight: 700; color: #0f2b46; }
.user-bar .who .role-chip {
    display: inline-block; margin-right: 8px; padding: 2px 10px;
    border-radius: 999px; font-size: 12px; font-weight: 700;
    background: #dbeafe; color: #1e40af;
}
.user-bar .who .role-chip.admin { background: #fef3c7; color: #92400e; }
.user-bar .stButton button {
    width: auto; padding: 6px 16px; font-size: 13px;
    background: #fee2e2 !important; color: #991b1b !important;
    border: 1px solid #fecaca !important; border-radius: 10px !important;
}
.user-bar .stButton button:hover { background: #fecaca !important; }

.sidebar-user {
    background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18);
    border-radius: 12px; padding: 10px 14px; margin: 0 0 10px;
    text-align: center;
}
.sidebar-user .name { font-size: 15px; font-weight: 700; color: #fff; }
.sidebar-user .role { font-size: 12px; opacity: .85; margin-top: 2px; }

/* ============ شارة حالة الاتصال والمزامنة (Online / Offline / Syncing) ============ */
.sync-pill {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 4px 12px; border-radius: 999px;
    font-size: 12.5px; font-weight: 700; line-height: 1.7;
    direction: rtl; white-space: nowrap; max-width: 100%;
}
.sync-pill .sync-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: currentColor; flex: 0 0 auto;
    animation: sync-pulse 1.6s ease-in-out infinite;
}
@keyframes sync-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: .3; }
}
.sync-pill.online  { background: #d1fae5; color: #065f46; }
.sync-pill.offline { background: #fef3c7; color: #92400e; }
.sync-pill.syncing { background: #dbeafe; color: #1e40af; }
.sync-pill.error   { background: #fee2e2; color: #991b1b; }

/* في القائمة الجانبية الداكنة: خلفية شفافة ونص فاتح */
[data-testid="stSidebar"] .sync-pill {
    background: rgba(255, 255, 255, .12);
    border: 1px solid rgba(255, 255, 255, .18);
    justify-content: center; width: 100%;
}
[data-testid="stSidebar"] .sync-pill.online  { color: #6ee7b7 !important; }
[data-testid="stSidebar"] .sync-pill.offline { color: #fcd34d !important; }
[data-testid="stSidebar"] .sync-pill.syncing { color: #93c5fd !important; }
[data-testid="stSidebar"] .sync-pill.error   { color: #fca5a5 !important; }

/* بطاقات «آخر التحديثات في المخزن» */
.activity-card {
    background: #fff;
    border-radius: 14px;
    padding: 14px 16px;
    margin-bottom: 10px;
    border-inline-start: 4px solid #2563eb;
    box-shadow: 0 2px 10px rgba(15,43,70,.06);
}
.activity-card .act-time {
    color: #64748b; font-size: 13px; font-weight: 700; unicode-bidi: plaintext;
}
.activity-card .act-title {
    color: #0f2b46; font-size: 16px; font-weight: 700; margin: 5px 0 4px;
}
.activity-card .act-code {
    color: #64748b; font-size: 13px; font-weight: 600;
}
.activity-card .act-meta { color: #334155; font-size: 14px; }

/* أزرار الوصول السريع الكبيرة */
.block-container [data-testid="stButton"] button[kind="primary"] {
    min-height: 52px !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
}

/* بطاقات st.metric */
[data-testid="stMetric"] {
    background: #fff;
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 4px 14px rgba(15,43,70,.07);
}
[data-testid="stMetricLabel"] { font-size: 14px !important; }
[data-testid="stMetricValue"] { font-size: 28px !important; }

.alert-box {
    background: #fff7ed; border: 1px solid #fdba74; border-inline-start: 5px solid #f59e0b;
    border-radius: 12px; padding: 14px 18px; margin: 8px 0; color: #7c2d12;
}
.alert-box strong { color: #9a3412; }

/* ===================== تحسينات الهواتف المحمولة ===================== */
@media (max-width: 768px) {
    .block-container {
        padding: 1rem .7rem 3rem;
        max-width: 100%;
    }

    /* 1) تكديس الأعمدة رأسيًا حتى لا تنضغط الحقول */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        flex-wrap: nowrap !important;
        gap: .7rem !important;
        width: 100% !important;
    }
    [data-testid="stColumn"] {
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
        flex: 1 1 auto !important;
    }

    /* 2) أهداف لمس أكبر (أزرار وحقول) */
    [data-testid="stButton"] > button,
    [data-testid="stDownloadButton"] > button,
    [data-testid="stFormSubmitButton"] > button {
        width: 100% !important;
        min-height: 46px !important;
        padding: 12px 16px !important;
        font-size: 16px !important;
    }
    input, textarea, [data-baseweb="input"] input, [data-baseweb="base-input"] {
        font-size: 16px !important; /* يمنع تكبير iOS التلقائي */
        min-height: 44px !important;
    }
    [data-testid="stSelectbox"] label,
    [data-testid="stDateInput"] label,
    [data-testid="stTimeInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stTextInput"] label,
    [data-testid="stCheckbox"] label {
        font-size: 15px !important;
    }
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label {
        min-height: 40px; /* مساحة لمس مريحة */
        display: flex; align-items: center;
    }

    /* 3) جداول قابلة للتمرير أفقيًا */
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    [data-testid="stHorizontalBlock"] [data-testid="stDataFrame"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
    }
    [data-testid="stTabs"] [role="tablist"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }

    /* 4) شارات المستخدم والترويسة بلا التواء */
    .user-bar {
        padding: 10px 12px;
        gap: 8px;
    }
    .user-bar .who {
        font-size: 13.5px;
        line-height: 1.6;
        flex-wrap: wrap;
        overflow-wrap: anywhere;
    }
    .user-bar .who .role-chip {
        margin: 3px 4px 0 0;
        font-size: 11px;
    }
    .sidebar-user { padding: 8px 10px; }
    .sidebar-user .name {
        font-size: 13.5px;
        word-break: break-word;
        line-height: 1.6;
    }
    .sidebar-user .role { font-size: 11.5px; }
    .app-header {
        padding: 16px;
        border-radius: 12px;
    }
    .app-header h1 { font-size: 19px; }
    .app-header p { font-size: 13px; }
    .metric-card { padding: 14px 16px; }
    .metric-card .value { font-size: 24px; }

    /* لوحة الرئيسية على الشاشات الصغيرة */
    [data-testid="stMetric"] { padding: 10px 12px; }
    [data-testid="stMetricValue"] { font-size: 22px !important; }
    .activity-card { padding: 12px; margin-bottom: 8px; }
    .activity-card .act-title { font-size: 15px; }
    .activity-card .act-meta { font-size: 13px; }
    .block-container [data-testid="stButton"] button[kind="primary"] {
        min-height: 50px !important;
        font-size: 16px !important;
    }
    h1, h2, h3, h4 { font-size: 18px; }
    .login-card { padding: 22px; }
}
</style>
"""


def inject_styles() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def metric_card(label: str, value, cls: str = "") -> str:
    return (
        f'<div class="metric-card {cls}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f"</div>"
    )


def header(title: str, subtitle: str = "") -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="app-header"><h1>{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def alert(text: str) -> None:
    st.markdown(f'<div class="alert-box">{text}</div>', unsafe_allow_html=True)