"""Replicates Zenodo's create_subsequences (gLLM/finetuning/test_helper.py:21-26)
for AnnoCTR/Bosch: replace newlines with space, then split on '. '.
TRAM2 sentences arrive pre-split."""


def split_zenodo(document):
    document = document.replace("\n", " ")
    return document.split(". ")
