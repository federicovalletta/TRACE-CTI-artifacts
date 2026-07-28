"""Manifest mapping JSONL prediction files -> (setup, dataset, method, seed).

Discard policy (per project brief):
  - DROP `TRAM2_RAG_seed0_parallel_sanity_20260510_192637*`  (F1=0 dry-run)
  - DROP `AnnoCTR_RAG+FSP_seed0_ollama_annoctr_conservative_seed0_20260510_204956*`
    (pipeline diversa, F1=29.32; sostituito da `final_table9_similarity`).
  - DROP every `_shardNofK` (we use the merged JSONL).
  - DROP `*_dryrun*`, `*ollama_conservative_dryrun*`, `*_limit*`, `smoke_*`.
  - DROP intermediate Mistral+E5 tags that are NOT the final canonical one.

S1 (gteqwen_llama) seed0:
  - The canonical `final_table9_similarity` tag only exists for seed1 and seed2.
  - We RENAME seed1 -> seed0 and seed2 -> seed1 (sigma=0 inter-seed determinism
    makes the seeds fungible; documented choice).

Setup IDs (stable):
  - S1 = gteqwen_llama         (retriever=GTE-Qwen2-7B Ollama F16, generator=Llama-3.1-8B-Instruct)
  - S2 = e5_mistral            (retriever=E5-large-v2 HF,           generator=Mistral-7B-Instruct-v0.3 HF)
  - S3 = gteqwen_mistral       (retriever=GTE-Qwen2-7B Ollama F16,  generator=Mistral-7B-Instruct-v0.3 HF)
  - S0 = e5_llama              (retriever=E5-large-v2 HF,           generator=Llama-3.1-8B-Instruct HF)
    -> closes the factorial 2x2 (retriever x generator). Populates GraphVersion v4.0.
  - S5 = e5_phi35              (retriever=E5-large-v2 HF,           generator=Phi-3.5-mini-instruct HF)
    -> extends to 2x3 (E5/GTE-Qwen x Llama/Mistral/Phi); GTE-Qwen+Phi NOT executed.
       Populates GraphVersion v5.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PREDICTIONS_DIR = Path("/home/azureuser/ttp_table9_method_replication/outputs/predictions")

SETUPS = {
    "gteqwen_llama":   {"retriever": "GTE-Qwen2-7B (Ollama F16)",  "generator": "Llama-3.1-8B-Instruct",   "import_batch_id": "ib_S1_gteqwen_llama"},
    "e5_mistral":      {"retriever": "E5-large-v2 (HF)",            "generator": "Mistral-7B-Instruct-v0.3","import_batch_id": "ib_S2_e5_mistral"},
    "gteqwen_mistral": {"retriever": "GTE-Qwen2-7B (Ollama F16)",  "generator": "Mistral-7B-Instruct-v0.3","import_batch_id": "ib_S3_gteqwen_mistral"},
    "e5_llama":        {"retriever": "E5-large-v2 (HF)",            "generator": "Llama-3.1-8B-Instruct",   "import_batch_id": "ib_S0_e5_llama"},
    "e5_phi35":        {"retriever": "E5-large-v2 (HF)",            "generator": "Phi-3.5-mini-instruct",   "import_batch_id": "ib_S5_e5_phi35"},
    "gteqwen_phi35":   {"retriever": "GTE-Qwen2-7B (Ollama F16)",  "generator": "Phi-3.5-mini-instruct",   "import_batch_id": "ib_S4_gteqwen_phi35"},
}

# Cumulative ordering: which setups belong to each GraphVersion
GRAPH_VERSIONS = [
    {"version_id": "v1.0", "setups": ["gteqwen_llama"]},
    {"version_id": "v2.0", "setups": ["gteqwen_llama", "e5_mistral"]},
    {"version_id": "v3.0", "setups": ["gteqwen_llama", "e5_mistral", "gteqwen_mistral"]},
    {"version_id": "v4.0", "setups": ["gteqwen_llama", "e5_mistral", "gteqwen_mistral", "e5_llama"]},
    {"version_id": "v5.0", "setups": ["gteqwen_llama", "e5_mistral", "gteqwen_mistral", "e5_llama", "e5_phi35"]},
    {"version_id": "v6.0", "setups": ["gteqwen_llama", "e5_mistral", "gteqwen_mistral", "e5_llama", "e5_phi35", "gteqwen_phi35"]},
]


@dataclass(frozen=True)
class RunSpec:
    path: Path
    setup_id: str
    dataset: str       # "TRAM2" | "AnnoCTR"
    method: str        # "RAG" | "RAG+FSP"
    seed: int          # canonical seed 0|1|2 (after rename)
    original_seed: int # raw seed as found in the filename
    tag: str           # the tag substring (provenance)


# Tag substrings that mark each setup (mutually exclusive, checked in order).
# More-specific tags must come before less-specific ones.
# v6 additions: setup1_gteqwen_llama (new 3-seed runs, no rename), setup4_gteqwen_phi35 (S4 closes the 2x3 factorial).
_TAG_TO_SETUP = [
    ("setup1_gteqwen_llama_seeds12", "gteqwen_llama"),  # v6: seed1/seed2 new runs (orig seeds used as-is)
    ("setup1_gteqwen_llama",         "gteqwen_llama"),  # v6: seed0 new run (orig seeds used as-is)
    ("final_table9_similarity",      "gteqwen_llama"),  # v1-v5 canonical (seed rename applied)
    ("setup4_gteqwen_phi35",         "gteqwen_phi35"),  # v6: closes the 2x3 factorial
    ("setup6_gteqwen_phi35",         "gteqwen_phi35"),  # seed0-only alt variant (superseded by setup4)
    ("setup3_gteqwen_mistral",       "gteqwen_mistral"),
    ("setup0_e5_llama",              "e5_llama"),     # S0 RAG and RAG+FSP both carry this tag
    ("mistral_e5_ragfsp",            "e5_mistral"),   # RAG+FSP canonical
    ("setup5_e5_phi35",              "e5_phi35"),     # S5 RAG and RAG+FSP both carry this tag
]


def _parse_filename(fp: Path):
    """Return RunSpec or None if file is to be skipped."""
    name = fp.name
    if not name.endswith(".jsonl"):
        return None
    # Drop shards & dryruns & smoke
    if "_shard" in name or "dryrun" in name.lower() or "_limit" in name or name.startswith("smoke_"):
        return None
    # Drop explicit dryrun/sanity tags
    if "parallel_sanity" in name or "conservative_dryrun" in name:
        return None
    # Drop S1 AnnoCTR seed0 ollama_annoctr_conservative pipeline (replaced)
    if "ollama_annoctr_conservative_seed0" in name or "ollama_tram2_conservative_seed0" in name:
        return None
    # Drop ollama_seed0 raw (pre final_table9_similarity)
    if "ollama_seed0_" in name:
        return None
    # Drop bare "_mistral7b_v03_gte" smokes
    if "_mistral7b_v03_gte" in name:
        return None
    # Drop bare "AnnoCTR_RAG_seed0.jsonl" / "TRAM2_RAG_seed0.jsonl" placeholders
    if name in {
        "AnnoCTR_RAG_seed0.jsonl", "AnnoCTR_RAG_FSP_seed0.jsonl",
        "TRAM2_RAG_seed0.jsonl",  "TRAM2_RAG_FSP_seed0.jsonl",
    }:
        return None

    # Dataset
    if name.startswith("TRAM2_"):
        dataset = "TRAM2"
    elif name.startswith("AnnoCTR_"):
        dataset = "AnnoCTR"
    else:
        return None

    # Method (order matters: "RAG+FSP" / "RAG_FSP" both denote RAG+FSP)
    if "_RAG+FSP_" in name or "_RAG_FSP_" in name:
        method = "RAG+FSP"
    elif "_RAG_" in name:
        method = "RAG"
    else:
        return None

    # Original seed
    import re
    m = re.search(r"_seed(\d+)_", name)
    if not m:
        return None
    original_seed = int(m.group(1))

    # Setup detection
    setup_id = None
    tag = None
    for substr, sid in _TAG_TO_SETUP:
        if substr in name:
            setup_id = sid
            tag = substr
            break

    # For S2 (e5_mistral) the RAG (not RAG+FSP) tag was different:
    if setup_id is None and "mistral_e5_seed" in name and method == "RAG":
        # canonical S2 RAG: mistral_e5_seed{N}_{ts}.jsonl (no ragfsp)
        # but only keep if NOT a "tram2_conservative" / "annoctr_conservative" intermediate
        if "conservative" in name:
            return None
        setup_id = "e5_mistral"
        tag = "mistral_e5_seed"

    if setup_id is None:
        return None

    # S1 seed handling:
    #   - Old 'final_table9_similarity' files: only seed1/seed2 exist; rename seed1->0, seed2->1.
    #   - New 'setup1_gteqwen_llama*' files: genuine seed0/1/2; use original seed as-is.
    #     These have later timestamps so they supersede the old files via discover_runs dedup.
    if setup_id == "gteqwen_llama" and tag == "final_table9_similarity":
        if original_seed == 0:
            return None  # no canonical S1 seed0 in old pipeline
        canonical_seed = original_seed - 1  # seed1->0, seed2->1
    else:
        canonical_seed = original_seed  # all other setups: original seed is canonical

    return RunSpec(
        path=fp, setup_id=setup_id, dataset=dataset, method=method,
        seed=canonical_seed, original_seed=original_seed, tag=tag,
    )


def discover_runs(pred_dir: Path = PREDICTIONS_DIR):
    """Return list[RunSpec], one per kept JSONL. Resolves duplicates by keeping
    the latest timestamp when multiple files map to the same key."""
    candidates = {}  # key -> (timestamp, RunSpec)
    import re
    for fp in sorted(pred_dir.glob("*.jsonl")):
        rs = _parse_filename(fp)
        if rs is None:
            continue
        key = (rs.setup_id, rs.dataset, rs.method, rs.seed)
        m = re.search(r"_(\d{8}_\d{6})", fp.name)
        ts = m.group(1) if m else "0"
        prev = candidates.get(key)
        if prev is None or ts > prev[0]:
            candidates[key] = (ts, rs)
    return [rs for _, rs in sorted(candidates.values(), key=lambda x: (x[1].setup_id, x[1].dataset, x[1].method, x[1].seed))]


def print_manifest(runs):
    by = {}
    for r in runs:
        by.setdefault(r.setup_id, []).append(r)
    for sid in sorted(by):
        print(f"\n[{sid}] {len(by[sid])} runs")
        for r in by[sid]:
            print(f"  {r.dataset:8s} {r.method:8s} seed={r.seed} (orig={r.original_seed})  {r.path.name}")


if __name__ == "__main__":
    runs = discover_runs()
    print(f"Total runs kept: {len(runs)}")
    print_manifest(runs)
