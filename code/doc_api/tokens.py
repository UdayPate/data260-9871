"""
DATA-260 Homework 6 - Part 3: exact token counts for prompt components.
Ollama only reports one prompt_eval_count per call, so to attribute tokens to the
system primer / long-term summary / short-term window / episodic facts we count each
component's text with the Qwen3 tokenizer (the same tokenizer family qwen3:8b uses).
Anything the chat template adds on top (role markers etc.) is reported separately as
`template_overhead = prompt_tokens - sum(components)`.
"""

import threading

import config

_tok = None
_lock = threading.Lock()


def count(text: str) -> int:
    global _tok
    if not text:
        return 0
    with _lock:
        if _tok is None:
            from transformers import AutoTokenizer
            _tok = AutoTokenizer.from_pretrained(config.TOKENIZER_NAME)
    return len(_tok.encode(text))
