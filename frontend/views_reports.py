"""Report, image, and combined analysis pages."""

import streamlit as st

from api import api, file_tuple, show_disclaimer

OPTIONS = {
    "analysis": ("🧠 Analyze Report", "/analyze-report", "analysis"),
    "lab": ("🧪 Lab Values", None, None),
    "terms": ("📚 Medical Terms", "/simplify-terms", "simplified_terms"),
    "questions": ("🩺 Doctor Questions", "/doctor-questions", "questions"),
    "specialist": ("👨‍⚕️ Suggested Specialist", "/suggest-specialist", "specialist"),
    "visit_summary": ("📅 Doctor Visit Summary", "/doctor-visit-summary", "summary"),
}


def _show_lab_values(labs: list[dict]):
    if not labs:
        st.info("No lab values with a printed reference range were found.")
    for item in labs:
        badge = {"HIGH": st.error, "LOW": st.warning}.get(item["status"], st.success)
        with st.container(border=True):
            st.markdown(f"**🧪 {item['test']}**")
            st.write(f"Result: **{item['value_text']} {item['unit']}** · "
                     f"Reference range: {item['reference_range']}")
            badge(item["status"])


def report_page(language_code: str):
    st.header("📄 Understand a Medical Report")

    st.session_state.setdefault("results", {})
    st.session_state.setdefault("selected", None)
    st.session_state.setdefault("report_key", None)

    uploaded_file = st.file_uploader(
        "Choose a medical report (PDF or photo)",
        type=["pdf", "jpg", "jpeg", "png", "webp"],
        key="main_medical_report",
    )
    if not uploaded_file:
        st.info("Upload a report to start. It is read in memory and not saved.")
        return

    # Clear old results when a different file or language is chosen.
    current_key = (uploaded_file.name, uploaded_file.size, language_code)
    if st.session_state.report_key != current_key:
        st.session_state.report_key = current_key
        st.session_state.results = {}
        st.session_state.selected = None

    st.subheader("🔍 What would you like to know?")
    keys = list(OPTIONS)
    for row in (keys[:3], keys[3:]):
        cols = st.columns(3)
        for col, key in zip(cols, row):
               if col.button(OPTIONS[key][0], width="stretch", key=f"btn_{key}"):
                st.session_state.selected = key

    selected = st.session_state.selected
    if not selected:
        return

    # Fetch each result once per file/language, then reuse it.
    if selected not in st.session_state.results:
        label, path, _ = OPTIONS[selected]
        with st.spinner(f"{label}..."):
            if selected == "lab":
                upload = api("POST", "/upload-report",
                             files={"file": file_tuple(uploaded_file)})
                result = upload and api("POST", "/analyze-lab-values",
                                        json={"text": upload["text"]})
            else:
                result = api("POST", path,
                             files={"file": file_tuple(uploaded_file)},
                             data={"language": language_code})
        if result:
            st.session_state.results[selected] = result

    result = st.session_state.results.get(selected)
    if not result:
        return

    st.divider()
    label, _, field = OPTIONS[selected]
    st.header(label)
    if selected == "lab":
        _show_lab_values(result.get("lab_values", []))
    else:
        st.markdown(result.get(field) or "No result was returned.")
    show_disclaimer(result)


def image_page(language_code: str):
    st.header("🩻 Medical Image Analysis")
    st.write("Upload X-ray, MRI, CT or ultrasound images.")

    medical_images = st.file_uploader(
        "Choose medical images", type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True, key="medical_images",
    )
    if medical_images:
        cols = st.columns(min(len(medical_images), 4))
        for i, image in enumerate(medical_images):
            cols[i % len(cols)].image(image, caption=image.name)

        if st.button("🩻 Analyze Medical Images", key="analyze_medical_images"):
            with st.spinner("Analyzing medical images..."):
                result = api(
                    "POST", "/analyze-medical-image",
                    files=[("files", file_tuple(img)) for img in medical_images],
                    data={"language": language_code},
                )
            if result:
                st.subheader("🩻 AI Medical Image Analysis")
                st.markdown(result["analysis"])
                show_disclaimer(result)

    st.divider()
    st.header("📄 + 🩻 Report and Images Together")

    combined_report = st.file_uploader(
        "Medical report", type=["pdf", "jpg", "jpeg", "png", "webp"], key="combined_report"
    )
    combined_images = st.file_uploader(
        "Medical images", type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True, key="combined_images",
    )
    if combined_report and combined_images:
        if st.button("📄 + 🩻 Analyze Report & Images", key="combined_analysis"):
            files = [("report_file", file_tuple(combined_report))]
            files += [("image_files", file_tuple(img)) for img in combined_images]
            with st.spinner("Analyzing report and medical images..."):
                result = api("POST", "/analyze-report-image-combined",
                             files=files, data={"language": language_code})
            if result:
                st.subheader("🧠 MediXplain AI Analysis")
                st.markdown(result["analysis"])
                show_disclaimer(result)