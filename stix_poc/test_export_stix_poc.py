import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_stix_poc as poc
from jsonschema import Draft202012Validator


class StixPocTest(unittest.TestCase):
    def setUp(self):
        self.row = poc.load_selected_assertion(poc.FIXTURES)
        self.attack_objects, self.attack_pattern = poc.load_attack_objects(
            poc.FIXTURES
        )

    def test_selected_claim_is_a_trusted_snapshot_record(self):
        self.assertEqual(self.row["scope_v6"], "gold_backed")
        self.assertEqual(self.row["attack_id"], "T1570")
        self.assertEqual(self.row["sentence_id"], "tram2_5__s17")
        self.assertEqual(self.attack_pattern.name, "Lateral Tool Transfer")

    def test_export_and_read_back_preserve_claim_metadata(self):
        bundle = poc.make_bundle(
            self.row,
            self.attack_objects,
            self.attack_pattern,
            scope="gold_backed",
            validation_basis="dataset-gold",
            modified=poc.CREATED,
            state="test-initial",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bundle.json"
            note = poc.write_and_read_back(bundle, path)
            self.assertEqual(
                note["extensions"][poc.EXTENSION_ID]["operational_scope"],
                "gold_backed",
            )
            note_metadata = json.loads(
                note["content"].split(
                    "TRACE-CTI metadata (JSON):\n", maxsplit=1
                )[1]
            )
            self.assertEqual(
                note_metadata["graph_assertion_id"],
                self.row["graph_assertion_id"],
            )
            self.assertEqual(note_metadata["operational_scope"], "gold_backed")
            self.assertIn(poc.REPORT_ID, note["object_refs"])
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(
                any(
                    obj["id"] == poc.ATTACK_PATTERN_ID
                    and obj["type"] == "attack-pattern"
                    for obj in document["objects"]
                )
            )

    def test_withdrawal_and_revocation_have_distinct_stix_semantics(self):
        states = []
        for scope, basis, modified, state, revoked in [
            ("gold_backed", "dataset-gold", poc.CREATED, "test-initial", False),
            ("prediction_only", "none", poc.WITHDRAWN, "test-withdrawal", False),
            ("prediction_only", "none", poc.REVOKED, "test-revocation", True),
        ]:
            bundle = poc.make_bundle(
                self.row,
                self.attack_objects,
                self.attack_pattern,
                scope=scope,
                validation_basis=basis,
                modified=modified,
                state=state,
                revoked=revoked,
            )
            states.append(bundle)
        notes = [
            next(obj for obj in bundle.objects if obj.type == "note")
            for bundle in states
        ]
        self.assertEqual(len({note.id for note in notes}), 1)
        self.assertTrue(all(poc.REPORT_ID in note.object_refs for note in notes))
        self.assertLess(notes[0].modified, notes[1].modified)
        self.assertLess(notes[1].modified, notes[2].modified)
        self.assertFalse(notes[1].revoked)
        self.assertTrue(notes[2].revoked)
        metadata = [
            json.loads(
                note.content.split(
                    "TRACE-CTI metadata (JSON):\n", maxsplit=1
                )[1]
            )
            for note in notes
        ]
        self.assertEqual(
            [item["lifecycle_state"] for item in metadata],
            ["test-initial", "test-withdrawal", "test-revocation"],
        )
        self.assertEqual(
            [item["revoked"] for item in metadata],
            [False, False, True],
        )

    def test_receiver_applies_scope_withdrawal_to_its_trusted_view(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for scope, basis, modified, state, revoked in [
                ("gold_backed", "dataset-gold", poc.CREATED, "test-receiver-initial", False),
                ("prediction_only", "none", poc.WITHDRAWN, "test-receiver-withdrawal", False),
            ]:
                bundle = poc.make_bundle(
                    self.row,
                    self.attack_objects,
                    self.attack_pattern,
                    scope=scope,
                    validation_basis=basis,
                    modified=modified,
                    state=state,
                    revoked=revoked,
                )
                path = Path(temp_dir) / f"{state}.json"
                path.write_text(bundle.serialize(pretty=True), encoding="utf-8")
                paths.append(path)
            self.assertEqual(poc.consumer_trusted_note_ids(paths[0]), {poc.NOTE_ID})
            self.assertEqual(poc.consumer_trusted_note_ids(paths[1]), set())

    def test_extension_schema_rejects_unknown_trust_scope(self):
        bundle = poc.make_bundle(
            self.row,
            self.attack_objects,
            self.attack_pattern,
            scope="gold_backed",
            validation_basis="dataset-gold",
            modified=poc.CREATED,
            state="test-schema",
        )
        note = next(obj for obj in bundle.objects if obj.type == "note")
        note_dict = json.loads(note.serialize())
        schema_path = (
            poc.ROOT
            / "schemas"
            / f"{poc.EXTENSION_ID}.json"
        )
        validator = Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        )
        self.assertTrue(validator.is_valid(note_dict))
        invalid_note = copy.deepcopy(note_dict)
        invalid_note["extensions"][poc.EXTENSION_ID][
            "operational_scope"
        ] = "not-a-valid-scope"
        self.assertFalse(validator.is_valid(invalid_note))


if __name__ == "__main__":
    unittest.main()
