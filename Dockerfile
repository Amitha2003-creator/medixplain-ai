# MediXplain AI - one container that runs both parts:
#   backend  (FastAPI)   on 127.0.0.1:8000  - private, only the frontend can reach it
#   frontend (Streamlit) on 0.0.0.0:7860    - the public web page
FROM python:3.13-slim

# Tesseract reads scanned PDFs and photos of reports.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs the app as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=user backend ./backend
COPY --chown=user frontend ./frontend

EXPOSE 7860

# Start the backend, wait until it answers, then start the frontend.
CMD ["bash", "-c", "uvicorn backend.main:app --host 127.0.0.1 --port 8000 & for i in $(seq 1 60); do python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\" 2>/dev/null && break; sleep 1; done; exec streamlit run frontend/app.py --server.port 7860 --server.address 0.0.0.0 --server.headless true --server.enableXsrfProtection false --server.enableCORS false --browser.gatherUsageStats false"]