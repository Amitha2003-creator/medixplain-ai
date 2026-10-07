"""Shared look-and-feel helpers: colour-coded lab tables, empty states, small styling."""

from html import escape

import pandas as pd
import streamlit as st

# Background / text colours for the Status column (readable, colour-blind safe text labels too).
STATUS_COLORS = {
    "HIGH": ("#fde8e8", "#9b1c1c"),    # soft red
    "LOW": ("#fef3c7", "#92400e"),     # soft amber
    "NORMAL": ("#e6f4ea", "#1e6b34"),  # soft green
}
STATUS_LABEL = {"HIGH": "🔺 High", "LOW": "🔻 Low", "NORMAL": "✅ Normal"}


def inject_css():
    """Colourful healthcare look: gradient hero, dark gradient sidebar, pill buttons, soft cards."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        :root {
            --mx-navy: #0b2a5b;
            --mx-blue: #2563eb;
            --mx-teal: #14b8a6;
            --mx-sky: #e0f2fe;
            --mx-ink: #0f172a;
            --mx-muted: #64748b;
            --mx-line: #e2e8f0;
        }
        html, body, [class*="css"], .stApp, button, input, textarea, select {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
        }
        .stApp {
            background: radial-gradient(1200px 500px at 85% -10%, #dbeafe 0%, transparent 60%),
                        radial-gradient(900px 400px at -10% 10%, #ccfbf1 0%, transparent 55%),
                        #f8fafc;
        }
        header[data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2rem; max-width: 1200px; }
        h1, h2, h3 { color: var(--mx-ink); font-weight: 700; letter-spacing: -0.02em; }

        /* ---------- Sidebar ---------- */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b2a5b 0%, #1e40af 55%, #0f766e 100%);
        }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] small {
            color: #f1f5f9 !important;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] span,
        section[data-testid="stSidebar"] div[data-baseweb="select"] div {
            color: var(--mx-ink) !important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            background: rgba(255, 255, 255, 0.08); border-radius: 12px;
            padding: 8px 12px; margin-bottom: 6px; width: 100%;
            transition: background 0.15s;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
            background: rgba(255, 255, 255, 0.18);
        }
        section[data-testid="stSidebar"] hr { border-color: rgba(255, 255, 255, 0.2); }
        section[data-testid="stSidebar"] a { color: #bfdbfe !important; text-decoration: none; }
        section[data-testid="stSidebar"] .stButton > button {
            background: rgba(255, 255, 255, 0.12); color: #fff !important;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }

        /* ---------- Buttons ---------- */
        .stButton > button, div[data-testid="stFormSubmitButton"] > button,
        div[data-testid="stDownloadButton"] > button {
            border-radius: 999px; font-weight: 600; padding: 0.5rem 1.25rem;
            border: 1px solid var(--mx-line);
            transition: transform 0.1s, box-shadow 0.15s;
        }
        .stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
            transform: translateY(-1px); box-shadow: 0 6px 16px rgba(37, 99, 235, 0.18);
        }
        button[kind="primary"], button[kind="primaryFormSubmit"] {
            background: linear-gradient(90deg, var(--mx-blue), var(--mx-teal)) !important;
            border: none !important; color: #fff !important;
        }

        /* ---------- Cards, metrics, tabs ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff; border-radius: 16px !important;
            border: 1px solid var(--mx-line) !important;
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
        }
        div[data-testid="stMetric"] {
            background: #ffffff; border: 1px solid var(--mx-line);
            border-left: 5px solid var(--mx-teal);
            border-radius: 16px; padding: 14px 18px;
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
        }
        div[data-testid="stMetricLabel"] p { font-size: 0.85rem; color: var(--mx-muted); font-weight: 600; }
        div[data-testid="stMetricValue"] { color: var(--mx-navy); font-weight: 800; }
        div[data-baseweb="tab-list"] { gap: 6px; }
        button[data-baseweb="tab"] {
            background: #ffffff; border: 1px solid var(--mx-line);
            border-radius: 999px; padding: 6px 16px;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(90deg, var(--mx-blue), var(--mx-teal));
            color: #fff !important; border: none;
        }
        button[data-baseweb="tab"][aria-selected="true"] p { color: #fff !important; }
        div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { display: none; }
        div[data-testid="stExpander"] details {
            background: #ffffff; border-radius: 14px; border: 1px solid var(--mx-line);
        }
        input, textarea { border-radius: 10px !important; }

        /* ---------- Hero banner and feature cards ---------- */
        .mx-hero {
            background: linear-gradient(120deg, #0b2a5b 0%, #1d4ed8 55%, #0d9488 100%);
            border-radius: 24px; padding: 36px 40px; color: #fff;
            box-shadow: 0 18px 40px rgba(11, 42, 91, 0.25); margin-bottom: 24px;
            position: relative; overflow: hidden;
        }
        .mx-hero::after {
            content: ""; position: absolute; right: -60px; top: -60px;
            width: 260px; height: 260px; border-radius: 50%;
            background: radial-gradient(circle, rgba(94, 234, 212, 0.45), transparent 70%);
        }
        .mx-badge {
            display: inline-block; background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 999px;
            padding: 4px 14px; font-size: 0.8rem; font-weight: 600; margin-bottom: 14px;
        }
        .mx-hero h1 { color: #fff !important; font-size: 2.4rem; font-weight: 800; margin: 0 0 8px 0; }
        .mx-hero p { color: #e0f2fe; font-size: 1.05rem; margin: 0; max-width: 720px; }
                .mx-card {
            background: #ffffff !important; border: 1px solid #cbd5e1; border-radius: 18px;
            border-top: 5px solid var(--mx-card-accent, #2563eb);
            padding: 18px; min-height: 150px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10);
        }
        .mx-card .mx-icon {
            width: 48px; height: 48px; border-radius: 14px; display: flex;
            align-items: center; justify-content: center; font-size: 1.6rem; margin-bottom: 10px;
        }
        .mx-card h4 {
            margin: 0 0 6px 0; color: #0f172a !important; font-weight: 800 !important;
            font-size: 1.08rem !important; padding: 0 !important;
        }
        .mx-card p { margin: 0; color: #334155 !important; font-size: 0.93rem; line-height: 1.45; }
        section[data-testid="stSidebar"] a { color: #bfdbfe !important; text-decoration: none; }
        .mx-brand { font-size: 1.35rem; font-weight: 800; color: #fff; margin-bottom: 2px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, badge: str = ""):
    """A gradient banner at the top of a page."""
    badge_html = f'<div class="mx-badge">{escape(badge)}</div>' if badge else ""
    st.markdown(
        f'<div class="mx-hero">{badge_html}<h1>{escape(title)}</h1>'
        f'<p>{escape(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


# (icon square background, card top-border colour)
CARD_TINTS = {
    "blue": ("#bfdbfe", "#2563eb"),
    "teal": ("#99f6e4", "#0d9488"),
    "violet": ("#ddd6fe", "#7c3aed"),
    "amber": ("#fde68a", "#d97706"),
}


def feature_card(icon: str, title: str, text: str, tint: str = "blue"):
    """A white card with a coloured top border and a coloured icon square."""
    bg, accent = CARD_TINTS.get(tint, CARD_TINTS["blue"])
    st.markdown(
        f'<div class="mx-card" style="--mx-card-accent:{accent}">'
        f'<div class="mx-icon" style="background:{bg}">{icon}</div>'
        f'<h4>{escape(title)}</h4><p>{escape(text)}</p></div>',
        unsafe_allow_html=True,
    )

def _status_style(value: str) -> str:
    for status, label in STATUS_LABEL.items():
        if value == label:
            bg, fg = STATUS_COLORS[status]
            return f"background-color: {bg}; color: {fg}; font-weight: 600;"
    return ""


def status_table(labs: list[dict]):
    """Lab values as a table with a colour-coded Status column (High red, Low amber, Normal green)."""
    if not labs:
        return
    df = pd.DataFrame([
        {"Test": lab["test"],
         "Result": f"{lab['value_text']} {lab['unit']}".strip(),
         "Reference range": lab.get("reference_range") or "Not printed",
         "Status": STATUS_LABEL.get(lab["status"], lab["status"])}
        for lab in labs
    ])
    styler = df.style
    styler = (styler.map(_status_style, subset=["Status"]) if hasattr(styler, "map")
              else styler.applymap(_status_style, subset=["Status"]))
    st.dataframe(styler, hide_index=True, width="stretch")


def status_counts(labs: list[dict]):
    """Three small metrics: values high, low, normal."""
    high = sum(1 for lab in labs if lab["status"] == "HIGH")
    low = sum(1 for lab in labs if lab["status"] == "LOW")
    normal = sum(1 for lab in labs if lab["status"] == "NORMAL")
    c1, c2, c3 = st.columns(3)
    c1.metric("🔺 High", high)
    c2.metric("🔻 Low", low)
    c3.metric("✅ Normal", normal)


def empty_state(icon: str, title: str, text: str):
    """A friendly box for pages with nothing to show yet."""
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.write(text)