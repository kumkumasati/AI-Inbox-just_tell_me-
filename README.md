# AI-Inbox for Conversation

## Setup
1. python -m venv venv && source venv/bin/activate   (Windows: venv\Scripts\activate)
2. pip install -r requirements.txt
3. python -m spacy download en_core_web_sm
4. copy .env.example to .env and fill in OPENAI_API_KEY
5. Make an encryption key and paste it as ENCRYPTION_KEY in .env:
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

## Run
- Offline test (no API key):  python tests/test_offline.py
- Command line:  python pipeline.py data/sample_chat.txt --me rahul --name Demo
- App:           streamlit run app.py
- Evaluation:    python evaluation/evaluate.py

## Local mode (nothing leaves your computer)
Install Ollama, run `ollama pull llama3.1`, `pip install sentence-transformers`, set MODE=local in .env.

## Files = steps
chat_parser.py (1) | schemas.py (2) | privacy.py (3) | db.py (4) | extract.py (5)
verify.py (6) | score.py (7) | search.py (8) | pipeline.py (glue) | evaluation/ (10) | app.py (11)
