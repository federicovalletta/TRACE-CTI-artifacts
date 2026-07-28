"""Parse MITRE ATT&CK IDs from LLM output.
Primary: ID-regex `T\\d{4}(?:\\.\\d{3})?` (matches techniques and 3-digit subtechniques).
Debug: name-based matching (replaceNametoID equivalent)."""

import re

# Same character class as user spec; \\d{3} (TRAM2 subtechnique IDs are 3 digits).
TECHNIQUE_ID_PATTERN = re.compile(r"T\d{4}(?:\.\d{3})?")

# Broader regex matching original Zenodo (used by extract_mitre_ids in llm_response.py)
# Useful only for cross-checking that we don't strip valid IDs.
ZENODO_ID_PATTERN = re.compile(r"(M\d{4}|G\d{4}|S\d{4}|T\d{4}(?:\.\d+)?|TA\d{4})")


def parse_ids(text, label_set=None):
    """Returns sorted list of unique IDs matched by TECHNIQUE_ID_PATTERN.
    Optionally filtered to label_set."""
    ids = set(TECHNIQUE_ID_PATTERN.findall(text or ""))
    if label_set is not None:
        ids = ids & set(label_set)
    return sorted(ids)


def parse_names(text, kb_df, label_set=None):
    """Match MITRE names appearing verbatim in text, return list of IDs.
    Iterates from bottom to top (sub-techniques first) like Zenodo replaceNametoID."""
    if not text:
        return []
    ids = []
    for _, row in kb_df[::-1].iterrows():
        if row["name"] and row["name"] in text:
            ids.append(row["ID"])
    if label_set is not None:
        ids = [i for i in ids if i in set(label_set)]
    return sorted(set(ids))
