# TRACE-CTI STIX 2.1 proof of concept

Published version: [v1.0.0 release](https://github.com/federicovalletta/TRACE-CTI-artifacts/releases/tag/stix-poc-v1.0.0).

This versioned proof of concept tests one existing, gold-backed v6.0
GraphAssertion. It serializes the claim as a STIX `note` referring to the
reused ATT&CK `attack-pattern`, carries claim identity/evidence/scope in a
registered `property-extension`, wraps the export in a STIX `report`, validates
the bundles, and reads them back. The note also references the export report:
the MISP-STIX converter uses that reference to retain the claim as an
event-level analyst note. A JSON metadata block in the note content provides a
human-readable fallback for consumers that discard custom extensions.

It exercises two distinct transitions:

1. A temporary exit from the trusted view creates a later version of the same
   exporter-owned `note`, changing its extension scope to `prediction_only`.
   The receiver test then suppresses that claim from its trusted view.
2. A permanent withdrawal creates a later version with `revoked: true`. That
   state is terminal: the PoC does not restore or further version the object.

The controlled receiver test applies the updated scope and removes the note
from its trusted set. An offline import through MISP-STIX Converter
`2026.11.12` also retains the note, ATT&CK galaxy cluster, and JSON metadata
fallback in MISP-format output. This is a converter-level test, not a live
MISP instance or a test of delivery/update behavior in a deployed platform.
No source/setup revocation is executed in Neo4j. The example uses one v6.0 CSV
record, not a population-wide export.

The two disabled best-practice checks concern only the reused, unmodified
ATT&CK v19.1 object: check 302 expects a hash on the `mitre-attack` external
reference, and check 401 flags ATT&CK's published `x_mitre_*` properties.
Core STIX 2.1 schema validation, the published extension schema, all other
best-practice checks, and internal reference checks remain enabled and strict.

## Reproduce

From this directory, using Python 3.10 or later:

```powershell
python -m pip install -r requirements.txt
python export_stix_poc.py
python -m unittest -v
stix2_validator --version=2.1 --strict --disable 302,401 --enforce-refs --schemas schemas output/01_initial_trusted_export.json
stix2_validator --version=2.1 --strict --disable 302,401 --enforce-refs --schemas schemas output/02_temporary_withdrawal_update.json
stix2_validator --version=2.1 --strict --disable 302,401 --enforce-refs --schemas schemas output/03_permanent_revocation_update.json
```

The versioned `schema` URI in the STIX `extension-definition` points to the
published file in `schemas/`.
The MISP converter check is an optional, independent test. It requires Python
3.11 or later and MISP-STIX Converter `2026.11.12`; see
`consumer_tests/misp_stix_converter/README.md` for the command and verified
behavior. The converter preserves the JSON metadata fallback but does not
interpret or enforce TRACE-CTI trust-scope semantics.

## Inputs and provenance

- `fixtures/graph_assertion.csv` and `fixtures/attack_technique.csv` are the
  selected source rows copied from the released TRACE-CTI v6.0 CSV snapshot.
- `fixtures/attack-pattern-T1570.json` contains the original ATT&CK v19.1
  `attack-pattern` object for T1570 and its direct referenced identity and
  marking objects, extracted without modification from MITRE's
  `enterprise-attack-19.1.json`.
- Official source:
  <https://github.com/mitre-attack/attack-stix-data/blob/master/enterprise-attack/enterprise-attack-19.1.json>
- SHA-256 of the full downloaded source bundle used for extraction:
  `BDF1CE86A4E604214C5076D37AE4DCB322678AFC528DF8492E6FDC1B554F5DA3`.
- The reproduced ATT&CK object retains MITRE's STIX marking; the MITRE
  permission notice is included in `THIRD_PARTY_NOTICES.md`.
- MITRE ATT&CK is a trademark of The MITRE Corporation.

The fixture's assertion is
`gteqwen_llama::TRAM2::RAG::tram2_5__s17::T1570`, with v6.0 scope
`gold_backed`. The STIX `report` in the bundle is an export container for this
selected claim, not a re-publication of the source CTI report.

## Interpretation boundary

The PoC validates STIX serialization, the published custom schema,
references, the behavior of a minimal receiver for scope changes, and
conversion to MISP-format JSON. It does not validate native document
ingestion, a live MISP instance, OpenCTI, TAXII delivery, update/revocation
propagation, Neo4j behavior, or scale. The property extension must be
understood by a consumer to interpret TRACE-CTI scope; STIX transport alone
cannot enforce that policy.
