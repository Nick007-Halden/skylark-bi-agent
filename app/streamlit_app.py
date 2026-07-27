"""
streamlit_app.py
-----------------
Entry point:
streamlit run app/streamlit_app.py

Flow:
User question
    -> route intent
    -> fetch cached monday.com data
    -> clean and normalize
    -> calculate metrics
    -> send metrics + question to Claude
    -> display answer
"""

import os
import streamlit as st

import monday_client
import cleaner
import analytics
import agent


# -----------------------------
# Page Configuration
# -----------------------------

st.set_page_config(
    page_title="Skylark Drones — BI Agent",
    page_icon="🛰️",
    layout="centered"
)


# -----------------------------
# Secrets Handling
# -----------------------------

def get_secret(name):
    """
    Works on both:
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


missing = []

if not get_secret("MONDAY_API_TOKEN"):
    missing.append("MONDAY_API_TOKEN")

if not get_secret("ANTHROPIC_API_KEY"):
    missing.append("ANTHROPIC_API_KEY")


if missing:
    st.error(
        f"Missing configuration: {', '.join(missing)}\n\n"
        "Add these values in Streamlit Cloud → Manage App → Settings → Secrets."
    )
    st.stop()


# -----------------------------
# Header
# -----------------------------

st.title("🛰️ Skylark Drones — Business Intelligence Agent")

st.caption(
    "Ask about pipeline, sectors, projects, billing, operational risks, "
    "or generate leadership updates."
)


# -----------------------------
# Sidebar Configuration
# -----------------------------

with st.sidebar:

    st.subheader("Configuration")

    deals_board_id = st.text_input(
        "Deals Board ID",
        value=os.environ.get("DEALS_BOARD_ID", "")
    )

    work_orders_board_id = st.text_input(
        "Work Orders Board ID",
        value=os.environ.get("WORK_ORDERS_BOARD_ID", "")
    )


    refresh = st.button(
        "🔄 Refresh monday.com data"
    )


    st.divider()

    st.caption(
        "Board IDs are the numbers in your monday.com board URL."
    )


if not deals_board_id or not work_orders_board_id:

    st.warning(
        "Enter both monday.com board IDs in the sidebar."
    )

    st.stop()



# -----------------------------
# Cached Data Loader
# -----------------------------

@st.cache_data(
    ttl=900,
    show_spinner="Loading monday.com data..."
)
def load_data(
    deals_id,
    work_orders_id,
    refresh_key
):

    cleaner.reset_quality_notes()

    deals_raw = monday_client.get_board_items(
        deals_id
    )

    work_orders_raw = monday_client.get_board_items(
        work_orders_id
    )


    deals_df = cleaner.clean_deals(
        deals_raw
    )

    work_orders_df = cleaner.clean_work_orders(
        work_orders_raw
    )


    notes = cleaner.get_quality_notes()


    return (
        deals_df,
        work_orders_df,
        notes
    )



# -----------------------------
# Refresh Handling
# -----------------------------

if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0


if refresh:

    st.session_state.refresh_key += 1

    st.success(
        "Refreshing monday.com data..."
    )



# -----------------------------
# Load Data
# -----------------------------

try:

    deals_df, work_orders_df, quality_notes = load_data(
        deals_board_id,
        work_orders_board_id,
        st.session_state.refresh_key
    )


except monday_client.MondayAPIError as e:

    st.error(
        "Unable to retrieve monday.com data.\n\n"
        "Check your API token and board IDs.\n\n"
        f"Details: {e}"
    )

    st.stop()


except Exception as e:

    st.error(
        "Unexpected error while loading data.\n\n"
        f"Details: {e}"
    )

    st.stop()



# -----------------------------
# Sidebar Metrics
# -----------------------------

st.sidebar.metric(
    "Deals Loaded",
    len(deals_df)
)

st.sidebar.metric(
    "Work Orders Loaded",
    len(work_orders_df)
)



if quality_notes:

    with st.sidebar.expander(
        f"⚠️ Data Quality Notes ({len(quality_notes)})"
    ):

        for note in quality_notes:
            st.write(
                f"- {note}"
            )



# -----------------------------
# Intent + Metrics
# -----------------------------

KNOWN_SECTORS = sorted(
    set(
        list(deals_df["sector"].dropna().unique())
        +
        list(work_orders_df["sector"].dropna().unique())
    )
)



def build_metrics_for_query(question):

    intent = agent.route_intent(
        question
    )


    if intent == "leadership":

        return analytics.leadership_update(
            deals_df,
            work_orders_df
        )


    if intent == "risk":

        return {
            "cross_board_risk":
                analytics.cross_board_risk_view(
                    deals_df,
                    work_orders_df
                )
        }


    if intent == "billing":

        return {
            "billing":
                analytics.billing_summary(
                    work_orders_df
                )
        }


    if intent == "operations":

        return {
            "operations":
                analytics.operations_summary(
                    work_orders_df
                )
        }


    if intent == "sector":

        matched = next(
            (
                s for s in KNOWN_SECTORS
                if s.lower() in question.lower()
            ),
            None
        )


        if matched:

            return {
                "sector_detail":
                    analytics.sector_pipeline(
                        deals_df,
                        matched
                    )
            }


        return {

            "pipeline":
                analytics.pipeline_summary(
                    deals_df
                ),

            "available_sectors":
                KNOWN_SECTORS,

            "note":
                "Ask user to select a sector."
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
                work_orders_df
            ),

        "available_sectors":
            KNOWN_SECTORS
    }




# -----------------------------
# Chat Interface
# -----------------------------

if "messages" not in st.session_state:

    st.session_state.messages = []



for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )



prompt = st.chat_input(
    "Example: How is our pipeline looking for Energy this quarter?"
)



if prompt:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )


    with st.chat_message("user"):

        st.markdown(prompt)



    with st.chat_message("assistant"):

        with st.spinner(
            "Analyzing business data..."
        ):


            metrics = build_metrics_for_query(
                prompt
            )


            # Only send recent history
            history = [
                {
                    "role": m["role"],
                    "content": m["content"]
                }

                for m in st.session_state.messages[-6:-1]
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


    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )
