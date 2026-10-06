"""Patient profile and timeline pages."""

from datetime import date

import streamlit as st

from api import api
from views_history import history_section

GENDERS = ["Select", "Male", "Female", "Other"]
BLOOD_GROUPS = ["Select", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
EVENT_TYPES = ["Lab test", "Imaging", "Consultation", "Medication change", "Other"]


def _choice(options: list[str], value: str | None) -> int:
    return options.index(value) if value in options else 0


def _profile_form(key: str, patient: dict | None = None) -> dict | None:
    """Show a profile form. Returns the entered data when submitted, else None."""
    p = patient or {}
    with st.form(key, clear_on_submit=patient is None):
        name = st.text_input("Full name", value=p.get("name", ""))
        dob_value = date.fromisoformat(p["date_of_birth"]) if p.get("date_of_birth") else None
        dob = st.date_input("Date of birth", value=dob_value, min_value=date(1900, 1, 1),
                            max_value=date.today(), format="DD/MM/YYYY")
        c1, c2 = st.columns(2)
        gender = c1.selectbox("Gender", GENDERS, index=_choice(GENDERS, p.get("gender")))
        blood = c2.selectbox("Blood group", BLOOD_GROUPS,
                             index=_choice(BLOOD_GROUPS, p.get("blood_group")))
        allergies = st.text_input("Allergies", value=p.get("allergies") or "",
                                  placeholder="Example: None / Penicillin")
        conditions = st.text_area("Existing medical conditions",
                                  value=p.get("existing_conditions") or "")
        medications = st.text_area("Current medications",
                                   value=p.get("current_medications") or "")
        submitted = st.form_submit_button("💾 Save" if patient else "➕ Create patient")

    if not submitted:
        return None
    if not name.strip():
        st.error("Please enter the name.")
        return None
    return {
        "name": name.strip(),
        "date_of_birth": str(dob) if dob else None,
        "gender": None if gender == "Select" else gender,
        "blood_group": None if blood == "Select" else blood,
        "allergies": allergies or None,
        "existing_conditions": conditions or None,
        "current_medications": medications or None,
    }


def _timeline(patient_id: int, can_delete: bool):
    st.subheader("📅 Health Timeline")

    with st.expander("➕ Add an event"):
        with st.form(f"add_event_{patient_id}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            event_date = c1.date_input("Date", value=date.today(), format="DD/MM/YYYY")
            event_type = c2.selectbox("Type", EVENT_TYPES)
            title = st.text_input("Title", placeholder="Example: Blood test")
            description = st.text_area("Notes (optional)")
            if st.form_submit_button("Add event"):
                if not title.strip():
                    st.error("Please enter a title.")
                elif api("POST", f"/patients/{patient_id}/timeline", json={
                    "event_date": str(event_date), "event_type": event_type,
                    "title": title.strip(), "description": description or None,
                }):
                    st.success("Event added.")

    result = api("GET", f"/patients/{patient_id}/timeline")
    events = (result or {}).get("timeline", [])
    if not events:
        st.info("No events yet.")
    for event in reversed(events):  # newest first
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**📌 {event['title']}**")
            c1.caption(f"{event['event_date']} · {event['event_type']}")
            if event.get("description"):
                c1.write(event["description"])
            if can_delete and c2.button("🗑️", key=f"del_event_{event['id']}",
                                        help="Delete this event"):
                if api("DELETE", f"/patients/{patient_id}/timeline/{event['id']}"):
                    st.rerun()


def my_profile_page(patient_id: int | None):
    """For patients: their own profile and timeline."""
    st.header("👤 My Health Profile")
    if not patient_id:
        st.error("No patient profile is linked to this account. Please contact the clinic.")
        return

    patient = api("GET", f"/patients/{patient_id}")
    if not patient:
        return
    data = _profile_form("my_profile", patient)
    if data and api("PUT", f"/patients/{patient_id}", json=data):
        st.success("Profile saved.")
    st.divider()
    _timeline(patient_id, can_delete=False)


def patients_page(role: str, language_code: str = "en"):
    """For doctors (assigned patients) and admins (all patients)."""
    st.header("👥 Patients" if role == "admin" else "👥 My Patients")

    with st.expander("➕ Register a new patient"):
        data = _profile_form("new_patient")
        if data:
            result = api("POST", "/patients", json=data)
            if result:
                st.success(f"Patient created (ID {result['patient']['id']}).")

    result = api("GET", "/patients")
    patients = (result or {}).get("patients", [])
    if not patients:
        st.info("No patients yet." if role == "admin"
                else "No patients are assigned to you yet.")
        return

    st.dataframe(
        [{"ID": p["id"], "Name": p["name"], "Date of birth": p.get("date_of_birth"),
          "Gender": p.get("gender"), "Blood group": p.get("blood_group")}
         for p in patients],
        hide_index=True, width="stretch",
    )

    labels = {f"{p['name']} (ID {p['id']})": p["id"] for p in patients}
    choice = st.selectbox("Open a patient", ["Select"] + list(labels))
    if choice == "Select":
        return

    patient_id = labels[choice]
    patient = api("GET", f"/patients/{patient_id}")
    if not patient:
        return

    st.divider()
    st.subheader(f"👤 {patient['name']}")
    data = _profile_form(f"edit_patient_{patient_id}", patient)
    if data and api("PUT", f"/patients/{patient_id}", json=data):
        st.success("Profile saved.")

    if role == "admin":
        with st.expander("⚠️ Delete this patient"):
            st.warning("This permanently deletes the profile and its timeline.")
            if st.button("Delete patient", key=f"delete_patient_{patient_id}"):
                if api("DELETE", f"/patients/{patient_id}"):
                    st.success("Patient deleted.")
                    st.rerun()

        st.divider()
    st.subheader("📊 Reports & Trends")
    history_section(patient_id, language_code)

    st.divider()
    _timeline(patient_id, can_delete=True)