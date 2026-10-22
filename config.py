import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MODE = os.getenv("MODE", "openai").lower()          
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED = "text-embedding-3-small"
LOCAL_URL = os.getenv("LOCAL_URL", "http://localhost:11434/v1")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "llama3.1")
LOCAL_EMBED = "all-MiniLM-L6-v2"

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
USE_PRESIDIO = os.getenv("USE_PRESIDIO", "1") == "1"

CHUNK_SIZE = 80
CHUNK_OVERLAP = 10
RETRIEVE_K = 8
LLM_TIMEOUT = 30.0

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "indexes"
DB_PATH = DATA_DIR / "inbox.db"

def index_path(chat_id: str) -> Path:
    safe_id = Path(chat_id).name
    return INDEX_DIR / f"{safe_id}.index"