"""UI-level tests of the login / sign-up / logout screens and per-user chat isolation (Streamlit AppTest)."""
import os, sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cryptography.fernet import Fernet
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["USE_PRESIDIO"] = "0"

pytest.importorskip("streamlit")
import streamlit as st
from streamlit.testing.v1 import AppTest

import config, db, extract, pipeline, search
from schemas import ActionItem, Extraction

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")

@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "idx")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(search, "embed", lambda t: (lambda v: v / np.linalg.norm(v, axis=1, keepdims=True))(
        np.random.default_rng(0).random((len(t), 8)).astype("float32")))
    monkeypatch.setattr(extract, "structured", lambda s, u, c: Extraction(topics=[], decisions=[], action_items=[
        ActionItem(task="Send report by Friday", assignee="ME", deadline="Friday", source_message_ids=[2],
                   quote="please send the project report by Friday")]))
    pipeline._chunk_cache.clear()
    st.cache_data.clear()
    db.init()
    return tmp_path

def make_chat(env, owner_id, name):
    raw = env / f"{name}.txt"
    raw.write_text((ROOT / "data" / "sample_chat.txt").read_text())
    return pipeline.process(str(raw), name, ["rahul"], user_id=owner_id)["chat_id"]

def new_app():
    return AppTest.from_file(APP, default_timeout=60)

def logged_in(uid, username):
    at = new_app()
    at.session_state["authenticated"] = True
    at.session_state["user_id"] = uid
    at.session_state["username"] = username
    return at.run()

def button(at, label):
    return [b for b in at.button if b.label == label][0]

def errors(at):
    return [e.value for e in at.error]

def do_login(at, username, password):
    at.text_input(key="login_user").set_value(username)
    at.text_input(key="login_pass").set_value(password)
    button(at, "Log In").click()
    return at.run()

# ------------------------------------------------------------------ login screen
def test_login_screen_renders_and_hides_the_app(env):
    at = new_app().run()
    assert not at.exception                                     # used to crash: set_page_config called twice
    assert {b.label for b in at.button} == {"Log In"}
    assert not at.sidebar.radio and not at.sidebar.button       # no navigation, no chats, no logout

def test_signup_validation_messages(env):
    at = new_app().run()
    at.radio(key="auth_mode").set_value("Sign Up").run()
    def signup(user, pw, confirm):
        at.text_input(key="signup_user").set_value(user)
        at.text_input(key="signup_pass").set_value(pw)
        at.text_input(key="signup_confirm").set_value(confirm)
        button(at, "Sign Up").click()
        at.run()
    signup("alice", "password123", "different123")
    assert "Passwords do not match." in errors(at)
    signup("alice", "short", "short")
    assert any("at least 8" in e for e in errors(at))
    signup("<img src=x onerror=alert(1)>", "password123", "password123")
    assert any("Username must be" in e for e in errors(at)) and db.get_user_id("<img src=x onerror=alert(1)>") is None
    signup("alice", "password123", "password123")
    assert [s.value for s in at.success] and db.get_user_id("alice")
    signup("ALICE", "password123", "password123")
    assert "That username is already taken." in errors(at)
    assert not at.exception

def test_signup_login_logout_roundtrip(env):
    db.create_user("ua", "alice", "password123")
    at = new_app().run()
    do_login(at, "alice", "wrong-password")
    assert "Invalid username or password." in errors(at) and not at.session_state["authenticated"]
    do_login(at, "ALICE", "password123")                        # username is case-insensitive
    assert not at.exception and at.session_state["authenticated"] and at.session_state["user_id"] == "ua"
    assert any("alice" in m.value for m in at.sidebar.markdown)
    button(at, "🚪 Logout").click(); at.run()
    assert not at.exception and not at.session_state["authenticated"]
    at.run()        # next interaction: AppTest keeps elements of the run interrupted by st.rerun(); a browser drops them
    assert {b.label for b in at.button} == {"Log In"}           # back on the login screen, nothing else
    assert not at.sidebar.button and not at.sidebar.radio

def test_lockout_message_after_five_wrong_passwords(env):
    db.create_user("ua", "alice", "password123")
    at = new_app().run()
    for _ in range(db.MAX_FAILED_LOGINS):
        do_login(at, "alice", "wrong-password")
    do_login(at, "alice", "password123")
    assert any("Too many failed attempts" in e for e in errors(at)) and not at.session_state["authenticated"]

# ------------------------------------------------------------------ logged-in behaviour
def test_each_user_sees_only_their_own_chats(env):
    db.create_user("ua", "alice", "password123"); db.create_user("ub", "bob", "password123")
    make_chat(env, "ua", "Alice chat")
    bob = logged_in("ub", "bob")
    assert not bob.exception and not bob.sidebar.radio[1:] and any("No chats yet" in c.value for c in bob.sidebar.caption)
    alice = logged_in("ua", "alice")
    assert not alice.exception and "Alice chat" in alice.sidebar.radio[1].options[0]

def test_every_page_renders_when_logged_in(env):
    db.create_user("ua", "alice", "password123")
    make_chat(env, "ua", "Alice chat")
    at = logged_in("ua", "alice")
    for page in ["home", "digest", "chats", "ask", "settings", "evaluation"]:
        at.session_state["nav"] = page
        at.run()
        assert not at.exception, (page, [e.value for e in at.exception])

def test_ask_and_delete_are_scoped_to_the_owner(env):
    db.create_user("ua", "alice", "password123")
    cid = make_chat(env, "ua", "Alice chat")
    at = logged_in("ua", "alice")
    at.session_state["nav"] = "ask"; at.run()
    button_label = [b.label for b in at.button if b.key == "suggest_0"][0]
    [b for b in at.button if b.key == "suggest_0"][0].click(); at.run()
    assert not at.exception, button_label
    [b for b in at.button if b.key == "delete_chat"][0].click(); at.run()
    assert not at.exception and db.list_chats("ua") == [] and not db.owns_chat(cid, "ua")

def test_username_is_escaped_in_the_sidebar(env):
    at = new_app()
    at.session_state["authenticated"] = True
    at.session_state["user_id"] = "ua"
    at.session_state["username"] = "<img src=x onerror=alert(1)>"     # cannot be created normally; defence in depth
    at.run()
    html = " ".join(m.value for m in at.sidebar.markdown)
    assert "<img" not in html and "&lt;img" in html

def test_database_is_initialised_before_login(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "brand_new.db")     # NO db.init() here on purpose
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "idx")
    st.cache_resource.clear()
    at = new_app().run()
    assert not at.exception
    at.radio(key="auth_mode").set_value("Sign Up").run()
    at.text_input(key="signup_user").set_value("alice")
    at.text_input(key="signup_pass").set_value("password123")
    at.text_input(key="signup_confirm").set_value("password123")
    button(at, "Sign Up").click(); at.run()
    assert not at.exception and db.get_user_id("alice")               # no "no such table: users"