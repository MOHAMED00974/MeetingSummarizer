"""Shared UI helpers used across multiple Streamlit pages."""

import streamlit as st

from utils.api_client import APIError

# Status values are guesses at what your pipeline might report.
# Adjust these keys to match whatever your FastAPI backend actually returns
# in a meeting's "status" field (e.g. "uploaded", "processing", "done"...).
STATUS_STYLES = {
    "uploaded": {"emoji": "📤", "label": "Uploaded", "color": "gray"},
    "queued": {"emoji": "🕒", "label": "Queued", "color": "gray"},
    "processing": {"emoji": "⚙️", "label": "Processing", "color": "orange"},
    "completed": {"emoji": "✅", "label": "Completed", "color": "green"},
    "done": {"emoji": "✅", "label": "Completed", "color": "green"},
    "failed": {"emoji": "❌", "label": "Failed", "color": "red"},
    "error": {"emoji": "❌", "label": "Failed", "color": "red"},
}


def status_badge(status: str | None) -> str:
    """Return a small markdown badge string for a meeting status."""
    if not status:
        return "❔ Unknown"
    style = STATUS_STYLES.get(status.lower(), {"emoji": "❔", "label": status, "color": "gray"})
    return f":{style['color']}[{style['emoji']} {style['label']}]"


def show_api_error(err: APIError):
    """Render a consistent error box for APIError exceptions."""
    st.error(f"**Request failed:** {err.message}")
    if err.status_code:
        st.caption(f"HTTP status code: {err.status_code}")
    with st.expander("Troubleshooting tips"):
        st.markdown(
            """
- Confirm your FastAPI server is running and reachable at the base URL set in the sidebar.
- Check your backend logs for a traceback.
- If this is a 4xx error, the request shape (JSON body, field names) may not
  match what your FastAPI route expects — check `utils/api_client.py`.
- If this is a 404, double check the meeting ID exists (try the Dashboard page).
            """
        )


def init_session_state():
    """Set default values in st.session_state on first load."""
    defaults = {
        "api_base_url": "http://localhost:8000",
        "selected_meeting_id": None,
        "meetings_cache": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sidebar_config():
    """Render the sidebar with backend config, shown on every page."""
    with st.sidebar:
        st.subheader("⚙️ Backend Settings")
        st.session_state["api_base_url"] = st.text_input(
            "FastAPI base URL",
            value=st.session_state.get("api_base_url", "http://localhost:8000"),
            help="Where your FastAPI server is running, e.g. http://localhost:8000",
        )
        st.divider()
        st.caption(
            "This UI is a thin client over your FastAPI backend. "
            "Nothing is stored here beyond your current browser session."
        )


def render_meeting_picker(meetings: list[dict], key: str = "meeting_picker"):
    """
    Render a selectbox of meetings and return the selected meeting's id.

    Expects each meeting dict to have an "id" field and ideally a "title"
    or "filename" field. Falls back gracefully if fields are missing —
    adjust the field names below to match your actual meeting schema.
    """
    if not meetings:
        st.info("No meetings found yet. Upload one from the **Upload & Process** page.")
        return None

    def _label(m: dict) -> str:
        title = m.get("title") or m.get("filename") or m.get("name") or "Untitled meeting"
        status = m.get("status")
        badge = f" — {status}" if status else ""
        return f"{title}{badge}  ({m.get('id')})"

    ids = [m.get("id") for m in meetings]
    labels = {m.get("id"): _label(m) for m in meetings}

    selected = st.selectbox(
        "Select a meeting",
        options=ids,
        format_func=lambda mid: labels.get(mid, str(mid)),
        key=key,
    )
    return selected
