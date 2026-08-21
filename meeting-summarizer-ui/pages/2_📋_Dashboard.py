import streamlit as st

from utils.api_client import (
    APIError,
    get_actions,
    get_decisions,
    get_meeting,
    get_summary,
    get_transcript,
    list_meetings,
)
from utils.ui_helpers import (
    init_session_state,
    render_meeting_picker,
    show_api_error,
    sidebar_config,
    status_badge,
)

st.set_page_config(page_title="Dashboard", page_icon="📋", layout="wide")
init_session_state()
sidebar_config()

st.title("📋 Meeting Dashboard")

# ---------------------------------------------------------------------------
# Meeting list — GET /meetings
# ---------------------------------------------------------------------------
refresh_col, _ = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Refresh list"):
        st.session_state["meetings_cache"] = None

if st.session_state.get("meetings_cache") is None:
    try:
        with st.spinner("Loading meetings…"):
            st.session_state["meetings_cache"] = list_meetings()
    except APIError as e:
        show_api_error(e)
        st.session_state["meetings_cache"] = []

meetings = st.session_state.get("meetings_cache") or []

if not isinstance(meetings, list):
    st.error(
        "Expected `GET /meetings` to return a list, but got something else. "
        "Check the raw response below and adjust `list_meetings()` in "
        "`utils/api_client.py` if your backend wraps the list in an object "
        "(e.g. `{\"meetings\": [...]}`)."
    )
    st.json(meetings)
    st.stop()

st.caption(f"{len(meetings)} meeting(s)")

# Compact table overview, when there's anything to show.
if meetings:
    table_rows = []
    for m in meetings:
        table_rows.append(
            {
                "ID": m.get("id"),
                "Title": m.get("title") or m.get("filename") or "—",
                "Status": m.get("status") or "—",
                "Created": m.get("created_at") or m.get("createdAt") or "—",
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Meeting detail — GET /meetings/{id} + sub-resources
# ---------------------------------------------------------------------------
st.header("Meeting detail")

selected_id = render_meeting_picker(meetings, key="dashboard_meeting_picker")

if selected_id:
    try:
        with st.spinner("Loading meeting details…"):
            meeting = get_meeting(selected_id)
    except APIError as e:
        show_api_error(e)
        st.stop()

    title = meeting.get("title") or meeting.get("filename") or "Untitled meeting"
    status = meeting.get("status")

    st.subheader(title)
    st.markdown(f"**Status:** {status_badge(status)}  |  **ID:** `{selected_id}`")

    with st.expander("Raw meeting object (GET /meetings/{id})"):
        st.json(meeting)

    tab_transcript, tab_summary, tab_decisions, tab_actions = st.tabs(
        ["📝 Transcript", "🧾 Summary", "✅ Decisions", "🎯 Action Items"]
    )

    with tab_transcript:
        try:
            with st.spinner("Loading transcript…"):
                transcript = get_transcript(selected_id)
        except APIError as e:
            show_api_error(e)
        else:
            # Handle a few plausible shapes: plain string, {"text": ...},
            # or a list of {speaker, text, timestamp} segments.
            if isinstance(transcript, str):
                st.text_area("Transcript", transcript, height=400, label_visibility="collapsed")
            elif isinstance(transcript, dict) and "text" in transcript:
                st.text_area(
                    "Transcript", transcript["text"], height=400, label_visibility="collapsed"
                )
            elif isinstance(transcript, list):
                for seg in transcript:
                    speaker = seg.get("speaker", "Unknown")
                    timestamp = seg.get("timestamp") or seg.get("start")
                    text = seg.get("text", "")
                    ts_label = f" · `{timestamp}`" if timestamp is not None else ""
                    st.markdown(f"**{speaker}**{ts_label}")
                    st.write(text)
                    st.markdown("---")
            else:
                st.warning(
                    "Transcript response shape wasn't recognized — showing raw JSON. "
                    "Adjust this rendering block once you confirm your actual schema."
                )
                st.json(transcript)

    with tab_summary:
        try:
            with st.spinner("Loading summary…"):
                summary = get_summary(selected_id)
        except APIError as e:
            show_api_error(e)
        else:
            if isinstance(summary, str):
                st.markdown(summary)
            elif isinstance(summary, dict) and "summary" in summary:
                st.markdown(summary["summary"])
            else:
                st.warning("Summary response shape wasn't recognized — showing raw JSON.")
                st.json(summary)

    with tab_decisions:
        try:
            with st.spinner("Loading decisions…"):
                decisions = get_decisions(selected_id)
        except APIError as e:
            show_api_error(e)
        else:
            if isinstance(decisions, list) and decisions:
                for i, d in enumerate(decisions, start=1):
                    if isinstance(d, dict):
                        text = d.get("text") or d.get("decision") or str(d)
                        st.markdown(f"**{i}.** {text}")
                        meta_bits = []
                        if d.get("owner"):
                            meta_bits.append(f"Owner: {d['owner']}")
                        if d.get("timestamp"):
                            meta_bits.append(f"At: {d['timestamp']}")
                        if meta_bits:
                            st.caption(" · ".join(meta_bits))
                    else:
                        st.markdown(f"**{i}.** {d}")
            elif isinstance(decisions, list):
                st.info("No decisions extracted for this meeting.")
            else:
                st.warning("Decisions response shape wasn't recognized — showing raw JSON.")
                st.json(decisions)

    with tab_actions:
        try:
            with st.spinner("Loading action items…"):
                actions = get_actions(selected_id)
        except APIError as e:
            show_api_error(e)
        else:
            if isinstance(actions, list) and actions:
                for a in actions:
                    if isinstance(a, dict):
                        text = a.get("text") or a.get("action") or str(a)
                        assignee = a.get("assignee") or a.get("owner")
                        due = a.get("due_date") or a.get("dueDate")
                        label = f"**{text}**"
                        if assignee:
                            label += f"  — assigned to *{assignee}*"
                        st.checkbox(label, key=f"action_{selected_id}_{a.get('id', text)}")
                        if due:
                            st.caption(f"Due: {due}")
                    else:
                        st.checkbox(str(a), key=f"action_{selected_id}_{a}")
            elif isinstance(actions, list):
                st.info("No action items extracted for this meeting.")
            else:
                st.warning("Action items response shape wasn't recognized — showing raw JSON.")
                st.json(actions)
