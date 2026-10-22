"""QuantPilot smoke test - run on the Mac where Zetaris lives.

Checks all three layers from the hackathon setup guide:
  1. Data:  Zetaris web interface is up
  2. Data:  Zetaris answers SQL over its REST API (SELECT 1)
  3. Power: Nemotron replies through the configured route

Setup on the Mac:
  1. python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  2. cp .env.example .env   (then fill in the values)
  3. .venv/bin/python smoke_test.py

Pass = all three lines say PASS.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # env vars can also come straight from the shell

import requests  # noqa: E402

from src.integrations.zetaris import ZetarisProvider  # noqa: E402

results = []


def check(name, fn):
    try:
        fn()
        results.append(("PASS", name, ""))
    except Exception as error:  # noqa: BLE001
        results.append(("FAIL", name, str(error)[:150]))


def zetaris_web():
    base = os.environ.get("ZETARIS_BASE_URL", "http://localhost:3000")
    requests.get(base, timeout=10).raise_for_status()


def zetaris_sql():
    provider = ZetarisProvider.from_env()
    assert provider.api_key, "Zetaris API key missing (env or key file)"
    assert provider.ping(), "SELECT 1 did not return 1"


def nemotron():
    base_url = os.environ.get("MODEL_BASE_URL", "")
    api_key = os.environ.get("MODEL_API_KEY", "")
    model = os.environ.get("NEMOTRON_MODEL", "")
    assert base_url and api_key and model, (
        "MODEL_BASE_URL / MODEL_API_KEY / NEMOTRON_MODEL missing from .env"
    )
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)
    reply = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        max_tokens=512,
    )
    assert reply.choices, "no reply from the model"


check("Data: Zetaris web interface", zetaris_web)
check("Data: Zetaris runs SQL over its REST API", zetaris_sql)
check("Power: Nemotron replies", nemotron)

for status, name, detail in results:
    print(f"{status}  {name}  {detail}")
