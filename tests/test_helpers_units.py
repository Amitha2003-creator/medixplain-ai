"""Small building blocks: speech cleaning, PDF builder, knowledge chunks, citations,
and file reading. No API key or internet needed."""

import io
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from backend.knowledge import chunk_text, is_trusted_url
from backend.report_processor import ReportReadError, detect_type, extract_text
from backend.routes_knowledge import cited_sources
from backend.summary_pdf import _styles, build_summary_pdf, markdown_to_flowables
from backend.voice import MAX_SPEECH_CHARS, VoiceError, clean_for_speech, text_to_speech
from tests.helpers import JULY_LINES, make_pdf

# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------


def test_clean_for_speech_removes_citations_markdown_and_links():
    text = ("**Vitamin D** helps bones [1].\n- See [this page](https://medlineplus.gov/x) "
            "or https://example.com [2] .")
    spoken = clean_for_speech(text)
    for unwanted in ("[1]", "[2]", "**", "https://", "- "):
        assert unwanted not in spoken
    assert spoken.startswith("Vitamin D helps bones.")
    assert "this page" in spoken


def test_clean_for_speech_shortens_long_answers():
    long_text = "This is one sentence. " * 200
    spoken = clean_for_speech(long_text)
    assert len(spoken) <= MAX_SPEECH_CHARS
    assert spoken.endswith(".")


def test_text_to_speech_needs_text():
    with pytest.raises(VoiceError):
        text_to_speech("[1] **")


# ---------------------------------------------------------------------------
# PDF summary
# ---------------------------------------------------------------------------


def test_markdown_converter_handles_headings_lists_and_paragraphs():
    markdown = "## Heading\nFirst line\nsame paragraph\n\n- bullet one\n- bullet two\n1. step"
    flowables = markdown_to_flowables(markdown, _styles())
    # heading + one paragraph + two bullets + one numbered item
    assert len(flowables) == 5


def test_build_summary_pdf_contains_values_and_disclaimer():
    labs = [SimpleNamespace(test="Glucose", value_text="145", unit="mg/dL",
                            reference_range="70 - 100", status="HIGH")]
    report = SimpleNamespace(title="Blood test", report_date="2026-07-01")
    pdf = build_summary_pdf("Demo Patient", report, labs, "Your glucose is **high**.")
    assert pdf.startswith(b"%PDF")
    text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Demo Patient" in text and "Glucose" in text and "High" in text
    assert "not a diagnosis" in text


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------


def test_chunk_text_sizes_and_overlap():
    text = " ".join(f"Sentence number {i} about lab tests." for i in range(200))
    chunks = chunk_text(text, size=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    # Neighbouring chunks share some text, so nothing is lost at the cut.
    assert chunks[1][:30] in chunks[0]
    assert chunk_text("   ") == []


def test_only_medlineplus_lab_test_pages_are_trusted():
    assert is_trusted_url("https://medlineplus.gov/lab-tests/vitamin-d-test/")
    assert not is_trusted_url("https://medlineplus.gov/ency/article/003570.htm")
    assert not is_trusted_url("http://medlineplus.gov/lab-tests/vitamin-d-test/")
    assert not is_trusted_url("https://medlineplus.gov.evil.com/lab-tests/")


def test_cited_sources_keeps_only_real_citations_once():
    sources = [
        {"title": "A", "source_name": "MedlinePlus", "source_url": "u1", "doc_id": 1},
        {"title": "B", "source_name": "MedlinePlus", "source_url": "u2", "doc_id": 2},
    ]
    used = cited_sources("Text [2] more [2] and a made-up [9] and [1].", sources)
    assert [s["number"] for s in used] == [2, 1]
    assert cited_sources("No citations here.", sources) == []


# ---------------------------------------------------------------------------
# Reading uploaded files
# ---------------------------------------------------------------------------


def test_detect_type():
    assert detect_type("report.PDF", None) == "pdf"
    assert detect_type("photo.jpg", None) == "image"
    assert detect_type("x", "image/png") == "image"
    assert detect_type("notes.txt", "text/plain") == "unknown"


def test_extract_text_from_pdf():
    text = extract_text(make_pdf(JULY_LINES), "report.pdf", "application/pdf")
    assert "Glucose 145 mg/dL" in text


@pytest.mark.parametrize("data, name", [
    (b"", "report.pdf"),
    (b"hello", "notes.txt"),
    (b"this is not really a pdf", "broken.pdf"),
])
def test_extract_text_errors_are_friendly(data, name):
    with pytest.raises(ReportReadError):
        extract_text(data, name)