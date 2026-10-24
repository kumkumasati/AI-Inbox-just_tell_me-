"""Small HTML helpers used by app.py (kept free of Streamlit so they can be unit-tested)."""
import html
import re

from privacy import KINDS

_ELLIPSIS = re.compile(r"\.\.\.|\u2026")
_PLACEHOLDER = re.compile(rf"(\b(?:{'|'.join(KINDS)})_\d+\b|(?<![\w-])ME(?![\w-]))")

def esc(value):
    return html.escape(str(value)).replace("\n", "<br>")

def _split(quote):
    return [f.strip() for f in _ELLIPSIS.split(quote or "")]

def placeholder_alternatives(privacy):
    """Placeholder -> every real string it may stand for in the ORIGINAL messages
    (full name, first name, the user's aliases, the phone number...). Built from the
    privacy record that db.get_privacy() returns, so highlighting is exact."""
    alts = {}
    for real, placeholder in (privacy or {}).get("map", {}).items():
        alts.setdefault(placeholder, set()).add(real)
    for placeholder, real in (privacy or {}).get("names", {}).items():
        if placeholder != "ME":                       # ME -> "You" is only a display label
            alts.setdefault(placeholder, set()).add(real)
    return alts

def _placeholder_patterns(fragment_safe, alternatives=None):
    """Candidate regexes for an anonymised quote, best first.
    Placeholders found in `alternatives` match exactly those real strings; any other
    placeholder falls back to text of the right SHAPE (name = 1-3 words, phone = digits,
    link/email = one token), so neighbouring words are never swallowed."""
    alternatives = alternatives or {}
    parts = _PLACEHOLDER.split(fragment_safe)
    literal = "".join(parts[0::2])
    if not re.search(r"\w", literal):          # only placeholders, e.g. just "ME": would match anything
        return []
    patterns, seen = [], set()
    for words in (1, 2, 3):
        name = r"\w+" + r"(?: \w+)" * (words - 1)
        regex = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                regex += re.escape(html.escape(part)) if part else ""
                continue
            options = alternatives.get(part)
            kind = part.split("_")[0]
            if options:
                ordered = sorted(options, key=len, reverse=True)
                regex += "(?:" + "|".join(re.escape(html.escape(o)) for o in ordered) + ")"
            elif kind in ("PHONE", "AADHAAR", "BANK", "OTP", "CARD"):
                regex += r"[+\d][\d \-]*\d"
            elif kind in ("EMAIL", "LINK", "PAN"):
                regex += r"\S+"
            else:                                   # PERSON, PLACE, ME (unknown)
                regex += name
        if regex not in seen:
            seen.add(regex)
            patterns.append(re.compile(regex, re.IGNORECASE))
    return patterns

def highlight(text, quote=None, quote_safe=None, alternatives=None):
    """Escape the WHOLE message first, then wrap the quote in <mark> (prevents stored XSS).
    If the de-anonymised quote is not found verbatim (names differ in case/form), fall back
    to matching the anonymised quote with placeholders as wildcards."""
    safe = html.escape(text or "")
    q_frags = _split(quote)
    s_frags = _split(quote_safe)
    if len(s_frags) != len(q_frags):
        s_frags = [""] * len(q_frags)
    for qf, sf in zip(q_frags, s_frags):
        candidates = []
        if qf:
            candidates.append(re.compile(re.escape(html.escape(qf)), re.IGNORECASE))
        if sf:
            candidates += _placeholder_patterns(sf, alternatives)
        for pat in candidates:
            if pat.search(safe):
                safe = pat.sub(lambda m: f"<mark>{m.group(0)}</mark>", safe, count=1)
                break
    return safe.replace("\n", "<br>")