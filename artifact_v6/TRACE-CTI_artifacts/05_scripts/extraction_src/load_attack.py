"""Load MITRE ATT&CK knowledge base from Zenodo's rag_db.csv.
Uses ID/name/description; ignores the embedding column (1024-dim, wrong dim).
We re-embed with gte-Qwen2-7B-instruct in rag_retriever.embed_kb."""

import pandas as pd


def load_attack_kb(csv_path):
    df = pd.read_csv(csv_path, encoding="ISO-8859-1")
    df = df[["ID", "name", "description"]].copy()
    df["ID"] = df["ID"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    df["description"] = df["description"].astype(str)
    df = df.reset_index(drop=True)
    df["full_text"] = df["ID"] + " - " + df["name"] + " - " + df["description"]
    return df


def kb_stats(df):
    prefixes = df["ID"].astype(str).str[0].value_counts().to_dict()
    return {"total": len(df), "by_prefix": prefixes}
