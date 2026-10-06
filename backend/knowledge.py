"""Trusted medical knowledge base (RAG).

Documents are split into small chunks, turned into vectors (embeddings) with
Gemini, and stored in ChromaDB on disk. When a user asks a question, the most
relevant chunks are found and given to Gemini with their source, so answers
can cite where the information came from.
"""

import re

import requests
from bs4 import BeautifulSoup

from backend.config import CHROMA_DIR, EMBEDDING_MODEL, TRUSTED_URL_PREFIXES
from backend.gemini_service import embed_texts

MEDLINEPLUS = "MedlinePlus, National Library of Medicine"

# Starter set: public-domain MedlinePlus lab-test pages for common tests.
STARTER_PAGES = [
    "https://medlineplus.gov/lab-tests/hemoglobin-test/",
    "https://medlineplus.gov/lab-tests/complete-blood-count-cbc/",
    "https://medlineplus.gov/lab-tests/blood-glucose-test/",
    "https://medlineplus.gov/lab-tests/hemoglobin-a1c-hba1c-test/",
    "https://medlineplus.gov/lab-tests/cholesterol-levels/",
    "https://medlineplus.gov/lab-tests/triglycerides-test/",
    "https://medlineplus.gov/lab-tests/vitamin-d-test/",
    "https://medlineplus.gov/lab-tests/calcium-blood-test/",
    "https://medlineplus.gov/lab-tests/creatinine-test/",
    "https://medlineplus.gov/lab-tests/liver-function-tests/",
    "https://medlineplus.gov/lab-tests/tsh-thyroid-stimulating-hormone-test/",
]

CHUNK_SIZE = 1000      # characters per chunk
CHUNK_OVERLAP = 150    # characters shared between neighbouring chunks
MIN_PAGE_CHARS = 400   # a page with less text than this was probably not read correctly


class KnowledgeError(RuntimeError):
    """Raised when a knowledge-base action fails. The message is safe to show users."""


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

_collection = None


def _get_collection():
    """Open the ChromaDB collection once. Each embedding model gets its own collection,
    because vectors from different models cannot be compared."""
    global _collection
    if _collection is None:
        import chromadb
        from chromadb.config import Settings

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False)
        )
        name = "knowledge_" + re.sub(r"[^a-zA-Z0-9]+", "_", EMBEDDING_MODEL).strip("_")
        _collection = client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    return _collection


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, breaking at paragraph or sentence ends."""
    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        return []

    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer to cut at a paragraph break, then a sentence end, in the second half.
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "))
            if cut > size // 2:
                end = start + cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def is_trusted_url(url: str) -> bool:
    return any(url.startswith(prefix) for prefix in TRUSTED_URL_PREFIXES)


def fetch_trusted_page(url: str) -> tuple[str, str]:
    """Download a trusted page and return (title, main text)."""
    if not is_trusted_url(url):
        raise KnowledgeError(
            "Only MedlinePlus lab-test pages (https://medlineplus.gov/lab-tests/...) can be added by link."
        )
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "MediXplainAI/1.0 (education)"})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise KnowledgeError(f"Could not download the page: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else url
    title = title.replace(": MedlinePlus Medical Test", "").strip()

    main = soup.select_one("#mplus-content") or soup.find("article") or soup.find("main") or soup.body
    if main is None:
        raise KnowledgeError("The page had no readable content.")
    for tag in main.select("script, style, nav, header, footer, aside, form, noscript"):
        tag.decompose()
    # Drop the page's own list of references, which is long and not useful for answers.
    for heading in main.find_all(["h2", "h3"]):
        if heading.get_text(strip=True).lower().startswith("references"):
            for sibling in list(heading.find_all_next()):
                sibling.decompose()
            heading.decompose()
            break

    text = main.get_text(separator="\n")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) < MIN_PAGE_CHARS:
        raise KnowledgeError("Very little text was found on that page, so it was not added.")
    return title, text


# ---------------------------------------------------------------------------
# Add, delete, search
# ---------------------------------------------------------------------------

def add_document(doc_id: int, title: str, source_name: str, source_url: str | None, text: str) -> int:
    """Chunk, embed and store a document. Returns the number of chunks stored."""
    chunks = chunk_text(text)
    if not chunks:
        raise KnowledgeError("The document has no text to add.")

    # Include the title in each chunk so a chunk still makes sense on its own.
    vectors = embed_texts([f"{title}\n\n{chunk}" for chunk in chunks], task="document")
    _get_collection().add(
        ids=[f"doc{doc_id}-chunk{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=vectors,
        metadatas=[
            {"doc_id": doc_id, "title": title, "source_name": source_name,
             "source_url": source_url or "", "chunk": i}
            for i in range(len(chunks))
        ],
    )
    return len(chunks)


def delete_document(doc_id: int) -> None:
    _get_collection().delete(where={"doc_id": doc_id})


def search(query: str, k: int = 4) -> list[dict]:
    """Return the k most relevant chunks for a question."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    vector = embed_texts([query], task="query")[0]
    result = collection.query(query_embeddings=[vector], n_results=min(k, collection.count()))
    hits = []
    for text, meta, distance in zip(result["documents"][0], result["metadatas"][0],
                                    result["distances"][0]):
        hits.append({
            "text": text,
            "title": meta.get("title", ""),
            "source_name": meta.get("source_name", ""),
            "source_url": meta.get("source_url") or None,
            "doc_id": meta.get("doc_id"),
            "distance": round(distance, 4),
        })
    return hits