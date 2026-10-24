"""Accounts, ownership, lockout and migration (db level, no Streamlit). Run: pytest -q"""
import os, sqlite3, sys, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cryptography.fernet import Fernet
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["USE_PRESIDIO"] = "0"

import config, db, pipeline, search
import extract
from schemas import Extraction

ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "idx")
    db.init()
    return tmp_path

def _chat_result():
    return {"messages": [{"id": 1, "timestamp": "t", "sender": "A", "text": "hello"}],
            "safe": [{"id": 1, "timestamp": "t", "sender": "PERSON_1", "text": "hello"}],
            "name_map": {}, "names": {}, "items": []}

# ------------------------------------------------------------------ passwords
def test_password_is_hashed_and_verifies(fresh):
    assert db.create_user("u1", "Rahul", "correct horse") is True
    with sqlite3.connect(db.DB_PATH) as c:
        stored = c.execute("SELECT pw_hash FROM users").fetchone()[0]
    assert "correct horse" not in stored and stored.startswith(("scrypt$", "pbkdf2$"))
    assert db.verify_user("rahul", "correct horse") == {"id": "u1", "username": "Rahul"}   # case-insensitive name
    assert db.verify_user("Rahul", "wrong password") is None
    assert db.verify_user("nobody", "whatever123") is None

def test_two_users_same_password_get_different_hashes(fresh):
    db.create_user("u1", "alice", "samepassword"); db.create_user("u2", "bob", "samepassword")
    with sqlite3.connect(db.DB_PATH) as c:
        hashes = [r[0] for r in c.execute("SELECT pw_hash FROM users")]
    assert hashes[0] != hashes[1]                                # per-user salt

def test_duplicate_username_is_rejected_case_insensitively(fresh):
    assert db.create_user("u1", "Rahul", "password123") is True
    assert db.create_user("u2", "RAHUL", "password456") is False

@pytest.mark.parametrize("name,pw", [
    ("ab", "password123"), ("<img src=x onerror=alert(1)>", "password123"),
    ("has space", "password123"), ("valid_name", "short"), ("valid_name", "x" * 129), ("", "password123"),
])
def test_invalid_username_or_password_is_refused(fresh, name, pw):
    with pytest.raises(ValueError):
        db.create_user("u1", name, pw)
    assert db.get_user_id(name.strip()) is None if name.strip() else True

def test_lockout_after_five_failures_and_unlock(fresh, monkeypatch):
    db.create_user("u1", "rahul", "password123")
    for _ in range(db.MAX_FAILED_LOGINS):
        assert db.verify_user("rahul", "nope-nope") is None
    with pytest.raises(db.AccountLocked) as exc:
        db.verify_user("rahul", "password123")                    # even the CORRECT password is refused
    assert 0 < exc.value.seconds <= db.LOCK_SECONDS + 1
    real_time = time.time
    monkeypatch.setattr(db.time, "time", lambda: real_time() + db.LOCK_SECONDS + 5)
    assert db.verify_user("rahul", "password123")["id"] == "u1"   # unlocked after the lock period

def test_successful_login_resets_failure_counter(fresh):
    db.create_user("u1", "rahul", "password123")
    for _ in range(db.MAX_FAILED_LOGINS - 1):
        db.verify_user("rahul", "bad-bad-bad")
    assert db.verify_user("rahul", "password123")
    for _ in range(db.MAX_FAILED_LOGINS - 1):                     # counter started again from zero
        db.verify_user("rahul", "bad-bad-bad")
    assert db.verify_user("rahul", "password123")                 # still not locked

# ------------------------------------------------------------------ isolation
def test_users_only_see_and_touch_their_own_chats(fresh):
    db.create_user("ua", "alice", "password123"); db.create_user("ub", "bob", "password123")
    db.save_chat("chatA", "Alice chat", _chat_result(), user_id="ua")
    db.save_chat("chatB", "Bob chat", _chat_result(), user_id="ub")
    assert [r[0] for r in db.list_chats("ua")] == ["chatA"] and [r[0] for r in db.list_chats("ub")] == ["chatB"]
    for fn in (db.get_messages, db.get_items, db.get_privacy, db.delete_chat):
        with pytest.raises(PermissionError):
            fn("chatA", user_id="ub")                              # Bob cannot read / delete Alice's chat
    assert len(db.get_messages("chatA", user_id="ua")) == 1
    db.delete_chat("chatA", user_id="ua")
    assert db.list_chats("ua") == [] and len(db.list_chats("ub")) == 1

def test_search_refuses_a_chat_owned_by_someone_else(fresh):
    db.create_user("ua", "alice", "password123"); db.create_user("ub", "bob", "password123")
    db.save_chat("chatA", "Alice chat", _chat_result(), user_id="ua")
    res = search.ask("chatA", "what did they say?", user_id="ub")
    assert res["verified"] is False and res["sources"] == [] and "unknown chat" in res["reason"]

def test_pipeline_process_assigns_the_owner(fresh, monkeypatch):
    import numpy as np
    monkeypatch.setattr(search, "embed", lambda t: (lambda v: v / np.linalg.norm(v, axis=1, keepdims=True))(
        np.random.default_rng(0).random((len(t), 8)).astype("float32")))
    monkeypatch.setattr(extract, "structured", lambda s, u, c: Extraction(topics=[], action_items=[], decisions=[]))
    pipeline._chunk_cache.clear()
    db.create_user("ua", "alice", "password123")
    raw = fresh / "c.txt"; raw.write_text((ROOT / "data" / "sample_chat.txt").read_text())
    info = pipeline.process(str(raw), "Mine", ["rahul"], user_id="ua")
    assert [r[0] for r in db.list_chats("ua")] == [info["chat_id"]]
    assert db.list_chats("someone-else") == []

# ------------------------------------------------------------------ migration of a pre-accounts database
def test_old_database_is_migrated_and_adopted_by_first_account(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:                              # schema exactly as it was BEFORE accounts
        c.execute("CREATE TABLE chats(chat_id TEXT PRIMARY KEY, name TEXT, created REAL, privacy_enc TEXT)")
        c.execute("CREATE TABLE messages(chat_id TEXT, msg_id INT, timestamp TEXT, sender_enc TEXT, text_enc TEXT, safe_sender_enc TEXT, safe_text_enc TEXT)")
        c.execute("CREATE TABLE items(chat_id TEXT, kind TEXT, data_enc TEXT)")
        c.execute("INSERT INTO chats VALUES('legacy1','Old chat',?, ?)", (time.time(), db.enc('{"map":{},"names":{}}')))
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "idx")
    db.init()                                                     # adds user_id column + users table
    db.init()                                                     # and is safe to run twice
    assert db.list_chats("anyone") == []                          # nobody owns it yet ...
    assert len(db.list_chats()) == 1
    db.create_user("first", "owner", "password123")               # ... until the first account appears
    assert [r[0] for r in db.list_chats("first")] == ["legacy1"]
    db.create_user("second", "other", "password123")
    assert db.list_chats("second") == []                          # later accounts do NOT inherit old chats