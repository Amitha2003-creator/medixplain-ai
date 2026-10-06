"""Ask My Report chatbot, voice assistant and knowledge-base admin (features 15-18, 32, 34).

Gemini, the knowledge search and text-to-speech are replaced by fakes, so these
tests need no API key and no internet.
"""

import base64

import pytest
from fastapi.testclient import TestClient

import backend.main as main
import backend.routes_knowledge as routes_knowledge
from backend.gemini_service import GeminiError
from tests.helpers import admin_headers, register_patient, save_report

FAKE_SOURCES = [
    {"text": "Glucose is a sugar...", "title": "Blood Glucose Test",
     "source_name": "MedlinePlus", "source_url": "https://medlineplus.gov/lab-tests/blood-glucose-test/",
     "doc_id": 1, "distance": 0.2},
    {"text": "Vitamin D helps bones...", "title": "Vitamin D Test",
     "source_name": "MedlinePlus", "source_url": "https://medlineplus.gov/lab-tests/vitamin-d-test/",
     "doc_id": 2, "distance": 0.3},
]
FAKE_AUDIO = ("question.wav", b"RIFF-fake-wave-data", "audio/wav")


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def calls(monkeypatch):
    """Fake AI pieces. Returns a dict that records what they were given."""
    seen = {}

    def fake_search(question, k=4):
        seen["search"] = question
        return FAKE_SOURCES

    def fake_answer(question, context, sources, history, language):
        seen.update(question=question, context=context, history=history, language=language)
        return "Vitamin D helps keep bones strong [2]."

    def fake_transcribe(audio_bytes, mime_type):
        seen["mime"] = mime_type
        return "വിറ്റാമിൻ ഡി എന്താണ്?", "ml"

    def fake_tts(text, language="en"):
        seen["tts_language"] = language
        return b"ID3-fake-mp3"

    monkeypatch.setattr(routes_knowledge, "search", fake_search)
    monkeypatch.setattr(routes_knowledge, "answer_report_question", fake_answer)
    monkeypatch.setattr(routes_knowledge, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(routes_knowledge, "text_to_speech", fake_tts)
    return seen


def ask(client, headers, pid, question="What is vitamin D?", **extra):
    return client.post(f"/patients/{pid}/chat", headers=headers,
                       json={"question": question, **extra})


# ---------------------------------------------------------------------------
# Typed chat
# ---------------------------------------------------------------------------

def test_chat_uses_report_and_shows_only_cited_sources(client, calls):
    headers, pid = register_patient(client)
    rid = save_report(client, headers, pid).json()["report"]["id"]

    r = ask(client, headers, pid, report_id=rid,
            history=[{"role": "user", "content": "Hello"}])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"].startswith("Vitamin D")
    assert [s["number"] for s in body["sources"]] == [2]  # [1] was not cited
    assert body["report"]["id"] == rid
    assert "disclaimer" in body
    # The verified lab values were given to the AI.
    assert "Vitamin D: 52 nmol/L" in calls["context"]
    assert "LOW" in calls["context"]
    assert calls["history"] == [{"role": "user", "content": "Hello"}]


def test_chat_without_saved_reports(client, calls):
    headers, pid = register_patient(client)
    r = ask(client, headers, pid)
    assert r.status_code == 200
    assert r.json()["report"] is None
    assert "no saved reports" in calls["context"]


def test_chat_unknown_language_falls_back_to_english(client, calls):
    headers, pid = register_patient(client)
    assert ask(client, headers, pid, language="xx").status_code == 200
    assert calls["language"] == "en"


def test_chat_still_answers_when_knowledge_base_fails(client, calls, monkeypatch):
    def broken_search(question, k=4):
        raise RuntimeError("vector store offline")

    monkeypatch.setattr(routes_knowledge, "search", broken_search)
    headers, pid = register_patient(client)
    r = ask(client, headers, pid)
    assert r.status_code == 200
    assert r.json()["note"]
    assert r.json()["sources"] == []


def test_chat_reports_ai_failure(client, calls, monkeypatch):
    def broken_answer(*args, **kwargs):
        raise GeminiError("The AI service is busy.")

    monkeypatch.setattr(routes_knowledge, "answer_report_question", broken_answer)
    headers, pid = register_patient(client)
    r = ask(client, headers, pid)
    assert r.status_code == 502
    assert "busy" in r.json()["detail"]


def test_chat_is_private(client, calls):
    a_headers, a_id = register_patient(client)
    b_headers, b_id = register_patient(client)
    b_report = save_report(client, b_headers, b_id).json()["report"]["id"]

    assert ask(client, a_headers, b_id).status_code == 404
    # Own patient id, but someone else's report id.
    assert ask(client, a_headers, a_id, report_id=b_report).status_code == 404


def test_chat_rejects_empty_question(client, calls):
    headers, pid = register_patient(client)
    assert ask(client, headers, pid, question="").status_code == 422


# ---------------------------------------------------------------------------
# Voice assistant
# ---------------------------------------------------------------------------

def voice(client, headers, pid, audio=FAKE_AUDIO, **data):
    return client.post(f"/patients/{pid}/voice-chat", headers=headers,
                       files={"audio": audio}, data=data)


def test_voice_chat_answers_in_the_language_spoken(client, calls):
    headers, pid = register_patient(client)
    rid = save_report(client, headers, pid).json()["report"]["id"]

    r = voice(client, headers, pid, report_id=str(rid), history="[]")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "വിറ്റാമിൻ ഡി എന്താണ്?"
    assert body["language"] == "ml"
    assert calls["language"] == "ml"          # the answer was asked for in Malayalam
    assert calls["tts_language"] == "ml"      # and read aloud in Malayalam
    assert base64.b64decode(body["audio_base64"]) == b"ID3-fake-mp3"
    assert body["audio_mime"] == "audio/mpeg"
    assert [s["number"] for s in body["sources"]] == [2]


def test_voice_chat_ignores_broken_history(client, calls):
    headers, pid = register_patient(client)
    r = voice(client, headers, pid, history="this is not json")
    assert r.status_code == 200
    assert calls["history"] == []


def test_voice_chat_rejects_non_audio(client, calls):
    headers, pid = register_patient(client)
    r = voice(client, headers, pid, audio=("notes.txt", b"hello", "text/plain"))
    assert r.status_code == 400


def test_voice_chat_rejects_long_recordings(client, calls):
    headers, pid = register_patient(client)
    big = ("long.wav", b"0" * (5 * 1024 * 1024 + 1), "audio/wav")
    assert voice(client, headers, pid, audio=big).status_code == 413


def test_voice_chat_when_nothing_was_heard(client, calls, monkeypatch):
    monkeypatch.setattr(routes_knowledge, "transcribe_audio", lambda data, mime: ("", "en"))
    headers, pid = register_patient(client)
    r = voice(client, headers, pid)
    assert r.status_code == 400
    assert "No clear question" in r.json()["detail"]


def test_voice_chat_keeps_written_answer_if_speech_fails(client, calls, monkeypatch):
    def broken_tts(text, language="en"):
        raise RuntimeError("no internet")

    monkeypatch.setattr(routes_knowledge, "text_to_speech", broken_tts)
    headers, pid = register_patient(client)
    r = voice(client, headers, pid)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert body["audio_base64"] is None
    assert "spoken answer" in body["note"]


def test_voice_chat_is_private(client, calls):
    a_headers, _ = register_patient(client)
    _, b_id = register_patient(client)
    assert voice(client, a_headers, b_id).status_code == 404


# ---------------------------------------------------------------------------
# Knowledge base (admin only)
# ---------------------------------------------------------------------------

def test_only_admin_manages_knowledge(client):
    headers, _ = register_patient(client)
    assert client.get("/admin/knowledge", headers=headers).status_code == 403
    assert client.post("/admin/knowledge/url", headers=headers,
                       json={"url": "https://medlineplus.gov/lab-tests/x/"}).status_code == 403
    assert client.get("/admin/knowledge", headers=admin_headers(client)).status_code == 200


def test_untrusted_links_are_refused(client):
    admin = admin_headers(client)
    for url in ("https://example.com/health", "https://medlineplus.gov/ency/article/000001.htm"):
        r = client.post("/admin/knowledge/url", headers=admin, json={"url": url})
        assert r.status_code == 400, url