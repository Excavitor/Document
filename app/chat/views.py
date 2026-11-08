import json

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .llm_client import ModelError, stream_model

DEFAULT_SYSTEM = "You are a helpful assistant. Answer briefly in English."


def index(request):
    return render(request, "chat/index.html", {"default_system": DEFAULT_SYSTEM})


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def _lines(messages, temperature, max_tokens):
    """One JSON object per line. Errors are sent as a line too."""
    try:
        for event in stream_model(messages, temperature, max_tokens):
            yield json.dumps(event) + "\n"
    except ModelError as exc:
        yield json.dumps({"type": "error", "message": str(exc)}) + "\n"


@require_POST
def api_chat_stream(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _error("Bad request.", 400)

    message = (body.get("message") or "").strip()
    if not message:
        return _error("Please type a question.", 400)
    system = (body.get("system") or DEFAULT_SYSTEM).strip()

    try:
        temperature = min(max(float(body.get("temperature", 0.3)), 0.0), 1.5)
    except (TypeError, ValueError):
        temperature = 0.3
    try:
        max_tokens = min(max(int(body.get("max_tokens", 300)), 16), 1024)
    except (TypeError, ValueError):
        max_tokens = 300

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message + " /no_think"},
    ]
    response = StreamingHttpResponse(
        _lines(messages, temperature, max_tokens),
        content_type="application/x-ndjson",
    )
    response["Cache-Control"] = "no-cache"
    return response