"""
agent.py
--------
The ONLY module that talks to an LLM.

Architecture:
- analytics.py calculates numbers
- cleaner.py provides data quality notes
- this file only sends compact metrics to Claude
- Claude explains insights in founder-friendly language

Model:
Claude via Anthropic API
"""

import os
import json
import anthropic
import streamlit as st


MODEL = os.environ.get(
    "ANTHROPIC_MODEL",
    "claude-3-5-sonnet-20240620"
)


SYSTEM_PROMPT = """
You are a Business Intelligence analyst agent for Skylark Drones,
a drone-services company.

Founders and executives ask natural language questions about:
- Sales pipeline (Deals board)
- Project execution (Work Orders board)
- Billing and collections
- Operational risks

Important rules:

1. You receive PRECOMPUTED metrics from Python.
Never invent numbers.
Only use numbers present in the metrics JSON.

2. Mention important data quality issues briefly when relevant.
Examples:
- missing values
- incomplete records
- approximate joins
- inconsistent categories

Do not overwhelm the user with disclaimers.

3. If the question is ambiguous:
- make a reasonable assumption
- state the assumption briefly
- continue answering

Only ask a clarification question if you truly cannot answer.

4. Write like a founder briefing:
- Start with the key numbers
- Explain business meaning
- Highlight risks or opportunities

Avoid:
- filler
- generic AI language
- "I hope this helps"

5. For leadership updates, use:

Sales:
- pipeline status
- important deals

Operations:
- execution status
- delays

Billing:
- collections

Risks:
- concerns

Recommendations:
- actions for leadership
"""


def _get_secret(name: str):

    """
    Supports:
    - Streamlit Cloud secrets
    - Environment variables
    """

    value = os.environ.get(name)

    if value:
        return value

    try:
        return st.secrets[name]
    except Exception:
        return None



def _client() -> anthropic.Anthropic:

    api_key = _get_secret(
        "ANTHROPIC_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing. "
            "Add it in Streamlit Cloud secrets."
        )

    return anthropic.Anthropic(
        api_key=api_key
    )



def answer_query(
    user_message: str,
    metrics_context: dict,
    data_quality_notes: list[str],
    conversation_history: list[dict] | None = None
) -> str:


    context_block = {

        "metrics": metrics_context,

        "data_quality_notes":
            data_quality_notes

    }


    messages = list(
        conversation_history or []
    )


    messages.append(
        {
            "role": "user",
            "content": (
                f"Founder's question:\n"
                f"{user_message}\n\n"

                f"Precomputed business metrics:\n"
                f"{json.dumps(context_block, indent=2, default=str)}"
            )
        }
    )


    try:

        response = _client().messages.create(

            model=MODEL,

            max_tokens=1200,

            temperature=0,

            system=SYSTEM_PROMPT,

            messages=messages

        )


        return "".join(

            block.text

            for block in response.content

            if block.type == "text"

        )


    except anthropic.AuthenticationError:

        return (
            "Claude authentication failed. "
            "Please check that ANTHROPIC_API_KEY is correctly configured."
        )


    except anthropic.APIError as e:

        return (
            "Claude API error occurred while generating the answer.\n\n"
            f"Details: {e}"
        )


    except Exception as e:

        return (
            "Unexpected error while generating the AI response.\n\n"
            f"Details: {e}"
        )



def route_intent(
    user_message: str
) -> str:

    """
    Lightweight transparent intent router.

    Returns:
    pipeline
    sector
    operations
    billing
    risk
    leadership
    general
    """

    q = user_message.lower()


    if any(
        k in q
        for k in [
            "leadership",
            "weekly update",
            "summary",
            "exec update",
            "brief"
        ]
    ):
        return "leadership"


    if any(
        k in q
        for k in [
            "risk",
            "at risk",
            "stalled",
            "problem"
        ]
    ):
        return "risk"


    if any(
        k in q
        for k in [
            "bill",
            "invoice",
            "receivable",
            "collection",
            "collected"
        ]
    ):
        return "billing"


    if any(
        k in q
        for k in [
            "operation",
            "execution",
            "delay",
            "delayed",
            "project status",
            "work order"
        ]
    ):
        return "operations"


    if any(
        k in q
        for k in [
            "sector",
            "energy",
            "mining",
            "railway",
            "renewable",
            "powerline",
            "construction",
            "tender"
        ]
    ):
        return "sector"


    if any(
        k in q
        for k in [
            "pipeline",
            "deal",
            "revenue",
            "closing",
            "quarter",
            "won",
            "lost"
        ]
    ):
        return "pipeline"


    return "general"
