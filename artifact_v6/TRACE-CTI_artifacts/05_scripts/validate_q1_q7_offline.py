"""Offline semantic validation of audit_queries_q1_q7.cypher against the CSVs.

Mirrors each of the seven Cypher queries with pandas on 01_kg_snapshot_v6/,
so column names, value formats, and join keys are exercised end-to-end.
Run from the artifact root:  python 05_scripts/validate_q1_q7_offline.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "01_kg_snapshot_v6" / "kg_csv"
GOLD = ROOT / "01_kg_snapshot_v6" / "gold" / "gold_assertions.csv"

ok = 0
fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    status = "PASS" if cond else "FAIL"
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


A = pd.read_csv(K / "nodes_graph_assertion.csv")
S = pd.read_csv(K / "nodes_sentence.csv")
R = pd.read_csv(K / "nodes_report.csv")
P = pd.read_csv(K / "nodes_prediction.csv")
RUN = pd.read_csv(K / "nodes_llm_run.csv")
SETUP = pd.read_csv(K / "nodes_extraction_setup.csv")
CONS = pd.read_csv(K / "nodes_consensus_assertion.csv")
E_EV = pd.read_csv(K / "edges_assertion_evidence.csv")
E_SET = pd.read_csv(K / "edges_assertion_setup.csv")
E_SUP = pd.read_csv(K / "edges_supports.csv")
DIS = pd.read_csv(K / "edges_disagrees_with.csv")

# Pick a corroborated assertion as the running example.
sample = A[A.trust_scope == "consensus_validated"].iloc[0]
aid = sample.graph_assertion_id

# Q1 — evidence walk: assertion -> sentence -> report
ev = E_EV[E_EV.graph_assertion_id == aid]
check("Q1 assertion->sentence edge exists", len(ev) == 1)
sent = S[S.sentence_id == ev.iloc[0].sentence_id]
check("Q1 sentence node + text", len(sent) == 1 and isinstance(sent.iloc[0].sentence, str) and len(sent.iloc[0].sentence) > 0)
rep = R[(R.dataset == sent.iloc[0].dataset) & (R.report_id == sent.iloc[0].doc_id)]
check("Q1 report containment (dataset::doc_id)", len(rep) == 1, f"{sent.iloc[0].dataset}::{sent.iloc[0].doc_id}")

# Q2 — provenance: assertion -> setup (retriever/generator) -> per-seed runs
es = E_SET[E_SET.graph_assertion_id == aid]
check("Q2 assertion->setup edge", len(es) == 1)
st = SETUP[SETUP.extraction_setup_id == es.iloc[0].extraction_setup_id]
check("Q2 setup has retriever+generator", len(st) == 1 and pd.notna(st.iloc[0].retriever) and pd.notna(st.iloc[0].generator),
      f"{st.iloc[0].retriever} x {st.iloc[0].generator}")
preds = P[(P.sentence_id == sample.sentence_id) & (P.attack_id == sample.attack_id)
          & (P.extraction_setup_id == st.iloc[0].extraction_setup_id) & (P.method == sample.method)]
check("Q2 per-seed predictions found", len(preds) >= 1, f"{len(preds)} preds, seeds {sorted(preds.seed.unique())}")
check("Q2 predictions link to LLMRuns", preds.llm_run_id.isin(RUN.llm_run_id).all())

# Q3 — trust scope + witness support
check("Q3 trust_scope populated on all assertions", A.trust_scope.notna().all()
      and set(A.trust_scope.unique()) <= {"gold_backed", "strong_consensus", "consensus_validated", "prediction_only"},
      str(sorted(A.trust_scope.unique())))
sup = E_SUP[E_SUP.graph_assertion_id == aid]
check("Q3 SUPPORTS edge reaches the corroborated assertion", len(sup) >= 1)
c = CONS[CONS.consensus_assertion_id.isin(sup.consensus_assertion_id)]
check("Q3 consensus node exposes n_supporters_latest >= 2", (c.n_supporters_latest >= 2).all())

# Q4 — version views materialised
for col in ["scope_v1", "scope_v2", "scope_v3", "scope_v4", "scope_v5", "scope_v6"]:
    assert col in A.columns, col
in_v1 = A.scope_v1.notna() & (A.scope_v1 != "")
in_v3 = A.scope_v3.notna() & (A.scope_v3 != "")
in_v6 = A.scope_v6.notna() & (A.scope_v6 != "")
check("Q4 view sizes monotone v1<=v3<=v6", in_v1.sum() <= in_v3.sum() <= in_v6.sum(),
      f"{in_v1.sum()} <= {in_v3.sum()} <= {in_v6.sum()}")
check("Q4 v6 view covers all assertions", int(in_v6.sum()) == len(A), f"{in_v6.sum()}/{len(A)}")

# Q5 — revocation dry-run (sole-witness targets for one setup)
setup_id = "e5_mistral"
mine = A.merge(E_SET, on="graph_assertion_id")
mine = mine[mine.extraction_setup_id == setup_id]
others = A.merge(E_SET, on="graph_assertion_id")
others = others[others.extraction_setup_id != setup_id][["sentence_id", "attack_id", "method"]].drop_duplicates()
sole = mine.merge(others, on=["sentence_id", "attack_id", "method"], how="left", indicator=True)
sole = sole[sole._merge == "left_only"]
check("Q5 sole-witness set non-empty and < total", 0 < len(sole) < len(mine), f"{len(sole)}/{len(mine)} sole-witness")

# Q6 — axis attribution on Disagreement pairs
d = DIS.merge(SETUP.add_prefix("a_"), left_on="setup_a", right_on="a_extraction_setup_id") \
       .merge(SETUP.add_prefix("b_"), left_on="setup_b", right_on="b_extraction_setup_id")
axis = pd.Series("both axes", index=d.index)
axis[(d.a_generator == d.b_generator) & (d.a_retriever != d.b_retriever)] = "retriever effect"
axis[(d.a_generator != d.b_generator) & (d.a_retriever == d.b_retriever)] = "generator effect"
counts = axis.value_counts()
check("Q6 all three attribution classes present", set(counts.index) == {"retriever effect", "generator effect", "both axes"},
      str(counts.to_dict()))

# Q7 — review queue
po = A[A.trust_scope == "prediction_only"]
check("Q7 prediction-only queue non-empty", len(po) > 0, f"{len(po)} candidates")

# Cross-check with paper headline numbers (Table 5)
check("Table5 GraphAssertion == 27420", len(A) == 27420, str(len(A)))
check("Table5 Prediction == 82260", len(P) == 82260, str(len(P)))
check("Table5 ConsensusAssertion == 5410", len(CONS) == 5410, str(len(CONS)))
check("Table5 LLMRun == 72", len(RUN) == 72, str(len(RUN)))
check("Table5 setups == 6", len(SETUP) == 6, str(len(SETUP)))
check("Table5 SUPPORTS == 15120", len(E_SUP) == 15120, str(len(E_SUP)))
g = pd.read_csv(GOLD)
check("Gold doc-level tuples == 663 (824 KG instances collapse)", len(g) == 663, str(len(g)))

print(f"\n{ok} PASS, {fail} FAIL")
sys.exit(1 if fail else 0)
