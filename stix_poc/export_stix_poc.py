#!/usr/bin/env python3
"""Export and exercise one v6.0 TRACE-CTI claim as STIX 2.1."""

from __future__ import annotations

import argparse
import csv
import json
import uuid
from pathlib import Path

import stix2
from stix2 import properties


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
OUTPUT = ROOT / "output"
EXTENSION_ID = (
    "extension-definition--d8b60f3d-96c5-41f3-b4db-b2fa68ed26c8"
)
CREATOR_ID = "identity--fa2ec008-d100-49a8-8c25-5fcee88649c2"
NOTE_ID = "note--038e837e-2dde-4715-a248-69cbe851a933"
REPORT_ID = "report--4fd009d8-1b0b-43d6-a642-ccda1334f22d"
GRAPH_ASSERTION_ID = (
    "gteqwen_llama::TRAM2::RAG::tram2_5__s17::T1570"
)
CREATED = "2026-11-19T00:00:00Z"
WITHDRAWN = "2026-11-19T01:00:00Z"
REVOKED = "2026-11-19T02:00:00Z"
ATTACK_PATTERN_ID = "attack-pattern--bf90d72c-c00b-45e3-b3aa-68560560d4c5"


@stix2.v21.CustomExtension(
    EXTENSION_ID,
    [
        ("graph_assertion_id", properties.StringProperty(required=True)),
        ("operational_scope", properties.StringProperty(required=True)),
        ("graph_version", properties.StringProperty(required=True)),
        ("source_dataset", properties.StringProperty(required=True)),
        ("source_report_id", properties.StringProperty(required=True)),
        ("evidence_sentence_id", properties.StringProperty(required=True)),
        ("attack_id", properties.StringProperty(required=True)),
        ("method", properties.StringProperty(required=True)),
        ("validation_basis", properties.StringProperty(required=True)),
    ],
)
class TraceCtiClaimExtension:
    extension_type = "property-extension"


def load_selected_assertion(fixtures: Path) -> dict[str, str]:
    path = fixtures / "graph_assertion.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    matches = [
        row for row in rows
        if row.get("graph_assertion_id") == GRAPH_ASSERTION_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one fixture row for {GRAPH_ASSERTION_ID}")
    row = matches[0]
    if row.get("scope_v6") != "gold_backed":
        raise ValueError("The demonstration claim is not gold-backed in v6.0")
    return row


def load_attack_objects(fixtures: Path) -> tuple[list[stix2.base._STIXBase], dict]:
    data = json.loads(
        (fixtures / "attack-pattern-T1570.json").read_text(encoding="utf-8")
    )
    objects = [
        stix2.parse(item, allow_custom=True)
        for item in data["objects"]
    ]
    patterns = [obj for obj in objects if obj.id == ATTACK_PATTERN_ID]
    if len(patterns) != 1:
        raise ValueError("MITRE ATT&CK fixture does not contain T1570 exactly once")
    return objects, patterns[0]


def extension_definition() -> stix2.v21.ExtensionDefinition:
    return stix2.v21.ExtensionDefinition(
        id=EXTENSION_ID,
        created=CREATED,
        modified=CREATED,
        created_by_ref=CREATOR_ID,
        name="TRACE-CTI GraphAssertion metadata",
        description=(
            "Published proof-of-concept property extension carrying TRACE-CTI "
            "claim identity, evidence location, graph version, and trust scope."
        ),
        schema=(
            "https://raw.githubusercontent.com/federicovalletta/"
            "TRACE-CTI-artifacts/stix-poc-v1.0.0/stix_poc/schemas/"
            "extension-definition--d8b60f3d-96c5-41f3-b4db-b2fa68ed26c8.json"
        ),
        version="1.0.0",
        extension_types=["property-extension"],
    )


def make_bundle(
    row: dict[str, str],
    attack_objects: list[stix2.base._STIXBase],
    attack_pattern: stix2.base._STIXBase,
    *,
    scope: str,
    validation_basis: str,
    modified: str,
    state: str,
    revoked: bool = False,
) -> stix2.v21.Bundle:
    creator = stix2.v21.Identity(
        id=CREATOR_ID,
        created=CREATED,
        modified=CREATED,
        name="TRACE-CTI STIX 2.1 proof of concept",
        identity_class="organization",
    )
    definition = extension_definition()
    claim_extension = TraceCtiClaimExtension(
        graph_assertion_id=row["graph_assertion_id"],
        operational_scope=scope,
        graph_version="v6.0",
        source_dataset=row["dataset"],
        source_report_id=row["doc_id"],
        evidence_sentence_id=row["sentence_id"],
        attack_id=row["attack_id"],
        method=row["method"],
        validation_basis=validation_basis,
    )
    claim_metadata = {
        "graph_assertion_id": row["graph_assertion_id"],
        "graph_version": "v6.0",
        "source_dataset": row["dataset"],
        "source_report_id": row["doc_id"],
        "evidence_sentence_id": row["sentence_id"],
        "method": row["method"],
        "attack_id": row["attack_id"],
        "operational_scope": scope,
        "validation_basis": validation_basis,
        "lifecycle_state": state,
        "revoked": revoked,
    }
    note_args = {
        "id": NOTE_ID,
        "created": CREATED,
        "modified": modified,
        "created_by_ref": CREATOR_ID,
        "abstract": f"TRACE-CTI claim {row['attack_id']} ({scope})",
        "content": (
            f"GraphAssertion {row['graph_assertion_id']} maps evidence "
            f"sentence {row['sentence_id']} in report {row['doc_id']} "
            f"to ATT&CK {row['attack_id']}; current operational scope: {scope}."
            "\n\nTRACE-CTI metadata (JSON):\n"
            f"{json.dumps(claim_metadata, ensure_ascii=False, sort_keys=True)}"
        ),
        # MISP imports this as event-level analyst data when it references the report.
        "object_refs": [attack_pattern.id, REPORT_ID],
        "external_references": [
            stix2.v21.ExternalReference(
                source_name="TRACE-CTI v6.0",
                external_id=row["graph_assertion_id"],
            ),
            stix2.v21.ExternalReference(
                source_name="TRAM v2",
                external_id=f"{row['doc_id']}#{row['sentence_id']}",
            ),
        ],
        "extensions": {EXTENSION_ID: claim_extension},
    }
    if revoked:
        note_args["revoked"] = True
    note = stix2.v21.Note(**note_args)
    report = stix2.v21.Report(
        id=REPORT_ID,
        created=CREATED,
        modified=CREATED,
        published=CREATED,
        created_by_ref=CREATOR_ID,
        name=f"TRACE-CTI selected-claim export: {row['doc_id']}",
        description=(
            "A versioned offline interoperability demonstration for one claim; "
            "this is not a re-publication of the source CTI report."
        ),
        report_types=["threat-report"],
        object_refs=[note.id, attack_pattern.id],
    )
    bundle_uuid = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "https://github.com/federicovalletta/TRACE-CTI-artifacts/"
        f"releases/tag/stix-poc-v1.0.0/bundle/{state}",
    )
    bundle_uuid = uuid.UUID(bytes=bundle_uuid.bytes, version=4)
    return stix2.v21.Bundle(
        id=f"bundle--{bundle_uuid}",
        objects=[
            creator,
            definition,
            *attack_objects,
            note,
            report,
        ],
        allow_custom=True,
    )


def write_and_read_back(bundle: stix2.v21.Bundle, path: Path) -> dict:
    path.write_text(bundle.serialize(pretty=True) + "\n", encoding="utf-8")
    parsed = stix2.parse(path.read_text(encoding="utf-8"), allow_custom=True)
    raw = json.loads(parsed.serialize())
    notes = [obj for obj in raw["objects"] if obj["type"] == "note"]
    if len(notes) != 1:
        raise AssertionError("Read-back did not yield exactly one claim Note")
    note = notes[0]
    extension = note["extensions"][EXTENSION_ID]
    if extension["graph_assertion_id"] != GRAPH_ASSERTION_ID:
        raise AssertionError("Read-back changed the source GraphAssertion ID")
    return note


def consumer_trusted_note_ids(bundle_path: Path) -> set[str]:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    trusted_scopes = {
        "gold_backed",
        "consensus_validated",
        "strong_consensus",
    }
    return {
        obj["id"]
        for obj in bundle["objects"]
        if obj["type"] == "note"
        and not obj.get("revoked", False)
        and obj["extensions"][EXTENSION_ID]["operational_scope"] in trusted_scopes
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    row = load_selected_assertion(args.fixtures)
    attack_objects, attack_pattern = load_attack_objects(args.fixtures)
    if attack_pattern.name != "Lateral Tool Transfer":
        raise ValueError("ATT&CK T1570 fixture name does not match the CSV")
    if row["attack_id"] != "T1570":
        raise ValueError("The selected v6.0 GraphAssertion is not T1570")

    states = [
        ("01_initial_trusted_export.json", "gold_backed", "dataset-gold", CREATED, "initial", False),
        ("02_temporary_withdrawal_update.json", "prediction_only", "none", WITHDRAWN, "temporary-withdrawal", False),
        ("03_permanent_revocation_update.json", "prediction_only", "none", REVOKED, "permanent-revocation", True),
    ]
    read_backs = {}
    for filename, scope, basis, modified, state, revoked in states:
        bundle = make_bundle(
            row,
            attack_objects,
            attack_pattern,
            scope=scope,
            validation_basis=basis,
            modified=modified,
            state=state,
            revoked=revoked,
        )
        note = write_and_read_back(bundle, args.output_dir / filename)
        read_backs[state] = note

    initial = read_backs["initial"]
    withdrawal = read_backs["temporary-withdrawal"]
    permanent = read_backs["permanent-revocation"]
    assert initial["id"] == withdrawal["id"] == permanent["id"]
    assert initial["modified"] < withdrawal["modified"] < permanent["modified"]
    assert initial["extensions"][EXTENSION_ID]["operational_scope"] == "gold_backed"
    assert withdrawal["extensions"][EXTENSION_ID]["operational_scope"] == "prediction_only"
    assert not initial.get("revoked", False) and not withdrawal.get("revoked", False)
    assert permanent["revoked"] is True
    initial_export = args.output_dir / states[0][0]
    withdrawal_update = args.output_dir / states[1][0]
    permanent_update = args.output_dir / states[2][0]
    assert consumer_trusted_note_ids(initial_export) == {NOTE_ID}
    assert consumer_trusted_note_ids(withdrawal_update) == set()
    assert consumer_trusted_note_ids(permanent_update) == set()
    print(
        "PASS: one v6.0 gold-backed GraphAssertion exported; all three bundles "
        "read back; temporary scope withdrawal updates the same Note ID; "
        "the controlled receiver removes it from its trusted view; permanent "
        "revocation is terminal and does not alter the ATT&CK object."
    )


if __name__ == "__main__":
    main()
