from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "01_initial_trusted_export.json": ("initial", "gold_backed", False),
    "02_temporary_withdrawal_update.json": (
        "temporary-withdrawal",
        "prediction_only",
        False,
    ),
    "03_permanent_revocation_update.json": (
        "permanent-revocation",
        "prediction_only",
        True,
    ),
}
GRAPH_ASSERTION_ID = "gteqwen_llama::TRAM2::RAG::tram2_5__s17::T1570"


def main() -> None:
    converter = shutil.which("misp_stix_converter")
    if converter is None:
        raise RuntimeError(
            "Install consumer_tests/misp_stix_converter/requirements.txt "
            "to run the MISP import check"
        )

    with tempfile.TemporaryDirectory(prefix="trace-cti-misp-") as temp_dir:
        output_dir = Path(temp_dir)
        for input_name, (state, scope, revoked) in INPUTS.items():
            output_name = f"{state}.misp.json"
            subprocess.run(
                [
                    converter,
                    "--debug",
                    "import",
                    "-f",
                    str(ROOT / "output" / input_name),
                    "--output-name",
                    output_name,
                    "--overwrite",
                    "--classification",
                    "external",
                    "-d",
                    "1",
                    "-cd",
                    "1",
                ],
                cwd=output_dir,
                check=True,
            )
            converted = json.loads(
                (output_dir / output_name).read_text(encoding="utf-8")
            )
            notes = converted.get("Note", [])
            if len(notes) != 1:
                raise AssertionError(
                    f"{input_name}: expected one MISP analyst note, "
                    f"found {len(notes)}"
                )
            content = notes[0]["note"]
            marker = "TRACE-CTI metadata (JSON):\n"
            if marker not in content:
                raise AssertionError(
                    f"{input_name}: MISP output lost the metadata fallback"
                )
            metadata = json.loads(content.split(marker, maxsplit=1)[1])
            expected = {
                "graph_assertion_id": GRAPH_ASSERTION_ID,
                "operational_scope": scope,
                "lifecycle_state": state,
                "revoked": revoked,
            }
            for key, value in expected.items():
                if metadata.get(key) != value:
                    raise AssertionError(
                        f"{input_name}: {key}={metadata.get(key)!r}, "
                        f"expected {value!r}"
                    )
            if not any(
                cluster.get("value") == "Lateral Tool Transfer"
                for galaxy in converted.get("Galaxy", [])
                for cluster in galaxy.get("GalaxyCluster", [])
            ):
                raise AssertionError(
                    f"{input_name}: MISP output lost ATT&CK T1570"
                )
            print(
                f"PASS: {input_name} -> MISP event note ({scope}, "
                f"{state}, revoked={revoked}) and ATT&CK galaxy cluster"
            )


if __name__ == "__main__":
    main()
