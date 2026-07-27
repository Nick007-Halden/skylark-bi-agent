"""
agent.py
--------
The ONLY module that talks to an LLM. It never sees raw or bulk row-level data —
only the compact metrics dictionaries produced by analytics.py, plus data-quality
notes from cleaner.py. This is the core architectural decision of this project:
Python computes, the LLM explains, decides what's relevant, asks clarifying
questions, and writes leadership-style prose.

Model: Claude (Anthropic API). Swap ANTHROPIC_MODEL env var if needed.
"""

import os
import json
import anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a Business Intelligence analyst agent for Skylark Drones, a drone-services
company. Founders and executives ask you natural-language questions about the sales pipeline
(Deals board) and project execution/billing (Work Orders board) in monday.com.

Rules you must follow:
1. You are given PRECOMPUTED, ALREADY-CORRECT metrics as JSON in the user context. Never invent
   numbers that are not present in that JSON. If something isn't in the provided metrics, say so
   plainly and, if useful, say what additional data or clarification would let you answer it.
2. Always mention material data-quality caveats provided to you (missing values excluded from a
   sum, an approximate cross-board join, unrecognized category values) when they affect the
   specific numbers you are citing — briefly, not as a wall of disclaimers.
3. If the founder's question is genuinely ambiguous (e.g. "this quarter" with no year, "pipeline"
   without specifying open vs all-time), make a reasonable assumption, state it in one line, and
   answer — only ask a clarifying question if you truly cannot proceed without it.
4. Write like an analyst briefing a founder: direct, numbers-first, then 1-3 sentences of
   interpretation or risk. No filler, no "I hope this helps."
5. For "prepare a leadership update" style requests, structure the answer with short sections
   (Sales / Operations / Billing / Risks / Recommendations) using the leadership_update metrics.
"""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=api_key)


def answer_query(user_message: str, metrics_context: dict, data_quality_notes: list[str],
                  conversation_history: list[dict] | None = None) -> str:
    """
    user_message: the founder's raw question
    metrics_context: dict of precomputed metrics relevant to this question
                      (caller decides which analytics.py functions to run based on keywords,
                      or passes the full leadership_update bundle for broad questions)
    data_quality_notes: list of strings from cleaner.get_quality_notes()
    conversation_history: prior turns for multi-turn clarification flows
    """
    context_block = {
        "metrics": metrics_context,
        "data_quality_notes": data_quality_notes,
    }

    messages = list(conversation_history or [])
    messages.append({
        "role": "user",
        "content": (
            f"Founder's question: {user_message}\n\n"
            f"Precomputed metrics and data-quality context (JSON):\n"
            f"{json.dumps(context_block, indent=2, default=str)}"
        ),
    })

    response = _client().messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")


def route_intent(user_message: str) -> str:
    """
    Lightweight keyword router deciding which analytics functions to run.
    Kept simple and inspectable on purpose (not an LLM call) — the 6-hour scope
    trades a fancier planner for something transparent and reliable. See Decision Log.
    Returns one of: 'pipeline', 'sector', 'operations', 'billing', 'risk', 'leadership', 'general'
    """
    q = user_message.lower()
    if any(k in q for k in ["leadership", "weekly update", "summary for", "brief the", "exec update"]):
        return "leadership"
    if any(k in q for k in ["risk", "at risk", "delayed but won", "stalled"]):
        return "risk"
    if any(k in q for k in ["bill", "invoice", "receivable", "collection", "collected", "revenue collected"]):
        return "billing"
    if any(k in q for k in ["operation", "execution", "delayed", "project status", "work order"]):
        return "operations"
    if any(k in q for k in ["sector", "energy", "mining", "railway", "renewable", "powerline", "construction", "tender"]):
        return "sector"
    if any(k in q for k in ["pipeline", "deal", "revenue", "closing", "quarter", "won", "lost"]):
        return "pipeline"
    return "general"
