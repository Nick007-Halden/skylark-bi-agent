"""
streamlit_app.py
-----------------
Entry point. Run with: streamlit run app/streamlit_app.py
Deploy for free on Streamlit Community Cloud pointing at this file.

Flow per user message:
  user question -> route_intent() -> pull live data from monday.com -> clean it
  -> compute relevant metrics -> send question + metrics (not raw rows) to Claude
  -> render answer
"""

import os
import streamlit as st

import monday_client
import cleaner
import analytics
import agent

st.set_page_config(page_title="Skylark Drones — BI Agent", page_icon="🛰️", layout="centered")
st.title("🛰️ Skylark Drones — Business Intelligence Agent")
st.caption("Ask about pipeline, sectors, project execution, billing, or ask for a leadership update.")

with st.sidebar:
    st.subheader("Configuration")
    deals_board_id = st.text_input("Deals board ID", value=os.environ.get("DEALS_BOARD_ID", ""))
    wo_board_id = st.text_input("Work Orders board ID", value=os.environ.get("WORK_ORDERS_BOARD_ID", ""))
    refresh = st.button("🔄 Refresh live data from monday.com")
    st.markdown("---")
    st.caption(
        "Board IDs: open the board in monday.com — the number in the URL "
        "(monday.com/boards/**1234567890**) is the board ID."
    )

missing_secrets = []
if not os.environ.get("MONDAY_API_TOKEN"):
    missing_secrets.append("MONDAY_API_TOKEN")
if not os.environ.get("ANTHROPIC_API_KEY"):
    missing_secrets.append("ANTHROPIC_API_KEY")
if missing_secrets:
    st.error(f"Missing required configuration: {', '.join(missing_secrets)}. "
             f"Set these as environment variables or in Streamlit secrets (see README).")
    st.stop()

if not deals_board_id or not wo_board_id:
    st.warning("Enter both board IDs in the sidebar to begin.")
    st.stop()


@st.cache_data(ttl=60, show_spinner="Pulling live data from monday.com...")
def load_data(deals_id: str, wo_id: str, _refresh_token: int):
    cleaner.reset_quality_notes()
    deals_raw = monday_client.get_board_items(deals_id)
    wo_raw = monday_client.get_board_items(wo_id)
    deals_df = cleaner.clean_deals(deals_raw)
    wo_df = cleaner.clean_work_orders(wo_raw)
    notes = cleaner.get_quality_notes()
    return deals_df, wo_df, notes


if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = 0
if refresh:
    st.session_state.refresh_token += 1
    st.cache_data.clear()

deals_df, wo_df, quality_notes = load_data(deals_board_id, wo_board_id, st.session_state.refresh_token)

st.sidebar.metric("Deals loaded", len(deals_df))
st.sidebar.metric("Work orders loaded", len(wo_df))
if quality_notes:
    with st.sidebar.expander(f"⚠️ {len(quality_notes)} data quality notes"):
        for n in quality_notes:
            st.write(f"- {n}")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

KNOWN_SECTORS = sorted(set(
    list(deals_df["sector"].dropna().unique()) + list(wo_df["sector"].dropna().unique())
))


def build_metrics_for_query(user_message: str) -> dict:
    intent = agent.route_intent(user_message)

    if intent == "leadership":
        return analytics.leadership_update(deals_df, wo_df)
    if intent == "risk":
        return {"cross_board_risk": analytics.cross_board_risk_view(deals_df, wo_df)}
    if intent == "billing":
        return {"billing": analytics.billing_summary(wo_df)}
    if intent == "operations":
        return {"operations": analytics.operations_summary(wo_df)}
    if intent == "sector":
        matched = next((s for s in KNOWN_SECTORS if s.lower() in user_message.lower()), None)
        if matched:
            return {"sector_detail": analytics.sector_pipeline(deals_df, matched)}
        return {
            "pipeline": analytics.pipeline_summary(deals_df),
            "available_sectors": KNOWN_SECTORS,
            "note_to_agent": "User mentioned a sector but it didn't match a known value — "
                              "ask them to pick from available_sectors, or infer the closest match.",
        }
    if intent == "pipeline":
        return {"pipeline": analytics.pipeline_summary(deals_df)}

    # general / unclear -> give the LLM the broad picture so it can decide, or ask a clarifying question
    return {
        "pipeline": analytics.pipeline_summary(deals_df),
        "operations": analytics.operations_summary(wo_df),
        "available_sectors": KNOWN_SECTORS,
    }


if prompt := st.chat_input("e.g. How's our pipeline looking for Mining this quarter?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            metrics = build_metrics_for_query(prompt)
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            answer = agent.answer_query(prompt, metrics, quality_notes, conversation_history=history)
            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
