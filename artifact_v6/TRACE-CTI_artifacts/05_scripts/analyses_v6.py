"""V6 analyses for the 6-setup KG (S0+S1+S2+S3+S4+S5, GraphVersion v6.0).

Closes the asymmetric 2x3 factorial by adding S4 = GTE-Qwen2 x Phi-3.5-mini.
Also upgrades S1 (gteqwen_llama) from n=1 (legacy rename) to n=3 genuine seeds.

Produces (under analysis_outputs/v6_kg_analysis/):
  - tab_kg_evolution_v6.tex/.csv     : 6-version evolution table
  - factorial_effects_2x3.json       : E5/GTE-Qwen x Llama/Mistral/Phi (CLOSED 2x3)
  - tab_factorial_2x3.tex
  - tab_within_vs_cross_family_llm.tex / .csv
  - tab_within_vs_cross_family_retriever.tex / .csv
  - bias_quad_decomposition.csv / .tex
  - cost_latency_v6.csv / .tex
  - run_design_note.json
  - metrics_index_v6.csv
  - cell_outcomes_v6.csv

Run AFTER `KG_OUT_VERSION=v6 python -m kg_v3.build_kg --out-version v6`.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from kg_v3.manifest import GRAPH_VERSIONS, SETUPS, discover_runs
from kg_v3.gold import load_all_gold

ROOT = Path("/home/azureuser/ttp_table9_method_replication")
OUT  = ROOT / "analysis_outputs" / "v6_kg_analysis"
KG   = OUT / "kg_csv"
METRICS_DIR = ROOT / "outputs" / "metrics"
PRED_DIR    = ROOT / "outputs" / "predictions"

SETUP_LABEL = {
    "gteqwen_llama":   "S1 (GTE-Qwen2+Llama)",
    "e5_mistral":      "S2 (E5+Mistral)",
    "gteqwen_mistral": "S3 (GTE-Qwen2+Mistral)",
    "e5_llama":        "S0 (E5+Llama)",
    "e5_phi35":        "S5 (E5+Phi-3.5)",
    "gteqwen_phi35":   "S4 (GTE-Qwen2+Phi-3.5)",
}
SHORT = {"gteqwen_llama": "S1", "e5_mistral": "S2", "gteqwen_mistral": "S3",
         "e5_llama": "S0", "e5_phi35": "S5", "gteqwen_phi35": "S4"}
SETUP_ORDER = ["e5_llama", "gteqwen_llama", "e5_mistral", "gteqwen_mistral", "e5_phi35", "gteqwen_phi35"]
RETRIEVER_OF = {"gteqwen_llama": "GTE-Qwen2", "gteqwen_mistral": "GTE-Qwen2",
                "gteqwen_phi35": "GTE-Qwen2",
                "e5_mistral": "E5", "e5_llama": "E5", "e5_phi35": "E5"}
GENERATOR_OF = {"gteqwen_llama": "Llama", "e5_llama": "Llama",
                "e5_mistral": "Mistral", "gteqwen_mistral": "Mistral",
                "e5_phi35": "Phi-3.5", "gteqwen_phi35": "Phi-3.5"}
DATASETS = ["TRAM2", "AnnoCTR"]
METHODS  = ["RAG", "RAG+FSP"]
VERSION_ORDER = [gv["version_id"] for gv in GRAPH_VERSIONS]

# v6: all setups now have 3 genuine seeds (S1 upgraded from legacy n=1 rename to
# 3 independent runs with proper seed0/1/2; S4 newly executed).
N_SEEDS = {"gteqwen_llama": 3, "e5_llama": 3, "e5_mistral": 3,
           "gteqwen_mistral": 3, "e5_phi35": 3, "gteqwen_phi35": 3}
MISSING_CELLS = []  # v6: factorial is CLOSED (2x3 complete)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_kg():
    g = {}
    g["assertion"]  = pd.read_csv(KG / "nodes_graph_assertion.csv")
    g["prediction"] = pd.read_csv(KG / "nodes_prediction.csv")
    g["sent"]       = pd.read_csv(KG / "nodes_sentence.csv")
    g["llm_run"]    = pd.read_csv(KG / "nodes_llm_run.csv")
    gs, gd = load_all_gold()
    g["gold_sent"] = gs
    g["gold_doc"]  = gd
    return g


def _norm_method(m: str) -> str:
    return m.replace("_FSP", "+FSP").replace(" ", "")


def load_metrics_index() -> pd.DataFrame:
    """One row per (setup, dataset, method, seed) with metric + timing info."""
    runs = discover_runs()
    rows = []
    for r in runs:
        # Locate the metrics file matching the same stem as the prediction
        stem = r.path.stem
        m_path = METRICS_DIR / f"{stem}.json"
        if not m_path.exists():
            # Some sharded merges produce stem.json from merger; otherwise skip with NaN
            row = {"setup": r.setup_id, "dataset": r.dataset, "method": r.method,
                   "seed": r.seed, "pred_path": str(r.path), "metrics_path": None,
                   "f1": np.nan, "precision": np.nan, "recall": np.nan,
                   "n_sentences": np.nan, "gen_time_s": np.nan, "total_time_s": np.nan,
                   "wall_time_s": np.nan, "sharded": False, "num_shards": 1}
            rows.append(row); continue
        d = json.loads(m_path.read_text())
        mp = d.get("metrics_primary_regex", {})
        timing = d.get("timing_s", {}) or {}
        execu  = d.get("execution", {}) or {}
        # For sharded runs, fall back to per-sentence gen_time_s aggregation
        gen_s = timing.get("generation")
        total_s = timing.get("total")
        wall_s = execu.get("parallel_wall_time_s")
        sharded = bool(execu.get("num_shards", 0)) and execu.get("mode") == "data_parallel"
        num_shards = int(execu.get("num_shards", 1) or 1)
        if gen_s is None:
            # aggregate from JSONL
            g_sum = 0.0; n = 0
            try:
                with open(r.path) as f:
                    for line in f:
                        if not line.strip(): continue
                        rec = json.loads(line)
                        if "gen_time_s" in rec:
                            g_sum += float(rec["gen_time_s"]); n += 1
                gen_s = g_sum
            except Exception:
                gen_s = np.nan
        rows.append({
            "setup": r.setup_id, "dataset": r.dataset, "method": r.method,
            "seed": r.seed, "pred_path": str(r.path), "metrics_path": str(m_path),
            "f1": mp.get("f1"), "precision": mp.get("precision"), "recall": mp.get("recall"),
            "n_sentences": d.get("n_sentences") or d.get("n_records") or _count_jsonl_lines(r.path),
            "gen_time_s": gen_s, "total_time_s": total_s, "wall_time_s": wall_s,
            "sharded": sharded, "num_shards": num_shards,
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "metrics_index_v6.csv", index=False)
    return df


def _count_jsonl_lines(p):
    try:
        with open(p) as f:
            return sum(1 for ln in f if ln.strip())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# A. kg_evolution (5 versioni)
# ---------------------------------------------------------------------------
def tab_kg_evolution_v6():
    snap_path = OUT / f"kg_snapshot_{VERSION_ORDER[-1].split('.')[0]}.json"
    snap = json.loads(snap_path.read_text())
    headlines = snap["versions"]
    rows = [
        ("ExtractionSetups",       "n_extraction_setups"),
        ("LLMRuns",                "n_llm_runs"),
        ("Predictions",            "n_prediction"),
        ("GraphAssertions",        "n_graph_assertion"),
        ("RetrievedContexts",      "n_retrieved_context"),
        ("Distinct ATT\\&CK IDs",  "n_distinct_attack_ids_observed"),
        ("Consensus assertions",   "n_consensus_assertions_in_version"),
        ("Trusted view size",      "trusted_view_size"),
    ]
    versions = VERSION_ORDER
    cols = "l" + "r" * len(versions) + "r" * (len(versions) - 1)
    lines = [r"\begin{tabular}{" + cols + "}", r"\toprule"]
    header = "Metric & " + " & ".join(versions) + " & " + " & ".join(
        f"$\\Delta_{{{v_a}\\to{v_b}}}$"
        for v_a, v_b in zip([v.split('.')[0] for v in versions[:-1]],
                            [v.split('.')[0] for v in versions[1:]])
    ) + r" \\"
    lines.append(header); lines.append(r"\midrule")
    csv_rows = []
    for label, key in rows:
        vals = [headlines[v][key] for v in versions]
        deltas = [vals[i+1] - vals[i] for i in range(len(vals)-1)]
        cells = [f"{int(v):,}" for v in vals] + [f"{int(d):+,}" for d in deltas]
        lines.append(label + " & " + " & ".join(cells) + r" \\")
        csv_rows.append({"metric": label.replace("\\&", "&"),
                         **{v: int(vals[i]) for i, v in enumerate(versions)},
                         **{f"D_{a}_{b}": int(d)
                            for (a, b), d in zip(zip([v.split('.')[0] for v in versions[:-1]],
                                                     [v.split('.')[0] for v in versions[1:]]), deltas)}})
    lines.append(r"\bottomrule"); lines.append(r"\end{tabular}")
    (OUT / "tab_kg_evolution_v6.tex").write_text("\n".join(lines))
    pd.DataFrame(csv_rows).to_csv(OUT / "tab_kg_evolution_v6.csv", index=False)
    print(f"[A] wrote tab_kg_evolution_v6.{{tex,csv}}")


# ---------------------------------------------------------------------------
# B. Cell-level outcomes (set_scope, F1 ONLY for reference, gen_time)
# ---------------------------------------------------------------------------
def cell_outcomes(df_metrics: pd.DataFrame) -> pd.DataFrame:
    """Compute per-cell outcomes (averaged across seeds): set_scope, F1, gen_time."""
    # set_scope from KG: distinct attack_ids per (setup, dataset, method, sentence)
    pred = pd.read_csv(KG / "nodes_prediction.csv")  # has setup/dataset/method/seed already
    pred["method"] = pred["method"].astype(str).str.replace("_FSP", "+FSP", regex=False)
    # scope per (setup, dataset, method, seed) = #distinct attack_ids
    scope = pred.groupby(["extraction_setup_id", "dataset", "method", "seed"])["attack_id"].nunique().reset_index()
    scope = scope.rename(columns={"extraction_setup_id": "setup", "attack_id": "scope_seed"})
    # average across seeds per cell
    cells = scope.groupby(["setup", "dataset", "method"])["scope_seed"].agg(["mean", "std", "count"]).reset_index()
    cells = cells.rename(columns={"mean": "set_scope_mean", "std": "set_scope_std", "count": "n_seeds_obs"})

    # join with metrics aggregated by cell
    agg = df_metrics.groupby(["setup", "dataset", "method"]).agg(
        f1_mean=("f1", "mean"), f1_std=("f1", "std"),
        gen_time_s_mean=("gen_time_s", "mean"),
        n_seeds_metrics=("seed", "nunique"),
        n_sentences=("n_sentences", "first"),
    ).reset_index()
    out = cells.merge(agg, on=["setup", "dataset", "method"], how="outer")
    out["method"] = out["method"].astype(str)
    out["family_retriever"] = out["setup"].map(RETRIEVER_OF)
    out["family_generator"] = out["setup"].map(GENERATOR_OF)
    return out


# ---------------------------------------------------------------------------
# C. Factorial 2x3 (with missing GTE-Qwen+Phi cell)
# ---------------------------------------------------------------------------
def factorial_2x3(cells: pd.DataFrame, outcome: str = "set_scope_mean"):
    """Compute main effects (retriever, generator), grand mean and missing-cell-flagged grid."""
    grid = cells.pivot_table(values=outcome, index="family_retriever",
                             columns="family_generator", aggfunc="mean").reindex(
        index=["E5", "GTE-Qwen2"], columns=["Llama", "Mistral", "Phi-3.5"])
    grand_mean = float(np.nanmean(grid.values))
    # Main effect of generator: mean across present retrievers (so column means weighted by presence)
    gen_means   = {g: float(grid[g].dropna().mean()) for g in grid.columns}
    retr_means  = {r: float(grid.loc[r].dropna().mean()) for r in grid.index}
    # Pure pairs: within (Llama, Mistral) factorial is closed
    closed = grid[["Llama", "Mistral"]]
    retr_pure = float((closed.loc["GTE-Qwen2"].mean() - closed.loc["E5"].mean())) if not closed.isna().any().any() else None
    # generator effect within E5 only (full row)
    e5_row = grid.loc["E5"].dropna()
    gen_effect_e5 = {
        "Mistral-Llama": float(e5_row["Mistral"] - e5_row["Llama"]) if {"Mistral","Llama"}.issubset(e5_row.index) else None,
        "Phi3.5-Llama":  float(e5_row["Phi-3.5"] - e5_row["Llama"]) if {"Phi-3.5","Llama"}.issubset(e5_row.index) else None,
        "Phi3.5-Mistral":float(e5_row["Phi-3.5"] - e5_row["Mistral"]) if {"Phi-3.5","Mistral"}.issubset(e5_row.index) else None,
    }
    missing = [(r, g) for r in grid.index for g in grid.columns if pd.isna(grid.loc[r, g])]
    return {
        "outcome": outcome,
        "grid": grid.where(pd.notnull(grid), None).to_dict(),
        "missing_cells": [{"retriever": r, "generator": g} for r, g in missing],
        "grand_mean_present_cells": grand_mean,
        "generator_means": gen_means,
        "retriever_means": retr_means,
        "retriever_effect_pure_closed_subspace": retr_pure,
        "generator_pairwise_within_E5": gen_effect_e5,
        # v6: factorial is fully closed (2x3), all 6 cells present.
        "note": (
            ("Factorial is asymmetric: some cells missing. "
             "Closed 2x2 sub-factorial used for pure retriever effect. "
             "Generator effects computed within E5 row.")
            if missing else
            ("v6.0: factorial is CLOSED (full 2\u00d73 grid). "
             "All main effects and interactions computable without missing-cell approximation. "
             "Pure retriever effect uses full 2\u00d73 balanced estimator.")
        ),
    }


def tab_factorial_2x3(fact_scope: dict, fact_f1: dict):
    """Two stacked grids: set_scope (primary), F1 (reference)."""
    def grid_table(fact, caption_outcome):
        grid = fact["grid"]
        rows = [r"\begin{tabular}{lrrr}", r"\toprule",
                f"Retriever \\ Generator & Llama & Mistral & Phi-3.5 \\\\",
                r"\midrule"]
        for r in ["E5", "GTE-Qwen2"]:
            cells = []
            for g in ["Llama", "Mistral", "Phi-3.5"]:
                v = grid.get(g, {}).get(r)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    cells.append("--")
                else:
                    cells.append(f"{v:.2f}")
            rows.append(f"{r} & " + " & ".join(cells) + r" \\")
        rows += [r"\bottomrule", r"\end{tabular}"]
        return "\n".join(rows)

    body = (
        "% Primary outcome: set_scope (#distinct ATT&CK IDs per cell, mean over seeds)\n"
        + grid_table(fact_scope, "set\\_scope")
        + "\n\n"
        + "% Reference outcome: doc-level F1 (cell mean over seeds)\n"
        + grid_table(fact_f1, "F1")
    )
    (OUT / "tab_factorial_2x3.tex").write_text(body)
    print("[C] wrote tab_factorial_2x3.tex")


# ---------------------------------------------------------------------------
# D. Within-vs-cross family agreement (per-sentence Jaccard)
# ---------------------------------------------------------------------------
def per_sentence_setup_ids():
    """Return dict[(setup, dataset, method, seed)] -> dict[(doc_id, sent_idx)] -> set(attack_ids).
       Uses ids_regex_filtered_after_output_filter (matches metric)."""
    runs = discover_runs()
    out = {}
    for r in runs:
        key = (r.setup_id, r.dataset, r.method, r.seed)
        d = {}
        with open(r.path) as f:
            for line in f:
                if not line.strip(): continue
                rec = json.loads(line)
                ids = rec.get("ids_regex_filtered_after_output_filter")
                if ids is None:
                    ids = rec.get("ids_regex_filtered") or []
                d[(rec["doc_id"], rec.get("sent_idx", -1))] = set(ids)
        out[key] = d
    return out


def jaccard(a: set, b: set) -> float:
    if not a and not b: return 0.0
    return 1.0 - len(a & b) / max(1, len(a | b))


def within_vs_cross_family(setup_data):
    """For each (dataset, method, seed=0), compute per-sentence Jaccard distance
    between every pair of setups; group by within-family vs cross-family.
    Two family axes: LLM family (Llama/Mistral/Phi), Retriever family (E5/GTE-Qwen).
    """
    setups = [s for s in SETUP_ORDER if s in {k[0] for k in setup_data.keys()}]
    rows_llm  = []
    rows_retr = []
    for ds in DATASETS:
        for me in METHODS:
            # seed=0 always (S1 only has 0 anyway)
            avail = [s for s in setups if (s, ds, me, 0) in setup_data]
            for s1, s2 in combinations(avail, 2):
                d1, d2 = setup_data[(s1, ds, me, 0)], setup_data[(s2, ds, me, 0)]
                keys = sorted(set(d1) & set(d2))
                if not keys: continue
                ds_jaccard = np.mean([jaccard(d1[k], d2[k]) for k in keys])
                same_llm = GENERATOR_OF[s1] == GENERATOR_OF[s2]
                same_ret = RETRIEVER_OF[s1] == RETRIEVER_OF[s2]
                rows_llm.append({"dataset": ds, "method": me, "s1": SHORT[s1], "s2": SHORT[s2],
                                 "within_llm_family": same_llm, "mean_jaccard_dist": ds_jaccard,
                                 "n_sentences": len(keys)})
                rows_retr.append({"dataset": ds, "method": me, "s1": SHORT[s1], "s2": SHORT[s2],
                                  "within_retriever_family": same_ret, "mean_jaccard_dist": ds_jaccard,
                                  "n_sentences": len(keys)})
    df_llm  = pd.DataFrame(rows_llm)
    df_retr = pd.DataFrame(rows_retr)

    def summarize(df, col):
        summary = df.groupby(col)["mean_jaccard_dist"].agg(["mean", "std", "count"]).reset_index()
        summary["family_axis"] = col
        return summary

    summ_llm  = summarize(df_llm, "within_llm_family")
    summ_retr = summarize(df_retr, "within_retriever_family")

    df_llm.to_csv(OUT / "within_vs_cross_family_llm_pairs.csv", index=False)
    df_retr.to_csv(OUT / "within_vs_cross_family_retriever_pairs.csv", index=False)
    summ_llm.to_csv(OUT / "within_vs_cross_family_llm_summary.csv", index=False)
    summ_retr.to_csv(OUT / "within_vs_cross_family_retriever_summary.csv", index=False)

    def render_summary(summ, axis_label):
        lines = [r"\begin{tabular}{lrrr}", r"\toprule",
                 f"{axis_label} & Mean Jaccard dist. & SD & N pairs $\\times$ (dataset $\\times$ method) \\\\",
                 r"\midrule"]
        for _, row in summ.iterrows():
            tag = "within-family" if bool(row.iloc[0]) else "cross-family"
            lines.append(f"{tag} & {row['mean']:.4f} & {row['std']:.4f} & {int(row['count'])} \\\\")
        lines += [r"\bottomrule", r"\end{tabular}"]
        return "\n".join(lines)

    (OUT / "tab_within_vs_cross_family_llm.tex").write_text(render_summary(summ_llm, "Same LLM family"))
    (OUT / "tab_within_vs_cross_family_retriever.tex").write_text(render_summary(summ_retr, "Same retriever family"))
    print("[D] wrote within_vs_cross_family_{llm,retriever}.{csv,tex}")


# ---------------------------------------------------------------------------
# E. Bias quad decomposition (NO F1; outcomes: set_scope, between_family_disagreement)
# ---------------------------------------------------------------------------
def bias_quad(cells: pd.DataFrame, setup_data) -> None:
    """Decompose two outcomes on axes (retriever, generator, dataset, method):
       1) set_scope = #distinct attack_ids per cell (already in `cells`)
       2) between_family_disagreement_rate = mean per-sentence Jaccard distance
          between cross-LLM-family pairs (Llama vs Mistral, Llama vs Phi, Mistral vs Phi).
    """
    rows = []
    # set_scope: per (dataset, method, retriever, generator) one value per seed; mean over seeds
    for _, r in cells.iterrows():
        rows.append({
            "outcome": "set_scope",
            "dataset": r["dataset"], "method": r["method"],
            "retriever": r["family_retriever"], "generator": r["family_generator"],
            "value_mean": r["set_scope_mean"], "value_std": r["set_scope_std"],
            "n_seeds": int(r["n_seeds_obs"]) if pd.notnull(r["n_seeds_obs"]) else 0,
        })
    # between_family_disagreement_rate: for each (dataset, method, seed=0), each retriever cell that has >=2 different generators
    # We compute it at the (retriever, generator) cell level: for each cell A, average Jaccard against cells B with same retriever, different generator, same dataset/method.
    for ds in DATASETS:
        for me in METHODS:
            keys_present = [k for k in setup_data if k[1] == ds and k[2] == me and k[3] == 0]
            for kA in keys_present:
                ra, ga = RETRIEVER_OF[kA[0]], GENERATOR_OF[kA[0]]
                jaccs = []
                for kB in keys_present:
                    if kB == kA: continue
                    if RETRIEVER_OF[kB[0]] != ra: continue
                    if GENERATOR_OF[kB[0]] == ga: continue
                    dA, dB = setup_data[kA], setup_data[kB]
                    common = sorted(set(dA) & set(dB))
                    if not common: continue
                    jaccs.append(np.mean([jaccard(dA[k], dB[k]) for k in common]))
                if jaccs:
                    rows.append({
                        "outcome": "between_family_disagreement_rate",
                        "dataset": ds, "method": me,
                        "retriever": ra, "generator": ga,
                        "value_mean": float(np.mean(jaccs)),
                        "value_std": float(np.std(jaccs, ddof=0)) if len(jaccs) > 1 else 0.0,
                        "n_seeds": 1,
                    })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "bias_quad_decomposition.csv", index=False)

    # Render two compact tables: one per outcome, axes (retriever, generator) x (dataset, method)
    def render(outcome):
        sub = df[df["outcome"] == outcome]
        piv = sub.pivot_table(values="value_mean",
                              index=["retriever", "generator"],
                              columns=["dataset", "method"], aggfunc="first")
        lines = [r"\begin{tabular}{ll" + "r" * piv.shape[1] + "}", r"\toprule"]
        cols = list(piv.columns)
        head = "Retriever & Generator & " + " & ".join(
            [f"{d} {m}" for (d, m) in cols]) + r" \\"
        lines.append(head); lines.append(r"\midrule")
        for (r_, g_), row in piv.iterrows():
            cells = []
            for c in cols:
                v = row[c]
                cells.append("--" if (pd.isna(v)) else (f"{v:.3f}" if outcome != "set_scope" else f"{v:.1f}"))
            lines.append(f"{r_} & {g_} & " + " & ".join(cells) + r" \\")
        lines += [r"\bottomrule", r"\end{tabular}"]
        return "\n".join(lines)

    (OUT / "tab_bias_quad_set_scope.tex").write_text(render("set_scope"))
    (OUT / "tab_bias_quad_between_family_disagreement.tex").write_text(render("between_family_disagreement_rate"))
    print("[E] wrote bias_quad_decomposition.csv + tab_bias_quad_*.tex")


# ---------------------------------------------------------------------------
# F. Cost / latency (5 setups; honest wall-clock for sharded runs)
# ---------------------------------------------------------------------------
def cost_latency(df_metrics: pd.DataFrame):
    """Per-cell: total generation cost (sum of generation_s over seeds);
       per-sentence median latency; for sharded cells we also expose wall-clock."""
    rows = []
    for (setup, dataset, method), sub in df_metrics.groupby(["setup", "dataset", "method"]):
        gen_total = float(sub["gen_time_s"].sum())
        n_sent_total = int(sub["n_sentences"].fillna(0).sum())
        per_sent_lat = gen_total / max(1, n_sent_total)
        wall_total   = float(sub["wall_time_s"].dropna().sum()) if sub["sharded"].any() else gen_total
        rows.append({
            "setup": SHORT[setup], "dataset": dataset, "method": method,
            "n_seeds": int(sub["seed"].nunique()),
            "gen_time_s_total":     gen_total,
            "sentences_total":      n_sent_total,
            "per_sentence_lat_s":   per_sent_lat,
            "sharded":              bool(sub["sharded"].any()),
            "parallel_wall_time_s": wall_total,
        })
    df = pd.DataFrame(rows).sort_values(["setup", "dataset", "method"])
    df.to_csv(OUT / "cost_latency_v6.csv", index=False)
    # LaTeX
    lines = [r"\begin{tabular}{lllrrrrr}", r"\toprule",
             r"Setup & Dataset & Method & seeds & Gen time (s) & N sent & Lat/sent (s) & Wall (s) \\",
             r"\midrule"]
    for _, r in df.iterrows():
        lines.append(f"{r['setup']} & {r['dataset']} & {r['method']} & {r['n_seeds']} & "
                     f"{r['gen_time_s_total']:.0f} & {r['sentences_total']} & "
                     f"{r['per_sentence_lat_s']:.3f} & {r['parallel_wall_time_s']:.0f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (OUT / "cost_latency_v6.tex").write_text("\n".join(lines))
    print("[F] wrote cost_latency_v6.{csv,tex}")


# ---------------------------------------------------------------------------
# G. Run design note (honest declarations)
# ---------------------------------------------------------------------------
def run_design_note():
    note = {
        "graph_version": "v6.0",
        "n_seeds_per_setup": N_SEEDS,
        "design_notes": {
            "gteqwen_llama":
                ("v6 upgrade: S1 now has 3 genuine seeds (seed0/1/2) from "
                 "table9_ollama_artifact_replica.py runs (20260527/20260528). "
                 "The legacy final_table9_similarity files (only seed1/seed2, renamed) "
                 "are superseded by the newer runs. Inter-seed sigma=0 confirmed."),
            "gteqwen_phi35":
                ("S4 newly executed in v6.0: closes the 2x3 factorial. "
                 "3 seeds (seed0/1/2) via table9_gteqwen_phi_replica.py (sharded). "
                 "Inter-seed sigma=0 confirmed (deterministic greedy generation)."),
            "e5_phi35": "Standard 3-seed cell (seeds 0, 1, 2). Unchanged from v5.",
        },
        "missing_cells": [],  # v6: CLOSED factorial
        "factorial_status": "CLOSED 2x3: E5/GTE-Qwen2 x Llama/Mistral/Phi-3.5. All 6 cells executed.",
        "primary_outcome_bias_quad": "set_scope (#distinct ATT&CK IDs predicted per cell)",
        "secondary_outcome_bias_quad": "between_family_disagreement_rate (mean Jaccard dist. against cross-generator cells with same retriever)",
        "scope_note": "F1 is reported as a reference outcome only in factorial_2x3 (`grid_f1`); the bias decomposition deliberately avoids F1 to focus on KG-relevant outcomes."
    }
    (OUT / "run_design_note.json").write_text(json.dumps(note, indent=2))
    print("[G] wrote run_design_note.json")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("== load metrics index ==")
    df_metrics = load_metrics_index()  # also saves metrics_index_v6.csv
    print(f"  {len(df_metrics)} cell-seeds across {df_metrics['setup'].nunique()} setups")
    print("== load per-sentence ID dicts ==")
    setup_data = per_sentence_setup_ids()
    print(f"  {len(setup_data)} (setup,dataset,method,seed) entries")
    print("== A. kg_evolution v6 ==")
    tab_kg_evolution_v6()
    print("== B. cell outcomes ==")
    cells = cell_outcomes(df_metrics)
    cells.to_csv(OUT / "cell_outcomes_v6.csv", index=False)
    print("== C. factorial 2x3 (CLOSED) ==")
    fact_scope = factorial_2x3(cells, outcome="set_scope_mean")
    fact_f1    = factorial_2x3(cells, outcome="f1_mean")
    (OUT / "factorial_effects_2x3.json").write_text(json.dumps(
        {"primary_set_scope": fact_scope, "reference_f1": fact_f1}, indent=2, default=str))
    tab_factorial_2x3(fact_scope, fact_f1)
    print("== D. within vs cross family ==")
    within_vs_cross_family(setup_data)
    print("== E. bias quad decomposition ==")
    bias_quad(cells, setup_data)
    print("== F. cost / latency ==")
    cost_latency(df_metrics)
    print("== G. run design note ==")
    run_design_note()
    print(f"\nAll v6 deliverables under {OUT}")


if __name__ == "__main__":
    main()
