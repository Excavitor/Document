import re
import time
import json

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

class _ThinkFilter:
    """Hides a <think>...</think> block if the model writes one."""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""
        self.state = "start"  # start -> thinking -> normal

    def feed(self, text):
        if self.state == "normal":
            return text
        self.buf += text
        if self.state == "start":
            if len(self.buf) < len(self.OPEN) and self.OPEN.startswith(self.buf):
                return ""  # could still turn into <think>
            if self.buf.startswith(self.OPEN):
                self.state = "thinking"
                self.buf = self.buf[len(self.OPEN):]
            else:
                self.state = "normal"
                out, self.buf = self.buf, ""
                return out
        if self.state == "thinking":
            end = self.buf.find(self.CLOSE)
            if end == -1:
                self.buf = self.buf[-len(self.CLOSE):]
                return ""
            rest = self.buf[end + len(self.CLOSE):].lstrip()
            self.state = "normal"
            self.buf = ""
            return rest
        return ""

    def flush(self):
        if self.state == "start":
            out, self.buf = self.buf, ""
            return out
        return ""


def stream_model(messages, temperature=0.3, max_tokens=300):
    """Yields {"type": "token", "text": ...} pieces, then one {"type": "done", ...}."""
    url = settings.LLAMA_SERVER_URL.rstrip("/") + "/v1/chat/completions"
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    started = time.monotonic()
    try:
        response = requests.post(
            url, json=payload, stream=True,
            timeout=(10, settings.LLAMA_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ModelError("The model server is not running. Start llama-server and try again.")
    except requests.exceptions.Timeout:
        raise ModelError("The model took too long to answer.")
    except requests.exceptions.RequestException as exc:
        raise ModelError(f"Model server error: {exc}")

    response.encoding = "utf-8"
    think_filter = _ThinkFilter()
    first = None
    count = 0
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content") or ""
            if not piece:
                continue
            count += 1  # the server sends about one token per piece
            out = think_filter.feed(piece)
            if out:
                if first is None:
                    first = time.monotonic() - started
                yield {"type": "token", "text": out}
        tail = think_filter.flush()
        if tail:
            if first is None:
                first = time.monotonic() - started
            yield {"type": "token", "text": tail}
    except requests.exceptions.RequestException as exc:
        raise ModelError(f"Model server error: {exc}")
    finally:
        response.close()  # also stops llama-server if the user pressed Stop

    total = time.monotonic() - started
    gen_time = total - (first or 0)
    tps = round((count - 1) / gen_time, 1) if count > 1 and gen_time > 0 else None
    yield {
        "type": "done",
        "first_token": round(first, 1) if first is not None else None,
        "seconds": round(total, 1),
        "tokens": count,
        "tokens_per_second": tps,
    }
