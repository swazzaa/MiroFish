"""Explicit model setup using MiroFish's environment names. Never log secrets."""
import os


def model_from_environment():
    required = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME")
    if any(not os.environ.get(key) for key in required):
        raise ValueError("Set LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL_NAME securely in the environment")
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=os.environ["LLM_MODEL_NAME"],
        api_key=os.environ["LLM_API_KEY"],
        url=os.environ["LLM_BASE_URL"],
        model_config_dict={"stream": False},
        timeout=20,
        max_retries=0,
    )
