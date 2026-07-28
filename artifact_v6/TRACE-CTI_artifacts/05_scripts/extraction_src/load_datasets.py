"""Load TRAM2 and AnnoCTR/Bosch test/train datasets and produce a uniform schema.

Output per document:
    {
      "doc_id": str,
      "doc_title": str | None,
      "sentences": [str, ...],
      "sentence_labels": [[str,...], ...] | None,   # only for TRAM2 (per-sentence)
      "doc_labels": [str, ...],                     # always
    }
"""

from pathlib import Path

from src.sentence_splitter import split_zenodo
from src.utils import load_json


def load_tram2(path):
    raw = load_json(path)
    docs = []
    for i, e in enumerate(raw):
        sentences = list(e.get("cti_report") or [])
        sentence_labels = list(e.get("label") or [])
        flat = [lid for lst in sentence_labels for lid in (lst or [])]
        doc_labels = sorted(set(flat))
        docs.append({
            "doc_id": f"tram2_{i}",
            "doc_title": e.get("doc_title"),
            "sentences": sentences,
            "sentence_labels": sentence_labels,
            "doc_labels": doc_labels,
        })
    return docs


def load_bosch(path):
    raw = load_json(path)
    docs = []
    for i, e in enumerate(raw):
        report = e.get("cti_report") or ""
        sentences = split_zenodo(report)
        doc_labels = sorted(set(e.get("mitre_ids") or []))
        docs.append({
            "doc_id": f"bosch_{i}",
            "doc_title": None,
            "sentences": sentences,
            "sentence_labels": None,
            "doc_labels": doc_labels,
        })
    return docs


def load_dataset(name, cfg, split="test"):
    p = cfg["paths"]
    if name == "TRAM2":
        return load_tram2(p["tram2_test"] if split == "test" else p["tram2_train"])
    if name == "AnnoCTR":
        return load_bosch(p["bosch_test"] if split == "test" else p["bosch_train"])
    raise ValueError(f"Unknown dataset: {name}")
