"""Read text from uploaded medical reports.

Everything happens in memory: uploaded files are never saved to disk.

- PDF with a text layer  -> pypdf
- Scanned PDF            -> PyMuPDF renders each page, Tesseract OCR reads it
- Photo of a report      -> Tesseract OCR
"""

import io

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pypdf import PdfReader

from backend.config import TESSERACT_CMD

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MIN_TEXT_CHARS = 30  # less than this means "probably a scanned PDF"

# "eng+mal" also reads Malayalam if the Malayalam language pack is installed.
OCR_LANG = "eng"


class ReportReadError(ValueError):
    """Raised when a file cannot be read. The message is safe to show users."""


def _ocr(image: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(image.convert("RGB"), lang=OCR_LANG)
    except pytesseract.TesseractNotFoundError as exc:
        raise ReportReadError(
            "OCR is not available. Install Tesseract and set TESSERACT_CMD in .env."
        ) from exc


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(p for p in pages if p.strip())


def _pdf_ocr(data: bytes) -> str:
    text = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for page in pdf:
            pix = page.get_pixmap(dpi=300)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            text.append(_ocr(image))
    return "\n".join(text)


def detect_type(filename: str, content_type: str | None) -> str:
    name = (filename or "").lower()
    if content_type in PDF_TYPES or name.endswith(".pdf"):
        return "pdf"
    if content_type in IMAGE_TYPES or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    return "unknown"


def extract_text(data: bytes, filename: str, content_type: str | None = None) -> str:
    """Return the report text, or raise ReportReadError."""
    if not data:
        raise ReportReadError("The uploaded file is empty.")

    kind = detect_type(filename, content_type)

    if kind == "pdf":
        try:
            text = _pdf_text(data)
            if len(text.strip()) >= MIN_TEXT_CHARS:
                return text
            text = _pdf_ocr(data)
        except ReportReadError:
            raise
        except Exception as exc:
            raise ReportReadError("This PDF could not be read. It may be damaged or password-protected.") from exc

    elif kind == "image":
        try:
            image = Image.open(io.BytesIO(data))
        except Exception as exc:
            raise ReportReadError("This image could not be opened.") from exc
        text = _ocr(image)

    else:
        raise ReportReadError("Unsupported file type. Upload a PDF, JPG, PNG or WEBP.")

    if not text.strip():
        raise ReportReadError("No readable text was found in this report.")
    return text


# Kept so older code that passes a file path still works.
def extract_text_from_pdf(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return extract_text(f.read(), file_path, "application/pdf")