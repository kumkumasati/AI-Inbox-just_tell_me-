import re

WEIGHTS = {"deadline": 3, "mention": 3, "urgent": 2}
URGENT_WORDS = [
    "urgent", "asap", "today", "immediately", "right now", "tonight", "eod",
    "jaldi", "turant", "aaj", "kal", "zaroori", "fatafat"
]
# BUG FIX #23: the model may answer "ME", "me" or "You" - all mean the current user
SELF_NAMES = {"me", "you"}

def score_item(original_text, deadline, assignee, my_aliases):
    text = original_text.lower()
    score, reasons = 0, []
    if deadline:
        score += WEIGHTS["deadline"]
        reasons.append("has deadline")
    mentioned = (assignee or "").strip().lower() in SELF_NAMES or any(
        re.search(rf"(?<!\w){re.escape(a.lower().strip())}(?!\w)", text) for a in my_aliases if a.strip()
    )
    if mentioned:
        score += WEIGHTS["mention"]
        reasons.append("mentions you")
    if any(re.search(rf"\b{re.escape(w)}\b", text) for w in URGENT_WORDS):
        score += WEIGHTS["urgent"]
        reasons.append("urgent word")
    return score, reasons