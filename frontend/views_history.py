"""Saved reports, report comparison and health trends for one patient."""

import base64
import json
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from api import api, api_file, file_tuple
from ui import empty_state, status_table

SERIES_COLOR = "#2a78d6"   # one series per chart, so one colour
RANGE_COLOR = "#8a8986"    # neutral grey for the reference range
STATUS_ICON = {"HIGH": "🔺 High", "LOW": "🔻 Low", "NORMAL": "✅ Normal"}
DIRECTION_ICON = {
    "increased": "⬆️ increased",
    "decreased": "⬇️ decreased",
    "stable": "➡️ stable",
    "new test": "🆕 new test",
    "not in newer report": "— not in newer report",
}
STATUS_CHANGE_ICON = {
    "newly outside range": "⚠️ newly outside range",
    "still outside range": "🔁 still outside range",
    "now within range": "✅ now within range",
    "within range": "within range",
}


def history_section(patient_id: int, language_code: str):
    """Tabs for saving, viewing, comparing and charting a patient's reports."""
    tab_save, tab_list, tab_ask, tab_compare, tab_trends = st.tabs(
        ["💾 Save a report", "📁 Saved reports", "💬 Ask My Report", "🔀 Compare", "📈 Trends"]
    )
    with tab_save:
        _save_tab(patient_id, language_code)
    with tab_list:
        _reports_tab(patient_id)
    with tab_ask:
        _ask_tab(patient_id, language_code)
    with tab_compare:
        _compare_tab(patient_id)
    with tab_trends:
        _trends_tab(patient_id)


def my_history_page(patient_id: int | None, language_code: str):
    """Patient's own page."""
    st.header("📊 My Reports & Trends")
    if not patient_id:
        st.error("No patient profile is linked to this account. Please contact the clinic.")
        return
    history_section(patient_id, language_code)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

MAX_FILES_AT_ONCE = 10


def _save_tab(patient_id: int, language_code: str):
    st.caption("Choose one or more reports. Only the lab values and the explanation "
               "are saved. The files themselves are not stored.")

    # Changing this number gives the uploader a fresh, empty state after saving.
    counter_key = f"upload_round_{patient_id}"
    st.session_state.setdefault(counter_key, 0)
    round_no = st.session_state[counter_key]

    uploaded_files = st.file_uploader(
        "Medical reports (PDF or photo)",
        type=["pdf", "jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"reports_{patient_id}_{round_no}",
    )

    # Results of the last save are shown until new files are chosen.
    results_key = f"save_results_{patient_id}"
    if uploaded_files:
        st.session_state.pop(results_key, None)
    elif st.session_state.get(results_key):
        _show_save_results(st.session_state[results_key])

    if not uploaded_files:
        return
    if len(uploaded_files) > MAX_FILES_AT_ONCE:
        st.error(f"Please choose at most {MAX_FILES_AT_ONCE} reports at a time.")
        return

    st.markdown("**Set the date printed on each report:**")
    details = []
    for i, f in enumerate(uploaded_files):
        with st.container(border=True):
            st.markdown(f"📄 **{f.name}**")
            c1, c2 = st.columns(2)
            report_date = c1.date_input(
                "Date on the report", value=date.today(), max_value=date.today(),
                format="DD/MM/YYYY", key=f"date_{patient_id}_{round_no}_{i}",
            )
            title = c2.text_input(
                "Title (optional)", placeholder="Example: Blood test",
                key=f"title_{patient_id}_{round_no}_{i}",
            )
            details.append((f, report_date, title))

    explain = st.checkbox("Also save an AI explanation for each report (takes longer)",
                          value=False, key=f"explain_{patient_id}_{round_no}")

    label = "💾 Save report" if len(details) == 1 else f"💾 Save all {len(details)} reports"
    if not st.button(label, type="primary", key=f"save_btn_{patient_id}_{round_no}"):
        return

    results = []
    progress = st.progress(0.0, text="Saving reports...")
    for n, (f, report_date, title) in enumerate(details, start=1):
        progress.progress((n - 1) / len(details), text=f"Saving {f.name} ({n} of {len(details)})...")
        st.session_state.pop("last_api_error", None)
        result = api(
            "POST", f"/patients/{patient_id}/reports",
            files={"file": file_tuple(f)},
            data={"report_date": str(report_date), "title": title,
                  "language": language_code, "explain": "true" if explain else "false"},
        )
        results.append({"file": f.name, "result": result,
                        "error": None if result else st.session_state.get("last_api_error")})
    progress.empty()

    # Clear the uploader, keep the results, and refresh so the other tabs update.
    st.session_state[results_key] = results
    st.session_state[counter_key] += 1
    st.rerun()


def _show_save_results(results: list[dict]):
    saved = [r for r in results if r["result"]]
    failed = [r for r in results if not r["result"]]
    if saved:
        st.success(f"Saved {len(saved)} of {len(results)} report(s).")
    for r in failed:
        st.error(f"❌ {r['file']} could not be saved: {r.get('error') or 'unknown error'}")
    for r in saved:
        res = r["result"]
        with st.expander(f"📄 {res['report']['report_date']} · {res['report']['title']} "
                         f"({res['report']['values_count']} lab values)"):
            if res.get("warning"):
                st.warning(res["warning"])
            _lab_table(res.get("lab_values", []))
            if res.get("summary"):
                st.markdown("**🧠 AI explanation**")
                st.markdown(res["summary"])


def _lab_table(labs: list[dict]):
    status_table(labs)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def _get_reports(patient_id: int) -> list[dict]:
    return (api("GET", f"/patients/{patient_id}/reports") or {}).get("reports", [])


def _label(report: dict) -> str:
    # The report number keeps labels unique even when two reports share a date and title.
    return f"{report['report_date']} · {report['title']} (#{report['id']})"


def _reports_tab(patient_id: int):
    reports = _get_reports(patient_id)
    if not reports:
           empty_state("📂", "No saved reports yet",
                       "Open the 'Save a report' tab and upload one or more lab reports.")
           return

    st.dataframe(
        [{"Date": r["report_date"], "Title": r["title"], "Lab values": r["values_count"],
          "Outside range": r["outside_range_count"]} for r in reports],
        hide_index=True, width="stretch",
    )

    labels = {_label(r): r["id"] for r in reports}
    choice = st.selectbox("Open a report", ["Select"] + list(labels),
                          key=f"open_report_{patient_id}")
    if choice == "Select":
        return

    report_id = labels[choice]
    report = api("GET", f"/patients/{patient_id}/reports/{report_id}")
    if not report:
        return
    _lab_table(report["lab_values"])
    if report.get("summary"):
        with st.expander("🧠 AI explanation", expanded=True):
            st.markdown(report["summary"])

    _download_section(patient_id, report_id, report)

    with st.expander("🗑️ Delete this report"):
        confirm = st.checkbox("Yes, delete this report and its values",
                              key=f"confirm_del_{report_id}")
        if st.button("Delete", key=f"del_report_{report_id}", disabled=not confirm):
            if api("DELETE", f"/patients/{patient_id}/reports/{report_id}"):
                st.success("Report deleted.")
                st.rerun()


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "—"
    return f"{value:g}"


def _compare_tab(patient_id: int):
    reports = _get_reports(patient_id)
    if len(reports) < 2:
        st.info("Save at least two reports to compare them.")
        return

    labels = {_label(r): r["id"] for r in reports}  # newest first
    names = list(labels)
    c1, c2 = st.columns(2)
    older = c1.selectbox("Older report", names, index=min(1, len(names) - 1),
                         key=f"cmp_old_{patient_id}")
    newer = c2.selectbox("Newer report", names, index=0, key=f"cmp_new_{patient_id}")
    if older == newer:
        st.warning("Choose two different reports.")
        return

    result = api("GET", f"/patients/{patient_id}/compare",
                 params={"old_report_id": labels[older], "new_report_id": labels[newer]})
    if not result:
        return

    counts = result.get("counts", {})
    m1, m2, m3 = st.columns(3)
    m1.metric("⚠️ Newly outside range", counts.get("newly outside range", 0))
    m2.metric("🔁 Still outside range", counts.get("still outside range", 0))
    m3.metric("✅ Now within range", counts.get("now within range", 0))

    old_date = result["old_report"]["report_date"]
    new_date = result["new_report"]["report_date"]
    rows = []
    for row in result["comparison"]:
        change = ""
        if row["change"] is not None:
            change = f"{row['change']:+g}"
            if row["change_percent"] is not None:
                change += f" ({row['change_percent']:+g}%)"
        rows.append({
            "Test": row["test"],
            old_date: _fmt(row["old_value"]),
            new_date: _fmt(row["new_value"]),
            "Unit": row["unit"],
            "Change": change,
            "Direction": DIRECTION_ICON.get(row["direction"], row["direction"] or ""),
            "Range status": STATUS_CHANGE_ICON.get(row["status_change"], ""),
        })
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Changes are calculated from the numbers in the reports. "
               "Discuss what they mean with your doctor.")


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def _trend_chart(points: list[dict], unit: str):
    df = pd.DataFrame(points)
    df["date"] = pd.to_datetime(df["date"])
    df["status_label"] = df["status"].map(STATUS_ICON).fillna(df["status"])

    x = alt.X("date:T", title="Report date", axis=alt.Axis(format="%d %b %Y", grid=False))
    y = alt.Y("value:Q", title=unit or "Value", scale=alt.Scale(zero=False),
              axis=alt.Axis(gridOpacity=0.3))
    tooltip = [alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
               alt.Tooltip("value:Q", title=f"Value ({unit})" if unit else "Value"),
               alt.Tooltip("status_label:N", title="Status")]

    layers = []
    latest = points[-1]
    for bound in ("low", "high"):
        if latest.get(bound) is not None:
            layers.append(
                alt.Chart(pd.DataFrame({"v": [latest[bound]], "label": [bound]}))
                .mark_rule(color=RANGE_COLOR, strokeDash=[4, 4], strokeWidth=1)
                .encode(y="v:Q", tooltip=[alt.Tooltip("v:Q", title=f"Reference {bound}")])
            )
    base = alt.Chart(df)
    layers.append(base.mark_line(color=SERIES_COLOR, strokeWidth=2).encode(x=x, y=y))
    layers.append(
        base.mark_point(filled=True, size=90, color=SERIES_COLOR, opacity=1,
                        stroke="white", strokeWidth=2)
        .encode(x=x, y=y, tooltip=tooltip)
    )
    st.altair_chart(alt.layer(*layers).properties(height=260), width="stretch")


def _trends_tab(patient_id: int):
    trends = (api("GET", f"/patients/{patient_id}/trends") or {}).get("trends", [])
    if not trends:
        st.info("Save reports to see how lab values change over time.")
        return

    st.caption("Dashed grey lines show the reference range printed on the latest report.")
    for trend in trends:
        with st.container(border=True):
            c1, c2 = st.columns([3, 2])
            c1.markdown(f"**{trend['test']}**")
            c1.caption(f"Reference range: {trend['reference_range'] or 'not printed'}")
            c2.write(f"Latest: **{trend['latest_value']} {trend['unit']}** · "
                     f"{STATUS_ICON.get(trend['latest_status'], trend['latest_status'])}")
            c2.caption(f"Trend: {DIRECTION_ICON.get(trend['direction'], trend['direction'])}")

            if len(trend["points"]) >= 2:
                _trend_chart(trend["points"], trend["unit"])
            else:
                st.caption("Only one result so far. Save another report to see a trend.")

            with st.expander("Show values as a table"):
                st.dataframe(
                    [{"Date": p["date"], "Value": p["value"],
                      "Status": STATUS_ICON.get(p["status"], p["status"])}
                     for p in trend["points"]],
                    hide_index=True, width="stretch",
                )


# ---------------------------------------------------------------------------
# Ask My Report (chatbot)
# ---------------------------------------------------------------------------

EXAMPLE_QUESTIONS = [
    "Which values are outside the normal range?",
    "What does vitamin D do in the body?",
    "What questions should I ask my doctor?",
]


def _show_sources(sources: list[dict]):
    if not sources:
        return
    parts = []
    for s in sources:
        name = f"[{s['title']}]({s['source_url']})" if s.get("source_url") else s["title"]
        parts.append(f"[{s['number']}] {name} · {s['source_name']}")
    st.caption("**Sources:** " + "  \n".join(parts))


def _ask_tab(patient_id: int, language_code: str):
    reports = _get_reports(patient_id)
    if not reports:
        st.info("Save a report first, then ask questions about it here.")
        return

    labels = {_label(r): r["id"] for r in reports}  # newest first
    choice = st.selectbox("Report to ask about", list(labels), key=f"ask_report_{patient_id}")
    report_id = labels[choice]

    # One conversation per patient and report.
    chat_key = f"chat_{patient_id}_{report_id}"
    history = st.session_state.setdefault(chat_key, [])

    for turn in history:
        with st.chat_message("user" if turn["role"] == "user" else "assistant"):
            st.markdown(turn["content"])
            if turn["role"] == "assistant":
                _play_answer(turn)
                _show_sources(turn.get("sources", []))
                if turn.get("note"):
                    st.caption(f"⚠️ {turn['note']}")

    if history:
        st.caption("ℹ️ Educational information only, not a diagnosis. Knowledge from "
                   "MedlinePlus is courtesy of the U.S. National Library of Medicine.")
    else:
        st.caption("Try: " + " · ".join(f"“{q}”" for q in EXAMPLE_QUESTIONS))

    with st.form(f"ask_form_{chat_key}", clear_on_submit=True):
        question = st.text_input("Your question", max_chars=1000,
                                 placeholder="Example: What does my haemoglobin result mean?")
        c1, c2 = st.columns([1, 1])
        asked = c1.form_submit_button("Ask", type="primary")
        cleared = c2.form_submit_button("Clear conversation")

    if cleared:
        st.session_state[chat_key] = []
        st.rerun()

    _voice_section(patient_id, report_id, chat_key, history)

    if not asked or not question.strip():
        return

    with st.spinner("Looking at your report..."):
        result = api("POST", f"/patients/{patient_id}/chat", json={
            "question": question.strip(),
            "report_id": report_id,
            "language": language_code,
            "history": [{"role": t["role"], "content": t["content"]} for t in history[-6:]],
        })
    if not result:
        return

    history.append({"role": "user", "content": question.strip()})
    history.append({"role": "assistant", "content": result["answer"],
                    "sources": result.get("sources", []), "note": result.get("note")})
    st.rerun()


# ---------------------------------------------------------------------------
# Downloadable PDF summary
# ---------------------------------------------------------------------------

def _download_section(patient_id: int, report_id: int, report: dict):
    with st.container(border=True):
        st.markdown("**📄 Download a summary PDF**")
        st.caption("Lab values, the explanation, questions for your doctor and specialist "
                   "guidance, ready to print or take to an appointment. The PDF is in English.")
        include_ai = st.checkbox("Include questions and specialist guidance (takes longer)",
                                 value=True, key=f"pdf_ai_{report_id}")
        pdf_key = f"pdf_{report_id}_{include_ai}"
        if st.button("Prepare PDF", key=f"pdf_btn_{report_id}"):
            with st.spinner("Preparing the PDF..."):
                pdf = api_file(f"/patients/{patient_id}/reports/{report_id}/summary.pdf",
                               params={"include_ai": "true" if include_ai else "false"})
            if pdf:
                st.session_state[pdf_key] = pdf
        if st.session_state.get(pdf_key):
            st.download_button(
                "⬇️ Download PDF", data=st.session_state[pdf_key],
                file_name=f"medixplain-summary-{report['report_date']}-{report_id}.pdf",
                mime="application/pdf", key=f"pdf_dl_{report_id}",
            )


# ---------------------------------------------------------------------------
# Voice assistant
# ---------------------------------------------------------------------------

def _voice_section(patient_id: int, report_id: int, chat_key: str, history: list):
    with st.expander("🎤 Ask by voice (English or Malayalam)"):
        st.caption("Press the microphone, ask your question, then press it again to stop. "
                   "The answer is given in the language you speak, and read aloud.")
        round_key = f"voice_round_{chat_key}"
        st.session_state.setdefault(round_key, 0)
        recording = st.audio_input("Record your question",
                                   key=f"voice_{chat_key}_{st.session_state[round_key]}")
        if recording is None:
            return
        if not st.button("Send voice question", type="primary", key=f"voice_send_{chat_key}"):
            return

        with st.spinner("Listening and preparing the answer..."):
            result = api(
                "POST", f"/patients/{patient_id}/voice-chat",
                files={"audio": ("question.wav", recording.getvalue(),
                                 recording.type or "audio/wav")},
                data={"report_id": str(report_id),
                      "history": json.dumps([{"role": t["role"], "content": t["content"]}
                                             for t in history[-6:]])},
            )
        if not result:
            return

        history.append({"role": "user", "content": f"🎤 {result['transcript']}"})
        history.append({"role": "assistant", "content": result["answer"],
                        "sources": result.get("sources", []), "note": result.get("note"),
                        "audio": result.get("audio_base64"), "autoplay": True})
        st.session_state[round_key] += 1  # clear the recorder
        st.rerun()


def _play_answer(turn: dict):
    """Show an audio player for spoken answers. Plays automatically the first time."""
    if not turn.get("audio"):
        return
    audio = base64.b64decode(turn["audio"])
    autoplay = turn.pop("autoplay", False)
    st.audio(audio, format="audio/mpeg", autoplay=autoplay)