"""Central settings. All secrets come from the .env file, never from code."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # the ai-medixplain folder
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Leave empty on Linux/Mac. On Windows: C:\Program Files\Tesseract-OCR\tesseract.exe
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'medixplain.db'}")

# First admin account, created automatically on startup if no admin exists yet.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrator")

MAX_UPLOAD_MB = 10
# Knowledge base (RAG)
CHROMA_DIR = BASE_DIR / "data" / "chroma"
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
# Only these web pages may be added by URL. MedlinePlus "lab-tests" pages are
# public domain (U.S. National Library of Medicine). Encyclopedia (/ency/) pages
# are copyrighted, so they are deliberately not allowed.
TRUSTED_URL_PREFIXES = ("https://medlineplus.gov/lab-tests/",)
SUPPORTED_LANGUAGES = {"en": "English", "ml": "Malayalam"}

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing. Copy .env.example to .env and fill it in."
    )