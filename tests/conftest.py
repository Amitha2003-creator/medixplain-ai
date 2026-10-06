import os

# Test settings: fake secrets, a throwaway database and a test admin.
# These are set before the app loads, so your real .env and database are not used.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-for-real-use")
os.environ["DATABASE_URL"] = "sqlite:///./test_medixplain.db"
os.environ["GEMINI_API_KEY"] = ""
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "adminpass123"

if os.path.exists("test_medixplain.db"):
    os.remove("test_medixplain.db")