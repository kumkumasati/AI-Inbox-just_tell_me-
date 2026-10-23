"""AI-Inbox - six-screen UI.
Run: streamlit run app.py

Backend interfaces used:
  db.init / purge_old / list_chats / get_messages / get_items / delete_chat
  search.ask(chat_id, question)
  pipeline.process(path, chat_name, aliases)
  config constants: MODE, RETENTION_DAYS, RAW_DIR, APP_PASSWORD
"""
import hmac
import os
import time
import uuid
from collections import Counter

import pandas as pd
import streamlit as st

import db
import score
import search
from config import (APP_PASSWORD, MAX_UPLOAD_MB, MODE, RAW_DIR, RETENTION_DAYS,
                    USE_PRESIDIO)
from pipeline import process
from ui_utils import esc, highlight, placeholder_alternatives

st.set_page_config(page_title="AI-Inbox", page_icon="📥", layout="wide")

# ---------------------------- Visual system ----------------------------
st.markdown("""
<style>
:root { --violet:#8b7cff; --cyan:#22b8f0; --mint:#35d6a1; --muted:#9ba8c9; }
html, body, [class*="css"], button, input, textarea {font-family:'Segoe UI',Inter,system-ui,-apple-system,sans-serif;}
.stApp { color:#edf0fb; background:
 radial-gradient(1000px 500px at 10% -8%,rgba(124,108,255,.32),transparent 62%),
 radial-gradient(900px 480px at 98% 0%,rgba(34,184,240,.18),transparent 58%), #0a0e1e; }
.block-container {padding-top:1.1rem;max-width:1450px;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stToolbar"] [data-testid="stAppDeployButton"],[data-testid="stToolbar"] [data-testid="stMainMenu"],[data-testid="stDecoration"],#MainMenu,footer {display:none;}
[data-testid="stSidebar"] {background:rgba(12,16,36,.94);border-right:1px solid rgba(255,255,255,.08);}
[data-testid="stSidebar"] > div:first-child {padding-top:1rem;}
.logo {display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.18rem;color:#fff;margin:4px 0 18px;}
.logo-icon {height:38px;width:38px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#7c6cff,#22b8f0);font-size:1.15rem;}
.side-label {font-size:.7rem;letter-spacing:.1em;color:#7783ab;margin:20px 0 8px 4px;text-transform:uppercase;}
.status {display:flex;gap:10px;align-items:center;padding:11px 12px;margin-top:18px;border-radius:13px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);}
.pulse {width:9px;height:9px;border-radius:50%;background:#35d6a1;box-shadow:0 0 10px #35d6a1;}
.status b {color:#fff;font-size:.82rem}.status span {color:#9ba8c9;font-size:.72rem}
div[class*="st-key-card_"],div[class*="st-key-panel_"],div[class*="st-key-askcard"] {background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10);border-radius:18px;padding:17px 19px 10px;backdrop-filter:blur(14px);box-shadow:0 10px 32px rgba(0,0,0,.2);}
.hero {border-radius:19px;padding:25px 27px;min-height:165px;background:linear-gradient(120deg,rgba(91,75,219,.97),rgba(124,108,255,.85) 48%,rgba(34,184,240,.72));border:1px solid rgba(255,255,255,.2);box-shadow:0 14px 38px rgba(91,75,219,.25);}
.hero h1 {font-size:1.65rem;color:white;margin:0;font-weight:800;letter-spacing:-.04em}
.hero p {color:#edf0ff;margin:11px 0 13px;max-width:650px;font-size:.9rem;line-height:1.5}
.pill {display:inline-block;padding:4px 10px;margin-right:6px;border-radius:999px;font-size:.7rem;color:#fff;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.22);}
.metrics {display:grid;grid-template-columns:1fr 1fr;min-height:165px;border-radius:18px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.1);overflow:hidden;}
.metric {padding:17px 19px;display:flex;flex-direction:column;justify-content:center;border-right:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08);}
.metric:nth-child(2n){border-right:none}.metric:nth-child(n+3){border-bottom:none}
.metric .num {font-size:1.8rem;font-weight:800;color:#fff;line-height:1.2}.metric .lbl{font-size:.76rem;color:#9ba8c9}
.page-head {display:flex;align-items:baseline;gap:12px;margin:7px 0 5px}
.page-head h1 {font-size:1.55rem;color:#fff;font-weight:800;margin:0;letter-spacing:-.035em}
.page-head span,.subtle {color:#9ba8c9;font-size:.82rem}
.section-title {font-size:1rem;color:#fff;font-weight:750;margin:5px 0 12px}
.card-head {display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-weight:750;color:#fff}
.item-row {display:flex;align-items:center;gap:13px;padding:13px 3px;border-top:1px solid rgba(255,255,255,.075)}
.item-icon {width:40px;height:40px;flex:none;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1rem;background:linear-gradient(135deg,#7c6cff,#a855f7)}
.item-icon.decision{background:linear-gradient(135deg,#10b981,#34d399)}
.item-title{font-size:.9rem;font-weight:650;color:#fff;line-height:1.4}
.item-meta{font-size:.75rem;color:#9ba8c9;margin-top:4px}
.tag{display:inline-block;padding:2px 8px;margin-left:6px;border-radius:7px;font-size:.66rem;font-weight:750;vertical-align:middle}
.tag.action{background:rgba(124,108,255,.22);color:#d2caff;border:1px solid rgba(124,108,255,.4)}
.tag.decision{background:rgba(16,185,129,.18);color:#7ce9c0;border:1px solid rgba(16,185,129,.4)}
.tag.high{background:rgba(255,92,108,.18);color:#ff9ca8;border:1px solid rgba(255,92,108,.4)}
.tag.medium{background:rgba(255,176,32,.15);color:#ffd27a;border:1px solid rgba(255,176,32,.4)}
.tag.low{background:rgba(46,211,160,.14);color:#7af0cb;border:1px solid rgba(46,211,160,.4)}
.src-count{margin-left:auto;white-space:nowrap;font-size:.74rem;color:#9ba8c9}
.bubble{background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.09);border-radius:4px 14px 14px 14px;padding:10px 13px;margin:7px 0;color:#e6e9f5;font-size:.88rem}
.bubble .who{font-weight:750;color:#b7abff;font-size:.78rem}.bubble .ts{color:#8f99c2;font-size:.7rem;margin-left:7px}
mark { background: rgba(255, 235, 59, 0.35); color: #fff; padding: 2px 4px; border-radius: 4px; font-weight: 600; }
.answer{background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:18px 21px;margin:14px 0;color:#edf0fb}
.ok{color:#35d6a1;font-weight:700;font-size:.85rem}.warn{color:#ffb020;font-weight:700;font-size:.85rem}
.topic-row{display:flex;align-items:center;gap:10px;padding:10px 2px;border-top:1px solid rgba(255,255,255,.06);font-size:.85rem;color:#e6e9f5}
.topic-dot{width:9px;height:9px;border-radius:50%;flex:none}.topic-count{margin-left:auto;color:#9ba8c9}
[data-testid="stExpander"]{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.09)!important;border-radius:12px;margin-bottom:7px}
[data-testid="stExpander"] summary p{color:#c6cdec;font-size:.82rem}
.stButton button,[data-testid="stFormSubmitButton"] button{border-radius:10px;background:rgba(255,255,255,.09);color:#f5f6ff;border:1px solid rgba(255,255,255,.16);font-weight:650}
.stButton button:hover,[data-testid="stFormSubmitButton"] button:hover{background:rgba(255,255,255,.16);color:#fff;border-color:rgba(255,255,255,.3)}
.stButton button[kind="primary"],[data-testid="stFormSubmitButton"] button[kind="primary"]{background:linear-gradient(135deg,#7c6cff,#5b4bdb);border:0}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{color:#edf0fb}
[data-testid="stTextInput"] div[data-baseweb="input"],[data-testid="stTextArea"] textarea{background:rgba(255,255,255,.045);border-radius:10px}
[data-testid="stDataFrame"]{border:1px solid rgba(255,255,255,.1);border-radius:12px;overflow:hidden}
hr{border-color:rgba(255,255,255,.09)}
</style>
""", unsafe_allow_html=True)

# ---------------------------- Optional login gate ----------------------------
def require_login():
    """Shown only when APP_PASSWORD is set (use it for any public deployment)."""
    if not APP_PASSWORD or st.session_state.get("authed"):
        return
    st.markdown("### 🔒 AI-Inbox")
    pw = st.text_input("Password", type="password", key="login_pw")
    if pw:
        if hmac.compare_digest(pw.encode(), APP_PASSWORD.encode()):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

require_login()

PALETTE = ["#7C6CFF", "#22B8F0", "#2ED3A0", "#FFB020", "#FF5C6C", "#A855F7"]

def priority(score_value):
    if score_value >= 6:
        return "high", "High"
    if score_value >= 3:
        return "medium", "Medium"
    return "low", "Low"

ACTIVE_ALTS = {}   

def bubbles(messages, quote=None, quote_safe=None):
    """Render message bubbles, highlighting the exact quote if provided."""
    for m in messages:
        st.markdown(
            f"<div class='bubble'><span class='who'>{esc(m.get('sender','Unknown'))}</span>"
            f"<span class='ts'>#{esc(m.get('id',''))} · {esc(m.get('timestamp',''))}</span>"
            f"<div>{highlight(m.get('text', ''), quote, quote_safe, ACTIVE_ALTS)}</div></div>",   
            unsafe_allow_html=True,
        )

def go_ask():
    st.session_state["pending_q"] = st.session_state.get("home_q", "")
    st.session_state["nav"] = "ask"

def open_page(page):
    st.session_state["nav"] = page

def open_priorities():
    st.session_state["digest_filter"] = "Priorities"
    open_page("digest")

def item_title(item):
    return item.get("task") or item.get("decision") or "Untitled item"

def item_matches(item, query, messages):
    if not query:
        return True
    q = query.lower()
    fields = [item_title(item), item.get("topic", ""), item.get("assignee") or "", item.get("deadline") or ""]
    for mid in item.get("source_message_ids", []):
        if mid in messages:
            fields += [messages[mid].get("text", ""), messages[mid].get("sender", "")]
    return any(q in str(value).lower() for value in fields)

def render_items(rows, messages, show_source=True):
    if not rows:
        st.markdown("<div class='subtle'>Nothing here yet. Upload a chat export to populate this view.</div>", unsafe_allow_html=True)
        return
    for index, item in enumerate(rows):
        level, label = priority(item.get("score", 0))
        is_action = item.get("kind") == "action"
        source_ids = item.get("source_message_ids", [])
        topic = esc(item.get("topic") or "General")
        meta = [f"#{topic}"]
        if item.get("assignee"):
            meta.append(esc(item["assignee"]))
        if item.get("deadline"):
            meta.append(f"⏰ {esc(item['deadline'])}")
        first = messages.get(source_ids[0], {}) if source_ids else {}
        if first.get("timestamp"):
            meta.append(esc(first["timestamp"]))
        kind = "Action" if is_action else "Decision"
        icon_class = "" if is_action else " decision"
        icon = "⚡" if is_action else "✓"
        st.markdown(
            f"<div class='item-row'><div class='item-icon{icon_class}'>{icon}</div><div style='flex:1;min-width:0'>"
            f"<div class='item-title'>{esc(item_title(item))}<span class='tag {'action' if is_action else 'decision'}'>{kind}</span>"
            f"<span class='tag {level}'>{label}</span></div><div class='item-meta'>{' · '.join(meta)}</div></div>"
            f"<div class='src-count'>◎ {len(source_ids)} source{'s' if len(source_ids) != 1 else ''}</div></div>",
            unsafe_allow_html=True,
        )
        if show_source:
            with st.expander(f"View source messages · {index + 1}", expanded=False):
                found = [messages[mid] for mid in source_ids if mid in messages]
                if found:
                    bubbles(found, quote=item.get("quote"), quote_safe=item.get("quote_safe"))
                else:
                    st.caption("No source messages are available for this item.")

def page_header(title, subtitle):
    st.markdown(f"<div class='page-head'><h1>{esc(title)}</h1><span>{esc(subtitle)}</span></div>", unsafe_allow_html=True)

# ---------------------------- Backend state ----------------------------
@st.cache_resource(ttl=600, show_spinner=False)
def _maintenance():
    """Create tables and purge expired chats - at most once per 10 minutes, not on every click."""
    db.init()
    return db.purge_old(RETENTION_DAYS)

try:
    _maintenance()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if st.session_state.pop("_reset_chat", False):
    st.session_state.pop("chat", None)
@st.cache_data(ttl=300, show_spinner=False, max_entries=8)
def _load_chat(chat_id):
    """Decrypting every message on every click took ~0.4 s per 5,000 messages."""
    return ({m["id"]: m for m in db.get_messages(chat_id)}, db.get_items(chat_id),
            placeholder_alternatives(db.get_privacy(chat_id)))

if "_new_chat" in st.session_state:
    st.session_state["chat"] = st.session_state.pop("_new_chat")

chat_rows = db.list_chats()
chat_ids = [row[0] for row in chat_rows]
chat_meta = {row[0]: (row[1], row[2]) for row in chat_rows} 
cid = st.session_state.get("chat")
if cid not in chat_ids:
    cid = chat_ids[0] if chat_ids else None
    if cid:
        st.session_state["chat"] = cid

NAV = ["home", "digest", "chats", "ask", "settings", "evaluation"]
NAV_LABELS = {
    "home": "⌂  Dashboard",
    "digest": "▤  Digests",
    "chats": "☷  Chats & Sources",
    "ask": "✦  Ask the Conversation",
    "settings": "⚙  Settings",
    "evaluation": "◫  Extraction & Evaluation",
}
qp = st.query_params.get("page", "home")
if qp not in NAV:
    qp = "home"
if "_last_page" not in st.session_state:
    st.session_state["nav"] = qp
elif qp != st.session_state["_last_page"]:
    st.session_state["nav"] = qp
nav = st.session_state.get("nav", "home")
if nav != qp:
    if nav == "home":
        if "page" in st.query_params:
            del st.query_params["page"]
    else:
        st.query_params["page"] = nav
st.session_state["_last_page"] = nav

# ---------------------------- Sidebar ----------------------------

with st.sidebar:
    st.markdown("<div class='logo'><div class='logo-icon'>📥</div><div>AI-Inbox<div style='font-size:.68rem;color:#9ba8c9;font-weight:500'>From Chats to Clarity</div></div></div>", unsafe_allow_html=True)
    st.radio("Navigation", NAV, format_func=lambda key: NAV_LABELS[key], key="nav", label_visibility="collapsed")
    nav = st.session_state["nav"]
    st.markdown("<div class='side-label'>Your conversations</div>", unsafe_allow_html=True)
    if chat_ids:
        st.radio("Chats", chat_ids, format_func=lambda chat_id: f"◉  {chat_meta[chat_id][0]}",
                 key="chat", label_visibility="collapsed")
        cid = st.session_state.get("chat")
    else:
        cid = None
        st.caption("No chats yet. Add an export to get started.")

    with st.expander("➕ Add a chat", expanded=not chat_ids):
        if MODE == "openai":
            st.caption("🔒 Names and numbers are hidden before text goes to OpenAI.")
        consent = st.checkbox("I have the right to share this chat", key="upload_consent")
        aliases = st.text_input("Your names / nicknames", placeholder="e.g. Rahul, Rahu", key="upload_aliases")
        chat_name = st.text_input("Chat name", "My chat", key="upload_chat_name")
        uploaded = st.file_uploader("WhatsApp export (.txt)", type=["txt"], key="whatsapp_upload")
        if st.button("🚀 Analyze chat", use_container_width=True, type="primary"):
            if uploaded is None:
                st.warning("Please choose a .txt file first.")
            elif not consent:
                st.warning("Please confirm you have permission to process this chat.")
            elif uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.warning(f"File is larger than {MAX_UPLOAD_MB} MB.")
            else:
                os.makedirs(RAW_DIR, exist_ok=True)
                
                file_path = os.path.join(RAW_DIR, f"upload_{uuid.uuid4().hex}.txt")
                try:
                    with open(file_path, "wb") as handle:
                        handle.write(uploaded.getbuffer())
                    with st.spinner("Reading, protecting and analyzing the conversation..."):
                        info = process(file_path, chat_name.strip() or "My chat",
                                       [a.strip() for a in aliases.split(",") if a.strip()])
                    st.session_state["_new_chat"] = info["chat_id"]
                    st.session_state["_upload_notice"] = {"stats": info["stats"], "raw_deleted": info["raw_deleted"]}
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not process this chat: {exc}")
                finally:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except OSError:
                        pass

    if cid:
        with st.expander("🗑 Delete chat data"):
            st.warning("This permanently removes this chat and its stored data.")
            if st.button("Delete this chat", use_container_width=True, key="delete_chat"):
                db.delete_chat(cid)
                _load_chat.clear()
                st.session_state["_reset_chat"] = True
                st.rerun()

    created = chat_meta[cid][1] if cid in chat_meta else None
    synced = time.strftime("%H:%M", time.localtime(created)) if created is not None else "Unknown"
    st.markdown(f"<div class='status'><div class='pulse'></div><div><b>Workspace ready</b><br><span>Last synced {synced}</span></div></div>", unsafe_allow_html=True)
    st.caption(f"AI mode: {MODE} · Retention: {RETENTION_DAYS} days")

# ---------------------------- Active chat data (loaded once) ----------------------------
messages = {}
items = []
if cid:
    messages, items, ACTIVE_ALTS = _load_chat(cid)
chat_title = chat_meta[cid][0] if cid in chat_meta else ""   # BUG FIX #24 (see notes)
action_items = [item for item in items if item.get("kind") == "action"]
decisions = [item for item in items if item.get("kind") == "decision"]
high_items = [item for item in items if item.get("score", 0) >= 6]
n_messages, n_actions, n_decisions, n_high = len(messages), len(action_items), len(decisions), len(high_items)


notice = st.session_state.pop("_upload_notice", None)
if notice:
    stats = notice["stats"]
    st.success(f"Analyzed {stats['messages']} messages → {stats['actions']} action items, {stats['decisions']} decisions.")
    if stats.get("failed_chunks"):
        st.warning(f"{stats['failed_chunks']} of {stats['total_chunks']} AI calls failed, so results may be incomplete. "
                   f"First error: {(stats.get('errors') or ['unknown'])[0]}")
    if stats.get("rejected_by_verification"):
        st.caption(f"{stats['rejected_by_verification']} extracted item(s) were rejected because they could not be verified against the chat.")
    if not notice.get("raw_deleted", True):
        st.warning("The raw uploaded file could not be deleted automatically. Please remove it from the data/raw folder.")

# ---------------------------- Top bar ----------------------------
top_left, top_right = st.columns([5, 1])
with top_left:
    query = st.text_input("Search messages, topics, or people", placeholder="Search messages, topics, or people...", label_visibility="collapsed", key="global_search")
with top_right:
    urgent = sorted(high_items, key=lambda item: item.get("score", 0), reverse=True)
    with st.popover(f"🔔 {len(urgent)}" if urgent else "🔔", use_container_width=True):
        st.markdown("**Priority notifications**")
        if not urgent:
            st.caption("No high-priority items found.")
        for item in urgent[:8]:
            st.markdown(f"🔴 **{esc(item_title(item))}**  \nScore: {item.get('score', 0)} · Deadline: {esc(item.get('deadline') or 'Not specified')}", unsafe_allow_html=True)
        st.button("Open priorities", use_container_width=True, on_click=open_priorities)

# ---------------------------- Empty state ----------------------------
if not cid:
    st.markdown(f"""<div class='hero' style='margin-top:12px'><h1>✨ AI-Inbox for Conversation</h1>
    <p>Turn noisy group chats into clear tasks, decisions and answers, with every item linked to its source.</p>
    <span class='pill'>Source-grounded</span><span class='pill'>Privacy-first</span><span class='pill'>Mode: {esc(MODE)}</span></div>""", unsafe_allow_html=True)
    st.info("Open **Add a chat** in the sidebar, upload a WhatsApp `.txt` export, confirm consent, and click Analyze.")
    st.stop()

filtered = [item for item in items if item_matches(item, query, messages)]

# ---------------------------- Dashboard ----------------------------
if nav == "home":
    left, right = st.columns([1.7, 1])
    with left:
        st.markdown(f"""<div class='hero'><h1>✨ AI-Inbox for Conversation</h1>
        <p>Turn noisy group chats into clear tasks, decisions and answers — with every insight linked to its original message.</p>
        <span class='pill'>Source-grounded</span><span class='pill'>Privacy-first</span><span class='pill'>Mode: {esc(MODE)}</span></div>""", unsafe_allow_html=True)
    with right:
        st.markdown(f"""<div class='metrics'><div class='metric'><div class='num'>{n_messages}</div><div class='lbl'>Messages indexed</div></div>
        <div class='metric'><div class='num'>{n_actions}</div><div class='lbl'>Action items</div></div>
        <div class='metric'><div class='num'>{n_decisions}</div><div class='lbl'>Decisions</div></div>
        <div class='metric'><div class='num'>{n_high}</div><div class='lbl'>High priority</div></div></div>""", unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    main_col, side_col = st.columns([1.55, 1])
    with main_col:
        with st.container(key="card_recent"):
            st.markdown("<div class='card-head'>Recent extracted insights <span class='subtle'>Source-linked</span></div>", unsafe_allow_html=True)
            options = ["All", "Action Items", "Decisions", "Priorities"]
            selected_filter = st.radio("Filter insights", options, horizontal=True, key="home_filter", label_visibility="collapsed")
            rows = filtered
            if selected_filter == "Action Items":
                rows = [item for item in rows if item.get("kind") == "action"]
            elif selected_filter == "Decisions":
                rows = [item for item in rows if item.get("kind") == "decision"]
            elif selected_filter == "Priorities":
                rows = [item for item in rows if item.get("score", 0) >= 6]
            rows = sorted(rows, key=lambda item: max(item.get("source_message_ids") or [0]), reverse=True)
            render_items(rows[:7], messages)
    with side_col:
        with st.container(key="card_topics"):
            st.markdown("<div class='card-head'>Topics in this chat</div>", unsafe_allow_html=True)
            topic_counts = Counter(item.get("topic") or "General" for item in items)
            if topic_counts:
                for idx, (topic, count) in enumerate(topic_counts.most_common(7)):
                    st.markdown(f"<div class='topic-row'><span class='topic-dot' style='background:{PALETTE[idx % len(PALETTE)]}'></span><span>{esc(topic)}</span><span class='topic-count'>{count}</span></div>", unsafe_allow_html=True)
            else:
                st.caption("Topics appear after extraction.")
        with st.container(key="askcard"):
            st.markdown("<div style='font-weight:800;color:#fff;font-size:1rem'>✦ Ask the Conversation</div><div class='subtle' style='margin:4px 0 10px'>Get answers grounded in your chat history.</div>", unsafe_allow_html=True)
            with st.form("home_ask_form"):
                st.text_input("Question", placeholder="e.g. What deadlines were mentioned?", key="home_q", label_visibility="collapsed")
                st.form_submit_button("Ask AI →", on_click=go_ask, use_container_width=True)

# ---------------------------- Digests ----------------------------
elif nav == "digest":
    page_header("Conversation Digest", f"{chat_title} · {len(items)} extracted items")
    tabs = st.tabs(["All insights", f"Action Items ({n_actions})", f"Decisions ({n_decisions})", f"Priorities ({n_high})", "Topics"])
    with tabs[0]:
        st.markdown(f"<span class='tag high'>High · {sum(1 for x in items if priority(x.get('score',0))[0]=='high')}</span><span class='tag medium'>Medium · {sum(1 for x in items if priority(x.get('score',0))[0]=='medium')}</span><span class='tag low'>Low · {sum(1 for x in items if priority(x.get('score',0))[0]=='low')}</span>", unsafe_allow_html=True)
        render_items(filtered, messages)
    with tabs[1]:
        render_items([item for item in filtered if item.get("kind") == "action"], messages)
    with tabs[2]:
        render_items([item for item in filtered if item.get("kind") == "decision"], messages)
    with tabs[3]:
        render_items(sorted([item for item in filtered if item.get("score", 0) >= 6], key=lambda item: item.get("score", 0), reverse=True), messages)
    with tabs[4]:
        topic_counts = Counter(item.get("topic") or "General" for item in items)
        if topic_counts:
            for idx, (topic, count) in enumerate(topic_counts.most_common()):
                with st.container(border=True):
                    st.markdown(f"<div class='topic-row'><span class='topic-dot' style='background:{PALETTE[idx % len(PALETTE)]}'></span><b>{esc(topic)}</b><span class='topic-count'>{count} items</span></div>", unsafe_allow_html=True)
                    render_items([item for item in items if (item.get("topic") or "General") == topic], messages, show_source=False)
        else:
            st.info("No topic labels found in the current chat.")

# ---------------------------- Chat explorer / source links ----------------------------
elif nav == "chats":
    page_header("Chats & Source Links", f"{chat_title} · {n_messages} messages")
    left, right = st.columns([1, 1.05])
    with left:
        st.markdown("<div class='section-title'>Original messages</div>", unsafe_allow_html=True)
        msg_query = st.text_input("Search this chat", placeholder="Search sender or message text...", key="message_search")
        all_messages = list(messages.values())
        all_messages.sort(key=lambda msg: int(msg.get("id", 0)), reverse=True)
        visible = [msg for msg in all_messages if msg_query.lower() in (str(msg.get("text", "")) + str(msg.get("sender", "")) + str(msg.get("id", ""))).lower()]
        if not visible:
            st.info("No messages match that search.")
        for msg in visible[:100]:
            mid = str(msg.get("id", ""))
            with st.expander(f"{msg.get('sender','Unknown')} · #{mid} · {msg.get('timestamp','')}", expanded=False):
                st.text(msg.get("text", ""))
                linked = [item for item in items if mid in [str(value) for value in item.get("source_message_ids", [])]]
                if linked:
                    st.caption(f"{len(linked)} extracted item(s) linked to this message")
                    for item in linked:
                        st.markdown(f"• **{esc(item_title(item))}** — {esc(item.get('kind','item'))}", unsafe_allow_html=True)
                else:
                    st.caption("No extracted item linked to this message.")
    with right:
        st.markdown("<div class='section-title'>Trace extracted items</div>", unsafe_allow_html=True)
        source_options = ["Choose an item"] + [f"{idx+1}. {item_title(item)[:75]}" for idx, item in enumerate(items)]
        chosen = st.selectbox("Select an extracted item", source_options, label_visibility="collapsed")
        if chosen != "Choose an item":
            item_idx = source_options.index(chosen) - 1
            selected_item = items[item_idx]
            lvl, label = priority(selected_item.get("score", 0))
            st.markdown(f"<div class='answer'><b>{esc(item_title(selected_item))}</b><br><span class='tag {lvl}'>{label} priority</span><span class='tag {'action' if selected_item.get('kind')=='action' else 'decision'}'>{esc(selected_item.get('kind','item').title())}</span><p class='subtle'>Topic: {esc(selected_item.get('topic') or 'General')} · Assignee: {esc(selected_item.get('assignee') or 'Unassigned')} · Deadline: {esc(selected_item.get('deadline') or 'Not specified')}</p></div>", unsafe_allow_html=True)
            source_messages = [messages[mid] for mid in selected_item.get("source_message_ids", []) if mid in messages]
            st.markdown("**Original evidence**")
            if source_messages:
                bubbles(source_messages, quote=selected_item.get("quote"), quote_safe=selected_item.get("quote_safe"))
            else:
                st.warning("The stored source IDs do not resolve to messages in this chat.")
            st.caption("Evidence shown here comes from the existing database records; this screen does not generate new source claims.")

# ---------------------------- Ask the Conversation ----------------------------
elif nav == "ask":
    page_header("Ask the Conversation", "Answers are checked against messages from the selected chat.")
    with st.container(key="card_ask"):
        st.markdown("<div style='font-weight:800;color:#fff;font-size:1rem'>✦ Conversation Q&A</div><div class='subtle'>Ask about decisions, deadlines, people, or commitments.</div>", unsafe_allow_html=True)
        pending = st.session_state.pop("pending_q", "")
        with st.form("ask_form"):
            question = st.text_input("Your question", value=pending, placeholder="Ask anything about this conversation...", label_visibility="collapsed")
            submitted = st.form_submit_button("Search conversation ✦", type="primary")
    if question.strip() and (submitted or pending):
        with st.spinner("Searching messages and verifying the answer..."):
            result = search.ask(cid, question)
        verified = bool(result.get("verified"))
        if result.get("derived"):
            badge = "<span class='ok'>✔ Built from verified extracted items</span>"
        elif verified:
            badge = "<span class='ok'>✔ Verified against source messages</span>"
        else:
            badge = "<span class='warn'>⚠ Could not verify completely</span>"
        st.markdown(f"<div class='answer'>{esc(result.get('answer','No answer returned.'))}<br><br>{badge}</div>", unsafe_allow_html=True)
        if not verified and result.get("reason"):
            st.caption(f"Verification detail: {result['reason']}")
        sources = result.get("sources") or []
        if sources:
            st.markdown("**Source messages**")
            bubbles(sources, quote=result.get("quote"), quote_safe=result.get("quote_safe"))
        elif result.get("retrieved"):
            with st.expander("Closest retrieved messages"):
                bubbles(result["retrieved"], quote=result.get("quote"), quote_safe=result.get("quote_safe"))
        elif not result.get("derived"):
            st.info("No source messages were returned for this answer.")
    else:
        st.markdown("<div class='subtle'>Suggested questions</div>", unsafe_allow_html=True)
        suggestions = ["What are the key decisions?", "Which tasks have deadlines?", "What was assigned to me?", "Summarize the main topics."]
        cols = st.columns(2)
        for idx, suggestion in enumerate(suggestions):
            with cols[idx % 2]:
                if st.button(suggestion, key=f"suggest_{idx}", use_container_width=True):
                    st.session_state["pending_q"] = suggestion
                    st.rerun()

# ---------------------------- Settings & privacy (read-only, shows REAL config) ----------------------------
elif nav == "settings":
    page_header("Settings & Privacy", "Current configuration (change it in your .env file and restart)")
    privacy_tab, scoring_tab, storage_tab = st.tabs(["Privacy controls", "Importance scoring", "Storage"])
    with privacy_tab:
        st.markdown("<div class='section-title'>Data protection</div>", unsafe_allow_html=True)
        st.info("These values come from your configuration and are read-only. The old toggles and sliders did nothing, so they were removed.")
        st.dataframe(pd.DataFrame([
            {"Setting": "AI mode", "Value": MODE},
            {"Setting": "Regex redaction (phones, emails, links, PAN, Aadhaar, bank no., OTP)", "Value": "Always on"},
            {"Setting": "Presidio name/place detection", "Value": "On" if USE_PRESIDIO else "Off"},
            {"Setting": "Raw upload deleted after processing", "Value": "Always (web upload)"},
            {"Setting": "Automatic retention (days)", "Value": str(RETENTION_DAYS)},
            {"Setting": "Login password", "Value": "Enabled" if APP_PASSWORD else "Not set"},
        ]), hide_index=True, use_container_width=True)
    with scoring_tab:
        st.markdown("<div class='section-title'>Importance scoring weights</div>", unsafe_allow_html=True)
        st.caption("Weights come from score.py. Edit WEIGHTS there to change them.")
        st.dataframe(pd.DataFrame([{"Signal": k, "Points": v} for k, v in score.WEIGHTS.items()]), hide_index=True, use_container_width=True)
        st.caption("Urgency words: " + ", ".join(score.URGENT_WORDS))
    with storage_tab:
        st.markdown("<div class='section-title'>Application storage</div>", unsafe_allow_html=True)
        st.code(f"Raw upload directory: {RAW_DIR}\nConfigured retention: {RETENTION_DAYS} days\nAI mode: {MODE}\nDatabase + search index: encrypted, managed by db.py / search.py")
        st.caption("Use 'Delete this chat' in the sidebar to remove a chat together with its search index.")

# ---------------------------- Extraction & evaluation ----------------------------
elif nav == "evaluation":
    page_header("Extraction & Evaluation", "Review available extraction data and source-validation status")

    total_items = len(items)
    sourced_items = sum(1 for item in items if item.get("source_message_ids") and any(mid in messages for mid in item.get("source_message_ids", [])))
    source_coverage = sourced_items / total_items if total_items else 0.0
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div class='metrics' style='min-height:115px;grid-template-columns:1fr'><div class='metric' style='border:0'><div class='num'>{total_items}</div><div class='lbl'>Extracted items</div></div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='metrics' style='min-height:115px;grid-template-columns:1fr'><div class='metric' style='border:0'><div class='num'>{sourced_items}</div><div class='lbl'>Items with resolvable sources</div></div></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='metrics' style='min-height:115px;grid-template-columns:1fr'><div class='metric' style='border:0'><div class='num'>{source_coverage:.0%}</div><div class='lbl'>Source coverage (not precision)</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("<div class='section-title'>Extracted item breakdown</div>", unsafe_allow_html=True)
        breakdown = pd.DataFrame([
            {"Type": "Action items", "Count": len(action_items)},
            {"Type": "Decisions", "Count": len(decisions)},
            {"Type": "High priority", "Count": len(high_items)},
            {"Type": "Items without a deadline", "Count": sum(1 for item in action_items if not item.get("deadline"))},
        ])
        st.bar_chart(breakdown.set_index("Type"), height=280)
    with right:
        st.markdown("<div class='section-title'>Source validation overview</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([
            {"Check": "Extracted items", "Count": total_items},
            {"Check": "Items with at least one resolvable source", "Count": sourced_items},
            {"Check": "Items without resolvable sources", "Count": total_items - sourced_items},
            {"Check": "Messages stored", "Count": n_messages},
        ]), hide_index=True, use_container_width=True)
        st.warning("Precision, recall, and F1 need hand-labeled ground truth. Run `python evaluation/evaluate.py` to compute them.")

if st.session_state.get("nav", "home") != st.query_params.get("page", "home"):
    current = st.session_state["nav"]
    if current == "home":
        if "page" in st.query_params:
            del st.query_params["page"]
    else:
        st.query_params["page"] = current
