"""LLM provider layer (Power): Meterless Runtime + NVIDIA direct.

Organizer ruling (Sam Cummings, Meterless team, HackOS #Help Meterless,
Oct 19, confirmed Oct 22): the Power rule is satisfied by implementing
Meterless Runtime as an OpenAI-compatible provider in the app (provider
contract: meterless.ai/engines.html, "Add Meterless as a provider",
Runtime 1.4 / provider contract v4). NVIDIA prize criteria do NOT
require Nemotron calls to go through Nightshift: developing and testing
against NVIDIA's direct API is fine, and the Nightshift provider
connection in the product auto-qualifies because NVIDIA is a featured
provider inside Nightshift.

So this module carries BOTH routes behind one interface:

  - "meterless": Meterless Runtime (Nightshift) as an OpenAI-compatible
    provider, contract v4 details below.
  - "nvidia": NVIDIA direct API (integrate.api.nvidia.com), the working
    default on the M1 Mac, where the free Nightshift edition exposes no
    callable endpoint (see GOAL.md, Meterless blocker, Oct 20).

Selection is env-driven (see resolve_provider):

  LLM_PROVIDER   "auto" (default) | "meterless" | "nvidia"
  auto = meterless when a Meterless base URL or token is configured,
         else nvidia.

Meterless env:
  METERLESS_RUNTIME_BASE_URL   Nightshift base URL or connect link.
                               Default http://127.0.0.1:8088/v1.
  METERLESS_RUNTIME_API_KEY    Runtime token (Bearer). The runtime
                               writes it to <stateDir>/proxy-token;
                               the placeholder "rt-local" is rejected
                               by the runtime (probe reports it as
                               "unauthorized", never "offline").
  METERLESS_RUNTIME_TOKEN_FILE Path to the proxy-token file, used when
                               the key env var is unset.
  METERLESS_RUNTIME_MODEL      Routing-mode model id, default
                               "meterless/auto".

NVIDIA env (unchanged, same names .env and smoke_test.py already use):
  MODEL_BASE_URL   default https://integrate.api.nvidia.com/v1
  MODEL_API_KEY    build.nvidia.com key
  NEMOTRON_MODEL   via src.config (default ultra-550b)

Runtime 1.4 contract points implemented here:
  - Base URL normalisation: a pasted URL with or without a scheme,
    /v1, /v1/chat/completions, /v1/models or /healthz is normalised to
    <host>/v1. Never /v1/v1.
  - Connect links (http://<host>:<port>/connect#k=<key>): base URL is
    the origin + /v1, the token comes from k. The link is never logged.
  - Authorization: Bearer <token> on every Meterless call, plus
    meterless-app: quantpilot on every Meterless request and
    meterless-scope: user on chat.
  - Model ids are routing modes (meterless/<disposition>,
    meterless/<class>, meterless/<class>.<disposition>); list_models()
    returns ids from GET /v1/models as-is, unknown meterless/* ids
    included.
  - probe(): GET /healthz only proves the process is up; the status is
    decided by GET /v1/models: 401/403 = "unauthorized", 200 with
    meterless ids = "online", anything else = "offline".
  - Chat timeout 180 s (a model load can take minutes); plain-text
    requests stay plain strings, exactly like OpenAI.

HTTP goes through requests (same as zetaris.py) so the module works in
the project venv without the openai package; the wire format is the
OpenAI chat-completions shape either way.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from .. import config

PROVIDER_METERLESS = "meterless"
PROVIDER_NVIDIA = "nvidia"

DEFAULT_METERLESS_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_METERLESS_MODEL = "meterless/auto"
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
APP_ID = "quantpilot"  # meterless-app header: stable lowercase app id
CHAT_TIMEOUT_S = 180   # contract: a model load can take minutes
# Transient failures (rate limit, gateway errors, timeouts) retry with
# backoff; anything else (401/403/404) fails fast - retrying a dead
# model id only burns the demo clock.
CHAT_RETRIES = 2
CHAT_BACKOFF_S = 4.0
_RETRY_STATUS = {429, 500, 502, 503, 504}

# -- Run-scoped model-call log -------------------------------------------
# The Official Rules (8.1/15.2/16/23) and the NVIDIA award are scored
# from run evidence: which provider and which model actually handled
# each request, and how long it took. Every chat() call appends one
# entry here; the runner clears the log at run start and drains it
# into artifacts.json as "model_calls".
# Entries: {"provider", "model", "latency_ms", "ok"}.
CALL_LOG: List[Dict] = []


def clear_call_log() -> None:
    """Start a fresh model-call log (called at run start)."""
    CALL_LOG.clear()


def get_call_log() -> List[Dict]:
    """A copy of the model-call entries recorded so far."""
    return [dict(entry) for entry in CALL_LOG]


def _record_call(provider: str, model: str, started: float, ok: bool) -> None:
    CALL_LOG.append(
        {
            "provider": provider,
            "model": model,
            "latency_ms": int(round((time.time() - started) * 1000)),
            "ok": ok,
        }
    )

# Path suffixes a pasted base URL may carry; all normalise away.
_SUFFIXES = ("/v1/chat/completions", "/v1/models", "/healthz", "/v1")


def parse_connect_link(raw: str) -> Optional[Tuple[str, str]]:
    """Parse a Nightshift connect link into (base_url, token).

    Link shape: http://<host>:<port>/connect#k=<key>. Returns None when
    the value is not a connect link. Never log the returned token.
    """
    if "#k=" not in raw:
        return None
    parts = urlsplit(raw.strip())
    if not parts.netloc:
        return None
    token = ""
    for pair in parts.fragment.split("&"):
        if pair.startswith("k="):
            token = pair[2:]
    if not token:
        return None
    scheme = parts.scheme or "http"
    return (f"{scheme}://{parts.netloc}/v1", token)


def normalize_base_url(raw: str) -> str:
    """Normalise a pasted provider URL to <host>/v1 (contract v4).

    Accepts a bare host, a host with /v1, /v1/chat/completions,
    /v1/models or /healthz, with or without a scheme. Never produces
    /v1/v1. Connect links are handled by parse_connect_link first.
    """
    url = raw.strip()
    if not url:
        return DEFAULT_METERLESS_BASE_URL
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    changed = True
    while changed:
        changed = False
        for suffix in _SUFFIXES:
            if path.endswith(suffix):
                path = path[: -len(suffix)].rstrip("/")
                changed = True
                break
    return f"{parts.scheme}://{parts.netloc}{path}/v1"


def _load_meterless_token(env: Dict[str, str]) -> str:
    """Meterless token: env var first, then the proxy-token file."""
    token = env.get("METERLESS_RUNTIME_API_KEY", "").strip()
    if token:
        return token
    token_file = env.get("METERLESS_RUNTIME_TOKEN_FILE", "").strip()
    if token_file:
        path = os.path.expanduser(token_file)
        if os.path.exists(path):
            with open(path) as fh:
                return fh.read().strip()
    return ""


@dataclass
class ProviderConfig:
    """Resolved provider connection (one route, fully specified)."""

    provider: str            # PROVIDER_METERLESS or PROVIDER_NVIDIA
    base_url: str            # OpenAI-compatible root, ends with /v1
    api_key: str = ""
    model: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)


def _meterless_config(env: Dict[str, str]) -> ProviderConfig:
    raw_url = env.get("METERLESS_RUNTIME_BASE_URL", "").strip()
    token = _load_meterless_token(env)
    link = parse_connect_link(raw_url) if raw_url else None
    if link is not None:
        base_url, link_token = link
        token = token or link_token
    elif raw_url:
        base_url = normalize_base_url(raw_url)
    else:
        base_url = DEFAULT_METERLESS_BASE_URL
    return ProviderConfig(
        provider=PROVIDER_METERLESS,
        base_url=base_url,
        api_key=token,
        model=env.get("METERLESS_RUNTIME_MODEL", "").strip()
        or DEFAULT_METERLESS_MODEL,
        extra_headers={"meterless-app": APP_ID},
    )


def _nvidia_config(env: Dict[str, str]) -> ProviderConfig:
    return ProviderConfig(
        provider=PROVIDER_NVIDIA,
        base_url=(
            env.get("MODEL_BASE_URL", "").strip() or DEFAULT_NVIDIA_BASE_URL
        ).rstrip("/"),
        api_key=env.get("MODEL_API_KEY", "").strip(),
        model=env.get("NEMOTRON_MODEL", "").strip() or config.NEMOTRON_MODEL,
    )


def resolve_provider(env: Optional[Dict[str, str]] = None) -> ProviderConfig:
    """Pick the active provider from the environment.

    LLM_PROVIDER=meterless forces the Meterless Runtime route;
    =nvidia forces NVIDIA direct; unset/"auto" picks Meterless when a
    Meterless base URL or token is configured, else NVIDIA direct (the
    current working default on the M1 Mac).
    """
    env = dict(os.environ) if env is None else env
    choice = env.get("LLM_PROVIDER", "auto").strip().lower() or "auto"
    if choice == PROVIDER_METERLESS:
        return _meterless_config(env)
    if choice == PROVIDER_NVIDIA:
        return _nvidia_config(env)
    if choice != "auto":
        raise ValueError(
            f"LLM_PROVIDER must be auto, meterless or nvidia, got {choice!r}"
        )
    meterless_configured = bool(
        env.get("METERLESS_RUNTIME_BASE_URL", "").strip()
        or env.get("METERLESS_RUNTIME_API_KEY", "").strip()
        or env.get("METERLESS_RUNTIME_TOKEN_FILE", "").strip()
    )
    if meterless_configured:
        return _meterless_config(env)
    return _nvidia_config(env)


class LLMProvider:
    """OpenAI-compatible chat client over one resolved ProviderConfig."""

    def __init__(self, cfg: ProviderConfig) -> None:
        self.config = cfg

    @classmethod
    def from_env(cls) -> "LLMProvider":
        return cls(resolve_provider())

    def _headers(self, chat: bool = False) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        headers.update(self.config.extra_headers)
        if chat and self.config.provider == PROVIDER_METERLESS:
            headers["meterless-scope"] = "user"
        return headers

    def list_models(self) -> List[str]:
        """Model ids from GET /v1/models, returned as-is."""
        resp = requests.get(
            self.config.base_url + "/models",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return [row.get("id", "") for row in resp.json().get("data", [])]

    def probe(self) -> str:
        """Connection status: "online", "unauthorized" or "offline".

        Per contract v4, GET /v1/models decides (a /healthz 200 only
        proves the process is up): 401/403 = unauthorized (a wrong or
        placeholder token lands here, not offline); 200 = online; any
        other outcome = offline.
        """
        try:
            resp = requests.get(
                self.config.base_url + "/models",
                headers=self._headers(),
                timeout=10,
            )
        except requests.RequestException:
            return "offline"
        if resp.status_code in (401, 403):
            return "unauthorized"
        if resp.status_code != 200:
            return "offline"
        if self.config.provider == PROVIDER_METERLESS:
            try:
                ids = [row.get("id", "") for row in resp.json().get("data", [])]
            except ValueError:
                return "offline"
            if not any(mid.startswith("meterless/") for mid in ids):
                return "offline"
        return "online"

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> dict:
        """One chat completion; returns the parsed OpenAI-shaped JSON.

        Every call is recorded in the module call log (see CALL_LOG).
        The model recorded is the one that actually served: the
        response's own "model" field when the endpoint returns one
        (the Meterless route echoes the concrete model it routed to),
        otherwise the requested model. A failed call is recorded with
        ok=False and the exception re-raised.
        """
        requested = model or self.config.model
        started = time.time()
        try:
            data = self._chat_impl(messages, requested, max_tokens, temperature)
        except Exception:
            _record_call(self.config.provider, requested, started, ok=False)
            raise
        served = data.get("model") if isinstance(data, dict) else None
        _record_call(self.config.provider, served or requested, started, ok=True)
        return data

    def _chat_impl(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: Optional[float],
    ) -> dict:
        payload: Dict[str, object] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        attempt = 0
        while True:
            try:
                resp = requests.post(
                    self.config.base_url + "/chat/completions",
                    headers=self._headers(chat=True),
                    json=payload,
                    timeout=CHAT_TIMEOUT_S,
                )
                if resp.status_code in _RETRY_STATUS and attempt < CHAT_RETRIES:
                    raise _Transient(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except (_Transient, requests.Timeout, requests.ConnectionError):
                if attempt >= CHAT_RETRIES:
                    raise
                attempt += 1
                time.sleep(CHAT_BACKOFF_S * attempt)

    def chat_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> str:
        """Plain-text in, plain-text out (the contract smoke shape)."""
        data = self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
            max_tokens=max_tokens,
        )
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message", {}) or {}
        content = message.get("content")
        if not isinstance(content, str):
            return ""
        # Reasoning models (Nemotron ultra) that hit max_tokens while
        # still thinking return the raw reasoning as the content. That
        # is not an answer: a parser could pull a verdict out of the
        # model's own deliberation. Treat it as no reply.
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip() and (
            content.strip() == reasoning.strip()
        ):
            return ""
        # Through the Meterless Runtime (Nightshift 0.92.7, measured Oct
        # 26) Nemotron's reasoning arrives INLINE in content, closed by
        # "</think>"; the answer is what follows. An opened, unclosed
        # think block is a reply cut off mid-thought: no answer.
        if "</think>" in content:
            content = content.rsplit("</think>", 1)[1].strip()
        elif "<think>" in content:
            return ""
        # House rule: no em dash anywhere, generated output included.
        # Models write them freely; normalize at the transport.
        return content.replace("\u2014", " - ").replace("\u2013", "-")


class _Transient(Exception):
    """A retryable HTTP status from the chat endpoint."""


def get_llm_provider(env: Optional[Dict[str, str]] = None) -> LLMProvider:
    """Factory mirroring get_provider() in src/data: env in, client out."""
    return LLMProvider(resolve_provider(env))
