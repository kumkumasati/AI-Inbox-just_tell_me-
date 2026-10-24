import glob, json, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from pipeline import analyze

def _gold_ids(g):
    ids = g.get("message_ids") or [g.get("message_id")]
    return {i for i in ids if i is not None}

def evaluate_one(label_file):
    with open(label_file, encoding="utf-8") as f:
        gold = json.load(f)
    # BUG FIX: resolve the chat path against the project folder, not the current directory
    chat_path = Path(gold["chat"])
    if not chat_path.is_absolute():
        chat_path = BASE_DIR / chat_path
    result = analyze(str(chat_path), gold["my_aliases"])

    ai_actions = [it for it in result["items"] if it["kind"] == "action"]
    gold_actions = gold.get("action_items", [])

    tp, fp = 0, 0
    matched_gold = set()

    for ai in ai_actions:
        ai_ids = set(ai["source_message_ids"])
        matched = False
        for i, g in enumerate(gold_actions):
            # BUG FIX: overlap match (exact set equality was too harsh) and each gold item counts once
            if i not in matched_gold and ai_ids & _gold_ids(g):
                tp += 1
                matched_gold.add(i)
                matched = True
                break
        if not matched:
            fp += 1

    fn = len(gold_actions) - len(matched_gold)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1

if __name__ == "__main__":
    files = sorted(glob.glob(str(BASE_DIR / "evaluation" / "labeled" / "*.json")))
    if not files:
        print("No evaluation sets found in evaluation/labeled/")
        sys.exit(0)
    for f in files:
        p, r, f1 = evaluate_one(f)
        print(f"{os.path.basename(f)} -> Precision: {p:.2f}, Recall: {r:.2f}, F1-Score: {f1:.2f}")