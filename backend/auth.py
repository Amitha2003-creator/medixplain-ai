"""Login, roles and access rules.

Who can see a patient's data:
- admin   -> every patient
- doctor  -> only patients linked to them (DoctorPatientLink)
- patient -> only their own profile
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import func
from sqlmodel import Session, select

from backend.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ADMIN_EMAIL,
    ADMIN_NAME,
    ADMIN_PASSWORD,
    ALGORITHM,
    SECRET_KEY,
)
from backend.database import engine, get_session
from backend.models import ActivityLog, DoctorPatientLink, PatientProfile, User

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SessionDep = Annotated[Session, Depends(get_session)]


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user.id), "role": user.role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def find_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(func.lower(User.email) == email.lower())).first()


def authenticate(session: Session, email: str, password: str) -> User:
    user = find_user_by_email(session, email)
    if not user or not password_hash.verify(password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated. Contact the clinic admin.")
    return user


# ---------------------------------------------------------------------------
# Current user and roles
# ---------------------------------------------------------------------------

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> User:
    error = HTTPException(401, "Please log in again.", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (InvalidTokenError, TypeError, ValueError):
        raise error
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """Use as a dependency: Depends(require_roles("admin"))."""
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission to do this.")
        return user
    return checker


AdminUser = Annotated[User, Depends(require_roles("admin"))]
StaffUser = Annotated[User, Depends(require_roles("doctor", "admin"))]


# ---------------------------------------------------------------------------
# Patient access
# ---------------------------------------------------------------------------

def can_access_patient(session: Session, user: User, patient: PatientProfile) -> bool:
    if user.role == "admin":
        return True
    if user.role == "patient":
        return patient.user_id == user.id
    if user.role == "doctor":
        link = session.exec(
            select(DoctorPatientLink).where(
                DoctorPatientLink.doctor_id == user.id,
                DoctorPatientLink.patient_id == patient.id,
            )
        ).first()
        return link is not None
    return False


def get_patient_for_user(session: Session, user: User, patient_id: int) -> PatientProfile:
    """Return the patient, or 404 if missing or not allowed.

    404 (not 403) so users cannot discover which patient IDs exist.
    """
    patient = session.get(PatientProfile, patient_id)
    if not patient or not can_access_patient(session, user, patient):
        raise HTTPException(404, "Patient not found")
    return patient


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

def log_activity(session: Session, user: User | None, action: str, detail: str = "") -> None:
    """Record an action. Never store report text or medical values here."""
    session.add(ActivityLog(user_id=user.id if user else None, action=action, detail=detail[:300]))
    session.commit()


# ---------------------------------------------------------------------------
# First admin
# ---------------------------------------------------------------------------

def ensure_admin_exists() -> None:
    """Create the first admin from .env if there is no admin yet."""
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        return
    with Session(engine) as session:
        if session.exec(select(User).where(User.role == "admin")).first():
            return
        existing = find_user_by_email(session, ADMIN_EMAIL)
        if existing:
            existing.role = "admin"
            existing.is_active = True
            session.add(existing)
        else:
            session.add(User(
                name=ADMIN_NAME,
                email=ADMIN_EMAIL.lower(),
                hashed_password=hash_password(ADMIN_PASSWORD),
                role="admin",
            ))
        session.commit()