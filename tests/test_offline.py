import os, sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["USE_PRESIDIO"] = "0"

import db, pipeline, llm
from schemas import Extraction, ActionItem, Decision, Topic

def test_payload_privacy_leak():
    fake_payloads = []
    def mock_structured(system, user, model_cls):
        fake_payloads.append(user)
        return Extraction(
            topics=[Topic(title="Test", message_ids=[1])],
            action_items=[ActionItem(task="Do thing", assignee="ME", deadline="Today", source_message_ids=[1], quote="Rahul: hello test@okaxis.com 9876543210")],
            decisions=[]
        )
    
    with patch("extract.structured", side_effect=mock_structured):
        res = pipeline.analyze("data/sample_chat.txt", ["rahul"], use_presidio=False)
        payload = " ".join(fake_payloads)
        assert "rahul" not in payload.lower()
        assert "9876543210" not in payload
        assert "test@okaxis.com" not in payload
    print("Privacy leak mock test passed!")

if __name__ == "__main__":
    test_payload_privacy_leak()
    print("ALL TESTS PASSED!")