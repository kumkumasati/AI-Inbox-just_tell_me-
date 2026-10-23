import argparse, hashlib, os, threading, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import db, search
from chat_parser import parse_chat
from config import USE_PRESIDIO
from extract import chunks, extract_chunk
from privacy import build_name_map, protect, pseudonymize, restore
from score import score_item
from verify import verify

class PipelineError(RuntimeError):
    pass

_CACHE_MAX = 256
_chunk_cache = {}
_cache_lock = threading.Lock()

def _hash_chunk(chunk_msgs):
    raw = "\n".join(f"{m['id']}|{m['sender']}|{m['text']}" for m in chunk_msgs)
    return hashlib.sha256(raw.encode()).hexdigest()

def _cache_get(h):
    with _cache_lock:
        return _chunk_cache.get(h)

def _cache_put(h, value):
    with _cache_lock:
        if len(_chunk_cache) >= _CACHE_MAX:
            _chunk_cache.pop(next(iter(_chunk_cache)))
        _chunk_cache[h] = value

def _process_single_chunk(ch_idx, ch):
    h = _hash_chunk(ch)
    cached = _cache_get(h)
    if cached is not None:
        return ch_idx, cached, None
    try:
        ex = extract_chunk(ch)
        if ex is None:
            return ch_idx, None, "empty extraction response"
        _cache_put(h, ex)
        return ch_idx, ex, None
    except Exception as e:
        return ch_idx, None, str(e)

def analyze(path, my_aliases, use_presidio=None):
    use_presidio = USE_PRESIDIO if use_presidio is None else use_presidio
    raw = parse_chat(path)
    if not raw:
        raise PipelineError("No messages found in chat file.")

    name_map, names = build_name_map(raw, my_aliases)

    sender_cache = {}
    def get_safe_sender(s):
        if s not in sender_cache:
            sender_cache[s] = pseudonymize(s, name_map)
        return sender_cache[s]

    safe = [{
        **m,
        "sender": get_safe_sender(m["sender"]),
        "text": protect(m["text"], name_map, use_presidio, names)
    } for m in raw]

    orig_by_id = {m["id"]: m for m in raw}
    safe_by_id = {m["id"]: m for m in safe}

    all_chunks = list(chunks(safe))
    total_chunks = len(all_chunks)
    failed_chunks, errors = 0, []
    chunk_results = [None] * total_chunks

    max_workers = min(8, max(1, total_chunks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_process_single_chunk, idx, ch): idx
            for idx, ch in enumerate(all_chunks)
        }
        for future in as_completed(future_to_index):
            idx, ex, err = future.result()
            if err:
                failed_chunks += 1
                errors.append(err)
            chunk_results[idx] = ex

    if total_chunks and failed_chunks == total_chunks:
        raise PipelineError(f"All {total_chunks} AI calls failed. Error: {errors[0] if errors else 'unknown'}")

    topics, actions, decisions, rejected, seen = [], [], [], 0, set()
    for ex in chunk_results:
        if ex is None:
            continue
        topics += ex.topics
        for kind, objs in (("action", ex.action_items), ("decision", ex.decisions)):
            for o in objs:
                item_title = getattr(o, "task", getattr(o, "decision", ""))
                key = (kind, tuple(sorted(o.source_message_ids)), item_title.lower())
                if key in seen:
                    continue
                seen.add(key)
                if not verify(o.source_message_ids, o.quote, safe_by_id, item_text=item_title):
                    rejected += 1
                    continue
                (actions if kind == "action" else decisions).append(o)

    topic_of = {}
    for t in topics:
        for i in t.message_ids:
            topic_of.setdefault(i, restore(t.title, names))

    items = []
    for kind, objs in (("action", actions), ("decision", decisions)):
        for o in objs:
            orig_text = " ".join(orig_by_id[i]["text"] for i in o.source_message_ids if i in orig_by_id)
            s, reasons = score_item(orig_text, getattr(o, "deadline", None), getattr(o, "assignee", None), my_aliases)
            d = o.model_dump()
            d["quote_safe"] = d.get("quote")      # anonymised quote, used for highlighting
            for f in ("task", "assignee", "decision", "deadline", "quote"):
                if d.get(f):
                    d[f] = restore(d[f], names)
            d.update(kind=kind, score=s, reasons=reasons, topic=topic_of.get(o.source_message_ids[0], "General"))
            items.append(d)

    return {
        "messages": raw, "safe": safe, "name_map": name_map, "names": names, "items": items,
        "stats": {
            "messages": len(raw), "actions": len(actions), "decisions": len(decisions),
            "rejected_by_verification": rejected, "total_chunks": total_chunks,
            "failed_chunks": failed_chunks, "errors": errors[:3]
        }
    }

def _remove_raw(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    return not os.path.exists(path)

def process(path, name, my_aliases, user_id,delete_raw=True):
    info, cid = None, None
    raw_deleted = False
    try:
        db.init()
        result = analyze(path, my_aliases)
        cid = uuid.uuid4().hex[:8]
        db.save_chat(cid, name, result,user_id=user_id)
        try:
            search.build_index(cid, result["safe"])
        except Exception as e:
            db.delete_chat(cid)
            raise PipelineError(f"Could not build search index: {e}") from e
        info = {"chat_id": cid, "stats": result["stats"]}
    finally:
        if delete_raw:
            raw_deleted = _remove_raw(path)
    if info:
        info["raw_deleted"] = raw_deleted
    return info

def run_pipeline(path, name, my_aliases, delete_raw=True):
    info = process(path, name, my_aliases, delete_raw)
    return info["chat_id"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--me", nargs="*", default=[], help="your names/aliases")
    ap.add_argument("--name", default="My chat")
    ap.add_argument("--keep-raw", action="store_true", help="Opt-out flag to keep raw upload file")
    a = ap.parse_args()
    cid = run_pipeline(a.file, a.name, a.me, delete_raw=not a.keep_raw)
    print("\nProcessed Chat ID:", cid)
