"""CAMEL model backend for a loopback llama.cpp server.

Direct clients ignore proxy environment variables and send no credentials.
This avoids cloud SDK defaults while retaining CAMEL's agent/memory loop.
"""
import httpx
from openai.types.chat import ChatCompletion
from camel.models import BaseModelBackend
from camel.types import UnifiedModelType
from .local_tokens import LlamaTokenCounter
from .model import validate_local_url


class LocalLlamaModel(BaseModelBackend):
    def __init__(self, settings):
        url = validate_local_url(settings.url)
        super().__init__(model_type=UnifiedModelType(settings.name),
                         model_config_dict={"stream": False, "temperature": 0.2,
                                            "max_tokens": 512, "response_format": {"type": "json_object"}},
                         api_key="local-no-secret", url=url,
                         token_counter=LlamaTokenCounter(url), timeout=settings.timeout, max_retries=0)
        self._sync = httpx.Client(timeout=settings.timeout, trust_env=False)
        self._async = httpx.AsyncClient(timeout=settings.timeout, trust_env=False)

    @property
    def token_counter(self):
        return self._token_counter

    @property
    def token_limit(self):
        # CAMEL's default treats max_tokens as a context limit. Keep the
        # full input window separate from the 512-token output cap.
        return 8192 - 512

    def _payload(self, messages, response_format=None, tools=None):
        if response_format is not None:
            raise ValueError("Local backend uses JSON-object output, not SDK-specific response classes")
        payload = {**self.model_config_dict, "model": str(self.model_type), "messages": messages}
        if tools:
            payload["tools"] = tools
        return payload

    def _run(self, messages, response_format=None, tools=None):
        response = self._sync.post(self._url + "/chat/completions", json=self._payload(messages, response_format, tools))
        response.raise_for_status()
        return ChatCompletion.model_validate(response.json())

    async def _arun(self, messages, response_format=None, tools=None):
        response = await self._async.post(self._url + "/chat/completions", json=self._payload(messages, response_format, tools))
        response.raise_for_status()
        return ChatCompletion.model_validate(response.json())

    async def aclose(self):
        await self._async.aclose()
        self._sync.close()
