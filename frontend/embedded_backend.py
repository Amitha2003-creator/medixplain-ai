"""Run the FastAPI backend inside the Streamlit app, for one-app hosting
(Streamlit Community Cloud).

It switches on when RUN_EMBEDDED_BACKEND = "1" is in the hosting site's Secrets,
or automatically on Streamlit Community Cloud (apps there run from /mount/src).
On your laptop nothing changes: you still start the backend yourself.
"""

import contextlib
import os
import sys
import threading
import time
from pathlib import Path

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOST, PORT = "127.0.0.1", 8000


def _secrets_to_env() -> None:
    """Copy the hosting site's Secrets into environment variables for the backend."""
    with contextlib.suppress(Exception):  # no secrets file on the laptop: nothing to copy
        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)):
                os.environ.setdefault(key, str(value))


def _healthy() -> bool:
    try:
        return requests.get(f"http://{HOST}:{PORT}/health", timeout=1).ok
    except requests.RequestException:
        return False


@st.cache_resource(show_spinner="Starting MediXplain... (about 20 seconds)")
def _start_backend() -> bool:
    """Start the backend once per server, in a background thread."""
    if _healthy():
        return True
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import uvicorn

    from backend.main import app

    class _ThreadServer(uvicorn.Server):
        # Signal handlers only work in the main thread; Streamlit owns it.
        def install_signal_handlers(self):
            pass

        @contextlib.contextmanager
        def capture_signals(self):
            yield

    server = _ThreadServer(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(120):
        if _healthy():
            return True
        time.sleep(0.5)
    return False


def _wanted() -> bool:
    flag = os.getenv("RUN_EMBEDDED_BACKEND", "").strip().strip('"').lower()
    return flag in {"1", "true", "yes"} or Path("/mount/src").exists()


def start_if_needed() -> None:
    _secrets_to_env()
    if not _wanted():
        return
    if not _start_backend():
        _start_backend.clear()
        st.error("The app could not start its backend. Please reload the page in a minute.")
        st.stop()
