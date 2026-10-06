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
from views_history import my_history_page  # noqa: E402
from views_patients import my_profile_page, patients_page  # noqa: E402
from views_reports import image_page, report_page  # noqa: E402

LANGUAGES = {"English 🇬🇧": "en", "മലയാളം 🇮🇳": "ml"}
DISCLAIMER = ("⚠️ MediXplain AI is an educational tool. It does not diagnose, prescribe, "
              "or replace professional medical advice.")


# =========================================================
# LOGIN / REGISTER
# =========================================================

def _start_session(result: dict):
    st.session_state.token = result["access_token"]
    me = api("GET", "/me")
    if me:
        st.session_state.user = me
        st.rerun()
    else:
        logout()


def login_screen():
    st.title("🩺 MediXplain AI")
    st.subheader("Understand your medical reports in simple language")
    st.caption(DISCLAIMER)

    tab_login, tab_register = st.tabs(["🔑 Log in", "📝 Create patient account"])

    with tab_login:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                result = api("POST", "/login", auth=False,
                             json={"email": email, "password": password})
                if result:
                    _start_session(result)

    with tab_register:
        st.caption("Doctor and admin accounts are created by the clinic admin.")
        with st.form("register"):
            name = st.text_input("Full name")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (at least 8 characters)", type="password",
                                     key="reg_password")
            confirm = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", type="primary"):
                if password != confirm:
                    st.error("The passwords do not match.")
                else:
                    result = api("POST", "/register", auth=False,
                                 json={"name": name, "email": email, "password": password})
                    if result:
                        _start_session(result)


# =========================================================
# MAIN APP (after login)
# =========================================================

PAGES = {
        "patient": {
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
        "📜 Activity Log": activity_page,
        "📚 Knowledge Base": knowledge_page,
        "📄 Understand a Report": report_page,
        "🩻 Medical Images": image_page,
    },
}


def main_app():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown("### 🩺 MediXplain AI")
        st.write(f"**{user['name']}**")
        st.caption(f"{user['email']} · {role.title()}")
        page = st.radio("Menu", list(PAGES[role]), label_visibility="collapsed")
        language_code = LANGUAGES[st.selectbox("🌐 Language", list(LANGUAGES))]
        st.divider()
        if st.button("🚪 Log out", width="stretch"):
            logout()
            st.rerun()

    st.caption(DISCLAIMER)

    if page == "👤 My Profile & Timeline":
        my_profile_page(user.get("patient_id"))
    elif page == "📊 My Reports & Trends":
        my_history_page(user.get("patient_id"), language_code)
    elif page in ("👥 My Patients", "👥 Patients"):
        patients_page(role, language_code)    
    elif page in ("📄 Understand a Report", "🩻 Medical Images"):
        PAGES[role][page](language_code)
    else:
        PAGES[role][page]()


if st.session_state.get("token") and st.session_state.get("user"):
    main_app()
else:
    login_screen()