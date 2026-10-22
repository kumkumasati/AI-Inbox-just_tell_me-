# 📥 AI-Inbox: Privacy-First WhatsApp Chat Analyzer

AI-Inbox transforms unstructured WhatsApp group chat exports into structured, verified action items and decisions using LLMs. Built with privacy-by-design principles, it redacts personal identifiable information (PII) before external AI processing and grounds every insight against source messages to eliminate hallucinations.

---

## Features

- ** Zero-Trust Privacy Pipeline:** Redacts Indian mobile numbers (+91), emails, URLs, bank accounts, PAN cards, and OTPs. Anonymizes senders and names (`PERSON_1`, `ME`) before passing text to LLMs.
- ** Multithreaded Parallel Ingestion:** Ingests large chat exports concurrently using `ThreadPoolExecutor` and hashes chunk results for fast retries.
- ** Strict Source Grounding:** Implements exact-quote verification and semantic entailment checks. Every extracted item is mapped to its original message ID.
- ** Interactive Source Tracing Highlights:** Visualizes original message bubbles with dynamic `<mark>` tag highlighting for extracted quotes.
- **Intent-Routed Q&A:** Routes aggregate queries (e.g., *"What were the key decisions?"*) directly to structured database records, and uses FAISS vector search for semantic factual questions.
- ** Secure Encrypted Storage:** Encrypts local chat data using AES-256 Fernet via SQLite with `PRAGMA secure_delete=ON`.
- **Metric Evaluation Framework:** Measures system accuracy against ground-truth datasets with Precision, Recall, and F1-score evaluation metrics.

---

## Tech Stack & Architecture

- **Frontend / UI:** [Streamlit](https://streamlit.io/)
- **LLM Layer:** OpenAI (`gpt-4o-mini`) or local Ollama (`llama3.1`) via `pydantic` structured outputs.
- **Vector Search:** [FAISS](https://github.com/facebookresearch/faiss)
- **PII Detection:** Custom Regex engine + [Microsoft Presidio](https://github.com/microsoft/presidio) (SpaCy `en_core_web_sm`)
- **Encryption:** `cryptography` (AES-256 Fernet)
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
[ Encrypted Local DB ]   ──► (Fernet AES-256 Encrypted SQLite Storage)