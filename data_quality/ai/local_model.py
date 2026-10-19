"""
The local Hugging Face model - A6 Part 2.2, Tejas Jaggi.

The model is never loaded when Django starts or on a GET request. The first
explanation a signed-in user asks for loads it, and every later request in the
same process reuses that one copy. torch and transformers are imported inside
the loader for the same reason: `manage.py check`, the test suite and a server
without torch (PythonAnywhere) never import them at all.

Loading and generation follow the benchmark notebook (llm-test/ai_prototype.ipynb): 16-bit on a
CUDA GPU (placed straight on the GPU), 32-bit on CPU, greedy decoding, and the
model's own chat template. SmolLM2-1.7B peaked at about 3.6 GB of GPU memory
there; on CPU it needs roughly 7 GB of RAM (an estimate from 1.71B x 4 bytes).
"""

import threading
import time

from django.conf import settings

# After a failed load, wait this long before trying again, so repeated clicks
# do not each re-read (or re-download) several GB of weights.
LOAD_RETRY_SECONDS = 60


class AIUnavailable(Exception):
    """The local model cannot be used here: switched off, not installed, or failed."""


class HuggingFaceGenerator:
    def __init__(self, model_id, device="auto", max_new_tokens=160):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        kwargs = {"dtype": torch.float16 if device != "cpu" else torch.float32}
        if device != "cpu":
            kwargs["device_map"] = device
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        self.model.eval()
        self._lock = threading.Lock()  # one generation at a time on one model

    def generate(self, messages):
        inputs = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
        ).to(self.model.device)
        with self._lock, self.torch.no_grad():
            output = self.model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id)
        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


_generator = None
_failure = None  # (time.monotonic(), message) of the last failed load
_load_lock = threading.Lock()


def get_generator():
    """The shared model, loaded on first use. Raises AIUnavailable instead of crashing."""
    global _generator, _failure
    if not settings.AI_LOCAL_ENABLED:
        raise AIUnavailable("The local model is switched off (AI_LOCAL_ENABLED).")
    if _generator is None:
        with _load_lock:
            if _generator is None:
                if _failure and time.monotonic() - _failure[0] < LOAD_RETRY_SECONDS:
                    raise AIUnavailable(_failure[1])
                try:
                    _generator = HuggingFaceGenerator(
                        settings.AI_LOCAL_MODEL_ID, settings.AI_LOCAL_DEVICE, settings.AI_MAX_NEW_TOKENS)
                except Exception as exc:
                    # Any load failure: missing torch, missing weights, CUDA out of
                    # memory, MemoryError on CPU, "Torch not compiled with CUDA".
                    _failure = (time.monotonic(), f"{type(exc).__name__}: {exc}")
                    raise AIUnavailable(_failure[1]) from exc
                _failure = None
    return _generator


def reset_for_tests():
    global _generator, _failure
    _generator = None
    _failure = None
