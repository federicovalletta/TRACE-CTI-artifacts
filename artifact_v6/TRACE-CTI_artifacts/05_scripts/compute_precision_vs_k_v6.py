"""Compute Precision-vs-k sweep at v6.0.

Replicates the metric in v4_extracted/kg_v3/analyses_v4.py (tab_consensus_scope):
- support count per (dataset, method, sentence_id, attack_id) = # distinct setups
- gold = doc-level (dataset, doc_id, attack_id) set from gold_assertions.csv
- For each k in 1..6:
    sel = assertions whose support >= k
    per dataset: size, n_ids, gold_recall = |doc_tuples & gold_tuples| / |gold_tuples|
                 gold_precision = |doc_tuples_on_gold_docs & gold_tuples| / |doc_tuples_on_gold_docs|
    aggregated: sum(size, n_ids), mean(recall, precision) across datasets.

Writes:
  deliverables/v6_kg_analysis/precision_vs_k_v6.csv
  deliverables/v6_kg_analysis/tab_precision_vs_k_v6.tex
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Artifact layout (run from anywhere inside the archive):
KG_CSV = ROOT / "01_kg_snapshot_v6/kg_csv"
GOLD = ROOT / "01_kg_snapshot_v6/gold/gold_assertions.csv"
OUT = ROOT / "04_analysis_v6"

DATASETS = ["AnnoCTR", "TRAM2"]
K_RANGE = list(range(1, 7))


def load_gold_doc_set() -> dict:
    g = pd.read_csv(GOLD)
    # report_id like "report::AnnoCTR::bosch_0"
    parts = g["report_id"].str.split("::", expand=True)
    g["dataset"] = parts[1]
    g["doc_id"] = parts[2]
    gold_doc_set = {}
    for ds, doc, aid in zip(g["dataset"], g["doc_id"], g["attack_id"]):
        gold_doc_set.setdefault((ds, doc), set()).add(aid)
    return gold_doc_set


def main() -> None:
    A = pd.read_csv(KG_CSV / "nodes_graph_assertion.csv")
    A = A[A["scope_v6"].notna()].copy()
    # support count per (dataset, method, sentence_id, attack_id) = # distinct setups in v6
    sup = (A.groupby(["dataset", "method", "sentence_id", "attack_id"])
             ["setup_id"].nunique().reset_index(name="n_sup_in_v"))
    A = A.merge(sup, on=["dataset", "method", "sentence_id", "attack_id"])
    gold_doc_set = load_gold_doc_set()

    rows = []
    for k in K_RANGE:
        sel = A[A["n_sup_in_v"] >= k]
        per_ds = []
        for ds in DATASETS:
            s = sel[sel["dataset"] == ds]
            size = int(len(s))
            n_ids = int(s["attack_id"].nunique()) if size else 0
            doc_tuples = set(zip(s["doc_id"], s["attack_id"]))
            gold_tuples = {(d, a) for (dset, d), aids in gold_doc_set.items()
                           if dset == ds for a in aids}
            gold_docs = {d for (dset, d) in gold_doc_set if dset == ds}
            on_gold_doc = {t for t in doc_tuples if t[0] in gold_docs}
            recall = (len(doc_tuples & gold_tuples) / len(gold_tuples)) if gold_tuples else 0.0
            precision = (len(on_gold_doc & gold_tuples) / len(on_gold_doc)) if on_gold_doc else 0.0
            per_ds.append({"dataset": ds, "size": size, "n_ids": n_ids,
                           "gold_recall": recall, "gold_precision": precision})
        agg_size = sum(d["size"] for d in per_ds)
        agg_nids = sum(d["n_ids"] for d in per_ds)
        agg_rec = sum(d["gold_recall"] for d in per_ds) / len(per_ds)
        agg_prec = sum(d["gold_precision"] for d in per_ds) / len(per_ds)
        # distinct IDs aggregated as union across datasets (better proxy than sum)
        union_ids = int(sel["attack_id"].nunique()) if len(sel) else 0
        rows.append({"k": k, "size": agg_size, "n_ids_sum": agg_nids,
                     "n_ids_union": union_ids,
                     "gold_recall": agg_rec, "gold_precision": agg_prec,
                     "per_dataset": per_ds})
        print(f"k={k}: size={agg_size}, ids_union={union_ids}, ids_sum={agg_nids}, "
              f"prec={agg_prec*100:.1f}%, rec={agg_rec*100:.1f}%")

    df = pd.DataFrame([{k: v for k, v in r.items() if k != "per_dataset"} for r in rows])
    df.to_csv(OUT / "precision_vs_k_v6.csv", index=False)

    # LaTeX table (mirrors paper Table IV shape)
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"$k$ & Scope size & \#IDs & Gold-Precision & Gold-Recall \\",
             r"\midrule"]
    for r in rows:
        lines.append(f"$\\geq {r['k']}$ & {r['size']:,} & {r['n_ids_union']} & "
                     f"{r['gold_precision']*100:.1f}\\% & {r['gold_recall']*100:.1f}\\% \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "tab_precision_vs_k_v6.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT/'precision_vs_k_v6.csv'} and {OUT/'tab_precision_vs_k_v6.tex'}")


if __name__ == "__main__":
    main()
