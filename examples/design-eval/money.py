"""What a stopped session cost: it reports no total, so its stream's token counts are priced at list price.

Rates are USD per million tokens, from ../supermarket-route/BENCHMARK.md (Claude API reference, 2026-11-03).
The stream needs --include-partial-messages, or output tokens are only the first of each reply.
"""
import json
from pathlib import Path

# input, output, cache read, 5-minute cache write, 1-hour cache write
RATES = {"claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125, 0.20),
         "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50, 4.00)}
LONG = {"claude-haiku-5-5": (100_000, (0.50, 2.50, 0.05, 0.625, 1.00))}  # prompts above 100K tokens


def events(log):
    for line in Path(log).read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def message_cost(model, usage):
    if model not in RATES:
        return None
    n = lambda d, k: d.get(k) or 0  # noqa: E731
    hour = n(usage.get("cache_creation") or {}, "ephemeral_1h_input_tokens")
    read, written = n(usage, "cache_read_input_tokens"), n(usage, "cache_creation_input_tokens")
    rates = RATES[model]
    if model in LONG and n(usage, "input_tokens") + read + written > LONG[model][0]:
        rates = LONG[model][1]
    counts = (n(usage, "input_tokens"), n(usage, "output_tokens"), read, written - hour, hour)
    return sum(c * r for c, r in zip(counts, rates)) / 1_000_000


def log_cost(log):
    """USD of every reply in a stream-json log, or None when it shows no usage or a model with no rate."""
    messages, current = {}, {}  # id -> [model, usage]; parent tool id -> id of the reply being streamed
    for event in events(log):
        parent = event.get("parent_tool_use_id")
        agent = event.get("tool_use_result")  # a subagent's replies are not streamed; its usage comes here
        if isinstance(agent, dict) and isinstance(agent.get("usage"), dict):
            messages[f"agent {len(messages)}"] = [agent.get("resolvedModel"), agent["usage"]]
        if event.get("type") == "assistant":
            m = event.get("message") or {}
            if m.get("id") and isinstance(m.get("usage"), dict):
                messages.setdefault(m["id"], [m.get("model"), dict(m["usage"])])
        elif event.get("type") == "stream_event":
            inner = event.get("event") or {}
            if inner.get("type") == "message_start":
                m = inner.get("message") or {}
                if m.get("id") and isinstance(m.get("usage"), dict):
                    current[parent] = m["id"]
                    messages.setdefault(m["id"], [m.get("model"), dict(m["usage"])])
            elif inner.get("type") == "message_delta" and current.get(parent) in messages:
                usage = messages[current[parent]][1]
                usage["output_tokens"] = (inner.get("usage") or {}).get("output_tokens", usage.get("output_tokens"))
    costs = [message_cost(model, usage) for model, usage in messages.values() if model != "<synthetic>"]
    return None if not costs or None in costs else sum(costs)
