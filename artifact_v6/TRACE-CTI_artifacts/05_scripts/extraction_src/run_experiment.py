"""End-to-end experiment for one (dataset, method, seed) triple.

Phase A — Embedding (Qwen):
  1. Load KB, optionally load/build KB embedding cache.
  2. Embed all sentences from the test docs (limited if --limit).
  3. Free Qwen.

Phase B — Inference (Llama):
  4. Load Llama.
  5. For each sentence: retrieve top-5 (filtered to dataset label set), build prompt, generate.
  6. Parse IDs (regex; also name-based for debug). Aggregate per document.

Phase C — Eval & dump.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import torch

from src.evaluate import aggregate, per_doc_metrics
from src.label_sets import LABEL_SETS
from src.llama_inference import LlamaGenerator
from src.load_attack import kb_stats, load_attack_kb
from src.load_datasets import load_dataset
from src.parse_attack_ids import parse_ids, parse_names
from src.prompts import build_chat_messages, build_sentence_rag_prompt
from src.rag_retriever import (QwenEmbedder, get_or_build_kb_embeddings,
                                retrieve_topk)
from src.utils import (load_config, save_json, save_jsonl, set_all_seeds,
                       setup_logging)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=["TRAM2", "AnnoCTR"])
    ap.add_argument("--method", required=True, choices=["RAG", "RAG+FSP"])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=0,
                    help="Limit number of test docs (0 = all). Doc-level slice [:limit].")
    ap.add_argument("--tag", default="",
                    help="Optional run tag prefix (e.g. 'dryrun').")
    return ap.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    set_all_seeds(args.seed)
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_cache"])

    method = args.method
    use_fsp = method == "RAG+FSP"

    base = f"{args.dataset}_{method.replace('+','_')}_seed{args.seed}"
    if args.limit > 0:
        base = (args.tag + "_" if args.tag else "dryrun_") + base + f"_limit{args.limit}"
    out_root = Path(cfg["paths"]["workspace"]) / "outputs"
    log_path = out_root / "logs" / f"{base}.log"
    pred_path = out_root / "predictions" / f"{base}.jsonl"
    metric_path = out_root / "metrics" / f"{base}.json"
    cfg_dump_path = out_root / "configs" / f"{base}.yaml"
    setup_logging(log_path)
    import logging
    logging.info(f"=== Run {base} ===")
    logging.info(f"Args: {vars(args)}")

    # Snapshot effective config + args
    save_json({"args": vars(args), "config": cfg}, cfg_dump_path)

    # 1) Load KB and dataset
    kb_df = load_attack_kb(cfg["paths"]["attack_kb_csv"])
    logging.info(f"KB stats: {kb_stats(kb_df)}")
    docs = load_dataset(args.dataset, cfg, split="test")
    logging.info(f"Loaded {args.dataset} test: {len(docs)} docs")
    if args.limit > 0:
        docs = docs[: args.limit]
        logging.info(f"Limited to first {len(docs)} docs (dry-run)")

    label_set_name = cfg["datasets"][args.dataset]["label_set_name"]
    label_set = LABEL_SETS[label_set_name]

    # Collect (doc_idx, sent_idx, sentence) for non-empty sentences
    queries = []
    for di, d in enumerate(docs):
        for si, sent in enumerate(d["sentences"]):
            if not sent or not sent.strip():
                continue
            queries.append((di, si, sent))
    logging.info(f"Total non-empty sentences to process: {len(queries)}")

    # 2) Phase A — embeddings
    embedder = QwenEmbedder(cfg["paths"]["embedding_model"])
    kb_emb = get_or_build_kb_embeddings(kb_df, embedder, cfg["paths"]["embed_cache_dir"])
    logging.info(f"KB embeddings shape: {kb_emb.shape}")

    sentence_texts = [s for (_, _, s) in queries]
    sent_emb = embedder.encode(sentence_texts, desc=f"sent[{args.dataset}]")
    embedder.free()
    logging.info("Released Qwen from VRAM")

    # 3) Retrieve per query
    retrieval_cfg = cfg["retrieval"]
    retrieved_per_query = []
    for q_emb in sent_emb:
        r = retrieve_topk(
            q_emb, kb_emb, kb_df, label_set,
            top_k_initial=retrieval_cfg["top_k_initial"],
            top_k_final=retrieval_cfg["top_k_final"],
            off_by_one_bug=retrieval_cfg["off_by_one_bug"],
        )
        retrieved_per_query.append(r)
    logging.info("Retrieval done")

    # 4) Phase B — Llama inference
    dec = cfg["decoding"]
    llm = LlamaGenerator(
        cfg["paths"]["llm_model"],
        max_new_tokens=dec["max_new_tokens"],
        repetition_penalty=dec["repetition_penalty"],
        dtype=torch.float16 if dec["precision"] == "fp16" else torch.bfloat16,
    )

    pred_records = []
    doc_predictions = {d["doc_id"]: [] for d in docs}     # ID-regex per doc
    doc_predictions_name = {d["doc_id"]: [] for d in docs}  # name-based per doc

    for k, ((di, si, sentence), retrieved) in enumerate(zip(queries, retrieved_per_query)):
        prompt_user = build_sentence_rag_prompt(sentence, retrieved, few_shot=use_fsp)
        messages = build_chat_messages(prompt_user)
        t0 = time.time()
        text, full_prompt = llm.generate(messages)
        dt = time.time() - t0

        ids_regex = parse_ids(text)  # full set including all techniques
        ids_regex_filtered = [i for i in ids_regex if i in set(label_set)]
        ids_name = parse_names(text, kb_df, label_set=label_set)

        doc_id = docs[di]["doc_id"]
        doc_predictions[doc_id].extend(ids_regex_filtered)
        doc_predictions_name[doc_id].extend(ids_name)

        pred_records.append({
            "doc_id": doc_id,
            "sent_idx": si,
            "sentence": sentence,
            "retrieved": [{"ID": r["ID"], "name": r["name"], "score": r["score"]} for r in retrieved],
            "raw_response": text,
            "ids_regex": ids_regex,
            "ids_regex_filtered": ids_regex_filtered,
            "ids_name": ids_name,
            "gen_time_s": round(dt, 3),
        })
        if (k + 1) % 25 == 0 or k == len(queries) - 1:
            logging.info(f"[{k+1}/{len(queries)}] doc={doc_id} sent={si} ids={ids_regex_filtered} ({dt:.2f}s)")

    llm.free()

    # 5) Aggregate doc-level + metrics
    per_doc = []
    per_doc_name = []
    summary_rows = []
    for d in docs:
        pred_set = sorted(set(doc_predictions[d["doc_id"]]))
        pred_set_name = sorted(set(doc_predictions_name[d["doc_id"]]))
        gold = [g for g in d["doc_labels"] if g in set(label_set)]
        m = per_doc_metrics(pred_set, gold)
        m_name = per_doc_metrics(pred_set_name, gold)
        per_doc.append(m)
        per_doc_name.append(m_name)
        summary_rows.append({
            "doc_id": d["doc_id"],
            "doc_title": d.get("doc_title"),
            "n_sentences": len(d["sentences"]),
            "gold": gold,
            "pred_regex": pred_set,
            "pred_name": pred_set_name,
            **{f"regex_{k}": v for k, v in m.items()},
            **{f"name_{k}": v for k, v in m_name.items()},
        })

    agg_regex = aggregate(per_doc)
    agg_name = aggregate(per_doc_name)
    metrics_out = {
        "run": base,
        "dataset": args.dataset,
        "method": method,
        "seed": args.seed,
        "limit": args.limit,
        "n_docs": len(docs),
        "n_sentences": len(queries),
        "metrics_primary_regex": agg_regex,
        "metrics_debug_name": agg_name,
        "per_doc": summary_rows,
    }

    save_jsonl(pred_records, pred_path)
    save_json(metrics_out, metric_path)
    logging.info(f"Wrote predictions: {pred_path}")
    logging.info(f"Wrote metrics: {metric_path}")
    logging.info(
        f"REGEX  P={agg_regex['precision']*100:.2f}  R={agg_regex['recall']*100:.2f}  F1={agg_regex['f1']*100:.2f}"
    )
    logging.info(
        f"NAME   P={agg_name['precision']*100:.2f}  R={agg_name['recall']*100:.2f}  F1={agg_name['f1']*100:.2f}"
    )
    print(json.dumps(
        {"primary": agg_regex, "name_debug": agg_name, "n_docs": len(docs)},
        indent=2,
    ))


if __name__ == "__main__":
    main()
