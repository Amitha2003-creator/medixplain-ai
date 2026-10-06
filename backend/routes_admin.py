"""Admin-only: manage users, doctor-patient assignments, and view activity."""

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from backend.auth import AdminUser, SessionDep, hash_password, log_activity
from backend.models import (
    ActivityLog,
    AdminUserCreate,
    AssignmentCreate,
    DoctorPatientLink,
    PatientProfile,
    User,
    UserPublic,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserPublic])
def list_users(admin: AdminUser, session: SessionDep, role: str | None = None):
    query = select(User).order_by(User.role, User.name)
    if role:
        query = query.where(User.role == role)
    return session.exec(query).all()


@router.post("/users", status_code=201, response_model=UserPublic)
def create_user(data: AdminUserCreate, admin: AdminUser, session: SessionDep):
    user = User(
        name=data.name.strip(),
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An account with this email already exists.")
    session.refresh(user)

    if user.role == "patient":
        session.add(PatientProfile(name=user.name, user_id=user.id, created_by=admin.id))
        session.commit()

    log_activity(session, admin, "create_user", f"{user.role} #{user.id}")
    return user


@router.patch("/users/{user_id}/active", response_model=UserPublic)
def set_user_active(user_id: int, active: bool, admin: AdminUser, session: SessionDep):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id and not active:
        raise HTTPException(400, "You cannot deactivate your own account.")
    user.is_active = active
    session.add(user)
    session.commit()
    session.refresh(user)
    log_activity(session, admin, "activate_user" if active else "deactivate_user", f"user #{user.id}")
    return user


# ---------------------------------------------------------------------------
# Doctor-patient assignments
# ---------------------------------------------------------------------------

@router.get("/assignments")
def list_assignments(admin: AdminUser, session: SessionDep):
    rows = session.exec(
        select(DoctorPatientLink, User, PatientProfile)
        .join(User, User.id == DoctorPatientLink.doctor_id)
        .join(PatientProfile, PatientProfile.id == DoctorPatientLink.patient_id)
        .order_by(User.name, PatientProfile.name)
    ).all()
    return [
        {
            "id": link.id,
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "patient_id": patient.id,
            "patient_name": patient.name,
            "assigned_at": link.assigned_at,
        }
        for link, doctor, patient in rows
    ]


@router.post("/assignments", status_code=201)
def create_assignment(data: AssignmentCreate, admin: AdminUser, session: SessionDep):
    doctor = session.get(User, data.doctor_id)
    if not doctor or doctor.role != "doctor":
        raise HTTPException(400, "That user is not a doctor.")
    if not session.get(PatientProfile, data.patient_id):
        raise HTTPException(404, "Patient not found")

    link = DoctorPatientLink(doctor_id=data.doctor_id, patient_id=data.patient_id)
    session.add(link)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "This doctor is already assigned to this patient.")
    log_activity(session, admin, "assign", f"doctor #{data.doctor_id} -> patient #{data.patient_id}")
    return {"message": "Doctor assigned to patient"}


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, admin: AdminUser, session: SessionDep):
    link = session.get(DoctorPatientLink, assignment_id)
    if not link:
        raise HTTPException(404, "Assignment not found")
    detail = f"doctor #{link.doctor_id} -x- patient #{link.patient_id}"
    session.delete(link)
    session.commit()
    log_activity(session, admin, "unassign", detail)
    return {"message": "Assignment removed"}


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

@router.get("/activity")
def activity(admin: AdminUser, session: SessionDep, limit: int = 100):
    rows = session.exec(
        select(ActivityLog, User)
        .join(User, User.id == ActivityLog.user_id, isouter=True)
        .order_by(ActivityLog.id.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    return [
        {
            "time": log.created_at,
            "user": user.name if user else "-",
            "role": user.role if user else "-",
            "action": log.action,
            "detail": log.detail,
        }
        for log, user in rows
    ]