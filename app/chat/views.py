import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .llm_client import ModelError, ask_model

DEFAULT_SYSTEM = "You are a helpful assistant. Answer briefly in English."


def index(request):
    return render(request, "chat/index.html", {"default_system": DEFAULT_SYSTEM})


def _error(message, status):
    return JsonResponse({"reply": None, "seconds": None, "error": message}, status=status)


@require_POST
def api_chat(request):
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
        # /no_think tells Qwen3 to skip its thinking part (faster on this CPU).
        {"role": "user", "content": message + " /no_think"},
    ]
    try:
        result = ask_model(messages, temperature, max_tokens)
    except ModelError as exc:
        return _error(str(exc), 502)

    return JsonResponse({"reply": result["reply"], "seconds": result["seconds"], "error": None})