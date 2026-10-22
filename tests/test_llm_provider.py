"""Unit tests for the LLM provider layer (src/integrations/llm.py).

Covers provider selection/fallback, Meterless Runtime 1.4 base-URL
normalisation, connect-link parsing, and the chat/probe wire shape.
The HTTP layer (requests) is mocked throughout: no live calls.
"""
from __future__ import annotations

from unittest import mock

import pytest
import requests

from src import config
from src.integrations import llm
from src.integrations.llm import (
    LLMProvider,
    get_llm_provider,
    normalize_base_url,
    resolve_provider,
)


# -- selection / fallback -------------------------------------------------


def test_default_is_nvidia_direct():
    cfg = resolve_provider({})
    assert cfg.provider == "nvidia"
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1"
    assert cfg.model == config.NEMOTRON_MODEL


def test_nvidia_env_route():
    cfg = resolve_provider(
        {
            "MODEL_BASE_URL": "https://integrate.api.nvidia.com/v1/",
            "MODEL_API_KEY": "nv-key",
            "NEMOTRON_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        }
    )
    assert cfg.provider == "nvidia"
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1"
    assert cfg.api_key == "nv-key"
    assert cfg.model == "nvidia/nemotron-3-ultra-550b-a55b"


def test_auto_picks_meterless_when_configured():
    cfg = resolve_provider(
        {"METERLESS_RUNTIME_BASE_URL": "http://127.0.0.1:8088/v1"}
    )
    assert cfg.provider == "meterless"
    assert cfg.base_url == "http://127.0.0.1:8088/v1"
    assert cfg.model == "meterless/auto"


def test_forced_nvidia_beats_meterless_env():
    cfg = resolve_provider(
        {
            "LLM_PROVIDER": "nvidia",
            "METERLESS_RUNTIME_BASE_URL": "http://127.0.0.1:8088/v1",
            "METERLESS_RUNTIME_API_KEY": "tok",
        }
    )
    assert cfg.provider == "nvidia"


def test_forced_meterless_defaults():
    cfg = resolve_provider({"LLM_PROVIDER": "meterless"})
    assert cfg.provider == "meterless"
    assert cfg.base_url == "http://127.0.0.1:8088/v1"
    assert cfg.model == "meterless/auto"
    assert cfg.extra_headers == {"meterless-app": "quantpilot"}


def test_meterless_model_override():
    cfg = resolve_provider(
        {
            "LLM_PROVIDER": "meterless",
            "METERLESS_RUNTIME_MODEL": "meterless/text.deep",
        }
    )
    assert cfg.model == "meterless/text.deep"


def test_invalid_provider_choice_raises():
    with pytest.raises(ValueError):
        resolve_provider({"LLM_PROVIDER": "grok"})


# -- base URL normalisation (contract v4) ---------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "127.0.0.1:8088",
        "http://127.0.0.1:8088",
        "http://127.0.0.1:8088/",
        "http://127.0.0.1:8088/v1",
        "http://127.0.0.1:8088/v1/",
        "http://127.0.0.1:8088/v1/chat/completions",
        "http://127.0.0.1:8088/v1/models",
        "http://127.0.0.1:8088/healthz",
        "http://127.0.0.1:8088/v1/v1",
        "localhost:8090",
    ],
)
def test_normalize_base_url(raw):
    expected_host = "127.0.0.1:8088" if "8090" not in raw else "localhost:8090"
    assert normalize_base_url(raw) == f"http://{expected_host}/v1"


def test_normalize_empty_is_default():
    assert normalize_base_url("") == "http://127.0.0.1:8088/v1"


# -- connect links and token file ------------------------------------------


def test_connect_link_supplies_base_and_token():
    cfg = resolve_provider(
        {
            "LLM_PROVIDER": "meterless",
            "METERLESS_RUNTIME_BASE_URL": "http://192.168.1.5:8088/connect#k=sekret",
        }
    )
    assert cfg.base_url == "http://192.168.1.5:8088/v1"
    assert cfg.api_key == "sekret"


def test_env_token_beats_connect_link_token():
    cfg = resolve_provider(
        {
            "LLM_PROVIDER": "meterless",
            "METERLESS_RUNTIME_BASE_URL": "http://h:8088/connect#k=linktok",
            "METERLESS_RUNTIME_API_KEY": "envtok",
        }
    )
    assert cfg.api_key == "envtok"


def test_token_loaded_from_file(tmp_path):
    token_file = tmp_path / "proxy-token"
    token_file.write_text("file-token\n")
    cfg = resolve_provider(
        {"METERLESS_RUNTIME_TOKEN_FILE": str(token_file)}
    )
    assert cfg.provider == "meterless"  # token file alone counts as configured
    assert cfg.api_key == "file-token"


# -- chat wire shape --------------------------------------------------------


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


_CHAT_OK = {
    "choices": [
        {"message": {"role": "assistant", "content": "ready"}}
    ]
}


def test_chat_meterless_headers_and_shape():
    provider = get_llm_provider(
        {
            "LLM_PROVIDER": "meterless",
            "METERLESS_RUNTIME_API_KEY": "tok123",
        }
    )
    with mock.patch.object(llm.requests, "post", return_value=_Resp(200, _CHAT_OK)) as post:
        text = provider.chat_text("hello")
    assert text == "ready"
    args, kwargs = post.call_args
    assert args[0] == "http://127.0.0.1:8088/v1/chat/completions"
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["meterless-app"] == "quantpilot"
    assert headers["meterless-scope"] == "user"
    assert kwargs["json"]["model"] == "meterless/auto"
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert kwargs["timeout"] == 180


def test_chat_nvidia_has_no_meterless_headers():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    assert isinstance(provider, LLMProvider)
    with mock.patch.object(llm.requests, "post", return_value=_Resp(200, _CHAT_OK)) as post:
        provider.chat([{"role": "user", "content": "hi"}])
    args, kwargs = post.call_args
    assert args[0] == "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer nv-key"
    assert "meterless-app" not in headers
    assert "meterless-scope" not in headers
    assert kwargs["json"]["model"] == config.NEMOTRON_MODEL


# -- probe / models ----------------------------------------------------------


def _models_payload(*ids):
    return {"data": [{"id": mid} for mid in ids]}


def test_probe_meterless_online():
    provider = get_llm_provider({"LLM_PROVIDER": "meterless"})
    with mock.patch.object(
        llm.requests, "get",
        return_value=_Resp(200, _models_payload("meterless/auto", "meterless/x.y")),
    ):
        assert provider.probe() == "online"


def test_probe_meterless_200_without_meterless_ids_is_offline():
    provider = get_llm_provider({"LLM_PROVIDER": "meterless"})
    with mock.patch.object(
        llm.requests, "get", return_value=_Resp(200, _models_payload("gpt-4o"))
    ):
        assert provider.probe() == "offline"


def test_probe_wrong_token_is_unauthorized_not_offline():
    provider = get_llm_provider(
        {"LLM_PROVIDER": "meterless", "METERLESS_RUNTIME_API_KEY": "rt-local"}
    )
    with mock.patch.object(llm.requests, "get", return_value=_Resp(401)):
        assert provider.probe() == "unauthorized"


def test_probe_connection_error_is_offline():
    provider = get_llm_provider({"LLM_PROVIDER": "meterless"})
    with mock.patch.object(
        llm.requests, "get", side_effect=requests.ConnectionError("refused")
    ):
        assert provider.probe() == "offline"


def test_probe_nvidia_online():
    provider = get_llm_provider({})
    with mock.patch.object(
        llm.requests, "get",
        return_value=_Resp(200, _models_payload("nvidia/nemotron-3-ultra-550b-a55b")),
    ):
        assert provider.probe() == "online"


def test_list_models_keeps_unknown_meterless_ids():
    provider = get_llm_provider({"LLM_PROVIDER": "meterless"})
    with mock.patch.object(
        llm.requests, "get",
        return_value=_Resp(
            200, _models_payload("meterless/auto", "meterless/future.thing")
        ),
    ):
        assert provider.list_models() == ["meterless/auto", "meterless/future.thing"]


# -- transport hardening (audit repair, Oct 22) -------------------------------


def test_chat_retries_429_then_succeeds():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    responses = [_Resp(429, {}), _Resp(200, _CHAT_OK)]
    with mock.patch.object(llm.requests, "post", side_effect=responses) as post, \
            mock.patch.object(llm.time, "sleep") as sleep:
        assert provider.chat_text("hi") == "ready"
    assert post.call_count == 2
    sleep.assert_called_once()


def test_chat_404_fails_fast_without_retry():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(llm.requests, "post", return_value=_Resp(404, {})) as post, \
            mock.patch.object(llm.time, "sleep"):
        with pytest.raises(requests.HTTPError):
            provider.chat_text("hi")
    assert post.call_count == 1


def test_chat_timeout_exhausts_retries_then_raises():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(llm.requests, "post", side_effect=requests.Timeout("slow")) as post, \
            mock.patch.object(llm.time, "sleep"):
        with pytest.raises(requests.Timeout):
            provider.chat_text("hi")
    assert post.call_count == 1 + llm.CHAT_RETRIES


def test_truncated_reasoning_is_not_returned_as_an_answer():
    """Measured live on ultra-550b (Oct 22): at max_tokens mid-thought,
    content == reasoning_content. That must read as no reply."""
    thinking = 'The user wants JSON... maybe {"verdict": "TRADE"} ... wait'
    payload = {"choices": [{"finish_reason": "length", "message": {
        "role": "assistant", "content": thinking, "reasoning_content": thinking}}]}
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(llm.requests, "post", return_value=_Resp(200, payload)):
        assert provider.chat_text("judge this") == ""


def test_model_dashes_are_normalized_to_hyphens():
    payload = {"choices": [{"message": {"role": "assistant",
               "content": "formed at 13:50 today\u2014roughly 12 minutes; 75\u201379%"}}]}
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(llm.requests, "post", return_value=_Resp(200, payload)):
        text = provider.chat_text("x")
    assert "\u2014" not in text and "\u2013" not in text
    assert text == "formed at 13:50 today - roughly 12 minutes; 75-79%"
