"""Patient profiles and timelines, with access checks on every request."""

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from backend.auth import (
    AdminUser,
    CurrentUser,
    SessionDep,
    StaffUser,
    get_patient_for_user,
    log_activity,
)
from backend.models import (
    DoctorPatientLink,
    LabResult,
    PatientCreate,
    PatientProfile,
    PatientTimeline,
    PatientUpdate,
    SavedReport,
    TimelineCreate,
    _today,
)

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("")
def list_patients(user: CurrentUser, session: SessionDep):
    """Admin: everyone. Doctor: assigned patients. Patient: only themselves."""
    query = select(PatientProfile).order_by(PatientProfile.name)
    if user.role == "doctor":
        query = query.join(
            DoctorPatientLink, DoctorPatientLink.patient_id == PatientProfile.id
        ).where(DoctorPatientLink.doctor_id == user.id)
    elif user.role == "patient":
        query = query.where(PatientProfile.user_id == user.id)
    return {"patients": session.exec(query).all()}


@router.post("", status_code=201)
def create_patient(data: PatientCreate, user: StaffUser, session: SessionDep):
    """Doctors and admins register clinic patients. A doctor is assigned automatically."""
    duplicate = session.exec(
        select(PatientProfile).where(
            PatientProfile.name == data.name,
            PatientProfile.date_of_birth == data.date_of_birth,
        )
    ).first()
    if duplicate:
        raise HTTPException(409, "A patient with the same name and date of birth already exists.")

    patient = PatientProfile.model_validate(data, update={"created_by": user.id})
    session.add(patient)
    session.commit()
    session.refresh(patient)

    if user.role == "doctor":
        session.add(DoctorPatientLink(doctor_id=user.id, patient_id=patient.id))
        session.commit()

    log_activity(session, user, "create_patient", f"patient #{patient.id}")
    return {"message": "Patient profile created successfully", "patient": patient}


@router.get("/{patient_id}")
def get_patient(patient_id: int, user: CurrentUser, session: SessionDep):
    patient = get_patient_for_user(session, user, patient_id)
    log_activity(session, user, "view_patient", f"patient #{patient_id}")
    return patient


@router.put("/{patient_id}")
def update_patient(patient_id: int, data: PatientUpdate, user: CurrentUser, session: SessionDep):
    patient = get_patient_for_user(session, user, patient_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return patient
    patient.sqlmodel_update(changes)
    patient.updated_at = _today()
    session.add(patient)
    session.commit()
    session.refresh(patient)
    log_activity(session, user, "update_patient", f"patient #{patient_id}")
    return patient


@router.delete("/{patient_id}")
def delete_patient(patient_id: int, admin: AdminUser, session: SessionDep):
    patient = session.get(PatientProfile, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    # Remove everything linked to the patient so no orphan records remain.
    for model in (LabResult, SavedReport, PatientTimeline, DoctorPatientLink):
        for row in session.exec(select(model).where(model.patient_id == patient_id)).all():
            session.delete(row)
    session.delete(patient)
    session.commit()
    log_activity(session, admin, "delete_patient", f"patient #{patient_id}")
    return {"message": "Patient deleted successfully", "patient_id": patient_id}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/timeline")
def get_timeline(patient_id: int, user: CurrentUser, session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    events = session.exec(
        select(PatientTimeline)
        .where(PatientTimeline.patient_id == patient_id)
        .order_by(PatientTimeline.event_date)
    ).all()
    return {"patient_id": patient_id, "timeline": events}


@router.post("/{patient_id}/timeline", status_code=201)
def add_timeline_event(patient_id: int, event: TimelineCreate, user: CurrentUser,
                       session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    db_event = PatientTimeline.model_validate(
        event, update={"patient_id": patient_id, "created_by": user.id}
    )
    session.add(db_event)
    session.commit()
    session.refresh(db_event)
    log_activity(session, user, "add_timeline", f"patient #{patient_id}")
    return {"message": "Timeline event created successfully", "timeline": db_event}


@router.delete("/{patient_id}/timeline/{timeline_id}")
def delete_timeline_event(patient_id: int, timeline_id: int, user: StaffUser,
                          session: SessionDep):
    get_patient_for_user(session, user, patient_id)
    event = session.get(PatientTimeline, timeline_id)
    if not event or event.patient_id != patient_id:
        raise HTTPException(404, "Timeline event not found")
    session.delete(event)
    session.commit()
    log_activity(session, user, "delete_timeline", f"patient #{patient_id}")
    return {"message": "Timeline event deleted successfully", "timeline_id": timeline_id}