"""MediXplain AI - Streamlit frontend.

Run from the ai-medixplain folder (with the backend already running):
    .\\mediai\\Scripts\\python.exe -m streamlit run frontend/app.py
"""

import streamlit as st

st.set_page_config(page_title="MediXplain AI", page_icon="🩺", layout="wide")

from embedded_backend import start_if_needed  # noqa: E402

start_if_needed()  # online hosting only; does nothing on your laptop

from api import api, logout  # noqa: E402
from views_admin import (  # noqa: E402
    activity_page,
    assignments_page,
    knowledge_page,
    users_page,
)
from ui import example_box, feature_card, hero, inject_css, status_table, step  # noqa: E402
from views_history import my_history_page  # noqa: E402
from views_home import home_page  # noqa: E402
from views_patients import my_profile_page, patients_page  # noqa: E402
from views_reports import image_page, report_page  # noqa: E402
from views_upload import upload_explain_page  # noqa: E402

LANGUAGES = {"English 🇬🇧": "en", "മലയാളം 🇮🇳": "ml"}
DISCLAIMER = ("⚠️ MediXplain AI is an educational tool. It does not diagnose, prescribe, "
              "or replace professional medical advice.")


# =========================================================
# LOGIN / REGISTER
# =========================================================

UPLOAD_PAGE = "📤 Upload & Explain"

# A fictional example, shown on the front page so visitors see what they will get.
EXAMPLE_LABS = [
    {"test": "Glucose (fasting)", "value_text": "145", "unit": "mg/dL",
     "reference_range": "70 - 100", "status": "HIGH"},
    {"test": "Vitamin D", "value_text": "52", "unit": "nmol/L",
     "reference_range": "75 - 250", "status": "LOW"},
    {"test": "Hemoglobin", "value_text": "13.8", "unit": "g/dL",
     "reference_range": "12 - 15.5", "status": "NORMAL"},
]
EXAMPLE_TEXT = (
    "<b>Glucose</b> is the sugar in your blood. Your result, 145, is above the range printed "
    "on the report (70 to 100). One high reading can happen for many reasons, so your doctor "
    "may suggest a repeat test.<br><br>"
    "<b>Vitamin D</b> helps keep your bones strong. Your result, 52, is below the printed "
    "range. Ask your doctor whether you need more sunlight, food changes or a supplement.<br><br>"
    "<b>Hemoglobin</b> carries oxygen in your blood. Your result is within the normal range. 👍"
)


def _start_session(result: dict):
    st.session_state.token = result["access_token"]
    me = api("GET", "/me")
    if me:
        st.session_state.user = me
        if me["role"] == "patient":
            st.session_state["nav"] = UPLOAD_PAGE  # first thing after login: upload a report
        st.rerun()
    else:
        logout()


def _login_box():
    with st.container(border=True):
        st.markdown("#### 👋 Get started")
        tab_register, tab_login = st.tabs(["📝 Create free account", "🔑 Log in"])

        with tab_register:
            with st.form("register"):
                name = st.text_input("Full name")
                email = st.text_input("Email", key="reg_email")
                password = st.text_input("Password (at least 8 characters)", type="password",
                                         key="reg_password")
                confirm = st.text_input("Confirm password", type="password")
                if st.form_submit_button("Create account & upload a report", type="primary",
                                         width="stretch"):
                    if password != confirm:
                        st.error("The passwords do not match.")
                    else:
                        result = api("POST", "/register", auth=False,
                                     json={"name": name, "email": email, "password": password})
                        if result:
                            _start_session(result)
            st.caption("Doctor and admin accounts are created by the clinic admin.")

        with tab_login:
            with st.form("login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log in", type="primary", width="stretch"):
                    result = api("POST", "/login", auth=False,
                                 json={"email": email, "password": password})
                    if result:
                        _start_session(result)


def login_screen():
    hero("Understand your medical reports in simple language",
         "Upload a lab report and MediXplain explains it in plain English or Malayalam: "
         "what each test means, which values are outside the normal range, and what to ask "
         "your doctor.",
         badge="🩺 MediXplain AI · Educational health assistant")

    left, right = st.columns([3, 2], gap="large")
    with right:
        _login_box()
    with left:
        st.markdown("### How it works")
        step(1, "Create a free account", "Takes 30 seconds. Only your name and email.")
        step(2, "Upload your report", "A PDF or a clear photo of your lab report.")
        step(3, "Get a simple explanation", "Each test explained in plain words, with "
             "high and low values marked.")
        step(4, "Ask, compare and track", "Ask questions by text or voice, compare reports "
             "and see your trends over time.")

    st.markdown("### 👀 See an example")
    st.caption("This is a made-up report, to show what your explanation will look like.")
    ex1, ex2 = st.columns(2, gap="large")
    with ex1:
        st.markdown("**🧪 Lab values**")
        status_table(EXAMPLE_LABS)
    with ex2:
        st.markdown("**🧠 Simple explanation**")
        example_box(EXAMPLE_TEXT)

    st.markdown("### ✨ What you get")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        feature_card("🧪", "Lab values", "High, low and normal values checked against your report.", "blue")
    with c2:
        feature_card("🧠", "Simple explanations", "Medical words turned into plain language.", "teal")
    with c3:
        feature_card("📈", "Trends", "Compare reports and see how values change.", "violet")
    with c4:
        feature_card("🎤", "Voice and Malayalam", "Ask questions by voice in English or Malayalam.", "amber")

    st.markdown("### ❓ Common questions")
    with st.expander("Is my report safe?"):
        st.write("Your report file is read in memory and never stored. Only the lab values and "
                 "the explanation are saved to your account, and only you (and a doctor you are "
                 "assigned to) can see them.")
    with st.expander("Does MediXplain diagnose diseases?"):
        st.write("No. It explains what your report says in simple words. Only a doctor can "
                 "diagnose or prescribe. Always discuss your results with your doctor.")
    with st.expander("Where do the answers come from?"):
        st.write("Explanations are written by Google's Gemini AI using the values on your report. "
                 "Answers in Ask My Report cite MedlinePlus from the U.S. National Library of "
                 "Medicine.")
    with st.expander("Which reports can I upload?"):
        st.write("Lab reports such as blood tests, as a PDF or a photo (JPG, PNG or WEBP). "
                 "Values are checked against the reference range printed on the report.")

    st.caption(DISCLAIMER)


# =========================================================
# MAIN APP (after login)
# =========================================================

PAGES = {
    "patient": {
        "📤 Upload & Explain": None,  # needs the user, handled below
        "🏠 Home": None,  # needs the user, handled below
        "📄 Understand a Report": report_page,
        "🩻 Medical Images": image_page,
        "📊 My Reports & Trends": None,  # needs patient_id, handled below
        "👤 My Profile & Timeline": None,  # needs patient_id, handled below
    },
    "doctor": {
        "👥 My Patients": None,
        "📄 Understand a Report": report_page,
        "🩻 Medical Images": image_page,
    },
    "admin": {
        "🛡️ Users": users_page,
        "🔗 Assignments": assignments_page,
        "👥 Patients": None,
        "📚 Knowledge Base": knowledge_page,
        "📜 Activity Log": activity_page,
        "📄 Understand a Report": report_page,
        "🩻 Medical Images": image_page,
    },
}


def main_app():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown('<div class="mx-brand">🩺 MediXplain AI</div>', unsafe_allow_html=True)
        st.write(f"**{user['name']}**")
        st.caption(f"{user['email']} · {role.title()}")
        page = st.radio("Menu", list(PAGES[role]), label_visibility="collapsed", key="nav")
        language_code = LANGUAGES[st.selectbox("🌐 Language", list(LANGUAGES))]
        st.divider()
        if st.button("🚪 Log out", width="stretch"):
            logout()
            st.rerun()

    st.caption(DISCLAIMER)

    if page == UPLOAD_PAGE:
        upload_explain_page(user, language_code)
    elif page == "🏠 Home":
        home_page(user)
    elif page == "👤 My Profile & Timeline":
        my_profile_page(user.get("patient_id"))
    elif page == "📊 My Reports & Trends":
        my_history_page(user.get("patient_id"), language_code)
    elif page in ("👥 My Patients", "👥 Patients"):
        patients_page(role, language_code)
    elif page in ("📄 Understand a Report", "🩻 Medical Images"):
        PAGES[role][page](language_code)
    else:
        PAGES[role][page]()


inject_css()

if st.session_state.get("token") and st.session_state.get("user"):
    main_app()
else:
    login_screen()