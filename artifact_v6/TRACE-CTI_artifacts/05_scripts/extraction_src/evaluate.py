"""Document-level evaluation. Per-doc P/R/F1, mean across docs.

Empty-case policy (Zenodo): both pred and gt empty -> 1.0/1.0/1.0/1.0 (acc=1).
Asymmetric (one empty, the other not) -> 0/0/0 by formula.
"""

from statistics import mean


def per_doc_metrics(pred_ids, gold_ids):
    pred = set(pred_ids)
    gold = set(gold_ids)
    if not pred and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "accuracy": 1.0,
                "tp": 0, "fp": 0, "fn": 0}
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    accuracy = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
            "tp": tp, "fp": fp, "fn": fn}


def aggregate(per_doc_list):
    if not per_doc_list:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "accuracy": 0.0, "n_docs": 0}
    return {
        "precision": mean(d["precision"] for d in per_doc_list),
        "recall":    mean(d["recall"]    for d in per_doc_list),
        "f1":        mean(d["f1"]        for d in per_doc_list),
        "accuracy":  mean(d["accuracy"]  for d in per_doc_list),
        "n_docs":    len(per_doc_list),
    }
