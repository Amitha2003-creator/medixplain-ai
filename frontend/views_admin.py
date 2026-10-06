"""Admin pages: users, doctor-patient assignments, activity log."""

import streamlit as st

from api import api

ROLE_ICONS = {"admin": "🛡️", "doctor": "👨‍⚕️", "patient": "🧑"}


def users_page():
    st.header("🛡️ Manage Users")

    with st.expander("➕ Create an account (doctor, admin or patient)"):
        with st.form("create_user", clear_on_submit=True):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            password = st.text_input("Temporary password (at least 8 characters)",
                                     type="password")
            role = st.selectbox("Role", ["doctor", "admin", "patient"])
            if st.form_submit_button("Create account"):
                if api("POST", "/admin/users", json={
                    "name": name, "email": email, "password": password, "role": role,
                }):
                    st.success(f"{role.title()} account created. Share the password privately.")

    users = api("GET", "/admin/users") or []
    me = st.session_state.user["id"]
    for user in users:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            status = "" if user["is_active"] else " · ⛔ deactivated"
            c1.markdown(f"{ROLE_ICONS.get(user['role'], '')} **{user['name']}** "
                        f"({user['role']}){status}")
            c1.caption(f"{user['email']} · ID {user['id']}")
            if user["id"] != me:
                label = "Deactivate" if user["is_active"] else "Activate"
                if c2.button(label, key=f"toggle_{user['id']}"):
                    if api("PATCH", f"/admin/users/{user['id']}/active",
                           params={"active": "false" if user["is_active"] else "true"}):
                        st.rerun()


def assignments_page():
    st.header("🔗 Doctor–Patient Assignments")
    st.caption("A doctor can only see patients assigned to them.")

    doctors = api("GET", "/admin/users", params={"role": "doctor"}) or []
    patients = (api("GET", "/patients") or {}).get("patients", [])

    if not doctors or not patients:
        st.info("You need at least one doctor account and one patient first.")
    else:
        with st.form("assign"):
            doctor_labels = {f"{d['name']} (ID {d['id']})": d["id"]
                             for d in doctors if d["is_active"]}
            patient_labels = {f"{p['name']} (ID {p['id']})": p["id"] for p in patients}
            doctor = st.selectbox("Doctor", list(doctor_labels))
            patient = st.selectbox("Patient", list(patient_labels))
            if st.form_submit_button("Assign"):
                if api("POST", "/admin/assignments", json={
                    "doctor_id": doctor_labels[doctor], "patient_id": patient_labels[patient],
                }):
                    st.success("Assigned.")

    st.subheader("Current assignments")
    rows = api("GET", "/admin/assignments") or []
    if not rows:
        st.info("No assignments yet.")
    for row in rows:
        c1, c2 = st.columns([5, 1])
        c1.write(f"👨‍⚕️ {row['doctor_name']}  →  🧑 {row['patient_name']} "
                 f"(patient ID {row['patient_id']})")
        if c2.button("Remove", key=f"unassign_{row['id']}"):
            if api("DELETE", f"/admin/assignments/{row['id']}"):
                st.rerun()


def activity_page():
    st.header("📜 Activity Log")
    st.caption("Who did what, and when. Medical content is never stored here.")
    rows = api("GET", "/admin/activity", params={"limit": 200}) or []
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No activity yet.")


def knowledge_page():
    st.header("📚 Knowledge Base")
    st.caption("Trusted medical information the chatbot uses to explain results, "
               "with the source shown for every answer.")

    with st.container(border=True):
        st.markdown("**Starter set: MedlinePlus lab-test pages**")
        st.caption("11 public-domain pages from the U.S. National Library of Medicine "
                   "(haemoglobin, glucose, cholesterol, vitamin D, thyroid and more). "
                   "Pages already added are skipped.")
        if st.button("⬇️ Add starter set", key="kb_starter"):
            with st.spinner("Downloading and indexing pages (about a minute)..."):
                result = api("POST", "/admin/knowledge/starter")
            if result:
                st.success(f"Added {len(result['added'])} page(s), "
                           f"skipped {result['skipped']} already added.")
                for fail in result["failed"]:
                    st.warning(f"Could not add {fail['url']}: {fail['error']}")

    with st.expander("🔗 Add a MedlinePlus lab-test page by link"):
        with st.form("kb_url", clear_on_submit=True):
            url = st.text_input("Page link",
                                placeholder="https://medlineplus.gov/lab-tests/...")
            if st.form_submit_button("Add page"):
                with st.spinner("Adding page..."):
                    if api("POST", "/admin/knowledge/url", json={"url": url.strip()}):
                        st.success("Page added.")

    with st.expander("📄 Upload a document (PDF or text)"):
        st.caption("Only upload material you are allowed to reuse, from a trustworthy source.")
        with st.form("kb_upload", clear_on_submit=True):
            file = st.file_uploader("Document", type=["pdf", "txt", "md"])
            title = st.text_input("Title")
            source_name = st.text_input("Source (required)",
                                        placeholder="Example: WHO fact sheet, 2025")
            source_url = st.text_input("Source link (optional)")
            if st.form_submit_button("Upload"):
                if not file:
                    st.error("Please choose a file.")
                else:
                    with st.spinner("Indexing document..."):
                        if api("POST", "/admin/knowledge/upload",
                               files={"file": (file.name, file.getvalue(), file.type)},
                               data={"title": title, "source_name": source_name,
                                     "source_url": source_url}):
                            st.success("Document added.")

    st.subheader("Documents")
    docs = (api("GET", "/admin/knowledge") or {}).get("documents", [])
    if not docs:
        st.info("The knowledge base is empty. Add the starter set to begin.")
    for doc in docs:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            link = f" · [open]({doc['source_url']})" if doc.get("source_url") else ""
            c1.markdown(f"**{doc['title']}**")
            c1.caption(f"{doc['source_name']} · {doc['chunk_count']} chunks{link}")
            if c2.button("🗑️", key=f"kb_del_{doc['id']}", help="Remove this document"):
                if api("DELETE", f"/admin/knowledge/{doc['id']}"):
                    st.rerun()