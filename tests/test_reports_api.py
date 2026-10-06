"""Saved reports, comparison, trends and the PDF summary (features 10-14, 33).

Gemini is replaced by small fake functions, so these tests need no API key
and no internet.
"""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

import backend.main as main
import backend.routes_reports as routes_reports
from tests.helpers import (
    JULY_LINES,
    SEPTEMBER_LINES,
    admin_headers,
    create_doctor,
    register_patient,
    save_report,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def fake_ai(monkeypatch):
    """Replace every Gemini call used by the report routes."""
    monkeypatch.setattr(routes_reports, "analyze_lab_report",
                        lambda text, language="en", labs=None: "## Summary\nFake explanation.")
    monkeypatch.setattr(routes_reports, "generate_doctor_questions",
                        lambda text, language="en", labs=None: "1. Is my glucose a concern?")
    monkeypatch.setattr(routes_reports, "suggest_specialist",
                        lambda text, language="en", labs=None: "**Specialist:** Endocrinologist")


def pdf_text(data: bytes) -> str:
    """All text in the PDF, with line breaks turned into single spaces."""
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def test_save_report_reads_lab_values(client):
    headers, pid = register_patient(client)
    r = save_report(client, headers, pid)
    assert r.status_code == 201, r.text
    body = r.json()
    statuses = {lab["test"]: lab["status"] for lab in body["lab_values"]}
    assert statuses == {"Glucose": "HIGH", "Calcium": "NORMAL", "Vitamin D": "LOW"}
    assert body["report"]["values_count"] == 3
    assert body["report"]["outside_range_count"] == 2
    assert body["summary"] is None  # explain was off


def test_save_report_with_ai_explanation(client, fake_ai):
    headers, pid = register_patient(client)
    r = save_report(client, headers, pid, explain=True)
    assert r.status_code == 201, r.text
    assert "Fake explanation" in r.json()["summary"]


def test_save_report_adds_timeline_event(client):
    headers, pid = register_patient(client)
    save_report(client, headers, pid, title="Sugar test")
    events = client.get(f"/patients/{pid}/timeline", headers=headers).json()["timeline"]
    assert any("Sugar test" in e["title"] for e in events)


@pytest.mark.parametrize("bad_date", ["2999-01-01", "18-08-2026", "yesterday"])
def test_save_report_rejects_bad_dates(client, bad_date):
    headers, pid = register_patient(client)
    assert save_report(client, headers, pid, report_date=bad_date).status_code == 400


def test_save_report_rejects_unsupported_file(client):
    headers, pid = register_patient(client)
    r = client.post(f"/patients/{pid}/reports", headers=headers,
                    files={"file": ("notes.txt", b"Glucose 145 mg/dL 70 - 100", "text/plain")},
                    data={"report_date": "2026-07-01"})
    assert r.status_code == 400


def test_report_routes_need_login(client):
    _, pid = register_patient(client)
    assert client.get(f"/patients/{pid}/reports").status_code == 401


# ---------------------------------------------------------------------------
# Privacy: who can see which reports
# ---------------------------------------------------------------------------

def test_patient_cannot_touch_another_patients_reports(client):
    a_headers, a_id = register_patient(client, "A")
    b_headers, b_id = register_patient(client, "B")
    report_id = save_report(client, b_headers, b_id).json()["report"]["id"]

    assert client.get(f"/patients/{b_id}/reports", headers=a_headers).status_code == 404
    assert client.get(f"/patients/{b_id}/reports/{report_id}",
                      headers=a_headers).status_code == 404
    assert save_report(client, a_headers, b_id).status_code == 404
    assert client.delete(f"/patients/{b_id}/reports/{report_id}",
                         headers=a_headers).status_code == 404
    # Using your own patient id with someone else's report id does not work either.
    assert client.get(f"/patients/{a_id}/reports/{report_id}",
                      headers=a_headers).status_code == 404


def test_doctor_sees_reports_only_after_assignment(client):
    admin = admin_headers(client)
    doctor_id, doctor = create_doctor(client, admin)
    headers, pid = register_patient(client)
    save_report(client, headers, pid)

    assert client.get(f"/patients/{pid}/reports", headers=doctor).status_code == 404
    client.post("/admin/assignments", headers=admin,
                json={"doctor_id": doctor_id, "patient_id": pid})
    r = client.get(f"/patients/{pid}/reports", headers=doctor)
    assert r.status_code == 200
    assert len(r.json()["reports"]) == 1


# ---------------------------------------------------------------------------
# List, view, delete
# ---------------------------------------------------------------------------

def test_list_view_and_delete_report(client):
    headers, pid = register_patient(client)
    report_id = save_report(client, headers, pid, title="To delete").json()["report"]["id"]

    listed = client.get(f"/patients/{pid}/reports", headers=headers).json()["reports"]
    assert [r["id"] for r in listed] == [report_id]

    detail = client.get(f"/patients/{pid}/reports/{report_id}", headers=headers).json()
    assert detail["title"] == "To delete"
    assert len(detail["lab_values"]) == 3

    assert client.delete(f"/patients/{pid}/reports/{report_id}",
                         headers=headers).status_code == 200
    assert client.get(f"/patients/{pid}/reports", headers=headers).json()["reports"] == []
    assert client.get(f"/patients/{pid}/trends", headers=headers).json()["trends"] == []


def test_admin_deleting_patient_removes_reports(client):
    admin = admin_headers(client)
    headers, pid = register_patient(client)
    save_report(client, headers, pid)
    assert client.delete(f"/patients/{pid}", headers=admin).status_code == 200
    assert client.get(f"/patients/{pid}/reports", headers=admin).status_code == 404


# ---------------------------------------------------------------------------
# Compare and trends
# ---------------------------------------------------------------------------

def test_compare_two_reports(client):
    headers, pid = register_patient(client)
    july = save_report(client, headers, pid, JULY_LINES, "2026-07-01").json()["report"]["id"]
    sept = save_report(client, headers, pid, SEPTEMBER_LINES, "2026-09-01").json()["report"]["id"]

    # Passed the "wrong" way round on purpose: the API always compares older -> newer.
    r = client.get(f"/patients/{pid}/compare", headers=headers,
                   params={"old_report_id": sept, "new_report_id": july})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_report"]["report_date"] == "2026-07-01"
    rows = {row["test"]: row for row in body["comparison"]}
    assert rows["Glucose"]["direction"] == "decreased"
    assert rows["Vitamin D"]["direction"] == "increased"
    assert rows["Calcium"]["direction"] == "stable"
    assert body["counts"]["now within range"] == 2


def test_compare_same_report_is_rejected(client):
    headers, pid = register_patient(client)
    rid = save_report(client, headers, pid).json()["report"]["id"]
    r = client.get(f"/patients/{pid}/compare", headers=headers,
                   params={"old_report_id": rid, "new_report_id": rid})
    assert r.status_code == 400


def test_trends_follow_values_over_time(client):
    headers, pid = register_patient(client)
    save_report(client, headers, pid, JULY_LINES, "2026-07-01")
    save_report(client, headers, pid, SEPTEMBER_LINES, "2026-09-01")

    trends = {t["test"]: t for t in
              client.get(f"/patients/{pid}/trends", headers=headers).json()["trends"]}
    glucose = trends["Glucose"]
    assert [p["value"] for p in glucose["points"]] == [145.0, 98.0]
    assert [p["date"] for p in glucose["points"]] == ["2026-07-01", "2026-09-01"]
    assert glucose["latest_status"] == "NORMAL"
    assert glucose["direction"] == "decreased"


# ---------------------------------------------------------------------------
# Downloadable PDF summary (feature 33)
# ---------------------------------------------------------------------------

def test_summary_pdf_without_ai(client):
    headers, pid = register_patient(client, "Pdf Patient")
    rid = save_report(client, headers, pid, title="Pdf test").json()["report"]["id"]
    r = client.get(f"/patients/{pid}/reports/{rid}/summary.pdf", headers=headers,
                   params={"include_ai": "false"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    text = pdf_text(r.content)
    assert "Pdf Patient" in text and "Glucose" in text and "Vitamin D" in text
    assert "not a diagnosis" in text


def test_summary_pdf_with_ai_sections(client, fake_ai):
    headers, pid = register_patient(client)
    rid = save_report(client, headers, pid).json()["report"]["id"]
    r = client.get(f"/patients/{pid}/reports/{rid}/summary.pdf", headers=headers)
    assert r.status_code == 200
    text = pdf_text(r.content)
    assert "Questions to ask your doctor" in text
    assert "Endocrinologist" in text


def test_summary_pdf_replaces_malayalam_summary(client, monkeypatch):
    monkeypatch.setattr(routes_reports, "analyze_lab_report",
                        lambda text, language="en", labs=None: "ഇത് ഒരു പരീക്ഷണമാണ്")
    headers, pid = register_patient(client)
    rid = save_report(client, headers, pid, language="ml",
                      explain=True).json()["report"]["id"]
    r = client.get(f"/patients/{pid}/reports/{rid}/summary.pdf", headers=headers,
                   params={"include_ai": "false"})
    assert r.status_code == 200
    assert "in Malayalam" in pdf_text(r.content)


def test_summary_pdf_is_private(client):
    other_headers, _ = register_patient(client)
    owner_headers, owner_id = register_patient(client)
    rid = save_report(client, owner_headers, owner_id).json()["report"]["id"]
    r = client.get(f"/patients/{owner_id}/reports/{rid}/summary.pdf", headers=other_headers,
                   params={"include_ai": "false"})
    assert r.status_code == 404