import json
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

def _call(fn, model, **kw):
    if model not in _no_temperature:
        try:
            return fn(model=model, temperature=0, **kw)
        except Exception as e:
            if "temperature" not in str(e).lower():
                raise
            _no_temperature.add(model)
    return fn(model=model, **kw)

def structured(system, user, model_cls):
    c = _client()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if MODE == "local":
            schema = json.dumps(model_cls.model_json_schema())
            msgs[0]["content"] = system + "\nReply ONLY with JSON matching schema:\n" + schema
            r = _call(c.chat.completions.create, LOCAL_MODEL, response_format={"type": "json_object"}, messages=msgs)
            return model_cls.model_validate_json(r.choices[0].message.content)
        
        parse = getattr(c.chat.completions, "parse", None) or c.beta.chat.completions.parse
        r = _call(parse, OPENAI_MODEL, response_format=model_cls, messages=msgs)
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
            c, out = _client(), []
            for i in range(0, len(texts), 256):
                resp = c.embeddings.create(model=OPENAI_EMBED, input=texts[i:i + 256])
                out += [d.embedding for d in resp.data]
            vecs = np.array(out, dtype="float32")
    except Exception as e:
        raise LLMError(f"Embedding failed: {e}") from e
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)