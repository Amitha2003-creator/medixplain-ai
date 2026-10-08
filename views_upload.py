"""Upload & Explain: the first page a patient sees after logging in.

One upload does everything: the report is read, lab values are checked,
the AI explanation is written, and the result is saved to the patient's history.
"""

from datetime import date

import streamlit as st

from api import api, file_tuple
from ui import hero, status_counts, status_table
from views_history import _download_section

REPORTS_PAGE = "📊 My Reports & Trends"


def _go(page: str):
    st.session_state["nav"] = page


def upload_explain_page(user: dict, language_code: str):
    first_name = (user.get("name") or "there").split()[0]
    hero(f"Hi {first_name}, let's explain your report 👋",
         "Upload a lab report (PDF or photo). In about a minute you get a simple explanation, "
         "the values outside the normal range, and it is saved to your history.",
         badge="📤 Step 1 · Upload your report")

    patient_id = user.get("patient_id")
    if not patient_id:
        st.error("No patient profile is linked to this account. Please contact the clinic.")
        return

    # A new number gives the uploader a fresh, empty state after each report.
    st.session_state.setdefault("ux_round", 0)
    round_no = st.session_state["ux_round"]

    with st.container(border=True):
        uploaded = st.file_uploader(
            "Choose your medical report",
            type=["pdf", "jpg", "jpeg", "png", "webp"],
            key=f"ux_file_{round_no}",
            help="The file is read in memory and not stored. Only the lab values "
                 "and the explanation are saved.",
        )
        c1, c2 = st.columns(2)
        report_date = c1.date_input("Date printed on the report", value=date.today(),
                                    max_value=date.today(), format="DD/MM/YYYY",
                                    key=f"ux_date_{round_no}")
        title = c2.text_input("Title (optional)", placeholder="Example: Blood test",
                              key=f"ux_title_{round_no}")

        clicked = st.button("✨ Upload & explain my report", type="primary",
                            width="stretch", disabled=uploaded is None,
                            key=f"ux_go_{round_no}")

    if clicked and uploaded is not None:
        with st.status("Working on your report...", expanded=True) as status:
            st.write("📄 Reading the report...")
            st.write("🧪 Checking lab values against the printed ranges...")
            st.write("🧠 Writing a simple explanation...")
            result = api(
                "POST", f"/patients/{patient_id}/reports",
                files={"file": file_tuple(uploaded)},
                data={"report_date": str(report_date), "title": title,
                      "language": language_code, "explain": "true"},
            )
            if result:
                status.update(label="Done! Your report is explained and saved.",
                              state="complete", expanded=False)
            else:
                status.update(label="Something went wrong. Please try again.", state="error")
        if result:
            st.session_state["ux_result"] = result
            st.session_state["ux_round"] += 1  # clear the uploader for the next report
            st.rerun()

    result = st.session_state.get("ux_result")
    if result:
        _show_result(patient_id, result)
    else:
        st.info("💡 Tip: use a clear PDF or a sharp photo where the numbers and the "
                "reference ranges are easy to read.")


def _show_result(patient_id: int, result: dict):
    report = result["report"]
    labs = result.get("lab_values", [])

    st.success(f"✅ Saved: **{report['title']}** · {report['report_date']}")
    if result.get("warning"):
        st.warning(result["warning"])

    tab_explain, tab_values = st.tabs(["🧠 Simple explanation", "🧪 Lab values"])
    with tab_explain:
        if result.get("summary"):
            st.markdown(result["summary"])
        else:
            st.info("The explanation is not available right now. Your lab values were saved.")
    with tab_values:
        if labs:
            status_counts(labs)
            status_table(labs)
        else:
            st.info("No lab values with a printed reference range were found.")

    _download_section(patient_id, report["id"], report)

    st.markdown("**What next?**")
    c1, c2 = st.columns(2)
    c1.button("💬 Ask questions, compare & see trends", type="primary", width="stretch",
              on_click=_go, args=(REPORTS_PAGE,), key="ux_next_reports")
    if c2.button("📤 Explain another report", width="stretch", key="ux_next_upload"):
        st.session_state.pop("ux_result", None)
        st.rerun()

    st.caption("ℹ️ This explanation is for education only. Please discuss your results "
               "with your doctor.")