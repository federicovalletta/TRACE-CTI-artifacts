# MISP-STIX converter interoperability check

This optional test exercises the public MISP-STIX Converter, not a live MISP
server. It imports the three PoC bundles into MISP-format JSON offline, then
checks that the event-level analyst note preserves the claim ID, source
sentence, scope, lifecycle state, and revoked flag in the JSON metadata block.
It also checks that ATT&CK T1570 is represented as an attack-pattern galaxy
cluster.

The converter does not retain TRACE-CTI extension fields as structured MISP
fields or enforce the trust policy. The JSON block is a readable fallback;
this test does not claim server-side update, delivery, or revocation
interoperability.

## Run

From the `stix_poc` directory with Python 3.11 or later:

```powershell
python -m pip install -r consumer_tests/misp_stix_converter/requirements.txt
python consumer_tests/misp_stix_converter/run_check.py
```

Verified with MISP-STIX Converter `2026.11.12`.
