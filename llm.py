"""Local Ollama LLM client.

The CI workflow installs Ollama and pulls gpt-oss:20b at start, so we can talk to a
model on localhost with no free-tier quota to run out of. Hosted providers (NIM,
Groq, OpenRouter) used to sit ahead of Ollama as a fallback chain, but their free
tiers went dark often enough that any run they touched would blow past the 110-min
CI cap before rolling over. Local-only removes that whole failure mode.

Reasoning models (gpt-oss) return content=null with reasoning_content set when the
token budget ran out mid-thought. That's handled here so callers don't have to.
"""
import json, os, random, re, time

import requests

_url = (os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
if not _url.endswith("/chat/completions"):
    _url = _url + "/v1/chat/completions"
OLLAMA_URL = _url
# Kept the NIM_MODEL name so callers don't need to change; OLLAMA_MODEL takes
# precedence when set (the CI workflow sets it).
NIM_MODEL = (os.environ.get("OLLAMA_MODEL") or os.environ.get("NIM_MODEL")
             or "gpt-oss:20b").strip()
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))
LLM_ATTEMPTS = int(os.environ.get("LLM_ATTEMPTS", "3"))


def log(msg): print(f"[llm] {msg}", flush=True)


class TransientError(Exception):
    """Worth retrying. A 4xx other than 408/429 is a config error and never is."""


def _content(data):
    """Reasoning models leave content null when reasoning eats the budget; return the
    finish reason so the caller can grow max_tokens and try again."""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    reasoned = bool((message.get("reasoning_content") or "").strip())
    return content, choice.get("finish_reason"), reasoned


def nim_chat(system, user, temperature=0.9, attempts=None, max_tokens=512):
    """One local LLM call with a small retry budget. Ollama is CPU-bound in CI so the
    per-call timeout is generous; retries only cover the reasoning-ran-out-of-budget
    case and transient socket blips."""
    budget = max_tokens
    tries = attempts or LLM_ATTEMPTS
    last = None
    for i in range(tries):
        try:
            r = requests.post(
                OLLAMA_URL,
                headers={"Authorization": "Bearer ollama"},
                json={
                    "model": NIM_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": budget,
                },
                timeout=LLM_TIMEOUT,
            )
            if r.status_code in (408, 429) or r.status_code >= 500:
                raise TransientError(f"{r.status_code} {r.text[:200]}")
            if r.status_code >= 400:
                raise RuntimeError(f"ollama returned {r.status_code}: {r.text[:200]}")
            content, finish, reasoned = _content(r.json())
            if content:
                return content
            why = ("spent the whole budget reasoning" if reasoned
                   else f"returned no content ({finish})")
            raise TransientError(f"{NIM_MODEL} {why} at max_tokens={budget}")
        except (requests.Timeout, requests.ConnectionError, TransientError) as e:
            last = e
            empty = isinstance(e, TransientError) and "max_tokens" in str(e)
            if empty:
                budget = min(budget * 4, 8000)
            if i < tries - 1:
                wait = 0 if empty else min(5 * 2 ** i, 30) + random.uniform(0, 2)
                log(f"ollama failed ({type(e).__name__}), attempt {i + 1}/{tries}, "
                    f"retry{'' if empty else f' in {wait:.0f}s'}: {str(e)[:140]}")
                if wait:
                    time.sleep(wait)
    raise last


def nim_json(system, user, temperature=0.6, max_tokens=1200):
    """Chat call that must return JSON. Models wrap answers in prose or fences often
    enough that the raw text is rarely parseable on its own."""
    raw = nim_chat(
        system + " Respond ONLY with valid JSON. No prose, no markdown fences.",
        user, temperature=temperature, max_tokens=max_tokens,
    )
    cleaned = re.sub(r"```[a-z]*|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"[{\[].*[}\]]", cleaned, re.S)
        if not match:
            raise RuntimeError(f"model returned no JSON: {cleaned[:200]}")
        return json.loads(match.group(0))
