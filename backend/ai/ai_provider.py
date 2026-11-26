"""Request structured output from local Ollama."""

import json
import os
from dataclasses import dataclass
from urllib.request import ProxyHandler, Request, build_opener


class AIProviderError(Exception):
    """An AI provider is unavailable or returned an incomplete response."""


@dataclass(frozen=True)
class AIConfig:
    model: str


def load_ai_config() -> AIConfig:
    model = os.environ.get("CLAIMS_AI_MODEL", "").strip()
    return AIConfig(model or "qwen3:1.7b")


def request_structured_output(
    config: AIConfig,
    *,
    instructions: str,
    payload: dict,
    schema: dict,
) -> str:
    content = json.dumps(payload, ensure_ascii=False)
    return _request_ollama(config.model, instructions, content, schema)


def _request_ollama(model: str, instructions: str, content: str, schema: dict) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ],
        "format": schema,
        "stream": False,
        "think": False,
        "keep_alive": 0,
        "options": {"temperature": 0, "num_predict": 256, "num_ctx": 4096},
    }
    request = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=90) as connection:
            result = json.load(connection)
        if result["done"] is True and result.get("done_reason") != "length":
            return result["message"]["content"]
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise AIProviderError(
            f"Could not get a response from Ollama. Check that it is running and that the model {model} is installed."
        ) from error
    raise AIProviderError("Ollama returned an incomplete response. Try again or select a policy entry manually.")
