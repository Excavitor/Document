import re
import time

import requests
from django.conf import settings


class ModelError(Exception):
    """A problem talking to the local model server."""


def ask_model(messages, temperature=0.3, max_tokens=300):
    url = settings.LLAMA_SERVER_URL.rstrip("/") + "/v1/chat/completions"
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    started = time.monotonic()
    try:
        response = requests.post(url, json=payload, timeout=settings.LLAMA_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ModelError("The model server is not running. Start llama-server and try again.")
    except requests.exceptions.Timeout:
        raise ModelError("The model took too long to answer.")
    except requests.exceptions.RequestException as exc:
        raise ModelError(f"Model server error: {exc}")

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise ModelError("Unexpected reply from the model server.")

    # Remove any leftover thinking block.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return {"reply": text, "seconds": round(time.monotonic() - started, 1)}