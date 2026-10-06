"""Talking to the backend. Every request carries the logged-in user's token."""

import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("MEDIXPLAIN_API_URL", "http://127.0.0.1:8000")
TIMEOUT = 180  # seconds; Gemini and OCR can be slow on long reports


def logout():
    # Clear everything, so the next person on this browser sees none of it.
    st.session_state.clear()


def api(method: str, path: str, auth: bool = True, **kwargs):
    """Call the backend. Returns the JSON body, or None after showing an error."""
    headers = kwargs.pop("headers", {})
    if auth and st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"

    try:
        response = requests.request(
            method, f"{BACKEND_URL}{path}", headers=headers, timeout=TIMEOUT, **kwargs
        )
    except requests.exceptions.ConnectionError:
        st.session_state["last_api_error"] = "Cannot connect to the backend."
        st.error("❌ Cannot connect to the backend. Is uvicorn running?")
        return None
    except requests.exceptions.Timeout:
        st.session_state["last_api_error"] = "The request took too long."
        st.error("❌ The request took too long. Please try again.")
        return None

    if response.ok:
        return response.json()

    # Session expired: send the user back to the login screen.
    if response.status_code == 401 and auth and st.session_state.get("token"):
        logout()
        st.warning("Your session has expired. Please log in again.")
        st.rerun()

    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    if isinstance(detail, list):  # validation errors from FastAPI
        detail = "; ".join(d.get("msg", str(d)) for d in detail)
    st.session_state["last_api_error"] = str(detail)
    st.error(f"❌ {detail}")
    return None


def api_file(path: str, **kwargs) -> bytes | None:
    """Download a file (for example a PDF) from the backend. Returns bytes, or None."""
    headers = {"Authorization": f"Bearer {st.session_state.token}"} \
        if st.session_state.get("token") else {}
    try:
        response = requests.get(f"{BACKEND_URL}{path}", headers=headers,
                                timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException:
        st.error("❌ Cannot connect to the backend. Is uvicorn running?")
        return None
    if response.ok:
        return response.content
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    st.error(f"❌ {detail}")
    return None


def file_tuple(uploaded):
    return (uploaded.name, uploaded.getvalue(), uploaded.type)


def show_disclaimer(result: dict):
    if result and result.get("disclaimer"):
        st.caption(f"ℹ️ {result['disclaimer']}")