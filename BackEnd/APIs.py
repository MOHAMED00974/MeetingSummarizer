from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

try:
    from . import SpeechToText as stt
    from .LLMsummrizer import MeetingSummarizerError, summarize_meeting
except ImportError:
    import SpeechToText as stt
    from LLMsummrizer import MeetingSummarizerError, summarize_meeting


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "DataBase" / "meetings.json"
UPLOADS_PATH = PROJECT_ROOT / "DataBase" / "uploads"
PENDING_PATH = PROJECT_ROOT / "DataBase" / "pending_uploads.json"

app = FastAPI(
	title="Meeting Summarizer API",
	description="Backend API for uploading, processing, and searching meetings.",
	version="0.1.0",
)


class ProcessRequest(BaseModel):
    meeting_id: str = Field(min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict) and "meetings" in data:
        data = data["meetings"]
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise RuntimeError(f"Invalid JSON list database: {path}")
    return data


def _write_json_list(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _meeting_view(meeting: dict) -> dict:
    return {
        "id": meeting["meeting_id"],
        "meeting_id": meeting["meeting_id"],
        "title": meeting.get("title", meeting["meeting_id"]),
        "filename": meeting.get("filename"),
        "status": meeting.get("status", "processed"),
        "created_at": meeting.get("created_at", meeting.get("date")),
    }


def _find_meeting(meeting_id: str) -> dict:
    meetings = _read_json_list(DATABASE_PATH)
    for meeting in meetings:
        if str(meeting.get("meeting_id", meeting.get("id"))) == meeting_id:
            return meeting
    raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id}")


def _find_pending(meeting_id: str) -> dict:
    pending = _read_json_list(PENDING_PATH)
    for meeting in pending:
        if meeting.get("meeting_id") == meeting_id:
            return meeting
    raise HTTPException(status_code=404, detail=f"Uploaded meeting not found: {meeting_id}")

@app.post("/meetings/upload", tags=["system"])
async def upload_meeting(
    file: UploadFile = File(...),
    title: str | None = Form(None),
):
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix
    meeting_id = f"meeting_{uuid4().hex}"
    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    input_path = UPLOADS_PATH / f"{meeting_id}{suffix}"

    with input_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)

    pending = _read_json_list(PENDING_PATH)
    pending.append({
        "meeting_id": meeting_id,
        "filename": filename,
        "title": title or Path(filename).stem,
        "audio_path": str(input_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "uploaded",
    })
    _write_json_list(PENDING_PATH, pending)

    return {
        "id": meeting_id,
        "meeting_id": meeting_id,
        "filename": filename,
        "title": title,
        "status": "uploaded",
    }


@app.post("/meetings/process", tags=["system"])
def process_meeting(request: ProcessRequest):
    pending = _find_pending(request.meeting_id)
    audio_path = Path(pending["audio_path"])

    try:
        transcript = stt.full_pipeline(str(audio_path), request.meeting_id)
        intelligence = summarize_meeting(transcript)
    except MeetingSummarizerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    processed_at = datetime.now(timezone.utc).isoformat()
    record = {
        "meeting_id": request.meeting_id,
        "id": request.meeting_id,
        "date": processed_at[:10],
        "title": pending["title"],
        "filename": pending["filename"],
        "created_at": pending["created_at"],
        "processed_at": processed_at,
        "status": "processed",
        "segments": transcript["segments"],
        "summary": intelligence["summary"],
        "key_points": intelligence["key_points"],
        "decisions": intelligence["decisions"],
        "action_items": intelligence["action_items"],
        "follow_ups": intelligence["follow_ups"],
    }

    meetings = _read_json_list(DATABASE_PATH)
    meetings = [item for item in meetings if item.get("meeting_id") != request.meeting_id]
    meetings.append(record)
    _write_json_list(DATABASE_PATH, meetings)

    pending_records = [
        item for item in _read_json_list(PENDING_PATH)
        if item.get("meeting_id") != request.meeting_id
    ]
    _write_json_list(PENDING_PATH, pending_records)

    return record


@app.get("/meetings", tags=["meetings"])
def list_meetings() -> list[dict]:
    return [_meeting_view(meeting) for meeting in _read_json_list(DATABASE_PATH)]


@app.get("/meetings/{meeting_id}", tags=["meetings"])
def get_meeting(meeting_id: str) -> dict:
    return _find_meeting(meeting_id)


@app.get("/meetings/{meeting_id}/transcript", tags=["meetings"])
def get_transcript(meeting_id: str) -> list[dict]:
    return _find_meeting(meeting_id).get("segments", [])


@app.get("/meetings/{meeting_id}/summary", tags=["meetings"])
def get_summary(meeting_id: str) -> dict:
    return {"summary": _find_meeting(meeting_id).get("summary", "")}


@app.get("/meetings/{meeting_id}/decisions", tags=["meetings"])
def get_decisions(meeting_id: str) -> list[dict]:
    return _find_meeting(meeting_id).get("decisions", [])


@app.get("/meetings/{meeting_id}/actions", tags=["meetings"])
def get_actions(meeting_id: str) -> list[dict]:
    return _find_meeting(meeting_id).get("action_items", [])


@app.post("/search", tags=["search"])
def search_meetings(request: SearchRequest) -> list[dict]:
    try:
        try:
            from . import RAG
        except ImportError:
            import RAG

        RAG.initialize_memory(str(DATABASE_PATH))
        results = RAG.semantic_search(request.query, top_k=10)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return [
        {
            "id": item["meeting_id"],
            "meeting_id": item["meeting_id"],
            "title": item["meeting_title"],
            "snippet": item["text"],
            "score": item["similarity"],
        }
        for item in results
    ]

@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}