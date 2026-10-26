from pathlib import Path
import importlib.util
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.model import resolve_model_settings, validate_local_url


class LocalModelSettingsTests(unittest.TestCase):
    def test_local_mode_needs_no_key_and_does_not_forward_cloud_secret(self):
        settings = resolve_model_settings({"LLM_PROVIDER": "local", "LLM_API_KEY": "cloud-secret"})
        self.assertEqual(settings.url, "http://127.0.0.1:8080/v1")
        self.assertEqual(settings.api_key, "local-no-secret")
        self.assertNotIn("cloud-secret", repr(settings))

    def test_local_mode_rejects_remote_or_credentialed_destinations(self):
        for url in ("https://api.openai.com/v1", "http://127.0.0.1.attacker.example/v1",
                    "http://secret@localhost:8080/v1", "http://127.0.0.1:8080/v1?key=secret",
                    "file:///v1"):
            with self.assertRaises(ValueError):
                validate_local_url(url)

    def test_cloud_mode_still_requires_explicit_configuration(self):
        with self.assertRaises(ValueError):
            resolve_model_settings({})
        settings = resolve_model_settings({"LLM_API_KEY": "secret", "LLM_BASE_URL": "https://api.openai.com/v1", "LLM_MODEL_NAME": "configured-model"})
        self.assertNotIn("secret", repr(settings))

    def test_invalid_timeouts_are_rejected(self):
        for timeout in ("0", "-1", "nan", "inf", "301", "invalid"):
            with self.assertRaises(ValueError):
                resolve_model_settings({"LLM_PROVIDER": "local", "LLM_TIMEOUT_SECONDS": timeout})


@unittest.skipUnless(importlib.util.find_spec("camel"), "Requires camel-ai")
class LocalTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_schemas_are_request_local_and_reset(self):
        import asyncio
        from pydantic import create_model
        from usability.local_backend import LocalLlamaModel
        model = LocalLlamaModel(resolve_model_settings({"LLM_PROVIDER": "local"}))
        first = create_model("FirstSession", first_only=(str, ...))
        second = create_model("SecondSession", second_only=(str, ...))
        async def payload(schema):
            with model.structured_output(schema):
                await asyncio.sleep(0)
                return model._payload([])["response_format"]["json_schema"]["schema"]
        try:
            left, right = await asyncio.gather(payload(first), payload(second))
            self.assertIn("first_only", left["properties"])
            self.assertNotIn("second_only", left["properties"])
            self.assertIn("second_only", right["properties"])
            self.assertEqual(model._payload([])["response_format"], {"type": "json_object"})
        finally:
            await model.aclose()

    async def test_local_requests_have_no_authorization_and_context_exceeds_output_cap(self):
        import httpx
        from usability.local_backend import LocalLlamaModel
        seen = []
        def respond(request):
            seen.append(request)
            return httpx.Response(200, json={
                "id": "local-test", "object": "chat.completion", "created": 0,
                "model": "qwen3-vl-2b-local", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
        model = LocalLlamaModel(resolve_model_settings({"LLM_PROVIDER": "local", "LLM_API_KEY": "cloud-secret"}))
        await model._async.aclose()
        model._async = httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)
        try:
            response = await model._arun([{"role": "user", "content": "Test"}])
            self.assertEqual(response.choices[0].message.content, "{}")
            self.assertNotIn("authorization", seen[0].headers)
            self.assertNotIn("cloud-secret", seen[0].content.decode())
            self.assertGreater(model.token_limit, model.model_config_dict["max_tokens"])
            self.assertGreaterEqual(model.token_limit, 4096)
        finally:
            await model.aclose()


if __name__ == "__main__":
    unittest.main()
