"""Build the virtual TRACE-CTI KG as a set of CSV node/edge tables.

Output: analysis_outputs/v3_kg_analysis/kg_csv/{nodes_*.csv, edges_*.csv}
        analysis_outputs/v3_kg_analysis/kg_snapshot_v3.json

Schema (no Neo4j required; tables are Neo4j-ready via LOAD CSV):
  - nodes_extraction_setup       (3 rows)
  - nodes_import_batch           (3 rows: one per ExtractionSetup)
  - nodes_graph_version          (3 rows: v1.0, v2.0, v3.0; cumulative property `included_setups`)
  - nodes_llm_run                (1 per (setup, dataset, method, seed); 32 total)
  - nodes_report                 (1 per doc_id)
  - nodes_sentence               (1 per (doc_id, sent_idx))
  - nodes_attack_id              (1 per ATT&CK ID observed in predictions OR gold)
  - nodes_prediction             (1 per (llm_run, sentence, attack_id))   -> all 3 seeds preserved
  - nodes_graph_assertion        (1 per (setup, dataset, method, sentence, attack_id))
                                 reified setup-level assertion; sigma=0 collapses 3 seeds -> 1
  - nodes_retrieved_context      (1 per (setup_id, sentence, rank))
  - nodes_consensus_assertion    (1 per (sentence, attack_id) with >=2 setup support; v2/v3 only)
  - edges_predicted_by           prediction -> llm_run
  - edges_evidenced_by           prediction -> sentence
  - edges_about                  prediction -> attack_id
  - edges_assertion_evidence     graph_assertion -> sentence
  - edges_assertion_about        graph_assertion -> attack_id
  - edges_assertion_setup        graph_assertion -> extraction_setup
  - edges_retrieved              retrieved_context -> attack_id ; retrieved_context -> sentence
  - edges_agrees_with            assertion <-> assertion (same (sentence, id), diff setups)
  - edges_disagrees_with         assertion -> sentence with another setup emitting a different id-set there
  - edges_supports               consensus_assertion -> graph_assertion (one per supporting setup)
  - edges_version_includes       graph_version -> import_batch (cumulative)

Trust scopes (property `trust_scope` on graph_assertion):
  - "prediction_only"      : default for setup-level assertion
  - "gold_backed"          : (doc_id, attack_id) present in gold
  - "consensus_validated"  : >=2 distinct setups (within version) emit (doc_id, sent_idx, attack_id)
  - "strong_consensus"     : all k setups in version emit it (k=3 in v3.0)
A single assertion gets the strongest applicable scope (gold_backed > strong_consensus > consensus_validated > prediction_only).

`first_seen_version` property on every node/edge: the earliest version in which it exists.
A "view" of a given GraphVersion = WHERE first_seen_version <= version.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

from kg_v3.manifest import SETUPS, GRAPH_VERSIONS, discover_runs
from kg_v3.load import load_all
from kg_v3.gold import load_all_gold

# Default output root corresponds to the *latest* version in GRAPH_VERSIONS.
# Override with KG_OUT_VERSION env var or --out-version CLI flag (e.g. v3, v4).
_LATEST_VERSION = GRAPH_VERSIONS[-1]["version_id"]              # "v4.0"
_LATEST_VTAG    = _LATEST_VERSION.split(".")[0]                  # "v4"
_DEFAULT_VTAG   = os.environ.get("KG_OUT_VERSION", _LATEST_VTAG)
OUT_ROOT = Path(f"/home/azureuser/ttp_table9_method_replication/analysis_outputs/{_DEFAULT_VTAG}_kg_analysis")
KG_DIR   = OUT_ROOT / "kg_csv"

# Mapping setup -> first version in which it appears
SETUP_FIRST_VERSION = {}
for gv in GRAPH_VERSIONS:
    for sid in gv["setups"]:
        SETUP_FIRST_VERSION.setdefault(sid, gv["version_id"])

VERSION_ORDER = [gv["version_id"] for gv in GRAPH_VERSIONS]


def _vmin(*versions):
    """Return the smallest (earliest) version string among args."""
    return min(versions, key=lambda v: VERSION_ORDER.index(v))


def _vmax(*versions):
    return max(versions, key=lambda v: VERSION_ORDER.index(v))


def build():
    KG_DIR.mkdir(parents=True, exist_ok=True)
    runs = discover_runs()
    df_pred, df_sent, df_retr = load_all(runs)
    df_gold_sent, df_gold_doc = load_all_gold()

    # --- nodes_extraction_setup -----------------------------------------------
    es_rows = []
    for sid, meta in SETUPS.items():
        es_rows.append({
            "extraction_setup_id": sid,
            "retriever": meta["retriever"],
            "generator": meta["generator"],
            "sampler": "greedy (do_sample=False, T=0.0)",
            "seed_range": "0,1,2" if sid != "gteqwen_llama" else "0,1 (renamed from canonical seed1,seed2)",
            "import_batch_id": meta["import_batch_id"],
            "first_seen_version": SETUP_FIRST_VERSION[sid],
        })
    df_es = pd.DataFrame(es_rows)

    # --- nodes_import_batch ---------------------------------------------------
    ib_rows = []
    for sid, meta in SETUPS.items():
        ib_rows.append({
            "import_batch_id": meta["import_batch_id"],
            "extraction_setup_id": sid,
            "first_seen_version": SETUP_FIRST_VERSION[sid],
        })
    df_ib = pd.DataFrame(ib_rows)

    # --- nodes_graph_version --------------------------------------------------
    gv_rows = [{
        "graph_version_id": gv["version_id"],
        "included_setups": "|".join(gv["setups"]),
        "included_import_batches": "|".join(SETUPS[s]["import_batch_id"] for s in gv["setups"]),
    } for gv in GRAPH_VERSIONS]
    df_gv = pd.DataFrame(gv_rows)

    # --- edges_version_includes ----------------------------------------------
    vi_rows = []
    for gv in GRAPH_VERSIONS:
        for sid in gv["setups"]:
            vi_rows.append({"graph_version_id": gv["version_id"], "import_batch_id": SETUPS[sid]["import_batch_id"]})
    df_vi = pd.DataFrame(vi_rows)

    # --- nodes_llm_run --------------------------------------------------------
    runs_df = pd.DataFrame([{
        "llm_run_id": f"{r.setup_id}__{r.dataset}__{r.method}__seed{r.seed}",
        "extraction_setup_id": r.setup_id,
        "dataset": r.dataset, "method": r.method, "seed": r.seed,
        "original_seed": r.original_seed, "source_file": r.path.name,
        "import_batch_id": SETUPS[r.setup_id]["import_batch_id"],
        "first_seen_version": SETUP_FIRST_VERSION[r.setup_id],
    } for r in runs])

    # --- nodes_report / nodes_sentence ---------------------------------------
    rep_df = (df_sent[["dataset", "doc_id"]].drop_duplicates()
              .assign(first_seen_version="v1.0")
              .rename(columns={"doc_id": "report_id"})
              .reset_index(drop=True))
    sent_df = (df_sent[["dataset", "doc_id", "sent_idx", "sentence"]]
               .drop_duplicates(subset=["doc_id", "sent_idx"])
               .assign(sentence_id=lambda d: d["doc_id"] + "__s" + d["sent_idx"].astype(str),
                       first_seen_version="v1.0")
               .reset_index(drop=True))

    # --- nodes_prediction -----------------------------------------------------
    # One per (llm_run, sentence, attack_id). Keeps all 3 seeds for provenance.
    pred_df = df_pred.copy()
    pred_df["llm_run_id"] = (pred_df["setup_id"] + "__" + pred_df["dataset"] + "__"
                             + pred_df["method"] + "__seed" + pred_df["seed"].astype(str))
    pred_df["sentence_id"] = pred_df["doc_id"] + "__s" + pred_df["sent_idx"].astype(str)
    pred_df["prediction_id"] = (pred_df["llm_run_id"] + "::" + pred_df["sentence_id"]
                                + "::" + pred_df["attack_id"])
    pred_df["first_seen_version"] = pred_df["setup_id"].map(SETUP_FIRST_VERSION)
    pred_out = pred_df[["prediction_id", "llm_run_id", "extraction_setup_id" if False else "setup_id",
                        "dataset", "method", "seed", "sentence_id", "attack_id", "first_seen_version"]].copy()
    pred_out = pred_out.rename(columns={"setup_id": "extraction_setup_id"})

    # --- nodes_graph_assertion ------------------------------------------------
    # Reified setup-level: (setup, dataset, method, sentence, attack_id).
    # sigma=0 means seed dimension collapses; we still record support_seeds for provenance.
    assert_grp = (pred_df.groupby(
        ["setup_id", "dataset", "method", "sentence_id", "doc_id", "sent_idx", "attack_id"], as_index=False
    ).agg(support_seeds=("seed", lambda s: ",".join(sorted({str(x) for x in s})))))
    assert_grp["graph_assertion_id"] = (assert_grp["setup_id"] + "::" + assert_grp["dataset"] + "::"
                                        + assert_grp["method"] + "::" + assert_grp["sentence_id"]
                                        + "::" + assert_grp["attack_id"])
    assert_grp["first_seen_version"] = assert_grp["setup_id"].map(SETUP_FIRST_VERSION)

    # gold doc-level set per (dataset, doc_id)
    gold_doc_set = defaultdict(set)
    for _, row in df_gold_doc.iterrows():
        gold_doc_set[(row["dataset"], row["doc_id"])].add(row["attack_id"])

    # Setup-level emission set per (dataset, method, sentence_id, attack_id) -> set of setups
    support_by_key = defaultdict(set)
    for _, row in assert_grp.iterrows():
        support_by_key[(row["dataset"], row["method"], row["sentence_id"], row["attack_id"])].add(row["setup_id"])

    # Assign trust_scope per assertion (in the *latest* version each row will live in v=first_seen_version_of_setup..v3.0)
    # The "current" trust_scope reported on the node is the scope it reaches by v3.0 (strongest applicable);
    # we additionally annotate `scope_v1`, `scope_v2`, `scope_v3` so per-version analysis can re-derive scope.
    def scope_for_assertion(setup_id, dataset, method, sentence_id, attack_id, doc_id, version):
        # Active setups in `version`
        active = next(gv["setups"] for gv in GRAPH_VERSIONS if gv["version_id"] == version)
        if setup_id not in active:
            return None  # not in this version
        supporters_in_version = support_by_key[(dataset, method, sentence_id, attack_id)] & set(active)
        n_active = len(active)
        n_sup = len(supporters_in_version)
        # gold-backed (doc-level proxy, both datasets supported)
        gold = attack_id in gold_doc_set.get((dataset, doc_id), set())
        if gold:
            return "gold_backed"
        if n_sup >= n_active and n_active >= 2:
            return "strong_consensus"
        if n_sup >= 2:
            return "consensus_validated"
        return "prediction_only"

    # Compute scope_v<n> columns for every declared GraphVersion (version-agnostic).
    scope_columns = {}  # version_id_short -> list aligned with assert_grp
    for v in VERSION_ORDER:
        scope_columns[v] = []
    for _, row in assert_grp.iterrows():
        args = (row["setup_id"], row["dataset"], row["method"], row["sentence_id"], row["attack_id"], row["doc_id"])
        for v in VERSION_ORDER:
            scope_columns[v].append(scope_for_assertion(*args, v))
    for v in VERSION_ORDER:
        # short form: v1.0 -> scope_v1, v4.0 -> scope_v4
        short = "scope_" + v.split(".")[0]
        assert_grp[short] = scope_columns[v]
    # legacy aliases preserved for downstream code that still references scope_v1..v3
    if "scope_v1" not in assert_grp.columns and "v1.0" in scope_columns:
        assert_grp["scope_v1"] = scope_columns["v1.0"]
    if "scope_v2" not in assert_grp.columns and "v2.0" in scope_columns:
        assert_grp["scope_v2"] = scope_columns["v2.0"]
    if "scope_v3" not in assert_grp.columns and "v3.0" in scope_columns:
        assert_grp["scope_v3"] = scope_columns["v3.0"]
    # The 'trust_scope' column reports the scope in the LATEST declared version.
    latest_scope_col = "scope_" + VERSION_ORDER[-1].split(".")[0]
    assert_grp["trust_scope"] = assert_grp[latest_scope_col]

    # --- nodes_attack_id ------------------------------------------------------
    aid_all = set(pred_df["attack_id"]) | set(df_gold_doc["attack_id"])
    aid_df = pd.DataFrame({"attack_id": sorted(aid_all)})
    aid_df["in_gold"] = aid_df["attack_id"].isin(set(df_gold_doc["attack_id"]))
    aid_df["first_seen_version"] = "v1.0"  # the ATT&CK label space pre-exists ingestion

    # --- nodes_retrieved_context ---------------------------------------------
    # GTE-Qwen2 retrieval cache is shared between S1 and S3, so its retrieved contexts
    # are identical -> we deduplicate by (retriever, sentence, rank, attack_id).
    df_retr = df_retr.copy()
    df_retr["sentence_id"] = df_retr["doc_id"] + "__s" + df_retr["sent_idx"].astype(str)
    df_retr["retriever_key"] = df_retr["setup_id"].map({
        "gteqwen_llama": "gteqwen2_7b", "gteqwen_mistral": "gteqwen2_7b",
        "e5_mistral": "e5_large_v2", "e5_llama": "e5_large_v2",
    })
    rc_unique = (df_retr.drop_duplicates(subset=["retriever_key", "dataset", "method", "sentence_id", "rank"])
                 .copy())
    rc_unique["retrieved_context_id"] = (rc_unique["retriever_key"] + "::" + rc_unique["dataset"]
                                         + "::" + rc_unique["method"] + "::" + rc_unique["sentence_id"]
                                         + "::r" + rc_unique["rank"].astype(str))
    # first_seen_version: GTE-Qwen2 retrievals first appear in v1.0; E5 in v2.0
    rc_unique["first_seen_version"] = rc_unique["retriever_key"].map({
        "gteqwen2_7b": "v1.0", "e5_large_v2": "v2.0",
    })

    # --- nodes_consensus_assertion -------------------------------------------
    # Definition: (dataset, method, sentence_id, attack_id) supported by >=2 setups.
    # Aggregate per consensus unit and compute support count per version.
    latest_active = set(GRAPH_VERSIONS[-1]["setups"])
    cons_rows = []
    for (ds, mt, sid_sent, aid), supporters in support_by_key.items():
        if len(supporters) < 2:
            continue
        # find the version where consensus first emerges
        first_v = None
        for gv in GRAPH_VERSIONS:
            sup_in_v = supporters & set(gv["setups"])
            if len(sup_in_v) >= 2:
                first_v = gv["version_id"]
                break
        if first_v is None:
            continue
        # strong consensus in latest version = all active setups in latest version agree
        sup_in_latest = supporters & latest_active
        is_strong = len(sup_in_latest) >= len(latest_active) and len(latest_active) >= 2
        # gold flag (doc-level)
        doc_id = sid_sent.split("__s")[0]
        gold = aid in gold_doc_set.get((ds, doc_id), set())
        cons_rows.append({
            "consensus_assertion_id": f"cons::{ds}::{mt}::{sid_sent}::{aid}",
            "dataset": ds, "method": mt, "sentence_id": sid_sent, "doc_id": doc_id,
            "attack_id": aid,
            "n_supporters_v3": len(supporters),         # kept for backward compat — total supporters across ALL setups
            "n_supporters_latest": len(sup_in_latest),  # supporters in latest version
            "supporters_v3": "|".join(sorted(supporters)),       # legacy column name (all setups)
            "supporters_latest": "|".join(sorted(sup_in_latest)),
            "scope": "strong_consensus" if is_strong else "consensus_validated",
            "gold_backed": bool(gold),
            "first_seen_version": first_v,
        })
    cons_df = pd.DataFrame(cons_rows)

    # --- edges_supports : consensus_assertion -> graph_assertion -------------
    sup_edges = []
    if len(cons_df):
        # Build lookup: (setup, dataset, method, sentence, aid) -> graph_assertion_id
        ga_lookup = {}
        for _, row in assert_grp.iterrows():
            ga_lookup[(row["setup_id"], row["dataset"], row["method"],
                       row["sentence_id"], row["attack_id"])] = row["graph_assertion_id"]
        for _, row in cons_df.iterrows():
            for sup in row["supporters_v3"].split("|"):
                ga_id = ga_lookup.get((sup, row["dataset"], row["method"], row["sentence_id"], row["attack_id"]))
                if ga_id is None:
                    continue
                sup_edges.append({
                    "consensus_assertion_id": row["consensus_assertion_id"],
                    "graph_assertion_id": ga_id,
                    "supporting_setup_id": sup,
                    "first_seen_version": row["first_seen_version"],
                })
    sup_edges_df = pd.DataFrame(sup_edges)

    # --- edges_agrees_with / edges_disagrees_with (assertion <-> assertion) --
    # For each (dataset, method, sentence_id, attack_id) supported by >=2 setups,
    # add AGREES_WITH between each pair of supporting graph_assertions.
    agree_edges = []
    if not cons_df.empty:
        ga_idx = {}
        for _, row in assert_grp.iterrows():
            key = (row["dataset"], row["method"], row["sentence_id"], row["attack_id"])
            ga_idx.setdefault(key, []).append((row["setup_id"], row["graph_assertion_id"]))
        for _, row in cons_df.iterrows():
            key = (row["dataset"], row["method"], row["sentence_id"], row["attack_id"])
            ga_list = sorted(ga_idx.get(key, []))
            for i in range(len(ga_list)):
                for j in range(i+1, len(ga_list)):
                    a, b = ga_list[i][1], ga_list[j][1]
                    sup_a, sup_b = ga_list[i][0], ga_list[j][0]
                    fsv = _vmax(SETUP_FIRST_VERSION[sup_a], SETUP_FIRST_VERSION[sup_b])
                    agree_edges.append({
                        "graph_assertion_id_a": a, "graph_assertion_id_b": b,
                        "setup_a": sup_a, "setup_b": sup_b,
                        "first_seen_version": fsv,
                    })
    agree_df = pd.DataFrame(agree_edges)

    # Disagreement edges: a per-(sentence, pair_of_setups, dataset, method) record where the
    # two setups' attack_id-sets on that sentence differ. We index symmetric difference size.
    # Build per-(setup, dataset, method, sentence) -> set(attack_ids)
    set_per_key = defaultdict(set)
    for _, row in pred_df.iterrows():
        set_per_key[(row["setup_id"], row["dataset"], row["method"], row["sentence_id"])].add(row["attack_id"])
    # universe of sentences
    sentences = sent_df["sentence_id"].tolist()
    methods = ["RAG", "RAG+FSP"]
    # All-pairs across declared setups, ordered alphabetically for stable IDs.
    setup_pairs = [tuple(sorted(p)) for p in combinations(sorted(SETUPS.keys()), 2)]
    sent_dataset = dict(zip(sent_df["sentence_id"], sent_df["dataset"]))
    dis_edges = []
    for sid_sent in sentences:
        ds = sent_dataset[sid_sent]
        for mt in methods:
            for a, b in setup_pairs:
                set_a = set_per_key.get((a, ds, mt, sid_sent), set())
                set_b = set_per_key.get((b, ds, mt, sid_sent), set())
                sym = set_a.symmetric_difference(set_b)
                if sym:
                    fsv = _vmax(SETUP_FIRST_VERSION[a], SETUP_FIRST_VERSION[b])
                    dis_edges.append({
                        "sentence_id": sid_sent, "dataset": ds, "method": mt,
                        "setup_a": a, "setup_b": b,
                        "n_a_only": len(set_a - set_b), "n_b_only": len(set_b - set_a),
                        "n_intersection": len(set_a & set_b),
                        "first_seen_version": fsv,
                    })
    dis_df = pd.DataFrame(dis_edges)

    # --- edges_predicted_by / evidenced_by / about ---------------------------
    pe = pred_df[["prediction_id", "llm_run_id", "sentence_id", "attack_id", "first_seen_version"]].copy()
    edges_predicted_by = pe[["prediction_id", "llm_run_id", "first_seen_version"]]
    edges_evidenced_by = pe[["prediction_id", "sentence_id", "first_seen_version"]]
    edges_about        = pe[["prediction_id", "attack_id", "first_seen_version"]]

    # --- assertion edges ------------------------------------------------------
    ae = assert_grp[["graph_assertion_id", "sentence_id", "attack_id", "setup_id", "first_seen_version"]].copy()
    edges_assertion_evidence = ae[["graph_assertion_id", "sentence_id", "first_seen_version"]]
    edges_assertion_about    = ae[["graph_assertion_id", "attack_id", "first_seen_version"]]
    edges_assertion_setup    = ae[["graph_assertion_id", "setup_id", "first_seen_version"]].rename(
        columns={"setup_id": "extraction_setup_id"})

    # --- retrieved edges ------------------------------------------------------
    edges_retrieved_about    = rc_unique[["retrieved_context_id", "attack_id", "first_seen_version"]]
    edges_retrieved_for_sent = rc_unique[["retrieved_context_id", "sentence_id", "first_seen_version"]]

    # ===================== WRITE ALL CSVs =====================================
    def w(df, name):
        path = KG_DIR / name
        df.to_csv(path, index=False)
        return name, len(df)

    written = []
    written.append(w(df_es, "nodes_extraction_setup.csv"))
    written.append(w(df_ib, "nodes_import_batch.csv"))
    written.append(w(df_gv, "nodes_graph_version.csv"))
    written.append(w(df_vi, "edges_version_includes.csv"))
    written.append(w(runs_df, "nodes_llm_run.csv"))
    written.append(w(rep_df, "nodes_report.csv"))
    written.append(w(sent_df, "nodes_sentence.csv"))
    written.append(w(aid_df, "nodes_attack_id.csv"))
    written.append(w(pred_out, "nodes_prediction.csv"))
    _scope_cols = ["scope_" + v.split(".")[0] for v in VERSION_ORDER]
    written.append(w(assert_grp[[
        "graph_assertion_id", "setup_id", "dataset", "method", "sentence_id", "doc_id",
        "sent_idx", "attack_id", "support_seeds", "first_seen_version",
        *_scope_cols, "trust_scope",
    ]], "nodes_graph_assertion.csv"))
    written.append(w(rc_unique[[
        "retrieved_context_id", "retriever_key", "dataset", "method", "sentence_id",
        "rank", "attack_id", "name", "score", "first_seen_version",
    ]], "nodes_retrieved_context.csv"))
    written.append(w(cons_df, "nodes_consensus_assertion.csv"))
    written.append(w(sup_edges_df, "edges_supports.csv"))
    written.append(w(agree_df, "edges_agrees_with.csv"))
    written.append(w(dis_df, "edges_disagrees_with.csv"))
    written.append(w(edges_predicted_by, "edges_predicted_by.csv"))
    written.append(w(edges_evidenced_by, "edges_evidenced_by.csv"))
    written.append(w(edges_about, "edges_about.csv"))
    written.append(w(edges_assertion_evidence, "edges_assertion_evidence.csv"))
    written.append(w(edges_assertion_about, "edges_assertion_about.csv"))
    written.append(w(edges_assertion_setup, "edges_assertion_setup.csv"))
    written.append(w(edges_retrieved_about, "edges_retrieved_about.csv"))
    written.append(w(edges_retrieved_for_sent, "edges_retrieved_for_sent.csv"))

    # ===================== AUDIT JSON =========================================
    # Retriever -> set of setups that use it (for headline filtering)
    _RETRIEVER_TO_SETUPS = {
        "gteqwen2_7b": {"gteqwen_llama", "gteqwen_mistral"},
        "e5_large_v2": {"e5_mistral", "e5_llama"},
    }

    def headline_for_version(version):
        active = next(gv["setups"] for gv in GRAPH_VERSIONS if gv["version_id"] == version)
        active_set = set(active)
        # Filter assertions
        a = assert_grp[assert_grp["setup_id"].isin(active)]
        p = pred_df[pred_df["setup_id"].isin(active)]
        active_retrievers = [rk for rk, setups in _RETRIEVER_TO_SETUPS.items() if active_set & setups]
        r = rc_unique[rc_unique["retriever_key"].isin(active_retrievers)]
        # scope column per version (dynamic)
        scope_col = "scope_" + version.split(".")[0]
        scope_counts = a[scope_col].value_counts().to_dict()
        # Trusted view = scope in {gold_backed, consensus_validated, strong_consensus}
        trusted_scopes = {"gold_backed", "consensus_validated", "strong_consensus"}
        trusted = a[a[scope_col].isin(trusted_scopes)]
        return {
            "n_extraction_setups": len(active),
            "n_llm_runs": int((runs_df["extraction_setup_id"].isin(active)).sum()),
            "n_prediction": int(len(p)),
            "n_graph_assertion": int(len(a)),
            "n_retrieved_context": int(len(r)),
            "n_distinct_attack_ids_observed": int(a["attack_id"].nunique()) if len(a) else 0,
            "n_consensus_assertions_in_version": int((cons_df["first_seen_version"].apply(
                lambda v: VERSION_ORDER.index(v) <= VERSION_ORDER.index(version)
            )).sum()) if len(cons_df) else 0,
            "scope_counts": {k: int(v) for k, v in scope_counts.items() if k is not None},
            "trusted_view_size": int(len(trusted)),
            "trusted_view_predictions_leak": 0,  # by construction: only graph_assertion nodes appear in trusted view; raw Prediction nodes never
        }

    snapshot = {
        "build_timestamp_utc": pd.Timestamp.utcnow().isoformat(),
        "consensus_unit": "(dataset, method, sentence_id, attack_id)",
        "prediction_field": "ids_regex_filtered_after_output_filter",
        "datasets": {
            "TRAM2":   {"n_reports": int(rep_df[rep_df.dataset == "TRAM2"]["report_id"].nunique()),
                        "n_sentences": int(sent_df[sent_df.dataset == "TRAM2"].shape[0])},
            "AnnoCTR": {"n_reports": int(rep_df[rep_df.dataset == "AnnoCTR"]["report_id"].nunique()),
                        "n_sentences": int(sent_df[sent_df.dataset == "AnnoCTR"].shape[0])},
        },
        "gold": {
            "n_doc_level_assertions": int(len(df_gold_doc)),
            "n_distinct_attack_ids_gold": int(df_gold_doc["attack_id"].nunique()),
            "per_dataset": df_gold_doc.groupby("dataset")["attack_id"].nunique().to_dict(),
        },
        "csv_files_written": [{"name": n, "rows": k} for n, k in written],
        "versions": {v: headline_for_version(v) for v in VERSION_ORDER},
        "trust_policy_violations": {
            "predictions_in_trusted_view": 0,
            "explanation": "Raw Prediction nodes are NEVER placed in the trusted view by construction; only GraphAssertion nodes with trust_scope in {gold_backed, consensus_validated, strong_consensus} are. Verified by schema.",
        },
    }
    snapshot_name = f"kg_snapshot_{VERSION_ORDER[-1].split('.')[0]}.json"
    (OUT_ROOT / snapshot_name).write_text(json.dumps(snapshot, indent=2, default=str))
    snapshot["_snapshot_file"] = str(OUT_ROOT / snapshot_name)

    return snapshot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-version", default=_DEFAULT_VTAG,
                    help="Short version tag for output dir (e.g. v3, v4). "
                         "Default = latest in GRAPH_VERSIONS or KG_OUT_VERSION env.")
    args = ap.parse_args()
    # Reassign globals if user overrode via CLI (env was applied at import time)
    OUT_ROOT = Path(f"/home/azureuser/ttp_table9_method_replication/analysis_outputs/{args.out_version}_kg_analysis")
    KG_DIR = OUT_ROOT / "kg_csv"
    s = build()
    import pprint
    pprint.pp(s["versions"])
    print(f"\nCSVs written under: {KG_DIR}")
    print(f"Snapshot dir: {OUT_ROOT}")
