"""
LLM factory — pick a backend for the agents to think with.

Priority: whatever RAEM_LLM_PROVIDER says, else auto-detect. The same agents run
whether you're on Anthropic, a local Ollama box, or another cloud provider.

Providers
  anthropic  (default)  cloud                  ANTHROPIC_API_KEY (RAEM_LLM_MODEL=claude-sonnet-5)
  ollama                 local, free            RAEM_LLM_MODEL=qwen2.5:7b, OLLAMA_BASE_URL
  openai                cloud                  OPENAI_API_KEY (+ optional OPENAI_BASE_URL, RAEM_LLM_MODEL)
  groq                  cloud, fast/cheap      GROQ_API_KEY   (RAEM_LLM_MODEL=llama-3.3-70b-versatile)
  kimi                  cloud (Moonshot AI)    MOONSHOT_API_KEY (RAEM_LLM_MODEL=kimi-k3, default)
"""

from __future__ import annotations

import os
import time

from . import config


def _provider() -> str:
    p = os.environ.get("RAEM_LLM_PROVIDER", "").strip().lower()
    if p:
        return p
    # ✅ CHANGED: Anthropic checked first in auto-detect (was last) — Claude
    # Sonnet 5 is now the intended default provider for this app.
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("MOONSHOT_API_KEY"):
        return "kimi"
    return "ollama"


def make_llm(temperature=None):
    """Return a chat model for the detected/configured provider."""
    provider = _provider()
    temp = config.LLM_TEMPERATURE if temperature is None else temperature

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=config.LLM_MODEL, base_url=config.OLLAMA_BASE_URL, temperature=temp)

    if provider == "groq":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=os.environ.get("RAEM_LLM_MODEL", "llama-3.3-70b-versatile"),
                          api_key=os.environ["GROQ_API_KEY"],
                          base_url="https://api.groq.com/openai/v1", temperature=temp)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": os.environ.get("RAEM_LLM_MODEL", "gpt-4o-mini"),
                  "api_key": os.environ["OPENAI_API_KEY"], "temperature": temp}
        if os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=os.environ.get("RAEM_LLM_MODEL", "claude-sonnet-5"),
                             api_key=os.environ["ANTHROPIC_API_KEY"])
    if provider == "kimi":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=os.environ.get("RAEM_LLM_MODEL", "kimi-k3"),
                          api_key=os.environ["MOONSHOT_API_KEY"],
                          base_url="https://api.moonshot.ai/v1", temperature=temp)

    raise ValueError(f"Unknown RAEM_LLM_PROVIDER: {provider}")
#Ari-----
def _normalize_content(content):
    """Claude's newer models can return `.content` as a list of content
    blocks (e.g. text/thinking blocks) instead of a plain string. Every
    agent node in agents.py expects a plain string, so flatten it here —
    once, centrally — rather than touching all 14 call sites."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return content


def invoke_llm_with_retry(llm, prompt_or_messages, max_attempts: int = 3):
    """llm.invoke() with rate-limit backoff — the shared helper from the
    notebook. Every agent used to carry its own copy-pasted
    "for attempt in range(3): ... except: sleep" loop; if every attempt hit
    a rate limit, that loop finished WITHOUT ever assigning `response`,
    causing a NameError on the next line. This single helper is used
    everywhere instead and raises a clear error if all retries are
    exhausted, rather than silently leaving a variable undefined.
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            response = llm.invoke(prompt_or_messages)
            response.content = _normalize_content(response.content)
            return response
        except Exception as e:  # noqa: BLE001
            last_err = e
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait_time = 60 * (attempt + 1)
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError(
        f"invoke_llm_with_retry: {max_attempts} attempts exhausted, last error: {last_err}"
    )
#-----Ari
def llm_info() -> dict:
    """Describe the active backend for the health panel (no network call)."""
    provider = _provider()
    model = {
        "ollama": config.LLM_MODEL,
        "groq": os.environ.get("RAEM_LLM_MODEL", "llama-3.3-70b-versatile"),
        "openai": os.environ.get("RAEM_LLM_MODEL", "gpt-4o-mini"),
        "anthropic": os.environ.get("RAEM_LLM_MODEL", "claude-sonnet-5"),
        "kimi": os.environ.get("RAEM_LLM_MODEL", "kimi-k3"),
    }.get(provider, config.LLM_MODEL)
    key_env = "MOONSHOT_API_KEY" if provider == "kimi" else f"{provider.upper()}_API_KEY"
    key_ok = provider == "ollama" or bool(os.environ.get(key_env))
    return {"provider": provider, "model": model, "configured": key_ok,
            "detail": ("local" if provider == "ollama" else ("API key set" if key_ok else "API key missing"))}
