from sqlmodel import Session, SQLModel, create_engine

from backend.config import DATABASE_URL

# The database file always lives in the project folder, no matter
# which folder you start uvicorn from.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    # expire_on_commit=False keeps loaded values usable after a commit,
    # so objects can still be returned to the frontend.
    with Session(engine, expire_on_commit=False) as session:
        yield session