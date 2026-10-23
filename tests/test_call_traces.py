"""Unit tests for the run-scoped evidence traces (rules compliance).

The Official Rules score Sponsor Tech and the NVIDIA award from run
logs, so every model call and every Zetaris query must leave a trace
line the runner can drain into artifacts.json:

- src/integrations/llm.py: one entry per chat call,
  {"provider", "model", "latency_ms", "ok"}; the model is the one
  that actually served (the response's own model field when present,
  else the requested model).
- src/integrations/zetaris.py: one entry per run_sql call,
  {"table_or_view", "elapsed_ms", "rows"}.

HTTP (requests) is mocked throughout: no live calls.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest
import requests

from src.integrations import llm, zetaris
from src.integrations.llm import get_llm_provider

REPO_ROOT = Path(__file__).resolve().parent.parent


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture(autouse=True)
def _fresh_logs():
    llm.clear_call_log()
    zetaris.clear_trace_log()
    yield
    llm.clear_call_log()
    zetaris.clear_trace_log()


def _chat_payload(model=None, content="ready"):
    payload = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if model is not None:
        payload["model"] = model
    return payload


# -- model-call log -------------------------------------------------------


def test_chat_records_provider_model_latency_and_ok():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(
        llm.requests, "post",
        return_value=_Resp(200, _chat_payload("nvidia/nemotron-3-ultra-550b-a55b")),
    ):
        assert provider.chat_text("hi") == "ready"
    (entry,) = llm.get_call_log()
    assert entry["provider"] == "nvidia"
    assert entry["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert isinstance(entry["latency_ms"], int) and entry["latency_ms"] >= 0
    assert entry["ok"] is True


def test_meterless_log_shows_served_model_not_routing_mode():
    """The request asks for the meterless/auto routing mode; the
    response names the concrete model that served. The log is award
    evidence, so it must carry the served model."""
    provider = get_llm_provider(
        {"LLM_PROVIDER": "meterless", "METERLESS_RUNTIME_API_KEY": "tok"}
    )
    with mock.patch.object(
        llm.requests, "post",
        return_value=_Resp(200, _chat_payload("nvidia/nemotron-3-ultra-550b-a55b")),
    ):
        provider.chat_text("hi")
    (entry,) = llm.get_call_log()
    assert entry["provider"] == "meterless"
    assert entry["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert entry["ok"] is True


def test_log_falls_back_to_requested_model_when_response_omits_it():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(
        llm.requests, "post", return_value=_Resp(200, _chat_payload())
    ):
        provider.chat_text("hi")
    (entry,) = llm.get_call_log()
    assert entry["model"] == provider.config.model


def test_failed_chat_is_logged_ok_false_and_reraises():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(llm.requests, "post", return_value=_Resp(404, {})):
        with pytest.raises(requests.HTTPError):
            provider.chat_text("hi")
    (entry,) = llm.get_call_log()
    assert entry["provider"] == "nvidia"
    assert entry["ok"] is False


def test_every_chat_call_appends_one_entry():
    provider = get_llm_provider({"MODEL_API_KEY": "nv-key"})
    with mock.patch.object(
        llm.requests, "post",
        return_value=_Resp(200, _chat_payload("nvidia/nemotron-3-ultra-550b-a55b")),
    ):
        provider.chat_text("bull case")
        provider.chat_text("bear case")
        provider.chat([{"role": "user", "content": "judge"}])
    assert len(llm.get_call_log()) == 3


# -- zetaris trace ----------------------------------------------------------


def test_run_sql_records_trace_line():
    provider = zetaris.ZetarisProvider(api_key="k")
    payload = {"data": [[1, 2], [3, 4], [5, 6]]}
    with mock.patch.object(
        zetaris.requests, "post", return_value=_Resp(200, payload)
    ):
        rows = provider.run_sql(
            "SELECT ts, close FROM yahoo_finance.spy_bars_1d ORDER BY ts",
            limit=10,
        )
    assert rows == [[1, 2], [3, 4], [5, 6]]
    (entry,) = zetaris.get_trace_log()
    assert entry["table_or_view"] == "yahoo_finance.spy_bars_1d"
    assert entry["rows"] == 3
    assert isinstance(entry["elapsed_ms"], int) and entry["elapsed_ms"] >= 0


def test_get_quote_traces_the_quote_view():
    provider = zetaris.ZetarisProvider(api_key="k")
    payload = {
        "data": [
            [700.0, 701.0, 699.0, 1729600000, 699.5, 701.0, 699.0, 700.5, 10000],
            [705.0, 706.0, 700.0, 1729700000, 701.0, 706.0, 700.0, 702.0, 12345],
        ]
    }
    with mock.patch.object(
        zetaris.requests, "post", return_value=_Resp(200, payload)
    ):
        quote = provider.get_quote("SPY")
    assert quote["price"] == 705.0
    assert quote["previous_close"] == 700.5
    targets = [e["table_or_view"] for e in zetaris.get_trace_log()]
    assert targets == ["yahoo_finance.spy_quote"]


def test_failed_sql_still_leaves_a_trace_line():
    provider = zetaris.ZetarisProvider(api_key="k")
    with mock.patch.object(
        zetaris.requests, "post", return_value=_Resp(500, {})
    ):
        with pytest.raises(requests.HTTPError):
            provider.run_sql("SELECT 1 AS one", limit=1)
    (entry,) = zetaris.get_trace_log()
    assert entry["table_or_view"] == "ping"
    assert entry["rows"] == 0


# -- runner drains both logs into artifacts.json ----------------------------


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_morning", REPO_ROOT / "scripts" / "run_morning.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_artifacts_carry_empty_trace_keys(tmp_path):
    runner = _load_runner()
    out_dir = tmp_path / "run"
    assert runner.main(["--sample-mode", "--output-dir", str(out_dir)]) == 0
    artifacts = json.loads((out_dir / "artifacts.json").read_text())
    assert artifacts["model_calls"] == []
    assert artifacts["data_calls"] == []
