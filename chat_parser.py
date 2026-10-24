import re

SEP = r"[/.\-]"
DATE = rf"(?:\d{{4}}{SEP}\d{{1,2}}{SEP}\d{{1,2}}|\d{{1,2}}{SEP}\d{{1,2}}{SEP}\d{{2,4}})"
TIME = r"\d{1,2}:\d{2}(?::\d{2})?\s?(?:[ap]\.?m\.?)?"
# A real WhatsApp header ALWAYS has a separator: Android "DATE, TIME - rest", iOS "[DATE, TIME] rest".
# BUG FIX: the old pattern made the separator optional, so a message line such as
# "13/03/2025 10:00 team sync" was mistaken for a new system line and the message was truncated.
START_ANDROID = re.compile(rf"^({DATE}),?\s+({TIME})\s*[-–—]\s*(.*)$", re.I)
START_IOS = re.compile(rf"^\[({DATE}),?\s+({TIME})\]\s*(.*)$", re.I)

def _match_start(line):
    return START_IOS.match(line) or START_ANDROID.match(line)

SKIP_TEXT = re.compile(
    r"^(<media omitted>"
    r"|<attached:.*>"
    r"|.*\(file attached\)"
    r"|\[?(image|video|audio|sticker|gif|document|contact card|location)\s+omitted\]?"
    r"|this message was deleted\.?"
    r"|you deleted this message\.?"
    r"|null)$",
    re.I,
)
EDITED_SUFFIX = re.compile(r"\s*<this message was edited>\s*$", re.I)

SYSTEM_SENDER = re.compile(
    r"\bchanged (the |this )?(group|subject|icon|description|settings)"
    r"|\bchanged (their|his|her) (phone|number)"
    r"|\bchanged to\b|\bcreated (group|this group)\b|\bpinned a message\b"
    r"|\bsecurity code\b|\b(added|removed|left|joined)\b.*\b(group|you|invite)\b",
    re.I,
)
# zero-width / bidi control characters WhatsApp sprinkles into exports
INVISIBLE = dict.fromkeys(
    [0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0xFEFF], None
)

# BUG FIX #2: case-insensitive, also catches attributes like <untrusted_message id=1>
PROMPT_TAG = re.compile(r"<\s*/?\s*untrusted_message\b[^>]*>", re.I)

def _clean(line: str) -> str:
    cleaned = line.replace("\u00a0", " ").replace("\u202f", " ")
    cleaned = cleaned.translate(INVISIBLE).rstrip("\r\n")
    # Neutralise any attempt to fake / close our <untrusted_message> wrapper
    return PROMPT_TAG.sub(lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"), cleaned)

def _clean_sender(sender: str) -> str:
    # BUG FIX #21: iOS marks non-contacts as "~ Name"
    return sender.strip().lstrip("~").strip()

def parse_text(text: str):
    messages, cur = [], None
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        m = _match_start(line)
        if m:
            if cur:
                messages.append(cur)
                cur = None
            rest = m.group(3)
            if ": " not in rest:
                continue
            sender, body = rest.split(": ", 1)
            if SYSTEM_SENDER.search(sender) or len(sender) > 60:
                continue
            sender = _clean_sender(sender)
            body = EDITED_SUFFIX.sub("", body).strip()
            if not sender or not body or SKIP_TEXT.match(body):
                continue
            cur = {
                "id": 0,
                # BUG FIX #12: no trailing space in the timestamp
                "timestamp": f"{m.group(1)} {m.group(2).strip()}",
                "sender": sender,
                "text": body,
            }
        elif cur is not None:
            cur["text"] += "\n" + line.strip()
    if cur:
        messages.append(cur)
    for i, m in enumerate(messages, 1):
        m["id"] = i
    return messages

def parse_chat(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return parse_text(f.read())