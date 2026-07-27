"""
streamlit_app.py
-----------------
Entry point.

Flow:
user question
    -> route_intent()
    -> pull live data from monday.com
    -> clean data
    -> compute business metrics
    -> send metrics + question to Gemini
    -> render executive answer

The LLM never receives raw monday.com rows.
Python computes metrics; Gemini explains insights.
"""

import os
import streamlit as st

import monday_client
import cleaner
import analytics
import agent


QUICK_QUESTIONS = [
    "How's our pipeline looking overall?",
    "Prepare my weekly leadership update",
    "Which projects are delayed?",
    "What's our billing and collections status?",
    "Are there any at-risk deals we should worry about?",
]


st.set_page_config(
    page_title="Skylark Drones — BI Agent",
    page_icon="🛰️",
    layout="centered"
)


st.title("🛰️ Skylark Drones — Business Intelligence Agent")

st.caption(
    "Ask about pipeline, sectors, project execution, billing, "
    "or request a leadership update."
)


# -----------------------------
# Sidebar configuration
# -----------------------------

with st.sidebar:

    st.subheader("Configuration")

    deals_board_id = st.text_input(
        "Deals board ID",
        value=os.environ.get("DEALS_BOARD_ID", "")
    )

    wo_board_id = st.text_input(
        "Work Orders board ID",
        value=os.environ.get("WORK_ORDERS_BOARD_ID", "")
    )

    refresh = st.button(
        "🔄 Refresh live data from monday.com"
    )

    st.markdown("---")

    st.caption(
        "Board IDs are available from the monday.com board URL."
    )


# -----------------------------
# Secret validation
# -----------------------------

missing_secrets = []

if not os.environ.get("MONDAY_API_TOKEN"):
    missing_secrets.append("MONDAY_API_TOKEN")

if not os.environ.get("GEMINI_API_KEY"):
    missing_secrets.append("GEMINI_API_KEY")


if missing_secrets:

    st.error(
        f"Missing required configuration: "
        f"{', '.join(missing_secrets)}. "
        "Add them in Streamlit Cloud → Settings → Secrets."
    )

    st.stop()



if not deals_board_id or not wo_board_id:

    st.warning(
        "Enter both monday.com board IDs in the sidebar to begin."
    )

    st.stop()



# -----------------------------
# Load monday.com data
# -----------------------------

@st.cache_data(
    ttl=300,
    show_spinner="Pulling live data from monday.com..."
)
def load_data(
    deals_id: str,
    wo_id: str,
    refresh_token: int
):

    cleaner.reset_quality_notes()

    deals_raw = monday_client.get_board_items(
        deals_id
    )

    wo_raw = monday_client.get_board_items(
        wo_id
    )


    deals_df = cleaner.clean_deals(
        deals_raw
    )

    wo_df = cleaner.clean_work_orders(
        wo_raw
    )


    notes = cleaner.get_quality_notes()


    return (
        deals_df,
        wo_df,
        notes
    )



if "refresh_token" not in st.session_state:

    st.session_state.refresh_token = 0



if refresh:

    st.session_state.refresh_token += 1

    st.cache_data.clear()



try:

    deals_df, wo_df, quality_notes = load_data(
        deals_board_id,
        wo_board_id,
        st.session_state.refresh_token
    )


except monday_client.MondayAPIError as e:

    st.error(
        "Unable to retrieve data from monday.com.\n\n"
        "Check your API token, board IDs, or monday.com availability.\n\n"
        f"Details: {e}"
    )

    st.stop()



except Exception as e:

    st.error(
        "Unexpected error while loading monday.com data.\n\n"
        f"Details: {e}"
    )

    st.stop()



# -----------------------------
# Sidebar metrics
# -----------------------------

st.sidebar.metric(
    "Deals loaded",
    len(deals_df)
)

st.sidebar.metric(
    "Work orders loaded",
    len(wo_df)
)



if quality_notes:

    with st.sidebar.expander(
        f"⚠️ {len(quality_notes)} data quality notes"
    ):

        for note in quality_notes:

            st.write(
                f"- {note}"
            )



# -----------------------------
# Chat state
# -----------------------------

if "messages" not in st.session_state:

    st.session_state.messages = []



for msg in st.session_state.messages:

    with st.chat_message(
        msg["role"]
    ):

        st.markdown(
            msg["content"]
        )



# -----------------------------
# Sector detection
# -----------------------------

KNOWN_SECTORS = sorted(
    set(
        list(
            deals_df["sector"]
            .dropna()
            .unique()
        )
        +
        list(
            wo_df["sector"]
            .dropna()
            .unique()
        )
    )
)



# -----------------------------
# Analytics routing
# -----------------------------

def build_metrics_for_query(
    user_message: str
):

    intent = agent.route_intent(
        user_message
    )


    if intent == "leadership":

        return analytics.leadership_update(
            deals_df,
            wo_df
        )


    if intent == "risk":

        return {
            "cross_board_risk":
                analytics.cross_board_risk_view(
                    deals_df,
                    wo_df
                )
        }


    if intent == "billing":

        return {
            "billing":
                analytics.billing_summary(
                    wo_df
                )
        }


    if intent == "operations":

        return {
            "operations":
                analytics.operations_summary(
                    wo_df
                )
        }


    if intent == "sector":

        matched_sector = next(
            (
                s for s in KNOWN_SECTORS
                if s.lower()
                in user_message.lower()
            ),
            None
        )


        if matched_sector:

            return {
                "sector_detail":
                    analytics.sector_pipeline(
                        deals_df,
                        matched_sector
                    )
            }


        return {

            "pipeline":
                analytics.pipeline_summary(
                    deals_df
                ),

            "available_sectors":
                KNOWN_SECTORS,

            "note_to_agent":
                "User mentioned a sector but it did not match "
                "known sectors. Ask for clarification."
        }



    if intent == "pipeline":

        return {

            "pipeline":
                analytics.pipeline_summary(
                    deals_df
                )
        }



    return {

        "pipeline":
            analytics.pipeline_summary(
                deals_df
            ),

        "operations":
            analytics.operations_summary(
                wo_df
            ),

        "available_sectors":
            KNOWN_SECTORS
    }



# -----------------------------
# Quick questions
# -----------------------------

if not st.session_state.messages:

    st.caption(
        "Quick questions:"
    )


    cols = st.columns(
        len(QUICK_QUESTIONS)
    )


    for col, question in zip(
        cols,
        QUICK_QUESTIONS
    ):

        if col.button(
            question,
            use_container_width=True
        ):

            st.session_state.pending_prompt = question



# -----------------------------
# Chat input
# -----------------------------

prompt = st.chat_input(
    "Example: How's our pipeline looking for Energy this quarter?"
)



if (
    not prompt
    and st.session_state.get("pending_prompt")
):

    prompt = st.session_state.pop(
        "pending_prompt"
    )



if prompt:


    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )


    with st.chat_message(
        "user"
    ):

        st.markdown(
            prompt
        )


    with st.chat_message(
        "assistant"
    ):


        with st.spinner(
            "Analyzing business data..."
        ):


            try:

                metrics = build_metrics_for_query(
                    prompt
                )


                history = [
                    {
                        "role": m["role"],
                        "content": m["content"]
                    }

                    for m in st.session_state.messages[:-1]
                ]


                answer = agent.answer_query(
                    prompt,
                    metrics,
                    quality_notes,
                    conversation_history=history
                )


                st.markdown(
                    answer
                )


            except Exception as e:

                answer = (
                    "Unexpected error while generating "
                    "the AI response.\n\n"
                    f"Details: {e}"
                )


                st.error(
                    answer
                )


    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )
