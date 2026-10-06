from datetime import date, datetime, timezone
from typing import Literal

from pydantic import EmailStr
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

Role = Literal["patient", "doctor", "admin"]
ROLES = ("patient", "doctor", "admin")


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = Field(default="patient", index=True)  # patient / doctor / admin
    is_active: bool = True
    created_at: str = Field(default_factory=_now)


class UserCreate(SQLModel):
    """Public sign-up. Always creates a patient account."""
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AdminUserCreate(UserCreate):
    """Admin creates any kind of account."""
    role: Role = "doctor"


class UserLogin(SQLModel):
    email: EmailStr
    password: str


class UserPublic(SQLModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: str


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

class PatientBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    date_of_birth: str | None = None
    gender: str | None = None
    blood_group: str | None = None
    allergies: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None


class PatientProfile(PatientBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # The patient's own login account, if they have one.
    # Clinic-registered patients may have no account (user_id is empty).
    user_id: int | None = Field(default=None, foreign_key="user.id", unique=True)
    created_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: str = Field(default_factory=_today)
    updated_at: str = Field(default_factory=_today)


class PatientCreate(PatientBase):
    """What the frontend sends. id, owner and dates are set by the server."""


class PatientUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: str | None = None
    gender: str | None = None
    blood_group: str | None = None
    allergies: str | None = None
    existing_conditions: str | None = None
    current_medications: str | None = None


# ---------------------------------------------------------------------------
# Doctor <-> patient access
# ---------------------------------------------------------------------------

class DoctorPatientLink(SQLModel, table=True):
    """A doctor can only see patients linked to them here."""
    __table_args__ = (UniqueConstraint("doctor_id", "patient_id"),)

    id: int | None = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="user.id", index=True)
    patient_id: int = Field(foreign_key="patientprofile.id", index=True)
    assigned_at: str = Field(default_factory=_now)


class AssignmentCreate(SQLModel):
    doctor_id: int
    patient_id: int


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

class TimelineBase(SQLModel):
    event_date: str
    event_type: str
    title: str
    description: str | None = None


class PatientTimeline(TimelineBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patientprofile.id", index=True)
    created_by: int | None = Field(default=None, foreign_key="user.id")


class TimelineCreate(TimelineBase):
    pass


# ---------------------------------------------------------------------------
# Activity log (admin monitoring)
# ---------------------------------------------------------------------------

class ActivityLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    action: str
    detail: str = ""
    created_at: str = Field(default_factory=_now, index=True)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class LabReportText(SQLModel):
    text: str = Field(min_length=1, max_length=100_000)



# ---------------------------------------------------------------------------
# Saved reports and their lab values (Phase 3)
# The original file is never stored - only the values and the AI summary.
# ---------------------------------------------------------------------------

class SavedReport(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patientprofile.id", index=True)
    report_date: str = Field(index=True)  # date printed on the report (YYYY-MM-DD)
    title: str
    summary: str | None = None  # AI explanation, if one was requested
    language: str = "en"
    created_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: str = Field(default_factory=_now)


class LabResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="savedreport.id", index=True)
    patient_id: int = Field(foreign_key="patientprofile.id", index=True)
    test: str
    test_key: str = Field(index=True)  # normalised name used to match tests across reports
    value: float
    value_text: str
    unit: str = ""
    reference_range: str = ""
    low: float | None = None
    high: float | None = None
    status: str  # NORMAL / HIGH / LOW
    report_date: str = Field(index=True)    



# ---------------------------------------------------------------------------
# Knowledge base documents (Phase 4)
# The text chunks and their embeddings live in ChromaDB; this table keeps the list.
# ---------------------------------------------------------------------------

class KnowledgeDocument(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    source_name: str  # e.g. "MedlinePlus, National Library of Medicine"
    source_url: str | None = Field(default=None, index=True)
    chunk_count: int = 0
    added_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: str = Field(default_factory=_now)


class ChatTurn(SQLModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(SQLModel):
    question: str = Field(min_length=1, max_length=1000)
    report_id: int | None = None
    language: str = "en"
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


class KnowledgeURL(SQLModel):
    url: str = Field(min_length=10, max_length=500)    