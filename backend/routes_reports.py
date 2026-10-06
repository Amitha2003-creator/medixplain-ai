"""Saved reports, report comparison and health trends for a patient.

Only extracted lab values and the AI summary are stored. The uploaded file
itself is read in memory and never saved.
"""

from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from sqlmodel import select

from backend.auth import CurrentUser, SessionDep, get_patient_for_user, log_activity
from backend.config import MAX_UPLOAD_MB, SUPPORTED_LANGUAGES
from backend.gemini_service import (
    GeminiError,
    analyze_lab_report,
    generate_doctor_questions,
    suggest_specialist,
)
from backend.lab_analyzer import analyze_lab_values
from backend.models import LabResult, PatientTimeline, SavedReport
from backend.report_compare import compare_reports, normalize_test_name, trend_direction
from backend.report_processor import ReportReadError, extract_text
from backend.summary_pdf import build_summary_pdf

router = APIRouter(prefix="/patients", tags=["Reports & Trends"])

MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _report_summary(report: SavedReport, labs: list[LabResult]) -> dict:
    outside = [lab for lab in labs if lab.status != "NORMAL"]
    return {
        "id": report.id,
        "report_date": report.report_date,
        "title": report.title,
        "values_count": len(labs),
        "outside_range_count": len(outside),
        "has_summary": bool(report.summary),
        "created_at": report.created_at,
    }


def _get_report(session, patient_id: int, report_id: int) -> SavedReport:
    report = session.get(SavedReport, report_id)
    if not report or report.patient_id != patient_id:
        raise HTTPException(404, "Report not found")
    return report


def _labs_for(session, report_id: int) -> list[LabResult]:
    return session.exec(
        select(LabResult).where(LabResult.report_id == report_id).order_by(LabResult.id)
    ).all()


# ---------------------------------------------------------------------------
# Save a report
# ---------------------------------------------------------------------------

@router.post("/{patient_id}/reports", status_code=201)
async def save_report(
    patient_id: int,
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
    report_date: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "en",
    explain: Annotated[bool, Form()] = True,
):
    get_patient_for_user(session, user, patient_id)

    try:
        report_day = date.fromisoformat(report_date) if report_date else date.today()
    except ValueError:
        raise HTTPException(400, "Report date must look like 2026-08-18.")
    if report_day > date.today():
        raise HTTPException(400, "Report date cannot be in the future.")
    if language not in SUPPORTED_LANGUAGES:
        language = "en"

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
    try:
        text = extract_text(data, file.filename or "", file.content_type)
    except ReportReadError as exc:
        raise HTTPException(400, str(exc)) from exc

    labs = analyze_lab_values(text)

    summary, warning = None, None
    if explain:
        try:
            summary = analyze_lab_report(text, language, labs)
        except GeminiError as exc:
            warning = f"Lab values were saved, but the AI explanation failed: {exc}"
    if not labs:
        note = "No lab values with reference ranges were found in this report."
        warning = f"{warning} {note}" if warning else note

    report = SavedReport(
        patient_id=patient_id,
        report_date=report_day.isoformat(),
        title=(title.strip() or file.filename or "Medical report")[:120],
        summary=summary,
        language=language,
        created_by=user.id,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    rows = [
        LabResult(
            report_id=report.id,
            patient_id=patient_id,
            test=lab["test"],
            test_key=normalize_test_name(lab["test"]),
            value=lab["value"],
            value_text=lab["value_text"],
            unit=lab["unit"],
            reference_range=lab["reference_range"],
            low=lab["low"],
            high=lab["high"],
            status=lab["status"],
            report_date=report.report_date,
        )
        for lab in labs
    ]
    session.add_all(rows)

    outside = sum(1 for lab in labs if lab["status"] != "NORMAL")
    session.add(PatientTimeline(
        patient_id=patient_id,
        event_date=report.report_date,
        event_type="Lab test",
        title=f"Report saved: {report.title}",
        description=f"{len(labs)} lab values read, {outside} outside the reference range.",
        created_by=user.id,
    ))
    session.commit()

    log_activity(session, user, "save_report", f"patient #{patient_id}, report #{report.id}")
    return {
        "report": _report_summary(report, rows),
        "lab_values": labs,
        "summary": summary,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# List, view, delete
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/reports")
def list_reports(patient_id: int, user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    reports = session.exec(
        select(SavedReport)
        .where(SavedReport.patient_id == patient_id)
        .order_by(SavedReport.report_date.desc(), SavedReport.id.desc())
    ).all()
    return {"reports": [_report_summary(r, _labs_for(session, r.id)) for r in reports]}


@router.get("/{patient_id}/reports/{report_id}")
def get_report(patient_id: int, report_id: int, user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    report = _get_report(session, patient_id, report_id)
    labs = _labs_for(session, report_id)
    log_activity(session, user, "view_report", f"patient #{patient_id}, report #{report_id}")
    return {
        **_report_summary(report, labs),
        "summary": report.summary,
        "lab_values": [lab.model_dump(exclude={"report_id", "patient_id", "test_key"})
                       for lab in labs],
    }


@router.delete("/{patient_id}/reports/{report_id}")
def delete_report(patient_id: int, report_id: int, user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    report = _get_report(session, patient_id, report_id)
    for lab in _labs_for(session, report_id):
        session.delete(lab)
    session.delete(report)
    session.commit()
    log_activity(session, user, "delete_report", f"patient #{patient_id}, report #{report_id}")
    return {"message": "Report deleted", "report_id": report_id}


# ---------------------------------------------------------------------------
# Compare two reports
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/compare")
def compare(patient_id: int, old_report_id: int, new_report_id: int,
            user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    if old_report_id == new_report_id:
        raise HTTPException(400, "Choose two different reports.")
    old = _get_report(session, patient_id, old_report_id)
    new = _get_report(session, patient_id, new_report_id)
    if old.report_date > new.report_date:  # always compare older -> newer
        old, new = new, old

    def rows(report):
        return [lab.model_dump() for lab in _labs_for(session, report.id)]

    comparison = compare_reports(rows(old), rows(new))
    counts = defaultdict(int)
    for row in comparison:
        if row["status_change"]:
            counts[row["status_change"]] += 1
    return {
        "old_report": {"id": old.id, "title": old.title, "report_date": old.report_date},
        "new_report": {"id": new.id, "title": new.title, "report_date": new.report_date},
        "comparison": comparison,
        "counts": dict(counts),
    }


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/trends")
def trends(patient_id: int, user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    labs = session.exec(
        select(LabResult)
        .where(LabResult.patient_id == patient_id)
        .order_by(LabResult.report_date, LabResult.id)
    ).all()

    grouped: dict[str, list[LabResult]] = defaultdict(list)
    for lab in labs:
        grouped[lab.test_key].append(lab)

    result = []
    for series in grouped.values():
        latest = series[-1]
        # Only plot results in the same unit as the latest one.
        same_unit = [lab for lab in series if lab.unit.lower() == latest.unit.lower()]
        result.append({
            "test": latest.test,
            "unit": latest.unit,
            "reference_range": latest.reference_range,
            "latest_value": latest.value_text,
            "latest_status": latest.status,
            "direction": trend_direction([lab.value for lab in same_unit]),
            "points": [
                {"date": lab.report_date, "value": lab.value, "status": lab.status,
                 "low": lab.low, "high": lab.high}
                for lab in same_unit
            ],
        })
    # Tests with several results and currently outside range first.
    result.sort(key=lambda t: (t["latest_status"] == "NORMAL", -len(t["points"]), t["test"]))
    return {"patient_id": patient_id, "trends": result}



# ---------------------------------------------------------------------------
# Downloadable PDF summary
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/reports/{report_id}/summary.pdf")
def download_summary(patient_id: int, report_id: int, user: CurrentUser, session: SessionDep,
                     include_ai: bool = True):
    """PDF with lab values, the saved explanation and (optionally) AI questions and
    specialist guidance. Built in memory; nothing is stored."""
    patient = get_patient_for_user(session, user, patient_id)
    report = _get_report(session, patient_id, report_id)
    labs = _labs_for(session, report_id)

    questions = specialist = None
    if include_ai and labs:
        # The original file is not stored, so the AI works from the saved values and summary.
        context = "\n".join(
            [f"Report: {report.title} (date {report.report_date})"]
            + [f"{lab.test}: {lab.value_text} {lab.unit} (reference {lab.reference_range})"
               for lab in labs]
            + ([report.summary[:4000]] if report.summary else [])
        )
        lab_dicts = [lab.model_dump() for lab in labs]
        try:
            questions = generate_doctor_questions(context, "en", lab_dicts)
            specialist = suggest_specialist(context, "en", lab_dicts)
        except GeminiError as exc:
            raise HTTPException(502, f"Could not prepare the AI sections: {exc}") from exc

    summary = report.summary
    if summary and report.language != "en":
        # The PDF library cannot draw Malayalam script correctly.
        summary = ("The saved explanation for this report is in Malayalam, which this PDF "
                   "cannot display. You can read it in the app under Saved reports.")
    pdf = build_summary_pdf(patient.name, report, labs, summary, questions, specialist)
    log_activity(session, user, "download_summary", f"patient #{patient_id}, report #{report_id}")

    filename = f"medixplain-summary-{report.report_date}-{report_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})