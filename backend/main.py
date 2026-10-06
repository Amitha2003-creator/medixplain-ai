"""MediXplain AI - FastAPI backend.

Run from the ai-medixplain folder:
    .\\mediai\\Scripts\\python.exe -m uvicorn backend.main:app --reload
API docs: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from backend.auth import CurrentUser, SessionDep, ensure_admin_exists, log_activity
from backend.config import MAX_UPLOAD_MB, SUPPORTED_LANGUAGES
from backend.database import create_db_and_tables
from backend.gemini_service import (
    GeminiError,
    analyze_lab_report,
    analyze_multiple_medical_images,
    analyze_report_and_images,
    generate_doctor_questions,
    generate_doctor_visit_summary,
    simplify_medical_terms,
    suggest_specialist,
)
from backend.lab_analyzer import analyze_lab_values
from backend.models import LabReportText
from backend.report_processor import ReportReadError, extract_text
from backend.routes_admin import router as admin_router
from backend.routes_auth import router as auth_router
from backend.routes_knowledge import router as knowledge_router
from backend.routes_patients import router as patients_router
from backend.routes_reports import router as reports_router

DISCLAIMER = (
    "MediXplain AI is for education only. It does not diagnose or replace a doctor. "
    "Please discuss your results with a qualified healthcare professional."
)
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    ensure_admin_exists()
    yield


app = FastAPI(
    title="MediXplain AI",
    description="AI-powered Medical Report Explanation Assistant (educational use only)",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(knowledge_router)

LanguageForm = Annotated[str, Form()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _language(code: str) -> str:
    return code if code in SUPPORTED_LANGUAGES else "en"


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, f"'{file.filename}' is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"'{file.filename}' is larger than {MAX_UPLOAD_MB} MB.")
    return data


async def _report_text(file: UploadFile) -> str:
    """Read an uploaded report in memory and return its text. Nothing is saved to disk."""
    data = await _read_upload(file)
    try:
        return extract_text(data, file.filename or "", file.content_type)
    except ReportReadError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _images(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    images = []
    for f in files:
        if f.content_type not in IMAGE_TYPES:
            raise HTTPException(400, f"'{f.filename}' is not a JPG, PNG or WEBP image.")
        images.append((await _read_upload(f), f.content_type))
    return images


def _ai(ai_function, *args, **kwargs) -> str:
    try:
        return ai_function(*args, **kwargs)
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc


# ---------------------------------------------------------------------------
# Basic
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {"message": "MediXplain AI Backend is Running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Report features (login required, any role)
# ---------------------------------------------------------------------------

@app.post("/upload-report", tags=["Reports"])
async def upload_report(user: CurrentUser, file: UploadFile = File(...)):
    text = await _report_text(file)
    return {"filename": file.filename, "text": text}


@app.post("/analyze-lab-values", tags=["Reports"])
def analyze_lab_values_endpoint(payload: LabReportText, user: CurrentUser):
    results = analyze_lab_values(payload.text)
    return {"lab_values": results, "count": len(results), "disclaimer": DISCLAIMER}


@app.post("/analyze-report", tags=["Reports"])
async def analyze_report(user: CurrentUser, session: SessionDep,
                         file: UploadFile = File(...), language: LanguageForm = "en"):
    text = await _report_text(file)
    labs = analyze_lab_values(text)
    analysis = _ai(analyze_lab_report, text, _language(language), labs)
    log_activity(session, user, "analyze_report")
    return {"analysis": analysis, "lab_values": labs, "disclaimer": DISCLAIMER}


@app.post("/simplify-terms", tags=["Reports"])
async def simplify_terms(user: CurrentUser, file: UploadFile = File(...),
                         language: LanguageForm = "en"):
    text = await _report_text(file)
    return {"simplified_terms": _ai(simplify_medical_terms, text, _language(language)),
            "disclaimer": DISCLAIMER}


@app.post("/doctor-questions", tags=["Reports"])
async def doctor_questions(user: CurrentUser, file: UploadFile = File(...),
                           language: LanguageForm = "en"):
    text = await _report_text(file)
    labs = analyze_lab_values(text)
    return {"questions": _ai(generate_doctor_questions, text, _language(language), labs),
            "disclaimer": DISCLAIMER}


@app.post("/suggest-specialist", tags=["Reports"])
async def suggest_specialist_endpoint(user: CurrentUser, file: UploadFile = File(...),
                                      language: LanguageForm = "en"):
    text = await _report_text(file)
    labs = analyze_lab_values(text)
    return {"specialist": _ai(suggest_specialist, text, _language(language), labs),
            "disclaimer": DISCLAIMER}


@app.post("/doctor-visit-summary", tags=["Reports"])
async def doctor_visit_summary(user: CurrentUser, file: UploadFile = File(...),
                               language: LanguageForm = "en"):
    text = await _report_text(file)
    labs = analyze_lab_values(text)
    return {"summary": _ai(generate_doctor_visit_summary, text, _language(language), labs),
            "disclaimer": DISCLAIMER}


@app.post("/analyze-medical-image", tags=["Reports"])
async def analyze_medical_image_endpoint(user: CurrentUser, session: SessionDep,
                                         files: list[UploadFile] = File(...),
                                         language: LanguageForm = "en"):
    images = await _images(files)
    analysis = _ai(analyze_multiple_medical_images, images, _language(language))
    log_activity(session, user, "analyze_images", f"{len(images)} image(s)")
    return {"analysis": analysis, "disclaimer": DISCLAIMER}


@app.post("/analyze-report-image-combined", tags=["Reports"])
async def analyze_report_image_combined(
    user: CurrentUser,
    session: SessionDep,
    report_file: UploadFile = File(...),
    image_files: list[UploadFile] = File(...),
    language: LanguageForm = "en",
):
    text = await _report_text(report_file)
    images = await _images(image_files)
    labs = analyze_lab_values(text)
    analysis = _ai(analyze_report_and_images, text, images, _language(language), labs)
    log_activity(session, user, "analyze_combined", f"{len(images)} image(s)")
    return {
        "report": report_file.filename,
        "images": [f.filename for f in image_files],
        "language": _language(language),
        "analysis": analysis,
        "lab_values": labs,
        "disclaimer": DISCLAIMER,
    }