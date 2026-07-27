"""
agent.py
--------
The ONLY module that talks to an LLM.

Architecture:
- Python computes business metrics (analytics.py)
- This module sends only structured metrics to Gemini
- Gemini explains insights in founder/executive language

Model: Google Gemini API
"""

import os
import json
import google.generativeai as genai


MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-1.5-flash"
)


SYSTEM_PROMPT = """
You are a Business Intelligence analyst agent for Skylark Drones, a drone-services
company.

Founders and executives ask you natural-language questions about:
- Sales pipeline (Deals board)
- Project execution (Work Orders board)
- Revenue and billing
- Sector performance
- Business risks

Your job is to turn structured analytics into executive-level insights.

Rules:

1. You are given PRECOMPUTED metrics as JSON.
Never invent numbers.
Only use numbers available in the provided metrics.

2. Mention important data-quality caveats when relevant:
- missing values
- incomplete records
- inconsistent categories
- approximate joins

Keep caveats brief.

3. If the question is ambiguous:
- make a reasonable assumption
- state the assumption briefly
- continue with the answer

Only ask a question if you cannot answer meaningfully.

4. Write like a founder briefing:
- Start with the key numbers
- Then explain business implications
- Highlight risks and opportunities

Avoid:
- generic statements
- unnecessary disclaimers
- saying "as an AI"

5. For leadership update requests, structure the answer as:

## Sales
## Operations
## Billing
## Risks
## Recommendations

Keep responses concise and executive-friendly.
"""


def _client():
    """
    Creates Gemini client.
    """

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set."
        )

    genai.configure(api_key=api_key)

    return genai.GenerativeModel(
        MODEL
    )


def answer_query(
    user_message: str,
    metrics_context: dict,
    data_quality_notes: list[str],
    conversation_history: list[dict] | None = None
) -> str:
    """
    Sends founder question + computed metrics to Gemini.

    Gemini does NOT receive raw monday.com rows.
    """

    context_block = {
        "metrics": metrics_context,
        "data_quality_notes": data_quality_notes
    }


    history_text = ""

    if conversation_history:
        history_text = "\nPrevious conversation:\n"

        for message in conversation_history:
            history_text += (
                f"{message['role']}: "
                f"{message['content']}\n"
            )


    prompt = f"""
{SYSTEM_PROMPT}


{history_text}


Founder's question:

{user_message}


Precomputed business metrics:

{json.dumps(
    context_block,
    indent=2,
    default=str
)}

Now provide the executive-level answer.
"""


    try:

        response = _client().generate_content(
            prompt
        )

        return response.text


    except Exception as e:

        return (
            "Gemini API error occurred while generating the answer.\n\n"
            f"Details: {str(e)}"
        )


def route_intent(user_message: str) -> str:
    """
    Lightweight keyword router.

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
            "summary for",
            "brief the",
            "exec update"
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
            "collected",
            "revenue collected"
        ]
    ):
        return "billing"


    if any(
        k in q
        for k in [
            "operation",
            "execution",
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
