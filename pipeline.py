import argparse, os, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import db, search
from chat_parser import parse_chat
from config import *
from extract import chunks, extract_chunk
from privacy import build_name_map, protect, pseudonymize, restore
from score import score_item
from verify import verify


class PipelineError(RuntimeError):
    """A problem the user should read (bad file, AI unreachable, ...)."""


def _process_single_chunk(ch_idx, ch, safe_by_id):
    """Worker function to process a single message chunk in a thread."""
    try:
        ex = extract_chunk(ch)
        if ex is None:
            return ch_idx, None, "empty extraction response"
        return ch_idx, ex, None
    except Exception as e:
        return ch_idx, None, str(e)


def analyze(path, my_aliases, use_presidio=None):
    """Parse -> protect -> extract (multithreaded) -> verify -> score."""
    use_presidio = USE_PRESIDIO if use_presidio is None else use_presidio
    raw = parse_chat(path)
    if not raw:
        raise PipelineError("No messages found in this file. Is it a WhatsApp .txt export?")
    
    name_map, names = build_name_map(raw, my_aliases)
    
    # Cache sender pseudonymization
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
    failed_chunks = 0
    errors = []

    # Prepare results container indexed by chunk position to preserve order
    chunk_results = [None] * total_chunks

    # Parallelize LLM extraction calls using ThreadPoolExecutor
    # max_workers=min(8, total_chunks) prevents socket exhaustion while maximizing throughput
    max_workers = min(8, max(1, total_chunks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_process_single_chunk, idx, ch, safe_by_id): idx
            for idx, ch in enumerate(all_chunks)
        }
        
        for future in as_completed(future_to_index):
            idx, ex, err = future.result()
            if err:
                failed_chunks += 1
                errors.append(err)
            chunk_results[idx] = ex

    if total_chunks and failed_chunks == total_chunks:
        raise PipelineError(f"All {total_chunks} AI calls failed, so nothing was saved. "
                            f"First error: {errors[0] if errors else 'unknown'}")

    topics, actions, decisions, rejected, seen = [], [], [], 0, set()
    
    for ex in chunk_results:
        if ex is None:
            continue
        topics += ex.topics
        for kind, objs, label in (("action", ex.action_items, "task"), ("decision", ex.decisions, "decision")):
            for o in objs:
                key = (kind, tuple(sorted(o.source_message_ids)), getattr(o, label).lower())
                if key in seen:
                    continue
                seen.add(key)
                if not verify(o.source_message_ids, o.quote, safe_by_id):
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
    """Delete the raw upload. Returns True only if it is really gone."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        print(f"[pipeline] could not delete raw file {path}: {e}")
    return not os.path.exists(path)


def process(path, name, my_aliases, delete_raw=True):
    """Full run. Returns {"chat_id", "stats", "raw_deleted"}; raises PipelineError on failure."""
    info, cid = None, None
    try:
        db.init()
        result = analyze(path, my_aliases)
        cid = uuid.uuid4().hex[:8]
        db.save_chat(cid, name, result)
        try:
            search.build_index(cid, result["safe"])
        except Exception as e:
            db.delete_chat(cid)
            raise PipelineError(f"Could not build the search index, so the chat was not saved: {e}") from e
        info = {"chat_id": cid, "stats": result["stats"]}
    finally:
        raw_deleted = _remove_raw(path) if delete_raw else False
    if info:
        info["raw_deleted"] = raw_deleted
    return info


def run_pipeline(path, name, my_aliases, delete_raw=True):
    """Backwards-compatible wrapper: returns just the chat id."""
    info = process(path, name, my_aliases, delete_raw)
    print("Stats:", info["stats"])
    return info["chat_id"]


def digest(items):
    """Group by topic, most important first."""
    groups = {}
    for it in items:
        groups.setdefault(it["topic"], []).append(it)
    for g in groups.values():
        g.sort(key=lambda x: -x["score"])
    return dict(sorted(groups.items(), key=lambda kv: -kv[1][0]["score"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--me", nargs="*", default=[], help="your names/aliases")
    ap.add_argument("--name", default="My chat")
    ap.add_argument("--delete-raw", action="store_true")
    a = ap.parse_args()
    cid = run_pipeline(a.file, a.name, a.me, a.delete_raw)
    msgs = {m["id"]: m for m in db.get_messages(cid)}
    for topic, its in digest(db.get_items(cid)).items():
        print(f"\n== {topic} ==")
        for it in its:
            title = it.get("task") or it.get("decision")
            print(f"[{it['score']}] ({it['kind']}) {title}  deadline={it.get('deadline')}  why={it['reasons']}")
            for i in it["source_message_ids"]:
                print(f"     source #{i}: {msgs[i]['sender']}: {msgs[i]['text']}")
    print("\nchat_id:", cid)