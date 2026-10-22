import re

EMAIL = re.compile(r"[\w\.-]+@[\w\.-]+(?:\.\w+)?")  # Catches UPI IDs like name@okaxis
URL = re.compile(r"https?://\S+")
PHONE = re.compile(r"\+?\d[\d\s\-]{8,}\d")
AADHAAR = re.compile(r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b")
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I)
BANK_ACC = re.compile(r"\b\d{9,18}\b")
OTP = re.compile(r"\b(?i:otp|code|verification)\s*[:\-]?\s*(\d{4,8})\b")

KINDS = ("PERSON", "PLACE", "PHONE", "LINK", "EMAIL", "AADHAAR", "PAN", "BANK", "OTP")
_KIND_ALT = "|".join(KINDS)
PLACEHOLDER = re.compile(rf"(?:{_KIND_ALT})_\d+|ME")
_RESTORE = re.compile(rf"\b((?:{_KIND_ALT})_\d+|ME)\b")

COMMON_WORDS = {"will", "hope", "may", "grant", "joy", "march", "mark", "rose", "grace"}

def build_name_map(messages, my_aliases):
    aliases = {a.lower().strip() for a in my_aliases if a.strip()}
    name_map = {a: "ME" for a in aliases}
    names = {"ME": "You"}
    n = 0
    for sender in dict.fromkeys(m["sender"] for m in messages):
        low = sender.lower()
        if low in aliases:
            continue
        n += 1
        fake = f"PERSON_{n}"
        name_map[low] = fake
        names[fake] = sender
        
        parts = low.split()
        if len(parts) > 1:
            first = parts[0]
            if len(first) > 2 and first not in aliases and first not in COMMON_WORDS:
                name_map.setdefault(first, fake)
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
    text = AADHAAR.sub(lambda m: _placeholder("AADHAAR", m.group(0), names), text)
    text = PAN.sub(lambda m: _placeholder("PAN", m.group(0), names), text)
    text = EMAIL.sub(lambda m: _placeholder("EMAIL", m.group(0), names), text)
    text = URL.sub(lambda m: _placeholder("LINK", m.group(0), names), text)
    text = PHONE.sub(lambda m: _placeholder("PHONE", m.group(0), names), text)
    text = BANK_ACC.sub(lambda m: _placeholder("BANK", m.group(0), names), text)
    text = OTP.sub(lambda m: _placeholder("OTP", m.group(0), names), text)
    return text

_analyzer = None

def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
        })
        _analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    return _analyzer

def presidio_redact(text, names):
    try:
        results = _get_analyzer().analyze(text=text, language="en", entities=["PERSON", "LOCATION"], score_threshold=0.5)
    except Exception:
        return text
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