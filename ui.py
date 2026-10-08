"""Shared look-and-feel helpers: colour-coded lab tables, empty states, small styling."""

import base64
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
            border-radius: 24px; padding: 26px 34px; color: #fff;
            box-shadow: 0 18px 40px rgba(11, 42, 91, 0.25); margin-bottom: 18px;
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

        /* ---------- Hide Streamlit's own toolbar (Share, star, edit, GitHub, menu) ---------- */
        [data-testid="stToolbarActions"], [data-testid="stMainMenu"],
        [data-testid="stAppDeployButton"], .stAppDeployButton,
        [data-testid="stDecoration"], footer {
            display: none !important;
        }

        /* ---------- "How it works" steps and the example box ---------- */
        .mx-step {
            display: flex; gap: 14px; align-items: flex-start;
            background: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px;
            padding: 14px 16px; margin-bottom: 12px;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.07);
        }
        .mx-step-num {
            flex: 0 0 36px; height: 36px; border-radius: 50%;
            background: linear-gradient(135deg, var(--mx-blue), var(--mx-teal));
            color: #fff; font-weight: 800; display: flex;
            align-items: center; justify-content: center;
        }
        .mx-step h5 { margin: 0 0 2px 0 !important; padding: 0 !important;
                      color: #0f172a !important; font-weight: 700; font-size: 1rem; }
        .mx-step p { margin: 0; color: #334155 !important; font-size: 0.9rem; }
        .mx-example {
            background: #f0fdfa; border: 1px dashed #14b8a6; border-radius: 14px;
            padding: 14px 18px; color: #134e4a; font-size: 0.93rem; line-height: 1.55;
        }
        .mx-example b { color: #0f172a; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    inject_medical_background()


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


def step(number: int, title: str, text: str):
    """One numbered step for the "How it works" section."""
    st.markdown(
        f'<div class="mx-step"><div class="mx-step-num">{number}</div>'
        f'<div><h5>{escape(title)}</h5><p>{escape(text)}</p></div></div>',
        unsafe_allow_html=True,
    )


def example_box(html_text: str):
    """A soft teal box for the sample explanation (html_text is our own fixed text)."""
    st.markdown(f'<div class="mx-example">{html_text}</div>', unsafe_allow_html=True)


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


# ---------------------------------------------------------------------------
# Medical background (drawn in code, so there is no image file to upload)
# ---------------------------------------------------------------------------

# One 220 x 220 tile of soft medical icons. The browser repeats it over the page.
_PATTERN_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220'>
  <g fill='none' stroke='#2563eb' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' opacity='0.10'>
    <path d='M28 18h12v12h12v12H40v12H28V42H16V30h12z'/>
    <path d='M0 110h40l8-16 10 34 10-46 10 40 6-12h136'/>
    <rect x='140' y='22' width='46' height='18' rx='9' transform='rotate(-30 163 31)'/>
    <path d='M154 40l12-20' />
    <path d='M60 170c-8-10-22-4-18 8 3 9 18 18 18 18s15-9 18-18c4-12-10-18-18-8z'/>
    <path d='M150 150c10 6 20 6 30 0M150 190c10-6 20-6 30 0M155 155v30M175 155v30M150 170h30'/>
  </g>
  <g fill='#14b8a6' opacity='0.10'>
    <circle cx='110' cy='40' r='4'/><circle cx='200' cy='110' r='3'/><circle cx='110' cy='200' r='4'/>
  </g>
</svg>
"""

# A heartbeat line that sits on the right side of every hero banner.
_HERO_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' width='600' height='160' viewBox='0 0 600 160'>
  <path d='M0 90h180l18-40 22 80 24-110 22 90 14-20h320' fill='none' stroke='white'
        stroke-width='3' stroke-linecap='round' stroke-linejoin='round' opacity='0.25'/>
  <path d='M470 40h18v18h18v18h-18v18h-18V76h-18V58h18z' fill='white' opacity='0.18'/>
</svg>
"""


def _svg_url(svg: str) -> str:
    data = base64.b64encode(" ".join(svg.split()).encode()).decode()
    return f'url("data:image/svg+xml;base64,{data}")'


def inject_medical_background():
    """Soft repeating medical icons on the page, and a heartbeat line in each hero banner."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(1200px 500px at 85% -10%, rgba(219, 234, 254, 0.9) 0%, transparent 60%),
                radial-gradient(900px 400px at -10% 10%, rgba(204, 251, 241, 0.9) 0%, transparent 55%),
                {_svg_url(_PATTERN_SVG)} repeat,
                #f8fafc;
        }}
        .mx-hero::before {{
            content: ""; position: absolute; right: 0; bottom: 0;
            width: 60%; height: 100%; pointer-events: none;
            background: {_svg_url(_HERO_SVG)} no-repeat right center / contain;
        }}
        .mx-hero > * {{ position: relative; z-index: 1; }}
        </style>
        """,
        unsafe_allow_html=True,
    )