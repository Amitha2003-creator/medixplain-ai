"""Knowledge base management (admin) and the Ask My Report chatbot."""

import base64
import json
import re
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlmodel import select

from backend.auth import AdminUser, CurrentUser, SessionDep, get_patient_for_user, log_activity
from backend.config import MAX_UPLOAD_MB, SUPPORTED_LANGUAGES
from backend.gemini_service import GeminiError, answer_report_question, transcribe_audio
from backend.knowledge import (
    MEDLINEPLUS,
    STARTER_PAGES,
    KnowledgeError,
    add_document,
    delete_document,
    fetch_trusted_page,
    search,
)
from backend.models import (
    ChatRequest,
    ChatTurn,
    KnowledgeDocument,
    KnowledgeURL,
    LabResult,
    SavedReport,
)
from backend.report_processor import ReportReadError, extract_text
from backend.voice import text_to_speech

router = APIRouter(tags=["Knowledge & Chat"])

MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
DISCLAIMER = (
    "MediXplain AI is for education only. It does not diagnose or replace a doctor. "
    "Please discuss your results with a qualified healthcare professional."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(session, user, title: str, source_name: str, source_url: str | None,
           text: str) -> KnowledgeDocument:
    """Save the document row, then its chunks. Removes the row again if embedding fails."""
    doc = KnowledgeDocument(title=title[:200], source_name=source_name[:200],
                            source_url=source_url, added_by=user.id)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    try:
        doc.chunk_count = add_document(doc.id, doc.title, doc.source_name, source_url, text)
    except (KnowledgeError, GeminiError) as exc:
        session.delete(doc)
        session.commit()
        raise HTTPException(400 if isinstance(exc, KnowledgeError) else 502, str(exc)) from exc
    session.add(doc)
    session.commit()
    session.refresh(doc)
    log_activity(session, user, "add_knowledge", f"document #{doc.id}")
    return doc


def _url_exists(session, url: str) -> bool:
    return session.exec(
        select(KnowledgeDocument).where(KnowledgeDocument.source_url == url)
    ).first() is not None


# ---------------------------------------------------------------------------
# Admin: manage the knowledge base
# ---------------------------------------------------------------------------

@router.get("/admin/knowledge")
def list_knowledge(admin: AdminUser, session: SessionDep):
    docs = session.exec(select(KnowledgeDocument).order_by(KnowledgeDocument.title)).all()
    return {"documents": docs}


@router.post("/admin/knowledge/url", status_code=201)
def add_from_url(data: KnowledgeURL, admin: AdminUser, session: SessionDep):
    url = data.url.strip()
    if _url_exists(session, url):
        raise HTTPException(409, "This page is already in the knowledge base.")
    try:
        title, text = fetch_trusted_page(url)
    except KnowledgeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"document": _store(session, admin, title, MEDLINEPLUS, url, text)}


@router.post("/admin/knowledge/starter")
def add_starter_set(admin: AdminUser, session: SessionDep):
    """Add the MedlinePlus starter pages that are not in the knowledge base yet."""
    added, skipped, failed = [], [], []
    for url in STARTER_PAGES:
        if _url_exists(session, url):
            skipped.append(url)
            continue
        try:
            title, text = fetch_trusted_page(url)
            doc = _store(session, admin, title, MEDLINEPLUS, url, text)
            added.append(doc.title)
        except (KnowledgeError, HTTPException) as exc:
            failed.append({"url": url, "error": getattr(exc, "detail", str(exc))})
    return {"added": added, "skipped": len(skipped), "failed": failed}


@router.post("/admin/knowledge/upload", status_code=201)
async def upload_document(
    admin: AdminUser,
    session: SessionDep,
    file: UploadFile = File(...),
    title: Annotated[str, Form()] = "",
    source_name: Annotated[str, Form()] = "",
    source_url: Annotated[str, Form()] = "",
):
    if not source_name.strip():
        raise HTTPException(400, "Please enter where this document comes from (the source).")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")

    name = (file.filename or "").lower()
    if name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="ignore")
    else:
        try:
            text = extract_text(data, file.filename or "", file.content_type)
        except ReportReadError as exc:
            raise HTTPException(400, str(exc)) from exc

    doc = _store(session, admin, title.strip() or file.filename or "Document",
                 source_name.strip(), source_url.strip() or None, text)
    return {"document": doc}


@router.delete("/admin/knowledge/{doc_id}")
def remove_document(doc_id: int, admin: AdminUser, session: SessionDep):
    doc = session.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    try:
        delete_document(doc_id)
    except Exception as exc:  # the vector store may be unavailable; still remove the row
        log_activity(session, admin, "knowledge_delete_warning", str(exc)[:200])
    session.delete(doc)
    session.commit()
    log_activity(session, admin, "delete_knowledge", f"document #{doc_id}")
    return {"message": "Document removed", "doc_id": doc_id}


# ---------------------------------------------------------------------------
# Ask My Report
# ---------------------------------------------------------------------------

def _report_context(session, patient_id: int, report_id: int | None) -> tuple[str, SavedReport | None]:
    """Build the text the chatbot uses as the patient's report."""
    if report_id is not None:
        report = session.get(SavedReport, report_id)
        if not report or report.patient_id != patient_id:
            raise HTTPException(404, "Report not found")
    else:
        report = session.exec(
            select(SavedReport).where(SavedReport.patient_id == patient_id)
            .order_by(SavedReport.report_date.desc(), SavedReport.id.desc())
        ).first()
    if not report:
        return "The patient has no saved reports yet.", None

    labs = session.exec(select(LabResult).where(LabResult.report_id == report.id)
                        .order_by(LabResult.id)).all()
    lines = [f"Report: {report.title} (date {report.report_date})", "Lab values:"]
    lines += [f"- {lab.test}: {lab.value_text} {lab.unit} (reference {lab.reference_range}) "
              f"-> {lab.status}" for lab in labs] or ["- none found"]
    if report.summary:
        lines += ["", "Earlier explanation of this report:", report.summary[:4000]]
    return "\n".join(lines), report


def cited_sources(answer: str, sources: list[dict]) -> list[dict]:
    """Return only the sources the answer actually cites, e.g. [1] or [2], once each."""
    used, seen = [], set()
    for number in re.findall(r"\[(\d+)\]", answer):
        index = int(number) - 1
        if 0 <= index < len(sources):
            src = sources[index]
            key = src.get("doc_id") or src["title"]
            if key not in seen:
                seen.add(key)
                used.append({"number": index + 1, "title": src["title"],
                             "source_name": src["source_name"], "source_url": src["source_url"]})
    return used


def _answer(session, user, patient_id: int, question: str, report_id: int | None,
            history: list[dict], language: str) -> dict:
    """Shared by typed and spoken questions."""
    get_patient_for_user(session, user, patient_id)
    language = language if language in SUPPORTED_LANGUAGES else "en"
    context, report = _report_context(session, patient_id, report_id)

    note = None
    try:
        sources = search(question, k=4)
    except Exception:  # knowledge base unavailable: answer from the report only
        sources = []
        note = "The knowledge base could not be searched, so this answer uses the report only."

    try:
        answer = answer_report_question(question, context, sources, history, language)
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {
        "answer": answer,
        "sources": cited_sources(answer, sources),
        "report": ({"id": report.id, "title": report.title, "report_date": report.report_date}
                   if report else None),
        "note": note,
        "disclaimer": DISCLAIMER,
    }


@router.post("/patients/{patient_id}/chat")
def ask_my_report(patient_id: int, data: ChatRequest, user: CurrentUser, session: SessionDep):
    result = _answer(session, user, patient_id, data.question, data.report_id,
                     [turn.model_dump() for turn in data.history], data.language)
    log_activity(session, user, "chat", f"patient #{patient_id}")
    return result


# ---------------------------------------------------------------------------
# Voice assistant
# ---------------------------------------------------------------------------

AUDIO_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/webm", "audio/ogg",
               "audio/mpeg", "audio/mp3", "audio/mp4", "audio/aac", "audio/flac"}
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # about 1-2 minutes of speech


@router.post("/patients/{patient_id}/voice-chat")
async def voice_chat(
    patient_id: int,
    user: CurrentUser,
    session: SessionDep,
    audio: UploadFile = File(...),
    report_id: Annotated[str, Form()] = "",
    history: Annotated[str, Form()] = "[]",
):
    """Spoken question -> transcript -> answer (in the language spoken) -> spoken answer."""
    get_patient_for_user(session, user, patient_id)

    mime = (audio.content_type or "").split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(400, "Unsupported audio format. Please record again.")
    data = await audio.read()
    if not data:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "The recording is too long. Please keep questions short.")

    try:
        turns = [ChatTurn.model_validate(t).model_dump() for t in json.loads(history or "[]")][-6:]
    except (ValueError, TypeError):
        turns = []
    rid = int(report_id) if report_id.strip().isdigit() else None

    try:
        transcript, language = transcribe_audio(data, "audio/wav" if "wav" in mime else mime)
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not transcript:
        raise HTTPException(400, "No clear question was heard. Please try again.")
    transcript = transcript[:1000]

    result = _answer(session, user, patient_id, transcript, rid, turns, language)

    audio_b64 = None
    try:
        audio_b64 = base64.b64encode(text_to_speech(result["answer"], language)).decode("ascii")
    except Exception as exc:  # still return the written answer if speech fails
        extra = f"The spoken answer could not be created ({exc})."
        result["note"] = f"{result['note']} {extra}" if result["note"] else extra

    log_activity(session, user, "voice_chat", f"patient #{patient_id}, {language}")
    return {**result, "transcript": transcript, "language": language,
            "audio_base64": audio_b64, "audio_mime": "audio/mpeg"}