"""Meterless agent-runtime integration.

Real details from the official Participant Setup Guide
(saved at docs/hackathon-setup-guide.txt).

Power rule: the product MUST run on Meterless Nightshift as the primary
AI provider (the "AI hotspot"). The app calls models through Meterless
using the Nightshift applications URL + API key. Free Nvidia cloud models
can run inside Nightshift with a build.nvidia.com key.

Build rule: must use Cursor (with Grok/Composer on Cursor credit) plus
1 or more Meterless Engines (Markovian Thinking, H-Mem, World State).

.env settings for the Power layer:
  MODEL_BASE_URL  = Meterless Nightshift applications URL (or NVIDIA's)
  MODEL_API_KEY   = Meterless API key (or NVIDIA key)
  NEMOTRON_MODEL  = exact Nemotron model ID from the route's model list

Keep the Meterless/NVIDIA key OUT of Cursor's settings - Cursor credit
pays for coding, the provider key is only used when the product runs.

UPDATE (Oct 22, organizer ruling): Sam Cummings (Meterless team) ruled
that the Power rule is satisfied by implementing Meterless Runtime as an
OpenAI-compatible provider in the app (meterless.ai/engines.html,
Runtime 1.4), and that NVIDIA-direct calls for dev/testing are fine.
That provider connection now lives in src/integrations/llm.py
(resolve_provider / LLMProvider): env-selected Meterless Runtime route
with NVIDIA direct as the fallback. This module remains the agent
runtime layer (skills + orchestration) only.

What Meterless gives QuantPilot:
  - The agent/swarm runtime: QuantPilot's tools (get_quote, get_intraday_bars,
    get_option_chain, compute_indicators, detect_order_blocks, score_liquidity,
    market_xray, check_events, build_trade_card, generate_briefing) register
    as Meterless skills, and Nemotron drives the orchestration loop.

Wiring checklist:
  1. Install Meterless Nightshift; get the applications URL + API key.
  2. Pick the Nemotron model ID in Meterless model settings (or use the
     vaulted NVIDIA key: nvidia/nemotron-3-super-120b-a12b via
     https://integrate.api.nvidia.com).
  3. Store keys in the vault (same flow as custom.nvidia); put the three
     MODEL_ settings in .env (all from the SAME route).
  4. Implement MeterlessRuntime below: register_agent() to create the
     QuantPilot agent, register_tool() to expose each src/tools function as
     a skill, and run() to execute the pre-market loop.

Until then, the tools in src/tools/ are plain Python functions with a
uniform signature (dict in, dict out) so registering them later is mechanical.

Note: the guide leaves the Meterless base URL / Nightshift setup link as
"[Organisers: add ...]" placeholders - confirm the exact URL from the
resent sponsor email or HackOS before wiring.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


class MeterlessRuntime:
    """Thin wrapper around the Meterless agent runtime.

    Raises NotImplementedError until the sponsor guide is wired on Oct 22.
    """

    def __init__(self, api_key: str = "", workspace: str = "") -> None:
        self.api_key = api_key
        self.workspace = workspace
        self._tools: Dict[str, Callable] = {}

    def _unwired(self) -> NotImplementedError:
        return NotImplementedError(
            "MeterlessRuntime is a stub until the Oct 22 sponsor wiring. "
            "See the module docstring for the checklist."
        )

    def register_tool(self, name: str, fn: Callable) -> None:
        """Register a QuantPilot tool (dict in, dict out) as a Meterless skill."""
        self._tools[name] = fn

    def register_agent(self, name: str, system_prompt: str) -> None:
        """Create the agent on Meterless with its system prompt."""
        raise self._unwired()

    def run(self, task: str) -> Dict[str, Any]:
        """Run the agent loop on a task (e.g. the pre-market briefing)."""
        raise self._unwired()
