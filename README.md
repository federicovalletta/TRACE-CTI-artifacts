# TRACE-CTI Reproducibility Artifacts

Companion artifacts for **TRACE-CTI: Auditable Post-Extraction Governance of
TTP Claims with Knowledge Graphs**, under submission at *Computers & Security*.

- **Browse the artifact:** [`artifact_v6/TRACE-CTI_artifacts/`](artifact_v6/TRACE-CTI_artifacts/), with the full README, the v6.0 KG snapshot, Neo4j loaders, the audit queries Q1-Q7, analysis outputs, and all scripts.
- **Download:** [Release v6.0](https://github.com/federicovalletta/TRACE-CTI-artifacts/releases/tag/v6.0) provides `TRACE-CTI_artifacts_v6_20260728.tar.gz` (7.2 MB).
- **SHA-256:** `E76E3AD2DCB658D43BDCEC406B75E1BC456BDB25639ADA49CEE0C144AB71C3BC`
- **License:** MIT for the original code and scripts (see [LICENSE](LICENSE)); third-party data keep their own terms, listed in the artifact README.

## Quick start

No database or GPU needed. From the extracted archive root:

```
python 05_scripts/validate_q1_q7_offline.py
```

Expected output: **22 PASS, 0 FAIL**. The script validates the seven SOC audit
queries and the headline KG counts directly on the shipped CSVs.

Every number in the paper can be reproduced offline from the archive alone; the
[artifact README](artifact_v6/TRACE-CTI_artifacts/README.md) describes the full
reproduction paths: offline validation, tables and figures, the Neo4j audit,
and an optional full re-extraction.
