# import json, os, sqlite3, time
# from contextlib import closing, contextmanager
# from functools import lru_cache
# from cryptography.fernet import Fernet
# from config import DB_PATH, ENCRYPTION_KEY, index_path

# KEY_HELP = ('python -c "from cryptography.fernet import Fernet; '
#             'print(Fernet.generate_key().decode())"')

# @lru_cache(maxsize=4)
# def _fernet_for(key: str):
#     try:
#         return Fernet(key.encode())
#     except Exception as e:
#         # Friendly message instead of a raw cryptography traceback
#         raise RuntimeError(
#             "ENCRYPTION_KEY is invalid (it must be a 44-character Fernet key). "
#             f"Generate one with:  {KEY_HELP}") from e

# def _fernet():
#     return _fernet_for(ENCRYPTION_KEY)

# def enc(s: str) -> str:
#     return _fernet().encrypt(s.encode()).decode()

# def dec(s: str) -> str:
#     return _fernet().decrypt(s.encode()).decode()


# def enc_bytes(b: bytes) -> bytes:
#     return _fernet().encrypt(b)

# def dec_bytes(b: bytes) -> bytes:
#     return _fernet().decrypt(b)

# @contextmanager
# def _conn():
#     os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
#     with closing(sqlite3.connect(DB_PATH)) as c:
#         c.execute("PRAGMA secure_delete=ON")
#         with c:
#             yield c

# def init():
#     if not ENCRYPTION_KEY:
#         raise RuntimeError(f"ENCRYPTION_KEY is not set. Refusing unencrypted run. "
#                            f"Generate one with:  {KEY_HELP}  and put it in .env")
#     _fernet()
#     with _conn() as c:
#         c.execute("CREATE TABLE IF NOT EXISTS chats(chat_id TEXT PRIMARY KEY, name TEXT, created REAL, privacy_enc TEXT)")
#         c.execute("""CREATE TABLE IF NOT EXISTS messages(chat_id TEXT, msg_id INT, timestamp TEXT,
#                      sender_enc TEXT, text_enc TEXT, safe_sender_enc TEXT, safe_text_enc TEXT)""")
#         c.execute("CREATE TABLE IF NOT EXISTS items(chat_id TEXT, kind TEXT, data_enc TEXT)")
#         c.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
#         c.execute("CREATE INDEX IF NOT EXISTS idx_items_chat ON items(chat_id)")

# def save_chat(chat_id, name, result):
#     with _conn() as c:
#         c.execute("INSERT INTO chats VALUES(?,?,?,?)", (chat_id, name, time.time(),
#                   enc(json.dumps({"map": result["name_map"], "names": result["names"]}))))
#         for m, s in zip(result["messages"], result["safe"]):
#             c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
#                       (chat_id, m["id"], m["timestamp"], enc(m["sender"]), enc(m["text"]),
#                        enc(s["sender"]), enc(s["text"])))
#         for it in result["items"]:
#             c.execute("INSERT INTO items VALUES(?,?,?)", (chat_id, it["kind"], enc(json.dumps(it))))

# def list_chats():
#     with _conn() as c:
#         return c.execute("SELECT chat_id, name, created FROM chats ORDER BY created DESC").fetchall()

# def get_privacy(chat_id):
#     with _conn() as c:
#         row = c.execute("SELECT privacy_enc FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
#     return json.loads(dec(row[0])) if row else None

# def get_messages(chat_id):
#     with _conn() as c:
#         rows = c.execute("SELECT msg_id,timestamp,sender_enc,text_enc,safe_sender_enc,safe_text_enc "
#                          "FROM messages WHERE chat_id=? ORDER BY msg_id", (chat_id,)).fetchall()
#     return [{"id": r[0], "timestamp": r[1], "sender": dec(r[2]), "text": dec(r[3]),
#              "safe_sender": dec(r[4]), "safe_text": dec(r[5])} for r in rows]

# def get_items(chat_id):
#     with _conn() as c:
#         rows = c.execute("SELECT data_enc FROM items WHERE chat_id=?", (chat_id,)).fetchall()
#     return [json.loads(dec(r[0])) for r in rows]

# def delete_chat(chat_id):
#     with _conn() as c:
#         for t in ("messages", "items", "chats"):
#             c.execute(f"DELETE FROM {t} WHERE chat_id=?", (chat_id,))
#     with closing(sqlite3.connect(DB_PATH)) as c:
#         c.execute("VACUUM")
#     p = index_path(chat_id)
#     if os.path.exists(p):
#         os.remove(p)

# def purge_old(days):
#     if days <= 0:
#         return 0
#     cutoff = time.time() - days * 86400
#     with _conn() as c:
#         old = [r[0] for r in c.execute("SELECT chat_id FROM chats WHERE created < ?", (cutoff,))]
#     for cid in old:
#         delete_chat(cid)
#     return len(old)

import json, os, sqlite3, time, hashlib
from contextlib import closing, contextmanager
from functools import lru_cache
from cryptography.fernet import Fernet
from config import DB_PATH, ENCRYPTION_KEY, index_path

KEY_HELP = ('python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"')

@lru_cache(maxsize=4)
def _fernet_for(key: str):
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise RuntimeError(
            "ENCRYPTION_KEY is invalid (it must be a 44-character Fernet key). "
            f"Generate one with:  {KEY_HELP}") from e

def _fernet():
    return _fernet_for(ENCRYPTION_KEY)

def enc(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode()

def dec(s: str) -> str:
    return _fernet().decrypt(s.encode()).decode()

def enc_bytes(b: bytes) -> bytes:
    return _fernet().encrypt(b)

def dec_bytes(b: bytes) -> bytes:
    return _fernet().decrypt(b)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@contextmanager
def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.execute("PRAGMA secure_delete=ON")
        with c:
            yield c

def init():
    if not ENCRYPTION_KEY:
        raise RuntimeError(f"ENCRYPTION_KEY is not set. Refusing unencrypted run. "
                           f"Generate one with:  {KEY_HELP}  and put it in .env")
    _fernet()
    with _conn() as c:
        # Users Table for Login Authentication
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id TEXT PRIMARY KEY, 
            username TEXT UNIQUE NOT NULL, 
            password_hash TEXT NOT NULL, 
            created REAL
        )""")
        
        # Chats Table updated with user_id foreign context
        c.execute("""CREATE TABLE IF NOT EXISTS chats(
            chat_id TEXT PRIMARY KEY, 
            user_id TEXT NOT NULL, 
            name TEXT, 
            created REAL, 
            privacy_enc TEXT
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            chat_id TEXT, msg_id INT, timestamp TEXT,
            sender_enc TEXT, text_enc TEXT, safe_sender_enc TEXT, safe_text_enc TEXT
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS items(chat_id TEXT, kind TEXT, data_enc TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_items_chat ON items(chat_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id)")

# --- USER AUTHENTICATION HELPERS ---

def create_user(user_id: str, username: str, password_raw: str) -> bool:
    init()
    p_hash = hash_password(password_raw)
    try:
        with _conn() as c:
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user_id, username, p_hash, time.time()))
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username: str, password_raw: str):
    init()
    p_hash = hash_password(password_raw)
    with _conn() as c:
        row = c.execute("SELECT user_id, username FROM users WHERE username = ? AND password_hash = ?", (username, p_hash)).fetchone()
    if row:
        return {"id": row[0], "username": row[1]}
    return None

# --- MULTI-TENANT FILTERED CHAT HELPERS ---

def save_chat(chat_id, name, result, user_id):
    init()
    with _conn() as c:
        c.execute("INSERT INTO chats VALUES(?,?,?,?,?)", (chat_id, user_id, name, time.time(),
                  enc(json.dumps({"map": result["name_map"], "names": result["names"]}))))
        for m, s in zip(result["messages"], result["safe"]):
            c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                      (chat_id, m["id"], m["timestamp"], enc(m["sender"]), enc(m["text"]),
                       enc(s["sender"]), enc(s["text"])))
        for it in result["items"]:
            c.execute("INSERT INTO items VALUES(?,?,?)", (chat_id, it["kind"], enc(json.dumps(it))))

def list_chats(user_id):
    init()
    with _conn() as c:
        return c.execute("SELECT chat_id, name, created FROM chats WHERE user_id = ? ORDER BY created DESC", (user_id,)).fetchall()

def get_privacy(chat_id):
    init()
    with _conn() as c:
        row = c.execute("SELECT privacy_enc FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
    return json.loads(dec(row[0])) if row else None

def get_messages(chat_id):
    init()
    with _conn() as c:
        rows = c.execute("SELECT msg_id,timestamp,sender_enc,text_enc,safe_sender_enc,safe_text_enc "
                         "FROM messages WHERE chat_id=? ORDER BY msg_id", (chat_id,)).fetchall()
    return [{"id": r[0], "timestamp": r[1], "sender": dec(r[2]), "text": dec(r[3]),
             "safe_sender": dec(r[4]), "safe_text": dec(r[5])} for r in rows]

def get_items(chat_id):
    init()
    with _conn() as c:
        rows = c.execute("SELECT data_enc FROM items WHERE chat_id=?", (chat_id,)).fetchall()
    return [json.loads(dec(r[0])) for r in rows]

def delete_chat(chat_id):
    init()
    with _conn() as c:
        for t in ("messages", "items", "chats"):
            c.execute(f"DELETE FROM {t} WHERE chat_id=?", (chat_id,))
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.execute("VACUUM")
    p = index_path(chat_id)
    if os.path.exists(p):
        os.remove(p)

def purge_old(days):
    init()
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    with _conn() as c:
        old = [r[0] for r in c.execute("SELECT chat_id FROM chats WHERE created < ?", (cutoff,))]
    for cid in old:
        delete_chat(cid)
    return len(old)