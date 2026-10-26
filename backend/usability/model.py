"""Explicit cloud or loopback-only local model setup. Never log credentials."""
from dataclasses import dataclass, field
import ipaddress
import os
from urllib.parse import urlparse


def validate_local_url(url: str) -> str:
    parsed = urlparse(url)
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme not in {"http", "https"} or not loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Local model endpoint must be a loopback URL without credentials or query parameters")
    if parsed.path.rstrip("/") != "/v1":
        raise ValueError("Local model endpoint must end with /v1")
    return url.rstrip("/")


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    url: str
    name: str
    timeout: float
    api_key: str = field(repr=False)


def resolve_model_settings(environ=None) -> ModelSettings:
    env = os.environ if environ is None else environ
    provider = env.get("LLM_PROVIDER", "cloud").strip().lower()
    if provider not in {"local", "cloud"}:
        raise ValueError("LLM_PROVIDER must be local or cloud")
    try:
        timeout = float(env.get("LLM_TIMEOUT_SECONDS", "120" if provider == "local" else "20"))
    except ValueError:
        raise ValueError("LLM_TIMEOUT_SECONDS must be a number") from None
    if not 1 <= timeout <= 300:
        raise ValueError("LLM_TIMEOUT_SECONDS must be from 1 to 300")
    if provider == "local":
        url = validate_local_url(env.get("LLM_BASE_URL", "http://127.0.0.1:8080/v1"))
        name = env.get("LLM_MODEL_NAME", "qwen3-vl-2b-local")
        # SDK-required placeholder, never a real credential. Do not forward
        # any configured cloud key to an unauthenticated local server.
        key = "local-no-secret"
    else:
        required = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME")
        if any(not env.get(key) for key in required):
            raise ValueError("Set LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL_NAME securely, or set LLM_PROVIDER=local")
        key, url, name = (env[key] for key in required)
    if not name.strip():
        raise ValueError("Model name cannot be empty")
    return ModelSettings(provider, url, name, timeout, key)


def model_from_environment():
    settings = resolve_model_settings()
    if settings.provider == "local":
        from .local_backend import LocalLlamaModel
        return LocalLlamaModel(settings)
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    config = {"stream": False}
    platform = ModelPlatformType.OPENAI
    return ModelFactory.create(model_platform=platform, model_type=settings.name,
                               api_key=settings.api_key, url=settings.url,
                               model_config_dict=config, timeout=settings.timeout,
                               max_retries=0)
