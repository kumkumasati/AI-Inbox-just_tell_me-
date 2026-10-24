import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MODE = os.getenv("MODE", "openai").lower()  # "openai" or "local"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED = "text-embedding-3-small"
LOCAL_URL = os.getenv("LOCAL_URL", "http://localhost:11434/v1")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "llama3.1")
LOCAL_EMBED = "all-MiniLM-L6-v2"

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
USE_PRESIDIO = os.getenv("USE_PRESIDIO", "1") == "1"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

CHUNK_SIZE = 80
CHUNK_OVERLAP = 10
RETRIEVE_K = 8

# Dynamically set timeout based on LLM execution mode
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120.0" if MODE == "local" else "30.0"))

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "indexes"
DB_PATH = DATA_DIR / "inbox.db"

def index_path(chat_id: str) -> Path:
    safe_id = Path(chat_id).name
    return INDEX_DIR / f"{safe_id}.index"