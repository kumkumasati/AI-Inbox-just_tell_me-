"""Step 1: read a WhatsApp export (.txt) into a list of messages.

Fixes (bug #9): BOM-safe open, dates written with '.' or '-' (12.03.25), iOS
"<attached: ...>" lines skipped, and system lines such as
`Rahul changed the subject to "Re: x"` (which contain ': ') are no longer read as messages.
"""
import re

SEP = r"[/.\-]"
DATE = rf"\d{{1,2}}{SEP}\d{{1,2}}{SEP}\d{{2,4}}"
START = re.compile(
    rf"^\[?({DATE}),?\s+(\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s?(?:[ap]\.?m\.?)?)\]?\s*[-–]?\s*(.*)$",
    re.I,
)

# Whole-message texts we never want: media placeholders, deleted/edited markers ...
SKIP_TEXT = re.compile(
    r"^(<media omitted>"
    r"|<attached:.*>"                                              # iOS attachments
    r"|.*\(file attached\)"                                        # Android attachments
    r"|\[?(image\vert{}video\vert{}audio\vert{}sticker\vert{}gif\vert{}document\vert{}contact card\vert{}location)\s+omitted\]?"
    r"|this message was deleted\.?"
    r"|you deleted this message\.?"
    r"|null)$",
    re.I,
)
EDITED_SUFFIX = re.compile(r"\s*<this message was edited>\s*$", re.I)

# Group-event lines that WhatsApp writes in the same "date - X: Y" shape as messages.
SYSTEM_SENDER = re.compile(
    r"\bchanged (the |this )?(group|subject|icon|description|settings)"
    r"|\bchanged (their|his|her) (phone|number)"
    r"|\bchanged to\b|\bcreated (group|this group)\b|\bpinned a message\b"
    r"|\bsecurity code\b|\b(added|removed|left|joined)\b.*\b(group|you|invite)\b",
    re.I,
)
INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮"), None)


def _clean(line):
    return line.replace(" ", " ").replace(" ", " ").translate(INVISIBLE).rstrip("\r\n")


def parse_text(text):
    """Parse the TEXT of an export -> [{id, timestamp, sender, text}, ...]."""
    messages, cur = [], None
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        m = START.match(line)
        if m:
            if cur:
                messages.append(cur)
                cur = None
            rest = m.group(3)
            if ": " not in rest:                      # system line like "Messages are encrypted"
                continue
            sender, body = rest.split(": ", 1)
            if SYSTEM_SENDER.search(sender) or len(sender) > 60:
                continue
            body = EDITED_SUFFIX.sub("", body).strip()
            if not body or SKIP_TEXT.match(body):
                continue
            cur = {"id": 0, "timestamp": f"{m.group(1)} {m.group(2)}",
                   "sender": sender.strip(), "text": body}
        elif cur is not None:                         # continuation of a multi-line message
            cur["text"] += "\n" + line.strip()
    if cur:
        messages.append(cur)
    for i, m in enumerate(messages, 1):
        m["id"] = i
    return messages


def parse_chat(path, special_senders=None):
    """Parse a WhatsApp export file into a list of messages.
    
    Accepts an optional `special_senders` argument for backwards compatibility.
    """
    # utf-8-sig removes the BOM some exports start with (a BOM hides the first line's date).
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return parse_text(f.read())