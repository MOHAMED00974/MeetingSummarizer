# MeetingSummarizer

Upload a meeting recording, get a searchable summary back.

MeetingSummarizer takes an audio/video recording of a meeting, transcribes it, summarizes it with an LLM, and stores the summary alongside its embedding — so you can later search across past meetings using natural language queries via RAG.

---

## How it works

```
Upload (audio/video)
      │
      ▼
Transcription  ──  faster-whisper
      │
      ▼
Summarization  ──  Groq (LLM)
      │
      ▼
Embedding      ──  all-MiniLM-L6-v2
      │
      ▼
Storage        ──  JSON (MVP)
      │
      ▼
Search Query ──▶ RAG ──▶ Answer
```

1. **Upload** — an audio/video file is uploaded to the backend.
2. **Transcribe** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) converts speech to text.
3. **Summarize** — the transcript is sent to an LLM via [Groq](https://groq.com/) to produce a summary.
4. **Embed** — the summary is embedded using `all-MiniLM-L6-v2`.
5. **Store** — the summary + embedding are persisted (currently as JSON — see [Roadmap](#roadmap)).
6. **Search** — a user query is embedded and matched against stored summaries; a RAG pipeline uses the retrieved context to answer.

---

## Tech stack

| Layer | Tool |
|---|---|
| Backend | FastAPI |
| Frontend | Streamlit |
| Transcription | faster-whisper |
| Summarization | Groq (LLM API) |
| Embeddings | all-MiniLM-L6-v2 |
| Storage | JSON (MVP — see [Roadmap](#roadmap)) |

---

## Project structure

The Streamlit app is a thin client over the FastAPI backend — it holds no state beyond the current browser session, and simply calls the FastAPI base URL (configurable in the sidebar, defaults to `http://localhost:8000`).

The backend flow is two explicit steps rather than one combined call:

- `POST /meetings/upload` — uploads the recording, returns a `meeting_id`
- `POST /meetings/process` — triggers transcription + summarization + embedding for a previously uploaded meeting

Keeping these separate means you can inspect an uploaded meeting before committing to a slow processing run.

---

## Setup

### Prerequisites

You can view them in requirements.txt

### Installation

```bash
git clone https://github.com/<your-username>/MeetingSummarizer.git
cd MeetingSummarizer

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
HF_TOKEN= your_hf_token_key
FASTAPI_BASE_URL=http://localhost:8000
```


### Running the backend

```bash
uvicorn backend.main:app --reload
```

Backend will be available at `http://localhost:8000`.

### Running the frontend

```bash
streamlit run frontend/app.py
```

By default, the Streamlit app expects the FastAPI backend at `http://localhost:8000` — this is configurable in the app's sidebar under **Backend Settings**.

---

## Usage

1. Start the FastAPI backend and Streamlit frontend (see above).
2. In the Streamlit UI, go to **Upload & Process**.
3. Give the meeting an optional title and upload an audio/video file → this hits `POST /meetings/upload`.
4. Trigger processing → this hits `POST /meetings/process`, which runs transcription, summarization, and embedding.
5. Once processed, go to **Search** to query past meetings using natural language — the RAG pipeline retrieves relevant summaries and answers your query.
6. Use **Dashboard** to view processed meetings.

### Example API response (upload step)

```json
{
  "id": "meeting_64cf80b8d9624ce5a9389cd720edbcfb",
  "meeting_id": "meeting_64cf80b8d9624ce5a9389cd720edbcfb",
  "filename": "processed_meeting_e30f258c04cf427aaeb655ef5ca130f1.wav",
  "title": null,
  "status": "uploaded"
}
```

---

## Roadmap

- [ ] Replace JSON storage with a proper vector database (e.g. Chroma, Qdrant, Pinecone, or Postgres + pgvector)
- [ ] Add authentication
- [ ] Support batch uploads
- [ ] Add tests

---

## Team

- [@ahmed-shamh](https://github.com/ahmed-shamh)
- [@MohamedHamed5](https://github.com/MohamedHamed5)

---

## License

This project is licensed under the [MIT License](LICENSE).
