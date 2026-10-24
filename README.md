# 📥 AI-Inbox: Privacy-First WhatsApp Chat Analyzer

AI-Inbox transforms unstructured WhatsApp group chat exports into structured, verified action items and decisions using LLMs. Built with privacy-by-design principles, it redacts personal identifiable information (PII) before external AI processing and grounds every insight against source messages to reduce hallucinations (every item must carry a quote that really exists in the chat).

---

## Features

- ** Zero-Trust Privacy Pipeline:** Redacts Indian mobile numbers (+91), emails, URLs, bank accounts, PAN cards, and OTPs. Anonymizes senders and names (`PERSON_1`, `ME`) before passing text to LLMs.
- ** Multithreaded Parallel Ingestion:** Ingests large chat exports concurrently using `ThreadPoolExecutor` and hashes chunk results for fast retries.
- ** Strict Source Grounding:** Implements exact-quote verification, a word-overlap check between the summary and its source, and removal of assignee/deadline values the cited messages do not support. This lowers, but cannot eliminate, wrong extractions. Every extracted item is mapped to its original message ID.
- ** Interactive Source Tracing Highlights:** Visualizes original message bubbles with dynamic `<mark>` tag highlighting for extracted quotes.
- **Intent-Routed Q&A:** Routes aggregate queries (e.g., *"What were the key decisions?"*) directly to structured database records, and uses FAISS vector search for semantic factual questions.
- ** Secure Encrypted Storage:** Message text, senders, extracted items and the FAISS search index are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) on disk; SQLite runs with `PRAGMA secure_delete=ON`. Chat names, timestamps and message numbers are stored unencrypted.
- **Metric Evaluation Framework:** Measures system accuracy against ground-truth datasets with Precision, Recall, and F1-score evaluation metrics.

---

## Tech Stack & Architecture

- **Frontend / UI:** [Streamlit](https://streamlit.io/)
- **LLM Layer:** OpenAI (`gpt-4o-mini`) or local Ollama (`llama3.1`) via `pydantic` structured outputs.
- **Vector Search:** [FAISS](https://github.com/facebookresearch/faiss)
- **PII Detection:** Custom Regex engine + [Microsoft Presidio](https://github.com/microsoft/presidio) (SpaCy `en_core_web_sm`)
- **Encryption:** `cryptography` (Fernet)
- **Database:** SQLite3

---

## Threat Model & Data Flow

```text
[ Raw Export (.txt) ] 
         │
         ▼
[ Local Privacy Engine ]  ──► (Redacts PII, Phone Nos, Real Names)
         │
         ▼
[ Safe Anonymized Text ]  ──► (Sent to OpenAI / Ollama LLM)
         │
         ▼
[ Structured JSON ]      ──► (Verified via Exact Quote & Entailment Check)
         │
         ▼
[ Encrypted Local DB ]   ──► (Fernet-encrypted SQLite + encrypted search index)
```

---

## Setup

```bash
python -m venv venv && venv\Scripts\activate      # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt                      # MODE=local also needs: pip install -r requirements-local.txt
cp .env.example .env                                 # then fill in the values
streamlit run app.py
```

`.env` values:

```
ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
OPENAI_API_KEY=sk-...
MODE=openai            # or local (Ollama)
RETENTION_DAYS=30
```

Run the tests with `pip install -r requirements-dev.txt` then `pytest -q`, and the accuracy check with `python evaluation/evaluate.py`.

### Docker (optional)

```bash
docker build -t ai-inbox .
docker run --env-file .env -p 8501:8501 -v ai_inbox_data:/app/data ai-inbox
```


### Requirements & known limits

- **Python 3.11 or 3.12.** Python 3.13+ is not supported by the pinned numpy / faiss-cpu / spaCy versions.
- Name/place detection uses spaCy's *small* model: it can miss names that are not chat participants
  (e.g. "Sharma ji") and can mis-tag common Hinglish words. Participant names are always pseudonymised;
  other names depend on the model. Use a larger spaCy model for better recall.
- `YYYY-MM-DD`, `DD/MM/YY` and `MM/DD/YY` exports are parsed, but dates stay as text (day/month order is not resolved).

### Accounts

The app opens on a **Login / Sign Up** page. Every chat belongs to the account that uploaded it, and every
read, search and delete re-checks that ownership.

- Passwords are stored as salted **scrypt** hashes (never in plain text); minimum 8 characters.
- 5 wrong passwords in a row lock that account for 5 minutes.
- Usernames: 3-32 characters (letters, numbers, `.`, `-`, `_`). Usernames are stored unencrypted (needed for login).
- **Upgrading an existing database:** the first account you create adopts all chats that existed before accounts were added.
- Logging in again after a browser refresh is expected (sessions live in the browser tab).
- CLI: `python pipeline.py chat.txt --me Rahul --user <username>` (create the account in the app first).