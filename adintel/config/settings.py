import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
FIXTURE_DIR = PROJECT_ROOT / "fixtures"

SERP_API_KEY = os.getenv("SERP_API_KEY", "")
SEARCH_API_KEYS = [k.strip() for k in os.getenv("SEARCH_API_KEYS", "").split(",") if k.strip()]

SERPAPI_URL = "https://serpapi.com/search.json"
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
GOOGLE_IMAGE_HOST = "tpc.googlesyndication.com"

DB = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "ocr_scraper"),
}

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

WORKERS = int(os.getenv("WORKERS", "8"))
DOWNLOAD_RETRIES = int(os.getenv("DOWNLOAD_RETRIES", "3"))
REQUEST_TIMEOUT = 60
PAGE_SIZE = 100

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Referer": "https://adstransparency.google.com/",
}
