import streamlit as st

from utils.api_client import APIError, search
from utils.ui_helpers import init_session_state, show_api_error, sidebar_config

st.set_page_config(page_title="Search", page_icon="🔍", layout="wide")
init_session_state()
sidebar_config()

st.title("🔍 Search Meetings")
st.markdown(
    "Sends a query to `POST /search`. The current payload shape is "
    "`{\"query\": \"...\"}` — see `search()` in `utils/api_client.py` if your "
    "backend expects extra filters (date range, meeting ID scope, etc.) and "
    "wire them into the form below."
)

st.divider()

with st.form("search_form"):
    query = st.text_input(
        "Search query",
        placeholder="e.g. budget approval, Q3 roadmap, who owns the deploy task",
    )
    # Placeholder for future filters — uncomment/extend once your backend
    # supports them. Left visible-but-disabled so it's obvious this is a
    # deliberate stub, not a bug.
    with st.expander("Advanced filters (optional — wire up once your API supports them)"):
        st.caption(
            "These aren't sent yet. Extend `search()` in `utils/api_client.py` "
            "and pass a `filters` dict once your backend accepts them."
        )
        st.text_input("Meeting ID (scope search to one meeting)", disabled=True)
        st.date_input("From date", disabled=True)
        st.date_input("To date", disabled=True)

    submitted = st.form_submit_button("Search", type="primary", use_container_width=True)

if submitted:
    if not query.strip():
        st.warning("Enter a search query first.")
    else:
        with st.spinner("Searching…"):
            try:
                results = search(query.strip())
            except APIError as e:
                show_api_error(e)
            else:
                if isinstance(results, list):
                    st.caption(f"{len(results)} result(s)")
                    if not results:
                        st.info("No matches found.")
                    for r in results:
                        if isinstance(r, dict):
                            title = (
                                r.get("title")
                                or r.get("meeting_title")
                                or r.get("meeting_id")
                                or "Result"
                            )
                            snippet = r.get("snippet") or r.get("text") or r.get("excerpt")
                            meeting_id = r.get("meeting_id") or r.get("id")
                            score = r.get("score")

                            with st.container(border=True):
                                header = f"**{title}**"
                                if score is not None:
                                    header += f"  ·  score: `{round(score, 3) if isinstance(score, float) else score}`"
                                st.markdown(header)
                                if snippet:
                                    st.write(snippet)
                                if meeting_id:
                                    st.caption(f"Meeting ID: `{meeting_id}` — open it on the Dashboard page.")
                        else:
                            st.write(r)
                else:
                    st.warning(
                        "Expected `POST /search` to return a list of results — "
                        "showing raw JSON instead. Adjust the rendering above once "
                        "you confirm your actual response schema."
                    )
                    st.json(results)
