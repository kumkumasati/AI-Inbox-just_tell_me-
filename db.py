import hashlib, hmac, json, os, re, secrets, sqlite3, time
from contextlib import closing, contextmanager
from functools import lru_cache
from cryptography.fernet import Fernet
from config import DB_PATH, ENCRYPTION_KEY, index_path

KEY_HELP = ('python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"')

# ----------------------------------------------------------------------------------------------
# Encryption of chat content
# ----------------------------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _fernet_for(key: str):
    try:
        return Fernet(key.encode())
    except Exception as e:
        # Friendly message instead of a raw cryptography traceback
        raise RuntimeError(
            "ENCRYPTION_KEY is invalid (it must be a 44-character Fernet key). "
            f"Generate one with:  {KEY_HELP}") from e

def _fernet():
    return _fernet_for(ENCRYPTION_KEY)

def enc(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode()

def dec(s: str) -> str:
    return _fernet().decrypt(s.encode()).decode()

# used to encrypt the FAISS index file on disk
def enc_bytes(b: bytes) -> bytes:
    return _fernet().encrypt(b)

def dec_bytes(b: bytes) -> bytes:
    return _fernet().decrypt(b)

@contextmanager
def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.execute("PRAGMA secure_delete=ON")
        with c:
            yield c

# ----------------------------------------------------------------------------------------------
# User accounts
# ----------------------------------------------------------------------------------------------
USERNAME_RE = re.compile(r"[A-Za-z0-9_.-]{3,32}")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
MAX_FAILED_LOGINS = 5            # after this many wrong passwords in a row ...
LOCK_SECONDS = 300               # ... the account is locked for 5 minutes

class AccountLocked(Exception):
    """Raised by verify_user() while an account is locked after too many failed logins."""
    def __init__(self, seconds):
        self.seconds = int(seconds)
        super().__init__(f"Too many failed attempts. Try again in {self.seconds} seconds.")

def _hash_password(password: str, salt: bytes = None) -> str:
    """Salted, memory-hard hash (scrypt). Falls back to PBKDF2 if this Python lacks scrypt."""
    salt = salt or secrets.token_bytes(16)
    raw = password.encode("utf-8")
    if hasattr(hashlib, "scrypt"):
        digest = hashlib.scrypt(raw, salt=salt, n=2 ** 14, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
        return f"scrypt$14$8$1${salt.hex()}${digest.hex()}"
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, 600_000, dklen=32)
    return f"pbkdf2$600000${salt.hex()}${digest.hex()}"

def _check_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        raw = password.encode("utf-8")
        if parts[0] == "scrypt":
            _, ln, r, p, salt, digest = parts
            calc = hashlib.scrypt(raw, salt=bytes.fromhex(salt), n=2 ** int(ln), r=int(r), p=int(p),
                                  dklen=32, maxmem=64 * 1024 * 1024)
        elif parts[0] == "pbkdf2":
            _, iters, salt, digest = parts
            calc = hashlib.pbkdf2_hmac("sha256", raw, bytes.fromhex(salt), int(iters), dklen=32)
        else:
            return False
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, AttributeError):
        return False

@lru_cache(maxsize=1)
def _dummy_hash():
    # Verified for unknown usernames so that "no such user" and "wrong password" take equally long
    return _hash_password("dummy-password-for-timing")

def create_user(user_id, username, password):
    """Create an account. Returns True, or False if the username is already taken.
    Raises ValueError (with a message safe to show) for an invalid username / password.
    The FIRST account ever created also adopts any chats that existed before accounts were added."""
    username = (username or "").strip()
    password = password or ""
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3-32 characters: letters, numbers, dot, dash or underscore.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise ValueError(f"Password must be at most {MAX_PASSWORD} characters.")
    pw_hash = _hash_password(password)
    try:
        with _conn() as c:
            c.execute("BEGIN IMMEDIATE")
            first_user = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            c.execute("INSERT INTO users(user_id, username, username_key, pw_hash, created) VALUES(?,?,?,?,?)",
                      (user_id, username, username.lower(), pw_hash, time.time()))
            if first_user:
                c.execute("UPDATE chats SET user_id=? WHERE user_id IS NULL", (user_id,))
    except sqlite3.IntegrityError:
        return False
    return True

def verify_user(username, password):
    """Return {"id", "username"} for correct credentials, None for wrong ones.
    Raises AccountLocked while the account is locked."""
    key = (username or "").strip().lower()
    password = (password or "")[:MAX_PASSWORD]
    with _conn() as c:
        row = c.execute("SELECT user_id, username, pw_hash, failed_count, locked_until "
                        "FROM users WHERE username_key=?", (key,)).fetchone()
    now = time.time()
    if row and row[4] > now:
        raise AccountLocked(row[4] - now + 1)
    correct = _check_password(password, row[2] if row else _dummy_hash())
    if row and correct:
        with _conn() as c:
            c.execute("UPDATE users SET failed_count=0, locked_until=0 WHERE user_id=?", (row[0],))
        return {"id": row[0], "username": row[1]}
    if row:
        failed = row[3] + 1
        locked_until = now + LOCK_SECONDS if failed >= MAX_FAILED_LOGINS else 0
        with _conn() as c:
            c.execute("UPDATE users SET failed_count=?, locked_until=? WHERE user_id=?",
                      (0 if locked_until else failed, locked_until, row[0]))
    return None

def get_user_id(username):
    with _conn() as c:
        row = c.execute("SELECT user_id FROM users WHERE username_key=?", ((username or "").strip().lower(),)).fetchone()
    return row[0] if row else None

# ----------------------------------------------------------------------------------------------
# Schema + chats (every chat belongs to one user)
# ----------------------------------------------------------------------------------------------
def init():
    if not ENCRYPTION_KEY:
        raise RuntimeError(f"ENCRYPTION_KEY is not set. Refusing unencrypted run. "
                           f"Generate one with:  {KEY_HELP}  and put it in .env")
    _fernet()
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS chats(chat_id TEXT PRIMARY KEY, name TEXT, created REAL, privacy_enc TEXT, user_id TEXT)")
        # migration: databases created before accounts existed have no user_id column
        if "user_id" not in [r[1] for r in c.execute("PRAGMA table_info(chats)")]:
            c.execute("ALTER TABLE chats ADD COLUMN user_id TEXT")
        c.execute("""CREATE TABLE IF NOT EXISTS messages(chat_id TEXT, msg_id INT, timestamp TEXT,
                     sender_enc TEXT, text_enc TEXT, safe_sender_enc TEXT, safe_text_enc TEXT)""")
        c.execute("CREATE TABLE IF NOT EXISTS items(chat_id TEXT, kind TEXT, data_enc TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, username TEXT NOT NULL,
                     username_key TEXT NOT NULL UNIQUE, pw_hash TEXT NOT NULL, created REAL NOT NULL,
                     failed_count INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_items_chat ON items(chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id)")

def owns_chat(chat_id, user_id):
    with _conn() as c:
        return c.execute("SELECT 1 FROM chats WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone() is not None

def _require_owner(chat_id, user_id):
    """When a user_id is given, the chat MUST belong to that user (defence in depth: the UI only
    lists a user's own chats, but every read/delete re-checks)."""
    if user_id is not None and not owns_chat(chat_id, user_id):
        raise PermissionError("This chat does not belong to your account.")

def save_chat(chat_id, name, result, user_id=None):
    with _conn() as c:
        c.execute("INSERT INTO chats(chat_id, name, created, privacy_enc, user_id) VALUES(?,?,?,?,?)",
                  (chat_id, name, time.time(),
                   enc(json.dumps({"map": result["name_map"], "names": result["names"]})), user_id))
        for m, s in zip(result["messages"], result["safe"]):
            c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                      (chat_id, m["id"], m["timestamp"], enc(m["sender"]), enc(m["text"]),
                       enc(s["sender"]), enc(s["text"])))
        for it in result["items"]:
            c.execute("INSERT INTO items VALUES(?,?,?)", (chat_id, it["kind"], enc(json.dumps(it))))

def list_chats(user_id=None):
    """Chats of one user (newest first). user_id=None returns ALL chats - for CLI/tests only."""
    with _conn() as c:
        if user_id is None:
            return c.execute("SELECT chat_id, name, created FROM chats ORDER BY created DESC").fetchall()
        return c.execute("SELECT chat_id, name, created FROM chats WHERE user_id=? ORDER BY created DESC",
                         (user_id,)).fetchall()

def get_privacy(chat_id, user_id=None):
    _require_owner(chat_id, user_id)
    with _conn() as c:
        row = c.execute("SELECT privacy_enc FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
    return json.loads(dec(row[0])) if row else None

def get_messages(chat_id, user_id=None):
    _require_owner(chat_id, user_id)
    with _conn() as c:
        rows = c.execute("SELECT msg_id,timestamp,sender_enc,text_enc,safe_sender_enc,safe_text_enc "
                         "FROM messages WHERE chat_id=? ORDER BY msg_id", (chat_id,)).fetchall()
    return [{"id": r[0], "timestamp": r[1], "sender": dec(r[2]), "text": dec(r[3]),
             "safe_sender": dec(r[4]), "safe_text": dec(r[5])} for r in rows]

def get_items(chat_id, user_id=None):
    _require_owner(chat_id, user_id)
    with _conn() as c:
        rows = c.execute("SELECT data_enc FROM items WHERE chat_id=?", (chat_id,)).fetchall()
    return [json.loads(dec(r[0])) for r in rows]

def delete_chat(chat_id, user_id=None):
    _require_owner(chat_id, user_id)
    with _conn() as c:
        for t in ("messages", "items", "chats"):
            c.execute(f"DELETE FROM {t} WHERE chat_id=?", (chat_id,))
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.execute("VACUUM")
    p = index_path(chat_id)
    if os.path.exists(p):
        os.remove(p)

def purge_old(days):
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    with _conn() as c:
        old = [r[0] for r in c.execute("SELECT chat_id FROM chats WHERE created < ?", (cutoff,))]
    for cid in old:
        delete_chat(cid)
    return len(old)