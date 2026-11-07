
"""Optional OpenAI, Gemini and Claude translation adapters."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

class ModelUnavailable(Exception):
    pass


PROVIDERS = {
    "openai": (
        "OPENAI_API_KEY",
        "OPENAI_TRANSLATION_MODEL"
    ),
    "gemini": (
        "GEMINI_API_KEY",
        "GEMINI_TRANSLATION_MODEL"
    ),
    "anthropic": (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_TRANSLATION_MODEL"
    )
}


def configured_providers():
    return [
        provider
        for provider, (key_var, model_var) in PROVIDERS.items()
        if os.getenv(key_var) and os.getenv(model_var)
    ]


def _post(url, headers, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as e:
        details = e.read().decode("utf-8", errors="replace")
        raise ModelUnavailable(
            f"HTTP {e.code}: {details}"
    )   from e

    except (URLError, TimeoutError, ValueError) as e:
        raise ModelUnavailable(str(e)) from e


def generate(text, direction, provider):
    """Return unverified model output or raise ModelUnavailable."""

    if provider not in PROVIDERS:
        raise ModelUnavailable(f"Unknown provider: {provider}")

    if direction not in ("en->roh", "roh->en"):
        raise ModelUnavailable("Invalid direction")

    key_var, model_var = PROVIDERS[provider]
    api_key = os.getenv(key_var)
    model = os.getenv(model_var)

    if not api_key or not model:
        raise ModelUnavailable(
            f"Set {key_var} and {model_var}"
        )

    source, target = (
        ("English", "Rohingya")
        if direction == "en->roh"
        else ("Rohingya", "English")
    )

    instruction = (
        f"Translate from {source} to {target}. "
        "Return ONLY the translation text, without explanations, "
        "alternatives, or quotation marks. "
        "If you cannot translate reliably, return exactly UNSURE. "
        "Do not fabricate facts or claim native-speaker verification."
    )

    prompt = f"{instruction}\nInput:\n{text}"

    if provider == "openai":
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )

        output = data["choices"][0]["message"]["content"]

    elif provider == "gemini":
        data = _post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(model, safe="")
            + ":generateContent",
            {"x-goog-api-key": api_key},
            {
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            }
        )

        output = "".join(
            part.get("text", "")
            for part in data["candidates"][0]["content"]["parts"]
        )

    else:
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            {
                "model": model,
                "max_tokens": 350,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )

        output = "".join(
            block.get("text", "")
            for block in data["content"]
            if block.get("type") == "text"
        )

    if not isinstance(output, str):
        raise ModelUnavailable("Model did not return text")

    output = output.strip().strip('"')

    if not output or output.upper().strip(".!") == "UNSURE":
        raise ModelUnavailable("Model abstained")

    return output
