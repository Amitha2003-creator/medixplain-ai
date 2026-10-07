"""Patient home dashboard: a quick overview and shortcuts."""

import streamlit as st

from api import api
from ui import empty_state, hero, status_table

REPORTS_PAGE = "📊 My Reports & Trends"
UNDERSTAND_PAGE = "📄 Understand a Report"
PROFILE_PAGE = "👤 My Profile & Timeline"


def _go(page: str):
    # Runs before the next rerun, so the sidebar menu switches page.
    st.session_state["nav"] = page


def home_page(user: dict):
    first_name = (user.get("name") or "there").split()[0]
    hero(f"Welcome back, {first_name} 👋",
         "Here is a quick look at your health reports. Values are compared with the reference "
         "range printed on each report.", badge="🏠 Your dashboard")

    patient_id = user.get("patient_id")
    if not patient_id:
        st.error("No patient profile is linked to this account. Please contact the clinic.")
        return

    reports = (api("GET", f"/patients/{patient_id}/reports") or {}).get("reports", [])

    if not reports:
        empty_state(
            "📂", "No reports yet",
            "Start in three steps: 1) upload a lab report, 2) read the simple explanation, "
            "3) ask questions about it. Your files are read in memory and not stored.",
        )
        c1, c2 = st.columns(2)
        c1.button("💾 Save my first report", type="primary", width="stretch",
                  on_click=_go, args=(REPORTS_PAGE,))
        c2.button("📄 Just explain a report", width="stretch",
                  on_click=_go, args=(UNDERSTAND_PAGE,))
        return

    latest = reports[0]  # newest first
    trends = (api("GET", f"/patients/{patient_id}/trends") or {}).get("trends", [])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📁 Reports saved", len(reports))
    m2.metric("📅 Latest report", latest["report_date"])
    m3.metric("⚠️ Outside range (latest)", latest["outside_range_count"])
    m4.metric("📈 Tests tracked", len(trends))

    st.subheader(f"Latest report: {latest['title']}")
    detail = api("GET", f"/patients/{patient_id}/reports/{latest['id']}") or {}
    labs = detail.get("lab_values", [])
    flagged = [lab for lab in labs if lab["status"] != "NORMAL"]
    if flagged:
        st.caption("These values are outside the reference range printed on the report. "
                   "Discuss them with your doctor.")
        status_table(flagged)
    elif labs:
        st.success("All values in your latest report are within the printed reference range.")
    else:
        st.info("No lab values with reference ranges were found in this report.")

    improving = [t for t in trends if len(t["points"]) >= 2]
    if improving:
        with st.expander(f"📈 How {len(improving)} test(s) changed over time"):
            for t in improving:
                first, last = t["points"][0]["value"], t["points"][-1]["value"]
                st.write(f"**{t['test']}**: {first:g} → {last:g} {t['unit']} · {t['direction']}")

    st.divider()
    st.markdown("**What would you like to do?**")
    c1, c2, c3 = st.columns(3)
    c1.button("💾 Save or compare reports", width="stretch", type="primary",
              on_click=_go, args=(REPORTS_PAGE,))
    c2.button("📄 Explain a new report", width="stretch",
              on_click=_go, args=(UNDERSTAND_PAGE,))
    c3.button("👤 My profile & timeline", width="stretch",
              on_click=_go, args=(PROFILE_PAGE,))