import os, sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["USE_PRESIDIO"] = "0"

import db, privacy, verify, score, chat_parser
from schemas import Extraction, ActionItem, Topic

def test_privacy_roundtrip():
    name_map = {"rahul": "PERSON_1"}
    names = {"PERSON_1": "Rahul"}
    raw = "Rahul said hello to PERSON_1"
    protected = privacy.protect(raw, name_map, use_presidio=False, names=names)
    restored = privacy.restore(protected, names)
    assert restored == "Rahul said hello to Rahul"

def test_parser():
    sample = "[12/05/2026, 10:15 AM] Alice: Let's meet at 5pm."
    parsed = chat_parser.parse_text(sample)
    assert len(parsed) == 1
    assert parsed[0]["sender"] == "Alice"

def test_verify():
    by_id = {1: {"text": "I will send the document today evening."}}
    ok, _ = verify.check([1], "I will send the document", by_id, item_text="Send document")
    assert ok is True

if __name__ == "__main__":
    test_privacy_roundtrip()
    test_parser()
    test_verify()
    print("ALL TESTS PASSED SUCCESSFULLY!")