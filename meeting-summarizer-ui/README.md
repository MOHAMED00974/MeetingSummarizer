# Meeting Summarizer — Streamlit UI

A thin Streamlit frontend over your FastAPI backend. This app makes **no
assumptions baked into the UI layer** — every place it guesses at your
request/response shape is called out below so you can fix it fast once your
FastAPI routes are real.

## Structure

```
meeting-summarizer-ui/
├── Home.py                          # entry point — run this with streamlit
├── pages/
│   ├── 1_📤_Upload_&_Process.py     # POST /meetings/upload, POST /meetings/process
│   ├── 2_📋_Dashboard.py            # GET /meetings, GET /meetings/{id},
│   │                                 #   /transcript, /summary, /decisions, /actions
│   └── 3_🔍_Search.py               # POST /search
├── utils/
│   ├── api_client.py                # ALL HTTP calls live here — start here when adapting
│   └── ui_helpers.py                # shared rendering helpers, session state, sidebar
└── requirements.txt
```

## Running it

```bash
cd meeting-summarizer-ui
pip install -r requirements.txt
streamlit run Home.py
```

Set your FastAPI base URL in the sidebar (defaults to `http://localhost:8000`).
Run your FastAPI server separately, e.g. `uvicorn main:app --reload`.

## What's guessed vs. what's solid

The **routing, error handling, spinners, and page structure** are solid —
that part doesn't depend on your exact schemas. What's guessed is the
**shape of request/response bodies**, since you haven't built the endpoints
yet. Every guess is marked with a comment. The main ones:

| Where | Assumption | Fix in |
|---|---|---|
| `upload_meeting()` | File sent as multipart field named `"file"`, optional `title` form field | `utils/api_client.py` |
| `process_meeting()` | Takes `{"meeting_id": "..."}` as JSON body | `utils/api_client.py` |
| Meeting ID field | Response has `id` or `meeting_id` | `utils/api_client.py`, `ui_helpers.py` |
| `search()` | Body is `{"query": "..."}`, response is a list of result dicts | `utils/api_client.py`, page 3 |
| Transcript/summary/decisions/actions shapes | Several plausible shapes handled defensively (string vs. dict vs. list) | `pages/2_📋_Dashboard.py` |
| Status values | `uploaded`, `processing`, `completed`, `failed`, etc. | `utils/ui_helpers.py` → `STATUS_STYLES` |

Once you've implemented an endpoint for real, run it, hit the corresponding
page, and check the "raw response" `st.json(...)` blocks the app prints —
they'll show you exactly what came back so you can tighten the rendering
code.

## Design choices worth knowing about

- **Upload and Process are separate steps**, not auto-chained. This mirrors
  your two distinct endpoints and lets you debug each stage independently —
  useful while your pipeline is still being built. If you'd rather they
  auto-chain once both endpoints are stable, that's a small change in
  `pages/1_📤_Upload_&_Process.py`.
- **Processing has a long timeout** (300s) since ASR + summarization pipelines
  are typically slow. If a real run takes longer, either raise the timeout in
  `api_client.py` or — better — make `/meetings/process` return immediately
  and add a status-polling loop here once your backend supports it.
- **Every API call is wrapped in try/except APIError** with a consistent,
  readable error box (`show_api_error`), so a broken/unbuilt endpoint fails
  gracefully instead of stack-tracing in the user's face.
