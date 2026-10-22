import glob, json, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from pipeline import analyze

def evaluate_one(label_file):
    gold = json.load(open(label_file))
    result = analyze(gold["chat"], gold["my_aliases"])
    
    ai_actions = [it for it in result["items"] if it["kind"] == "action"]
    gold_actions = gold.get("action_items", [])
    
    tp, fp = 0, 0
    matched_gold = set()
    
    for ai in ai_actions:
        matched = False
        for i, g in enumerate(gold_actions):
            if set(ai["source_message_ids"]) == set(g.get("message_ids", [g.get("message_id")])):
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