import re
import unicodedata

from privacy import KINDS

LEAD = re.compile(r"^\s*\[\d+\]\s*[^:]{1,60}:\s*")

# Placeholder tokens (PERSON_1, ME ...) carry no meaning for the entailment check
_PLACEHOLDER_TOKEN = re.compile(rf"\b(?:{'|'.join(KINDS)})_\d+\b|\bME\b")
STOPWORDS = {"the", "a", "an", "is", "are", "to", "and", "or", "in", "on", "at", "by",
             "for", "with", "this", "that", "will", "please"}
# BUG FIX #10: share of the task's meaningful words that must appear in the quote
MIN_OVERLAP_RATIO = 0.34

def _norm(s):
    """Lower-case, NFKC-normalise and drop punctuation.
    BUG FIX #17: keep letters (L*), combining marks (M*) and digits (N*) so Hindi /
    Devanagari words are no longer shredded into single characters."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in s)
    return re.sub(r"\s+", " ", s).strip()

def _stem(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word

def entailment_check(item_text, quote_text, min_ratio=MIN_OVERLAP_RATIO):
    """Checks that enough of the task summary's words really occur in the quoted text."""
    if not item_text or not quote_text:
        return True
    item_words = _norm(_PLACEHOLDER_TOKEN.sub(" ", item_text)).split()
    meaningful = {_stem(w) for w in item_words if len(w) > 2 and w not in STOPWORDS}
    if not meaningful:
        return True
    quote_stems = {_stem(w) for w in _norm(quote_text).split()}
    overlap = meaningful & quote_stems
    return len(overlap) / len(meaningful) >= min_ratio

def check(source_ids, quote, by_id, item_text=None):
    if not source_ids:
        return False, "No source message cited"
    missing = [i for i in source_ids if i not in by_id]
    if missing:
        return False, f"Cited message(s) {missing} missing from context"
    if not quote or not quote.strip():
        return False, "Empty quote"

    cleaned_quote = LEAD.sub("", quote.strip())
    norm_quote = _norm(cleaned_quote)
    words = norm_quote.split()

    if len(norm_quote) < 10 or len(words) < 3:
        return False, "Quote too short (minimum 10 characters and 3 words required)"

    text = " " + _norm(" ".join(by_id[i]["text"] for i in source_ids if i in by_id)) + " "
    parts = re.split(r"\.\.\.|\u2026", cleaned_quote)
    frags = [_norm(p) for p in parts if _norm(p)]

    pos = 0
    for f in frags:
        padded = " " + f + " "
        i = text.find(padded, pos)
        if i < 0:
            return False, "Quote phrase not found in source text"
        pos = i + len(padded) - 1

    if item_text and not entailment_check(item_text, cleaned_quote):
        return False, "Extracted task summary does not align semantically with the quoted source text"

    return True, "ok"

def verify(source_ids, quote, by_id, item_text=None):
    return check(source_ids, quote, by_id, item_text)[0]


# ---------------------------------------------------------------------------------------------
# Grounding of the optional fields. The exact-quote check proves a TASK exists in the chat, but
# `assignee` and `deadline` used to be accepted from the model without any look at the source.
# Unsupported values are removed (the item itself is kept) - never invented.
# ---------------------------------------------------------------------------------------------
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_DATE_NAMES = _WEEKDAYS + _MONTHS
_DEADLINE_STOP = STOPWORDS | {"before", "till", "until", "end", "eod", "next", "coming", "upcoming",
                              "from", "within", "latest", "day", "date", "time", "of", "the"}
_RELATIVE = {
    "today": {"today", "aaj", "tdy", "2day"},
    "tomorrow": {"tomorrow", "kal", "tmrw", "tmr", "2morrow"},
    "tonight": {"tonight", "aaj", "raat", "tnite"},
    "week": {"week", "hafta", "saptah", "wk"},
    "weekend": {"weekend", "sat", "sun", "saturday", "sunday"},
    "morning": {"morning", "subah"},
    "evening": {"evening", "shaam"},
    "noon": {"noon", "dopahar"},
    "asap": {"asap", "urgent", "immediately", "jaldi"},
}
_ASSIGNEE_PLACEHOLDER = re.compile(r"PERSON_\d+")

def _date_key(token):
    """'fri' / 'friday' -> 'fri', 'sept' / 'september' -> 'sep' (None if not a weekday/month name)."""
    if len(token) >= 3:
        for name in _DATE_NAMES:
            if name.startswith(token):
                return name[:3]
    return None

def _support_keys(text):
    keys = set()
    for tok in _norm(text).split():
        keys.add(tok)
        key = _date_key(tok)
        if key:
            keys.add("date:" + key)
        for num in re.findall(r"\d+", tok):
            keys.add("num:" + str(int(num)))
    return keys

def deadline_supported(deadline, source_text):
    """True if at least one meaningful part of the deadline (a weekday/month, a number, a relative
    word like today / kal) occurs in the cited messages. A deadline with nothing checkable passes."""
    if not deadline:
        return True
    required = [t for t in _norm(deadline).split() if t not in _DEADLINE_STOP]
    if not required:
        return True
    src = _support_keys(source_text)
    for tok in required:
        if tok in src:
            return True
        key = _date_key(tok)
        if key and "date:" + key in src:
            return True
        if any("num:" + str(int(n)) in src for n in re.findall(r"\d+", tok)):
            return True
        for canon, variants in _RELATIVE.items():
            if (tok == canon or tok in variants) and ((variants | {canon}) & src):
                return True
    return False

def assignee_supported(assignee, source_ids, by_id):
    """An assignee given as ME / PERSON_n must be the sender of a cited message or be named in it.
    Free text such as 'Everyone' is not checked."""
    if not assignee:
        return True
    key = "ME" if assignee.strip().lower() in ("me", "you") else assignee.strip()
    if key != "ME" and not _ASSIGNEE_PLACEHOLDER.fullmatch(key):
        return True
    for i in source_ids:
        msg = by_id.get(i)
        if not msg:
            continue
        if msg.get("sender", "") == key:
            return True
        if re.search(rf"(?<![\w-]){re.escape(key)}(?!\w)", msg.get("text", "")):
            return True
    return False

def ground_fields(assignee, deadline, source_ids, by_id):
    """-> (assignee_ok, deadline_ok). `by_id` holds the anonymised messages (sender + text)."""
    source_text = " ".join(by_id[i].get("text", "") for i in source_ids if i in by_id)
    return (assignee_supported(assignee, source_ids, by_id),
            deadline_supported(deadline, source_text))