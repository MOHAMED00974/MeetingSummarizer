import streamlit as st

from utils.api_client import APIError, process_meeting, upload_meeting
from utils.ui_helpers import init_session_state, sidebar_config, show_api_error

st.set_page_config(page_title="Upload & Process", page_icon="📤", layout="wide")
init_session_state()
sidebar_config()

st.title("📤 Upload & Process a Meeting")
st.markdown(
    "This page mirrors your two-step backend flow: first the file is uploaded "
    "(`POST /meetings/upload`), then processing is triggered separately "
    "(`POST /meetings/process`). Keeping these as two explicit steps means you "
    "can inspect the uploaded meeting before committing to a (likely slow) "
    "processing run."
)

st.divider()

# ---------------------------------------------------------------------------
# Step 1 — Upload
# ---------------------------------------------------------------------------
st.header("Step 1 — Upload a recording")

with st.form("upload_form", clear_on_submit=False):
    meeting_title = st.text_input(
        "Meeting title (optional)",
        placeholder="e.g. Weekly Sync — Aug 20",
        help="Sent along with the file if your backend accepts a title field. "
        "Safe to leave blank if your /upload endpoint doesn't use one.",
    )
    uploaded_file = st.file_uploader(
        "Audio or video file",
        type=["mp3", "wav", "m4a", "flac", "ogg", "mp4", "mov", "mkv", "webm"],
        accept_multiple_files=False,
        help="Anything your backend's /meetings/upload endpoint accepts. "
        "Adjust the allowed types above if your pipeline is pickier.",
    )
    submitted = st.form_submit_button("Upload", type="primary", use_container_width=True)

if submitted:
    if not uploaded_file:
        st.warning("Please choose an audio or video file first.")
    else:
        with st.spinner(f"Uploading {uploaded_file.name}…"):
            try:
                result = upload_meeting(uploaded_file, meeting_title or None)
            except APIError as e:
                show_api_error(e)
            else:
                st.success("Upload succeeded.")
                st.json(result)

                # Try to pull an id out of common shapes so we can prefill
                # Step 2 for convenience. Falls back to manual entry if the
                # response doesn't look like what we expect.
                candidate_id = None
                if isinstance(result, dict):
                    candidate_id = (
                        result.get("id")
                        or result.get("meeting_id")
                        or result.get("meetingId")
                    )
                if candidate_id:
                    st.session_state["last_uploaded_meeting_id"] = str(candidate_id)
                    st.info(f"Detected meeting ID: `{candidate_id}` — prefilled below.")
                else:
                    st.warning(
                        "Couldn't automatically detect a meeting ID in the response "
                        "above. Copy the correct field manually into Step 2, and "
                        "consider adjusting `upload_meeting()` in `utils/api_client.py` "
                        "to match your actual response shape."
                    )

st.divider()

# ---------------------------------------------------------------------------
# Step 2 — Process
# ---------------------------------------------------------------------------
st.header("Step 2 — Run the processing pipeline")
st.markdown(
    "Triggers your pipeline (transcription, summarization, decision/action "
    "extraction, etc.) for a given meeting ID. This may take a while depending "
    "on file length — the request timeout is set generously in "
    "`utils/api_client.py`, but consider making this async on the backend "
    "(return immediately, poll for status) if files are long."
)

default_id = st.session_state.get("last_uploaded_meeting_id", "")
process_id = st.text_input(
    "Meeting ID to process",
    value=default_id,
    placeholder="Paste or confirm the meeting ID from Step 1",
)

if st.button("Start processing", type="primary", disabled=not process_id):
    with st.spinner("Processing… this can take a while for longer recordings."):
        try:
            result = process_meeting(process_id)
        except APIError as e:
            show_api_error(e)
        else:
            st.success("Processing request completed.")
            st.json(result)
            st.markdown(
                f"Head to the **Dashboard** page and open meeting `{process_id}` "
                "to view its transcript, summary, decisions, and action items."
            )
