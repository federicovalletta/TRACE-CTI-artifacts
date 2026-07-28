# TRACE-CTI Reproducibility Artifact (v6.0)

Companion artifact for:

> *TRACE-CTI: Auditable Post-Extraction Governance of TTP Claims with
> Knowledge Graphs*, under submission at Computers & Security.

Every number in the paper is reproducible from this archive alone: no live LLM
call is required (paper, Section "Evaluation"). All outputs are deterministic
under the published seeds (greedy decoding, inter-seed sigma = 0).

**Quick start (no database, no GPU):**

```
python 05_scripts/validate_q1_q7_offline.py
```

validates the seven SOC audit queries and the headline KG counts directly on
the shipped CSVs (expected: 22 PASS, 0 FAIL).

**Distribution.** The same archive is published at
<https://github.com/federicovalletta/TRACE-CTI-artifacts>, both as a browsable
copy and as a `tar.gz` release; the release page and the paper's Data
availability statement carry its SHA-256.

## Layout

| Directory | Content | Paper claim it supports |
|---|---|---|
| `01_kg_snapshot_v6/` | The v6.0 KG snapshot. `kg_csv/`: 23 Neo4j-ready node/edge tables (82,260 Predictions, 27,420 GraphAssertions with materialised `trust_scope` and per-version scopes `scope_v1..v6`, 5,410 ConsensusAssertions, 72 LLMRuns, 6 setups). `ontology/`: ATT&CK (1,250 techniques, 21,324 relationships) and MALOnt (75/60). `gold/`: 663 doc-level analyst tuples (the 824 KG-level gold instances collapse to 663 distinct doc-level tuples). | "the v6.0 KG snapshot" (Data availability); Table 5 headline counts |
| `02_neo4j/` | `load_kg_v6.cypher` (constraints and vanilla LOAD CSV, no APOC), `audit_queries_q1_q7.cypher` (the seven SOC audit queries), `docker-compose.yml`. | "KG schema, CSV loaders, Cypher import scripts, audit queries Q1–Q7" |
| `03_runs/` | `metrics_index_v6.csv` (canonical index of the 72 LLMRuns: 6 setups x 2 datasets x 2 methods x 3 seeds), the 72 referenced metrics JSONs, `run_design_note.json` (the six extraction setups and design rationale). | "the six extraction setups"; 72 LLMRuns, sigma = 0 |
| `04_analysis_v6/` | Derived deliverables: factorial / bias / within-vs-cross tables (CSV and TeX), evolution table, precision-ladder outputs (`precision_vs_k_v6.csv`, `precision_vs_version_v6.csv`), `kg_snapshot_v6.json` build manifest, the three paper figures (PDF). | Tables 6–7, Figures 3–5 |
| `05_scripts/` | KG pipeline (`build_kg.py`, `analyses_v6.py`, `manifest_v6.py`), paper analyses (`compute_precision_vs_k_v6.py`, `compute_precision_vs_version_v6.py`, `make_paper_figures.py`; paths already set to this artifact's layout), `validate_q1_q7_offline.py` (semantic validation of the audit queries on the CSVs), and `extraction_src/` (the RAG extraction pipeline implementing the six setups). | Methods reproducibility |

## Reproduction paths

### A. Validate without any infrastructure (fastest)

```
python 05_scripts/validate_q1_q7_offline.py
```
Mirrors each audit query Q1–Q7 with pandas on `01_kg_snapshot_v6/` and
cross-checks the Table 5 headline counts (expected output: 22 PASS, 0 FAIL).

### B. Recompute paper tables and figures (Python with pandas)

```
python 05_scripts/compute_precision_vs_k_v6.py        # Table 7 / Fig 3, k axis
python 05_scripts/compute_precision_vs_version_v6.py  # Table 7, version axis
python 05_scripts/make_paper_figures.py               # Figures (PDF)
```
Outputs land in `04_analysis_v6/` and reproduce the shipped CSVs byte-for-byte.

### C. Load and audit the KG in Neo4j

1. `cd 02_neo4j && docker compose up -d` (vanilla Neo4j 5, no APOC).
2. Copy `01_kg_snapshot_v6/{kg_csv,ontology,gold}` into the container's
   `import/` directory (keep the subfolder names).
3. Run `load_kg_v6.cypher` (constraints first, then the LOAD CSV blocks; the
   large blocks use `:auto ... IN TRANSACTIONS`, run them from Neo4j Browser
   or `cypher-shell`).
4. Audit with `audit_queries_q1_q7.cypher`: the seven SOC questions of the
   paper (Q1 evidence audit, Q2 extraction provenance, Q3 trust scope,
   Q4 version delta, Q5 setup-revocation dry-run, Q6 retriever-vs-generator
   attribution, Q7 analyst review queue). Expected counts after load are
   listed in the header of `load_kg_v6.cypher`.

### D. Full re-extraction (optional, needs GPUs and model weights)

`05_scripts/extraction_src/` contains the extraction pipeline (retriever,
generator, and prompts). Rerunning it requires the public model weights
(E5-large-v2, GTE-Qwen2-7B-Instruct, Llama-3.1-8B-Instruct,
Mistral-7B-Instruct-v0.3, Phi-3.5-mini-instruct) and the public corpora
(TRAM v2, AnnoCTR). `build_kg.py` then rebuilds `01_kg_snapshot_v6/kg_csv/`
from the prediction JSONLs (not included for size; script headers document the
expected layout). Under the published seeds the pipeline reproduces the
included metrics byte-for-byte (sigma = 0 across all 72 runs).

## Provenance of this archive

Curated from the working artifact of 2026-05-28: retained exactly the 72
metrics files referenced by `metrics_index_v6.csv` (dry-runs, smoke tests,
superseded May-2026 runs, CTIBench probes, and rescoring variants not used in
the paper were removed); the canonical KG snapshot is the v6.0 `kg_csv` build
of 2026-05-28 whose counts match Table 5 exactly; loaders and audit queries
target that snapshot's schema. See `MANIFEST.sha256` for per-file checksums.

## Requirements

| Path | Needs |
|---|---|
| A (offline validation) | Python ≥ 3.10, pandas |
| B (tables and figures) | Python ≥ 3.10, pandas, numpy, matplotlib |
| C (Neo4j audit) | Docker (vanilla Neo4j 5, no APOC) |
| D (full re-extraction) | GPUs, public model weights and corpora (see D above) |

## Integrity

`MANIFEST.sha256` lists the SHA-256 of every file in this archive.
Verify on Linux/macOS:

```
sha256sum -c MANIFEST.sha256
```

or on Windows (PowerShell, from the archive root):

```powershell
Get-Content MANIFEST.sha256 | ForEach-Object {
  $h, $p = $_ -split '\s+', 2
  if ((Get-FileHash $p -Algorithm SHA256).Hash -ne $h) { "FAIL: $p" }
}
```

No output after the PowerShell loop (or `OK` for every line with `sha256sum`)
means the archive is intact. After any local modification, regenerate with
`python 05_scripts/manifest_v6.py`.

## Third-party data

- **MITRE ATT&CK®** (`01_kg_snapshot_v6/ontology/attack_*.csv`): © The MITRE
  Corporation, redistributed under the ATT&CK Terms of Use (v19.1 STIX bundles,
  retrieved 22 May 2026).
- **MALOnt** (`01_kg_snapshot_v6/ontology/malont_*.csv`): derived from the
  public MALOnt ontology release; see its repository for license terms.
- **TRAM v2** and **AnnoCTR** sentences, annotations, and gold labels are
  redistributed for research reproducibility from their public releases.

The archive adds no proprietary data; all extraction outputs were produced
with publicly available model weights.

## Cite

```bibtex
@article{tracecti2026,
  title   = {TRACE-CTI: Auditable Post-Extraction Governance of TTP Claims
             with Knowledge Graphs},
  journal = {Computers \& Security},
  year    = {2026},
  note    = {Under submission. Reproducibility artifact v6.0:
             https://github.com/federicovalletta/TRACE-CTI-artifacts}
}
```

Questions about the artifact: open an issue on the GitHub repository.
