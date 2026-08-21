"""
Centralized client for the Meeting Summarizer FastAPI backend.

Every HTTP call in the app goes through this module. If your endpoint
contracts change (field names, status codes, etc.), this is the only
file you should need to touch.
"""

import requests
import streamlit as st


class APIError(Exception):
    """Raised when the backend returns an error or is unreachable."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _base_url() -> str:
    return st.session_state.get("api_base_url", "http://localhost:8000").rstrip("/")


def _handle_response(resp: requests.Response):
    """Raise APIError with a readable message on non-2xx, else return parsed JSON."""
    if resp.ok:
        # Some endpoints (e.g. a 204 on delete) may have no body.
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # Try to surface FastAPI's {"detail": "..."} message if present.
    detail = None
    try:
        body = resp.json()
        detail = body.get("detail") if isinstance(body, dict) else None
    except ValueError:
        pass

    message = detail or resp.text or f"Request failed with status {resp.status_code}"
    raise APIError(message, status_code=resp.status_code)


def _request(method: str, path: str, timeout: int = 30, **kwargs):
    url = f"{_base_url()}{path}"
    try:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.exceptions.ConnectionError as e:
        raise APIError(
            f"Could not reach the backend at {url}. "
            f"Is your FastAPI server running? ({e.__class__.__name__})"
        )
    except requests.exceptions.Timeout:
        raise APIError(f"Request to {url} timed out after {timeout}s.")
    except requests.exceptions.RequestException as e:
        raise APIError(f"Request to {url} failed: {e}")

    return _handle_response(resp)


# ---------------------------------------------------------------------------
# Endpoint wrappers — one function per FastAPI route
# ---------------------------------------------------------------------------


def upload_meeting(file, meeting_title: str | None = None):
    """
    POST /meetings/upload

    `file` is a Streamlit UploadedFile (audio or video).
    Adjust the field name "file" below if your FastAPI route expects a
    different multipart field name.
    """
    files = {"file": (file.name, file.getvalue(), file.type)}
    data = {}
    if meeting_title:
        data["title"] = meeting_title

    return _request(
        "POST",
        "/meetings/upload",
        files=files,
        data=data,
        timeout=120,  # uploads can be large; give this more room
    )


def process_meeting(meeting_id: str):
    """
    POST /meetings/process

    Assumes the backend expects the meeting_id in a JSON body:
        {"meeting_id": "..."}
    If your route instead expects it as a query param or path param,
    change this call accordingly (see note below the class).
    """
    return _request(
        "POST",
        "/meetings/process",
        json={"meeting_id": meeting_id},
        timeout=300,  # processing pipelines (ASR + summarization) can be slow
    )


def list_meetings():
    """GET /meetings"""
    return _request("GET", "/meetings")


def get_meeting(meeting_id: str):
    """GET /meetings/{id}"""
    return _request("GET", f"/meetings/{meeting_id}")


def get_transcript(meeting_id: str):
    """GET /meetings/{id}/transcript"""
    return _request("GET", f"/meetings/{meeting_id}/transcript")


def get_summary(meeting_id: str):
    """GET /meetings/{id}/summary"""
    return _request("GET", f"/meetings/{meeting_id}/summary")


def get_decisions(meeting_id: str):
    """GET /meetings/{id}/decisions"""
    return _request("GET", f"/meetings/{meeting_id}/decisions")


def get_actions(meeting_id: str):
    """GET /meetings/{id}/actions"""
    return _request("GET", f"/meetings/{meeting_id}/actions")


def search(query: str, filters: dict | None = None):
    """
    POST /search

    Assumes a JSON body like {"query": "...", **filters}.
    Adjust the payload shape to match your actual request model.
    """
    payload = {"query": query}
    if filters:
        payload.update(filters)
    return _request("POST", "/search", json=payload)
