"""Cosine-similarity retriever using gte-Qwen2-7B-instruct embeddings.
- Last-token pool, L2 normalize.
- KB embeddings cached to disk (.npy) keyed by KB hash.
- Retrieval policy (Zenodo replica): top_k_initial=100 over full KB,
  filter to dataset label set, take top_k_final=5 (no off-by-one)."""

import hashlib
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer


def _last_token_pool(last_hidden_states, attention_mask):
    left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
    if left_padding:
        return last_hidden_states[:, -1]
    seq_lens = attention_mask.sum(dim=1) - 1
    bsz = last_hidden_states.shape[0]
    return last_hidden_states[
        torch.arange(bsz, device=last_hidden_states.device),
        seq_lens,
    ]


class QwenEmbedder:
    def __init__(self, model_path, max_length=2048, batch_size=4, device="cuda"):
        self.model_path = model_path
        self.max_length = max_length
        self.batch_size = batch_size
        self.device = device
        logging.info(f"Loading embedder {model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(
            model_path,
            trust_remote_code=False,
            dtype=torch.float16,
            device_map="auto",
            attn_implementation="eager",
        )
        self.model.eval()
        self.dim = int(self.model.config.hidden_size)
        logging.info(f"Embedder loaded. hidden_size={self.dim}")

    @torch.no_grad()
    def encode(self, texts, desc="embed"):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i in tqdm(range(0, len(texts), self.batch_size), desc=desc):
            batch = texts[i:i + self.batch_size]
            tok = self.tokenizer(
                batch,
                max_length=self.max_length,
                padding=True,
                truncation=True,
                return_tensors="pt",
            ).to(self.model.device)
            outputs = self.model(**tok, use_cache=False)
            emb = _last_token_pool(outputs.last_hidden_state, tok["attention_mask"])
            emb = F.normalize(emb, p=2, dim=1)
            out[i:i + len(batch)] = emb.detach().cpu().float().numpy()
        return out

    def free(self):
        del self.model
        del self.tokenizer
        torch.cuda.empty_cache()


def _kb_signature(kb_df):
    h = hashlib.sha256()
    for s in kb_df["full_text"].tolist():
        h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()[:16]


def kb_cache_paths(cache_dir, kb_df, model_tag="gte-qwen2-7b"):
    sig = _kb_signature(kb_df)
    base = Path(cache_dir) / f"kb_{model_tag}_{sig}"
    return base.with_suffix(".npy"), base.with_suffix(".meta.json")


def get_or_build_kb_embeddings(kb_df, embedder, cache_dir):
    emb_path, _ = kb_cache_paths(cache_dir, kb_df)
    if emb_path.exists():
        logging.info(f"Loading cached KB embeddings: {emb_path}")
        return np.load(emb_path)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    texts = kb_df["full_text"].tolist()
    logging.info(f"Embedding {len(texts)} KB entries with gte-Qwen2 (cache miss)")
    emb = embedder.encode(texts, desc="kb")
    np.save(emb_path, emb)
    logging.info(f"Saved KB embeddings to {emb_path}")
    return emb


def retrieve_topk(query_emb, kb_emb, kb_df, label_set, top_k_initial=100,
                  top_k_final=5, off_by_one_bug=False):
    """Cosine sim (vectors are pre-normalized). top_k_initial over full KB,
    filter to label_set, then top_k_final. Returns list of dicts."""
    sims = kb_emb @ query_emb
    cap = min(top_k_initial, sims.shape[0])
    top_idx = np.argpartition(-sims, cap - 1)[:cap]
    top_idx = top_idx[np.argsort(-sims[top_idx])]
    label_set = set(label_set) if label_set is not None else None
    out = []
    target = top_k_final + (1 if off_by_one_bug else 0)
    for idx in top_idx:
        idx = int(idx)
        kb_id = kb_df.at[idx, "ID"]
        if label_set is not None and kb_id not in label_set:
            continue
        out.append({
            "kb_index": idx,
            "ID": kb_id,
            "name": kb_df.at[idx, "name"],
            "description": kb_df.at[idx, "description"],
            "score": float(sims[idx]),
        })
        if len(out) >= target:
            break
    return out
