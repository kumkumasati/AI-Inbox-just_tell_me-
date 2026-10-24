import re
from collections import Counter

EMAIL = re.compile(r"[\w\.-]+@[\w\.-]+(?:\.\w+)?")
URL = re.compile(r"https?://\S+")

# Indian mobile numbers: optional +91 / 91 / leading 0, then 10 digits that may be split
# anywhere by a space or hyphen (98765 43210, 9876 543210, 098765 43210, +91-98765-43210)
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9](?:[\s-]?\d){9}(?!\d)")
# Landlines with an STD code: 080-2345-6789, 022 2345 6789
LANDLINE = re.compile(r"(?<!\d)0\d{2,4}(?:[\s-]?\d){6,8}(?!\d)")
# Grouped card numbers: 4111 1111 1111 1111 (Visa/MC style) and 3782 822463 10005 (Amex style)
CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{4,5})(?!\d)")
INTERNATIONAL_PHONE = re.compile(r"(?<!\d)\+(?:[0-9]\s?){6,14}[0-9](?!\d)")

PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I)
# BUG FIX #14: Aadhaar (12 digits, optionally grouped 4-4-4, never starts with 0/1)
AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
BANK_ACC = re.compile(r"\b\d{9,18}\b")
# BUG FIX #11: keep the keyword ("otp", "code"...) and redact only the digits
# also "Your OTP is 482913", "verification code is 123456", "one time password: 1234"
OTP = re.compile(
    r"\b((?i:otp|one[\s-]?time[\s-]?password|verification code|verification|passcode|code|pin)\b"
    r"(?:\s+(?:is|was|number|no\.?))?\s*[:\-=]?\s*)(\d{4,8})\b"
)

KINDS = ("PERSON", "PLACE", "PHONE", "LINK", "EMAIL", "PAN", "CARD", "AADHAAR", "BANK", "OTP")
_KIND_ALT = "|".join(KINDS)

# BUG FIX #19: word boundaries, so "AHMEDABAD" / "HOME" no longer look like the placeholder ME
PLACEHOLDER = re.compile(rf"\b(?:(?:{_KIND_ALT})_\d+|ME)\b")
# BUG FIX #18: "ME" is only restored when it stands alone (not in HOME-ME, ME-based, etc.)
_RESTORE = re.compile(rf"(\b(?:{_KIND_ALT})_\d+\b|(?<![\w-])ME(?![\w-]))")

COMMON_WORDS = {"will", "hope", "may", "grant", "joy", "march", "mark", "rose", "grace"}

def _find_my_senders(senders, aliases):
    """Which sender name(s) in the export are the user?
    Exact alias match wins. Otherwise, if exactly ONE sender contains an alias as a whole
    word (alias 'Rahul' vs export name 'Rahul Sharma') that sender is the user.
    Ambiguous matches (two 'Rahul's) are left alone rather than guessed."""
    exact = {s for s in senders if s.lower() in aliases}
    if exact:
        return exact
    single_word = {a for a in aliases if " " not in a}
    loose = [s for s in senders if single_word & set(re.findall(r"\w+", s.lower()))]
    return set(loose) if len(loose) == 1 else set()

def build_name_map(messages, my_aliases):
    aliases = {a.lower().strip() for a in my_aliases if a.strip()}
    name_map = {a: "ME" for a in aliases}
    names = {"ME": "You"}
    senders = list(dict.fromkeys(m["sender"] for m in messages))
    me_senders = _find_my_senders(senders, aliases)
    for s in me_senders:
        name_map[s.lower()] = "ME"          # BUG FIX: user's full export name -> ME, not PERSON_n
    def first_word(sender):
        parts = sender.lower().split()
        return parts[0] if len(parts) > 1 else None

    first_counts = Counter(f for f in map(first_word, senders) if f)
    n = 0
    for sender in senders:
        low = sender.lower()
        if sender in me_senders or low in aliases:
            continue
        n += 1
        fake = f"PERSON_{n}"
        name_map[low] = fake
        names[fake] = sender

        first = first_word(sender)
        if first and len(first) > 2 and first not in aliases and first not in COMMON_WORDS:
            if first_counts[first] == 1:
                name_map.setdefault(first, fake)
            elif first not in name_map:
                # BUG FIX: "Amit Kumar" and "Amit Shah" share a first name. A bare "Amit" must not be
                # attributed to either of them, so it gets its OWN placeholder, restored as plain "Amit".
                n += 1
                shared = f"PERSON_{n}"
                name_map[first] = shared
                names[shared] = sender.split()[0]
    return name_map, names

def _placeholder(kind, value, names):
    value = value.strip()
    taken = 0
    for key, real in names.items():
        if key.startswith(kind + "_"):
            taken = max(taken, int(key.split("_")[1]))
            if real.lower() == value.lower():
                return key
    key = f"{kind}_{taken + 1}"
    names[key] = value
    return key

def pseudonymize(text, name_map):
    if not name_map:
        return text
    keys = sorted(name_map, key=len, reverse=True)
    pat = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keys) + r")(?!\w)", re.I)
    return pat.sub(lambda m: name_map[m.group(0).lower()], text)

def regex_redact(text, names):
    text = PAN.sub(lambda m: _placeholder("PAN", m.group(0), names), text)
    text = EMAIL.sub(lambda m: _placeholder("EMAIL", m.group(0), names), text)
    text = URL.sub(lambda m: _placeholder("LINK", m.group(0), names), text)
    text = CARD.sub(lambda m: _placeholder("CARD", m.group(0), names), text)   # before PHONE/AADHAAR
    text = PHONE.sub(lambda m: _placeholder("PHONE", m.group(0), names), text)
    text = LANDLINE.sub(lambda m: _placeholder("PHONE", m.group(0), names), text)
    text = INTERNATIONAL_PHONE.sub(lambda m: _placeholder("PHONE", m.group(0), names), text)
    text = AADHAAR.sub(lambda m: _placeholder("AADHAAR", m.group(0), names), text)
    text = BANK_ACC.sub(lambda m: _placeholder("BANK", m.group(0), names), text)
    text = OTP.sub(lambda m: m.group(1) + _placeholder("OTP", m.group(2), names), text)
    return text

_analyzer = None

def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        _analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    return _analyzer

def presidio_redact(text, names):
    # Fail closed: raises if the Presidio engine is unavailable while enabled
    analyzer = _get_analyzer()
    results = analyzer.analyze(text=text, language="en", entities=["PERSON", "LOCATION"], score_threshold=0.5)
    out, limit = text, len(text)
    for r in sorted(results, key=lambda r: r.start, reverse=True):
        span = text[r.start:r.end]
        if r.end > limit or PLACEHOLDER.search(span):
            continue
        kind = "PLACE" if r.entity_type == "LOCATION" else "PERSON"
        out = out[:r.start] + _placeholder(kind, span, names) + out[r.end:]
        limit = r.start
    return out

def protect(text, name_map, use_presidio=True, names=None):
    names = {} if names is None else names
    text = pseudonymize(text, name_map)
    text = regex_redact(text, names)
    return presidio_redact(text, names) if use_presidio else text

def restore(text, names):
    if not text:
        return text
    return _RESTORE.sub(lambda m: names.get(m.group(1), m.group(1)), text)