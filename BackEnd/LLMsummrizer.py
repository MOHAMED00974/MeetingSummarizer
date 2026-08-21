from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, ValidationError

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_MAX_TOKENS = 1500

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")


class Decision(BaseModel):
  decision: str
  topic: str
  speaker: str
  timestamp: float


class ActionItem(BaseModel):
  task: str
  owner: str
  deadline: str
  timestamp: float


class FollowUp(BaseModel):
  task: str
  owner: str
  deadline: str
  timestamp: float


class MeetingIntelligence(BaseModel):
  meeting_id: str
  summary: str
  key_points: list[str] = Field(default_factory=list)
  decisions: list[Decision] = Field(default_factory=list)
  action_items: list[ActionItem] = Field(default_factory=list)
  follow_ups: list[FollowUp] = Field(default_factory=list)
class MeetingSummarizerError(RuntimeError):
  """Base error raised by the meeting summarizer."""


def _api_key() -> str:
  key = os.environ.get("GROQ_API_KEY") or os.environ.get("groq_api_key")
  if not key:
    raise MeetingSummarizerError(
      "GROQ_API_KEY is not configured. Set it before summarizing meetings."
    )
  return key

def _client() -> Groq:
  return Groq(api_key=_api_key())

def _meeting_id(meeting: dict[str, Any]) -> str:
  value = meeting.get("meeting_id") or meeting.get("id")
  if value is None or not str(value).strip():
    raise ValueError("The meeting must contain a non-empty meeting_id or id.")
  return str(value)

def _transcript_text(meeting: dict[str, Any]) -> str:
  segments = meeting.get("segments")
  if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
    raise ValueError("The meeting must contain a segments list.")

  lines = []
  for index, segment in enumerate(segments):
    if not isinstance(segment, dict):
      raise ValueError(f"Segment {index} must be an object.")
    text = str(segment.get("text", "")).strip()
    if not text:
      continue
    start = segment.get("start", segment.get("start_time", "?"))
    end = segment.get("end", segment.get("end_time", start))
    speaker = segment.get(
      "speaker_name",
      segment.get("speaker", segment.get("speaker_id", "Unknown Speaker")),
    )
    lines.append(f"[{start} - {end}] {speaker}: {text}")

  if not lines:
    raise ValueError("The meeting must contain at least one non-empty segment.")
  return "\n".join(lines)

def call_llm(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
  """Call Groq and return the generated text, with errors made actionable."""
  if not prompt.strip():
    raise ValueError("The LLM prompt cannot be empty.")
  if max_tokens <= 0:
    raise ValueError("max_tokens must be greater than zero.")

  try:
    response = _client().chat.completions.create(
      model=os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
      messages=[{"role": "user", "content": prompt}],
      max_tokens=max_tokens,
      temperature=0,
    )
  except Exception as error:
    raise MeetingSummarizerError("Groq request failed.") from error

  content = response.choices[0].message.content
  if not content or not content.strip():
    raise MeetingSummarizerError("Groq returned an empty response.")
  return content.strip()

def extract_json(text: str) -> Any:
  """Parse JSON returned by an LLM, including fenced JSON responses."""
  if not text or not text.strip():
    raise ValueError("The LLM returned an empty JSON response.")

  cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
  try:
    return json.loads(cleaned)
  except json.JSONDecodeError as error:
    raise ValueError("The LLM returned invalid JSON.") from error

def _list_prompt(instruction: str, transcript: str, item_name: str) -> str:
  return f"""You are analyzing a meeting transcript.

{instruction}

Return ONLY a valid JSON list. Do not include Markdown or commentary.
Use the exact requested fields and return [] when there are no {item_name}.

Transcript:
{transcript}
"""

def _extract_list(prompt: str, model_type: type[BaseModel]) -> list[dict[str, Any]]:
  value = extract_json(call_llm(prompt))
  if not isinstance(value, list):
    raise ValueError("The LLM response must be a JSON list.")

  parsed = []
  for item in value:
    try:
      parsed.append(model_type.model_validate(item).model_dump())
    except ValidationError as error:
      raise ValueError("The LLM returned an invalid structured item.") from error
  return parsed

def _summary(transcript: str) -> str:
  prompt = f"""Summarize this meeting in 2-3 clear sentences.
Focus on what was discussed and decided. Use past tense for completed decisions.
Do not invent information.

Transcript:
{transcript}
"""
  return call_llm(prompt, max_tokens=300)

def summarize_meeting(
  meeting: dict[str, Any],
  output_path: str | Path | None = None,
) -> dict[str, Any]:
  """Summarize one STT meeting and optionally persist validated JSON."""
  if not isinstance(meeting, dict):
    raise TypeError("meeting must be a dictionary.")

  meeting_id = _meeting_id(meeting)
  transcript = _transcript_text(meeting)

  decisions = _extract_list(
    _list_prompt(
      "Extract ONLY final decisions, agreements, or conclusions. "
      "Do not include tasks, deadlines, or general discussion. "
      'Each item must have: decision, topic, speaker, timestamp.',
      transcript,
      "decisions",
    ),
    Decision,
  )
  action_items = _extract_list(
    _list_prompt(
      "Extract all assigned action items. "
      "Each item must have: task, owner, deadline, timestamp. "
      "Use 'Not specified' when no deadline is mentioned.",
      transcript,
      "action items",
    ),
    ActionItem,
  )
  follow_ups = _extract_list(
    _list_prompt(
      "Extract personal follow-up commitments such as 'I will' or 'I am going to'. "
      "Each item must have: task, owner, deadline, timestamp. "
      "Use 'Not specified' when no deadline is mentioned.",
      transcript,
      "follow-up commitments",
    ),
    FollowUp,
  )

  intelligence = MeetingIntelligence(
    meeting_id=meeting_id,
    summary=_summary(transcript),
    key_points=[],
    decisions=decisions,
    action_items=action_items,
    follow_ups=follow_ups,
  )
  result = intelligence.model_dump()

  if output_path is not None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
      json.dumps(result, indent=2, ensure_ascii=False),
      encoding="utf-8",
    )
    temporary.replace(destination)

  return result