"""
agent.py
--------
Gemini-powered Business Intelligence Agent.

Architecture:
- Python analytics.py calculates metrics.
- This file sends only summarized metrics to Gemini.
- Gemini explains insights in founder-friendly language.
"""

import os
import json
import google.generativeai as genai


MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
)


SYSTEM_PROMPT = """
You are a Business Intelligence analyst for Skylark Drones.

You answer founder and executive questions using data from:
1. monday.com Deals board
2. monday.com Work Orders board

Rules:

1. You only use numbers provided in the metrics JSON.
Do not invent values.

2. If data quality issues exist, mention them briefly.

3. Answer like a founder briefing:
- Start with important numbers
- Explain business meaning
- Highlight risks
- Suggest actions

4. If the question is unclear:
make a reasonable assumption and state it.

5. For leadership updates use:

Sales:
Operations:
Billing:
Risks:
Recommendations:

Keep responses concise and executive-friendly.
"""


def _client():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    genai.configure(api_key=api_key)

    return genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=SYSTEM_PROMPT
    )


def answer_query(
    user_message: str,
    metrics_context: dict,
    data_quality_notes: list[str],
    conversation_history=None
):

    context = {
        "metrics": metrics_context,
        "data_quality_notes": data_quality_notes
    }


    prompt = f"""
Founder question:

{user_message}


Business metrics:

{json.dumps(context, indent=2, default=str)}


Provide the executive analysis.
"""


    try:
        model = _client()

        response = model.generate_content(
            prompt
        )

        return response.text


    except Exception as e:

        raise RuntimeError(
            f"Gemini API error occurred while generating the answer.\n\nDetails: {e}"
        )


def route_intent(user_message: str):

    q = user_message.lower()


    if any(k in q for k in [
        "leadership",
        "weekly update",
        "exec update",
        "summary"
    ]):
        return "leadership"


    if any(k in q for k in [
        "risk",
        "at risk",
        "stalled"
    ]):
        return "risk"


    if any(k in q for k in [
        "bill",
        "invoice",
        "collection",
        "revenue collected"
    ]):
        return "billing"


    if any(k in q for k in [
        "operation",
        "execution",
        "project status",
        "work order",
        "delay"
    ]):
        return "operations"


    if any(k in q for k in [
        "sector",
        "energy",
        "mining",
        "railway",
        "renewable",
        "construction"
    ]):
        return "sector"


    if any(k in q for k in [
        "pipeline",
        "deal",
        "closing",
        "quarter",
        "won",
        "lost"
    ]):
        return "pipeline"


    return "general"
