import re
import unicodedata

LEAD = re.compile(r"^\s*\[\d+\]\s*[^:]{1,60}:\s*")

def _norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[\W_]+", " ", s).strip()

def entailment_check(item_text, quote_text):
    """Verifies semantic token overlap between task summary and quoted text."""
    if not item_text or not quote_text:
        return True
    item_words = set(_norm(item_text).split())
    quote_words = set(_norm(quote_text).split())
    
    # Filter out common short stopwords
    stopwords = {"the", "a", "an", "is", "are", "to", "and", "or", "in", "on", "at", "by", "for", "with", "this", "that"}
    meaningful_words = {w for w in item_words if len(w) > 2 and w not in stopwords}
    
    if not meaningful_words:
        return True
    
    overlap = meaningful_words.intersection(quote_words)
    return len(overlap) > 0

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