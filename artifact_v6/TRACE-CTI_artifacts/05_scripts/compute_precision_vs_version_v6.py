"""Compute Gold-Precision/Recall per VERSION (v1.0..v6.0) at fixed trust view.

Companion to compute_precision_vs_k_v6.py. That script sweeps the consensus
threshold k at a *fixed* version (v6). This script instead fixes the trust
*view* and sweeps the *version* axis v1.0..v6.0, isolating the
"more datasets/setups -> higher precision" effect, orthogonal to the k axis.

Each version v_n is the cumulative set of the first n ExtractionSetups (in
first-seen order). Within that version, per-version support is the number of
distinct setups (among those n) that agree on a given
(dataset, method, sentence_id, attack_id). Trust views (matching the existing
deliverables/v4_kg_analysis/trust_scope_evolution.csv definitions):
  - consensus_validated : support >= 2 (at least two setups agree)
  - strong_consensus    : support >= n (unanimous across all n setups)

Gold metric is identical to compute_precision_vs_k_v6.py:
  gold = doc-level (dataset, doc_id, attack_id) set from gold_assertions.csv
  per dataset: gold_recall = |doc_tuples & gold| / |gold|
               gold_precision = |doc_tuples_on_gold_docs & gold| / |doc_tuples_on_gold_docs|
  aggregated: sum(size, n_ids_union), mean(recall, precision) across datasets.

Writes:
  deliverables/v6_kg_analysis/precision_vs_version_v6.csv
  deliverables/v6_kg_analysis/tab_precision_vs_version_v6.tex
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
# ExtractionSetups in first-seen order: one added per version v1.0..v6.0.
SETUP_ORDER = ["gteqwen_llama", "e5_mistral", "gteqwen_mistral",
               "e5_llama", "e5_phi35", "gteqwen_phi35"]
KEY = ["dataset", "method", "sentence_id", "attack_id"]
VIEW = "strong_consensus"  # support >= n (unanimous); the high-trust view


def load_gold_doc_set() -> dict:
    g = pd.read_csv(GOLD)
    parts = g["report_id"].str.split("::", expand=True)
    g["dataset"] = parts[1]
    g["doc_id"] = parts[2]
    gold_doc_set = {}
    for ds, doc, aid in zip(g["dataset"], g["doc_id"], g["attack_id"]):
        gold_doc_set.setdefault((ds, doc), set()).add(aid)
    return gold_doc_set


def per_dataset_metrics(sel: pd.DataFrame, gold_doc_set: dict) -> list:
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
    return per_ds


def main() -> None:
    A = pd.read_csv(KG_CSV / "nodes_graph_assertion.csv")
    gold_doc_set = load_gold_doc_set()

    rows = []
    for n in range(1, 7):
        setups = SETUP_ORDER[:n]
        sub = A[A["setup_id"].isin(setups)].copy()
        sup = sub.groupby(KEY)["setup_id"].nunique().reset_index(name="k")
        sub = sub.merge(sup, on=KEY)
        # strong_consensus view = unanimous across all n setups
        sel = sub[sub["k"] >= n]
        per_ds = per_dataset_metrics(sel, gold_doc_set)
        agg_size = sum(d["size"] for d in per_ds)
        agg_rec = sum(d["gold_recall"] for d in per_ds) / len(per_ds)
        agg_prec = sum(d["gold_precision"] for d in per_ds) / len(per_ds)
        union_ids = int(sel["attack_id"].nunique()) if len(sel) else 0
        row = {"version": f"v{n}.0", "setups": n, "view": VIEW,
               "size": agg_size, "n_ids_union": union_ids,
               "gold_recall": agg_rec, "gold_precision": agg_prec}
        for d in per_ds:
            row[f"{d['dataset']}_size"] = d["size"]
            row[f"{d['dataset']}_precision"] = d["gold_precision"]
            row[f"{d['dataset']}_recall"] = d["gold_recall"]
        rows.append(row)
        print(f"v{n}.0 ({n} setups): size={agg_size}, ids={union_ids}, "
              f"prec={agg_prec*100:.1f}%, rec={agg_rec*100:.1f}% | "
              + " ".join(f"{d['dataset']}={d['gold_precision']*100:.1f}%" for d in per_ds))

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "precision_vs_version_v6.csv", index=False)

    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Version (\# setups) & View size & \#IDs & Gold-Precision & Gold-Recall \\",
             r"\midrule"]
    for r in rows:
        if r["size"] == 0:
            continue
        lines.append(f"v{r['setups']}.0 ({r['setups']}) & {r['size']:,} & {r['n_ids_union']} & "
                     f"{r['gold_precision']*100:.1f}\\% & {r['gold_recall']*100:.1f}\\% \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "tab_precision_vs_version_v6.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT/'precision_vs_version_v6.csv'} and {OUT/'tab_precision_vs_version_v6.tex'}")


if __name__ == "__main__":
    main()
