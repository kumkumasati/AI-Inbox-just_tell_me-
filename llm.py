import json
from functools import lru_cache

import numpy as np
from openai import OpenAI

from config import (LLM_TIMEOUT, LOCAL_EMBED, LOCAL_MODEL, LOCAL_URL, MODE,
                    OPENAI_EMBED, OPENAI_MODEL)

class LLMError(RuntimeError):
    pass

@lru_cache(maxsize=1)
def _client():
   
    if MODE == "local":
        return OpenAI(base_url=LOCAL_URL, api_key="ollama", timeout=LLM_TIMEOUT, max_retries=2)
    return OpenAI(timeout=LLM_TIMEOUT, max_retries=3)

def _create_deterministic(fn, **kwargs):
    """temperature=0 for reproducible extraction; retry without it for models that reject it."""
    try:
        return fn(temperature=0, **kwargs)
    except Exception as e:
        if "temperature" in str(e).lower():
            return fn(**kwargs)
        raise

def structured(system, user, model_cls):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        c = _client()
        if MODE == "local":
            schema = json.dumps(model_cls.model_json_schema())
            msgs[0]["content"] = system + "\nReply ONLY with JSON matching schema:\n" + schema
            r = _create_deterministic(c.chat.completions.create, model=LOCAL_MODEL, response_format={"type": "json_object"}, messages=msgs)
            raw_content = r.choices[0].message.content


            try:
                return model_cls.model_validate_json(raw_content)
            except Exception:
                repair_msgs = msgs + [
                    {"role": "assistant", "content": raw_content},
                    {"role": "user", "content": "Your output had invalid JSON syntax. Fix it and output valid JSON only."},
                ]
                r_fix = _create_deterministic(c.chat.completions.create, model=LOCAL_MODEL, response_format={"type": "json_object"}, messages=repair_msgs)
                return model_cls.model_validate_json(r_fix.choices[0].message.content)

        parse_fn = getattr(c.chat.completions, "parse", None) or c.beta.chat.completions.parse
        r = _create_deterministic(parse_fn, model=OPENAI_MODEL, response_format=model_cls, messages=msgs)
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
