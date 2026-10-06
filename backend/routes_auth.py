"""Register, log in, and "who am I"."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from backend.auth import (
    CurrentUser,
    SessionDep,
    authenticate,
    create_access_token,
    hash_password,
    log_activity,
)
from backend.models import PatientProfile, User, UserCreate, UserLogin

router = APIRouter(tags=["Authentication"])


def _login_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }


@router.post("/register", status_code=201)
def register(data: UserCreate, session: SessionDep):
    """Public sign-up. Creates a patient account and its patient profile."""
    user = User(
        name=data.name.strip(),
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        role="patient",
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An account with this email already exists.")
    session.refresh(user)

    session.add(PatientProfile(name=user.name, user_id=user.id, created_by=user.id))
    session.commit()
    log_activity(session, user, "register", "patient account created")
    return _login_response(user)


@router.post("/login")
def login(data: UserLogin, session: SessionDep):
    user = authenticate(session, data.email, data.password)
    log_activity(session, user, "login")
    return _login_response(user)


@router.post("/token", include_in_schema=False)
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    """Same as /login, in the form the /docs "Authorize" button uses."""
    user = authenticate(session, form.username, form.password)
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.get("/me")
def me(user: CurrentUser, session: SessionDep):
    patient_id = None
    if user.role == "patient":
        profile = session.exec(
            select(PatientProfile).where(PatientProfile.user_id == user.id)
        ).first()
        patient_id = profile.id if profile else None
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "patient_id": patient_id,
    }