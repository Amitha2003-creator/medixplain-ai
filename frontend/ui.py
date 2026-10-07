"""Shared look-and-feel helpers: colour-coded lab tables, empty states, small styling."""

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
    """Small visual polish on top of the theme in .streamlit/config.toml."""
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            background: #f1f5fb; border: 1px solid #dbe4f0;
            border-radius: 12px; padding: 12px 16px;
        }
        div[data-testid="stMetricLabel"] p { font-size: 0.85rem; color: #4b5563; }
        h1, h2, h3 { letter-spacing: -0.01em; }
        </style>
        """,
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