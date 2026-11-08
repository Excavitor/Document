# Model register

| Item | Source URL | Licence | File name | SHA-256 | Date |
|---|---|---|---|---|---|
| llama.cpp (release tag: b12186) | github.com/ggml-org/llama.cpp | MIT | llama-b12186-bin-win-cpu-x64.zip | 2353A275B364552C7BBE739D3391918B8762506F02BD56751CE568AC13B24C0F | 2026-11-07 |
| Qwen3 4B Q4_K_M (GGUF) | huggingface.co/ggml-org/Qwen3-4B-GGUF (original model: huggingface.co/Qwen/Qwen3-4B) | Apache 2.0 (shown on the model page) | Qwen3-4B-Q4_K_M.gguf (2,497,280,640 bytes) | AB27B9BFA375A178D6CBA48F3AD892B94B7739659DCC7AAE8058CE0FFED6B328 | 2026-11-07 |

## Install locations

- llama.cpp: C:\local-ai\llama.cpp (llama-server version 0.9.0-dev, build 12186)
- Model: C:\local-ai\models
- Project: C:\Users\My Local PC\Desktop\Selim\Document (Django project in the app folder)

## Server command (current)

```powershell
cd C:\local-ai\llama.cpp
.\llama-server.exe -m C:\local-ai\models\Qwen3-4B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -c 4096 -t 8 -np 1 --no-webui
```

- --no-webui turns off the built-in web page on port 8080. The API (/v1/chat/completions and /health) still works. Our own Django page is the only interface.

## Django command (current)

```powershell
cd "C:\Users\My Local PC\Desktop\Selim\Document\app"
..\.venvDocument\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

Page: http://127.0.0.1:8000/ (start llama-server first).

## Useful commands

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
netstat -ano | findstr :8080
netstat -ano | findstr :8000
```

Skip the thinking part by ending a question with /no_think, for example:
`What is the capital of France? /no_think`
(Our Django page adds /no_think automatically.)

## Phase 1 results (2026-11-07)

- First test, "hello": 210 prompt tokens read at about 20 tokens/s, 74 tokens written at about 9 tokens/s (included hidden thinking). Not a proper benchmark.
- /health returned ok. netstat showed 127.0.0.1:8080 LISTENING only (no 0.0.0.0).
- Worked with the internet turned off.
- "/no_think" skips the thinking part (21 tokens instead of 74).

## About the context limit

- The limit shown in the web page (4.10K) is the context size I set with -c 4096. It is a local setting, not an external limit.
- Context = how much text the model keeps in memory for one chat (questions, answers and history).
- A bigger context uses more RAM, and the CPU has more text to read, so answers get slower.
- When the context is full, start a new chat. It is not permanent: restart the server with a bigger -c, for example -c 8192.
- Follow-up questions are fast because earlier text is cached (only new tokens are re-read).

## Phase 2: llama-bench results (2026-11-07)

Command: `.\llama-bench.exe -m C:\local-ai\models\Qwen3-4B-Q4_K_M.gguf -p 512,2048 -n 128 -t 4,8`
CPU backend loaded: ggml-cpu-haswell.dll (AVX2). Nothing else running. Build 12186.

| Threads | pp512 (tokens/s) | pp2048 (tokens/s) | tg128 (tokens/s) |
|---|---|---|---|
| 4 | 22.23 ± 0.67 | 19.43 ± 0.33 | 10.26 ± 0.45 |
| 8 | 27.35 ± 0.88 | 26.25 ± 0.15 | 12.68 ± 0.06 |

- pp = speed of reading the prompt. tg = speed of writing the answer.
- Decision: use 8 threads.
- A 2,000-token prompt takes about 75 seconds to read (calculated, not measured in a real chat).

## Phase 2: test question results (2026-11-07)

Settings: -c 4096 -t 8 -np 1, /no_think. Sample document of about 400 words (invented data).
Peak RAM (llama-server): 4.6 GB.

| # | Test | Prompt tokens | First word (s) | Total (s) | Write speed (tok/s) | Correct |
|---|---|---|---|---|---|---|
| 1 | Short question | 220 | 8.4 | 9.8 | 8.1 | yes |
| 2 | Deposit and date | 529 | 20.8 | 24.7 | 9.0 | yes |
| 3 | People and roles | 60 | 3.5 | 14.9 | 8.4 | yes |
| 4 | Nominee (not in document) | 113 | 4.9 | 6.4 | 9.5 | yes (said not mentioned) |
| 5 | Name, DOB, ID, branch | 46 | 3.8 | 12.0 | 7.8 | yes |
| 6 | One-sentence follow-up | 83 | 4.2 | 10.7 | 8.8 | yes |

- Reading speed about 25 tokens/s on larger prompts; real writing speed about 8 to 9.5 tokens/s.
- Decision: keep Qwen3 4B Q4_K_M, 8 threads, context 4096 for now (8192 if needed), temperature 0.2 to 0.3 in our own page.
- Not tested yet: Vulkan build (Vega 11), Gemma 4 26B-A4B, scanned documents.

## Phase 3 results: Django test page (2026-11-08)

Versions: Python 3.12.5, Django 6.1.3, requests 2.34.2 (venv .venvDocument).

- Page at http://127.0.0.1:8000/ with system prompt, temperature, max tokens and a question box. No login (test only).
- Server on: "What is the capital of France?" answered "Paris" in 2.3 s. A longer answer (cricket) took 8.5 s.
- llama-server stopped: page shows "The model server is not running. Start llama-server and try again." (Django returns 502, no crash).
- netstat: Django listens on 127.0.0.1:8000 only.
- With --no-webui, http://127.0.0.1:8080/ returns 404 "File Not Found". The Django page still works.
- Django calls llama-server only through chat/llm_client.py, so the model can be swapped later.
- Next: Phase 4 (streaming, Stop button, timing), then LC check v1.

## Phase 4 results (2026-11-08)
- Streaming works: words appear as the model writes them.
- Stop button works: text stays, status shows "Stopped."
- Timing shown at the end: first word, total time, tokens/s.