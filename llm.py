import json
import time
import numpy as np
from openai import OpenAI
from config import *

class LLMError(RuntimeError):
    pass

def _client():
    if MODE == "local":
        return OpenAI(base_url=LOCAL_URL, api_key="ollama", timeout=LLM_TIMEOUT, max_retries=2)
    return OpenAI(timeout=LLM_TIMEOUT, max_retries=3)

_no_temperature = set()

def _call_with_backoff(fn, **kw):
    retries = 3
    delay = 2.0
    for attempt in range(retries):
        try:
            return fn(**kw)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2.0
            else:
                raise

def structured(system, user, model_cls):
    c = _client()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if MODE == "local":
            schema = json.dumps(model_cls.model_json_schema())
            msgs[0]["content"] = system + "\nReply ONLY with JSON matching schema:\n" + schema
            r = _call_with_backoff(c.chat.completions.create, model=LOCAL_MODEL, response_format={"type": "json_object"}, messages=msgs)
            raw_content = r.choices[0].message.content
            
            # Local JSON Repair attempt
            try:
                return model_cls.model_validate_json(raw_content)
            except Exception:
                repair_msgs = msgs + [
                    {"role": "assistant", "content": raw_content},
                    {"role": "user", "content": "Your output had invalid JSON syntax. Fix it and output valid JSON only."}
                ]
                r_fix = _call_with_backoff(c.chat.completions.create, model=LOCAL_MODEL, response_format={"type": "json_object"}, messages=repair_msgs)
                return model_cls.model_validate_json(r_fix.choices[0].message.content)
        
        parse_fn = getattr(c.chat.completions, "parse", None) or c.beta.chat.completions.parse
        r = _call_with_backoff(parse_fn, model=OPENAI_MODEL, response_format=model_cls, messages=msgs)
        parsed = r.choices[0].message.parsed
        if parsed is None:
            raise LLMError("Model returned empty structured response")
        return parsed
    except Exception as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e

_local_model = None

def embed(texts):
    if not texts:
        return np.zeros((0, 0), dtype="float32")
    try:
        if MODE == "local":
            global _local_model
            if _local_model is None:
                from sentence_transformers import SentenceTransformer
                _local_model = SentenceTransformer(LOCAL_EMBED)
            vecs = np.array(_local_model.encode(texts), dtype="float32")
        else:
            c = _client()
            out = []
            for i in range(0, len(texts), 256):
                resp = c.embeddings.create(model=OPENAI_EMBED, input=texts[i:i + 256])
                out += [d.embedding for d in resp.data]
            vecs = np.array(out, dtype="float32")
    except Exception as e:
        raise LLMError(f"Embedding failed: {e}") from e
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)