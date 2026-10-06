"""Shared helpers for the API tests: accounts, logins and small fake reports."""

import io
import uuid

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "adminpass123"

# Fictional lab lines. One row per line, the layout the analyzer reads.
JULY_LINES = [
    "MediXplain Test Lab - Demo Patient (fictional)",
    "Glucose 145 mg/dL 70 - 100",
    "Calcium 9.1 mg/dL 8.4 - 10.2",
    "Vitamin D 52 nmol/L 75 - 250",
]
SEPTEMBER_LINES = [
    "MediXplain Test Lab - Demo Patient (fictional)",
    "Glucose 98 mg/dL 70 - 100",
    "Calcium 9.3 mg/dL 8.4 - 10.2",
    "Vitamin D 90 nmol/L 75 - 250",
]


def make_pdf(lines: list[str]) -> bytes:
    """Build a small text PDF in memory."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(60, y, line)
        y -= 20
    pdf.save()
    return buffer.getvalue()


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


def login(client, email: str, password: str) -> dict:
    r = client.post("/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_headers(client) -> dict:
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def register_patient(client, name: str = "Test Patient") -> tuple[dict, int]:
    """Create a patient account. Returns (headers, patient_id)."""
    r = client.post("/register", json={"name": name, "email": unique_email("patient"),
                                       "password": "password123"})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    patient_id = client.get("/me", headers=headers).json()["patient_id"]
    return headers, patient_id


def create_doctor(client, admin: dict) -> tuple[int, dict]:
    """Create a doctor account. Returns (doctor_id, headers)."""
    email = unique_email("doctor")
    r = client.post("/admin/users", headers=admin,
                    json={"name": "Dr Test", "email": email, "password": "password123",
                          "role": "doctor"})
    assert r.status_code == 201, r.text
    return r.json()["id"], login(client, email, "password123")


def save_report(client, headers: dict, patient_id: int, lines=None,
                report_date: str = "2026-07-01", title: str = "Blood test",
                language: str = "en", explain: bool = False):
    """Upload a fake PDF report. Returns the raw response."""
    pdf = make_pdf(lines or JULY_LINES)
    return client.post(
        f"/patients/{patient_id}/reports", headers=headers,
        files={"file": ("report.pdf", pdf, "application/pdf")},
        data={"report_date": report_date, "title": title, "language": language,
              "explain": "true" if explain else "false"},
    )