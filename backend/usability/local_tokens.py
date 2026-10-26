"""Local text tokenization with estimated chat and image allowances.

llama.cpp enforces the actual context limit. No OpenAI tokenizer downloads or
cloud requests are involved.
"""
import json
import urllib.request
from camel.utils import BaseTokenCounter
from .model import validate_local_url


class LlamaTokenCounter(BaseTokenCounter):
    def __init__(self, url: str):
        self.root = validate_local_url(url).removesuffix("/v1")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _post(self, endpoint: str, payload: dict) -> dict:
        request = urllib.request.Request(self.root + endpoint, json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=10) as response:
            return json.load(response)

    def encode(self, text: str) -> list[int]:
        return self._post("/tokenize", {"content": text, "add_special": False})["tokens"]

    def decode(self, token_ids: list[int]) -> str:
        return self._post("/detokenize", {"tokens": token_ids})["content"]

    def count_tokens_from_messages(self, messages) -> int:
        count = 32
        for message in messages:
            count += 32
            content = message.get("content", "")
            if isinstance(content, str):
                count += len(self.encode(content))
            elif isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        count += len(self.encode(item.get("text", "")))
                    elif item.get("type") == "image_url":
                        count += 1024  # launcher fixes image tokens at 1024
                    else:
                        raise ValueError("Unsupported local token-counting content")
        return count
