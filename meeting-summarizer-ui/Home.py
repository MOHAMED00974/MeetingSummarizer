import streamlit as st

from utils.api_client import APIError, list_meetings
from utils.ui_helpers import init_session_state, sidebar_config, show_api_error

st.set_page_config(
    page_title="Meeting Summarizer",
    page_icon="🗒️",
    layout="wide",
)

init_session_state()
sidebar_config()

st.title("🗒️ Meeting Summarizer")
st.markdown(
    "Upload a recording, run it through your pipeline, and browse transcripts, "
    "summaries, decisions, and action items — all backed by your FastAPI service."
)

st.divider()

# Quick health check + at-a-glance count, so the home page isn't just a
# static wall of text. If the backend isn't running yet, this fails
# gracefully rather than crashing the app.
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Backend status")
    try:
        meetings = list_meetings()
        count = len(meetings) if isinstance(meetings, list) else "?"
        st.success(f"Connected — {count} meeting(s) found")
    except APIError as e:
        st.warning("Backend not reachable yet")
        with st.expander("Details"):
            show_api_error(e)

with col2:
    st.subheader("Where to go")
    st.markdown(
        """
- **📤 Upload & Process** — send an audio/video file to `/meetings/upload`, then kick off `/meetings/process`
- **📋 Dashboard** — browse all meetings (`GET /meetings`) and drill into one
- **🔍 Search** — query across meetings via `POST /search`
        """
    )

st.divider()
st.caption(
    "Use the sidebar to point this app at your FastAPI server, then use the "
    "page navigation above the sidebar to move between screens."
)
