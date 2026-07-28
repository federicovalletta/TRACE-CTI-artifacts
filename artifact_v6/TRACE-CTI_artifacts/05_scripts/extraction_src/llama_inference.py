"""Llama-3.1-8B-Instruct inference. Decoding params per Zenodo test_helper.inference:
do_sample=False, temperature=0, top_p=1, repetition_penalty=1.2, max_new_tokens=512."""

import logging

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class LlamaGenerator:
    def __init__(self, model_path, max_new_tokens=512, repetition_penalty=1.2,
                 dtype=torch.float16, device="cuda"):
        self.model_path = model_path
        self.max_new_tokens = max_new_tokens
        self.repetition_penalty = repetition_penalty
        self.dtype = dtype
        logging.info(f"Loading LLM {model_path} dtype={dtype}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            dtype=dtype,
            device_map="auto",
        )
        self.model.eval()
        logging.info("LLM loaded")

    @torch.inference_mode()
    def generate(self, messages, max_new_tokens=None, repetition_penalty=None):
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        input_ids = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(self.model.device)
        out = self.model.generate(
            input_ids=input_ids,
            do_sample=False,
            temperature=0.0,
            top_p=1.0,
            repetition_penalty=repetition_penalty if repetition_penalty is not None else self.repetition_penalty,
            max_new_tokens=max_new_tokens if max_new_tokens is not None else self.max_new_tokens,
            num_return_sequences=1,
            pad_token_id=self.tokenizer.pad_token_id,
        )
        gen_ids = out[0][input_ids.shape[1]:]
        text = self.tokenizer.decode(gen_ids, skip_special_tokens=True)
        return text, prompt

    def free(self):
        del self.model
        del self.tokenizer
        torch.cuda.empty_cache()
