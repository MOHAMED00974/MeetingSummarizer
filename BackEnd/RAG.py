import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

HF_TOKEN = os.environ.get("HF_TOKEN")
DATABASE_PATH = "/home/mohamed-tamer/Meetings_Summarizer/DataBase/meetings.json"
CHUNK_SIZE_WORDS = 80
CHUNK_OVERLAP_WORDS = 15
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL_NAME = os.environ.get("HF_LLM_MODEL", "google/flan-t5-small")
embedding_model = None
llm_tokenizer = None
llm_model = None
TOP_K = 1
DECISION_STATUSES = {"ACTIVE", "SUPERSEDED", "REJECTED", "PENDING"}
decision_store = []


all_chunk_records = []
all_chunk_vectors = None
_memory_initialized = False

FIELD_ALIASES = {
    "meeting_id": ["meeting_id", "id", "meetingId"],
    "meeting_date": ["date", "meeting_date", "meetingDate"],
    "meeting_title": ["title", "meeting_title", "meetingTitle"],
    "segments": ["segments", "transcript", "transcription"],
    "decisions": ["decisions", "decision"],
    "action_items": ["action_items", "actions", "actionItems"],
    "summary": ["summary"],
    "key_points": ["key_points", "keyPoints"],
    "follow_ups": ["follow_ups", "followUps"],
}


def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            device="cpu",
        )
    return embedding_model


def get_llm():
    global llm_tokenizer, llm_model
    if llm_tokenizer is None or llm_model is None:
        llm_tokenizer = AutoTokenizer.from_pretrained(
            LLM_MODEL_NAME,
            token=HF_TOKEN,
        )
        llm_model = AutoModelForSeq2SeqLM.from_pretrained(
            LLM_MODEL_NAME,
            token=HF_TOKEN,
        ).to("cpu")
    return llm_tokenizer, llm_model

def add_chunks_to_memory(records, vectors, chunks):
        '''
        Convert chunk txts into embeddings
        '''
        texts = [chunk["text"] for chunk in chunks]
        new_vectors = get_embedding_model().encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
        )

        records.extend(chunks)

        if vectors is None:
            vectors = new_vectors
        else:
            vectors = np.vstack([vectors, new_vectors])

        return records, vectors

def search_memory(query, records, vectors, top_k=1):
    if vectors is None or len(records) == 0:
        return []

    # convert the user que into an embedding
    query_vector = get_embedding_model().encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    )
    # calc cosine similarity scores
    scores = cosine_similarity(query_vector, vectors)[0]

    # tet the indexes of the highest scores
    best_indexes = np.argsort(scores)[::-1][:top_k]

    results = []
    for index in best_indexes:
        result = dict(records[int(index)])
        result["similarity"] = float(scores[int(index)])
        results.append(result)

    return results

def retrieve_meetings(
	database_path: Union[str, Path] = DATABASE_PATH,
	meeting_id: Optional[Union[str, int]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
	"""Load all meetings, or one meeting when ``meeting_id`` is provided."""
	path = Path(database_path)
	if not path.exists():
		raise FileNotFoundError(f"Meetings database not found: {path}")

	with path.open("r", encoding="utf-8") as file:
		data = json.load(file)

	if isinstance(data, dict):
		if "meetings" in data:
			meetings = data["meetings"]
		else:
			meetings = [data]
	else:
		meetings = data

	if not isinstance(meetings, list):
		raise ValueError("The meetings JSON database must contain a list of meetings.")

	if meeting_id is None:
		return meetings

	for meeting in meetings:
		if (
			isinstance(meeting, dict)
			and str(meeting.get("id", meeting.get("meeting_id")))
			== str(meeting_id)
		):
			return meeting

	raise LookupError(f"Meeting not found: {meeting_id}")

FIELD_NAMES = [
    "meeting_id", 
    "date",
    "title",
    "segments",
    "decisions",
    "action_items",
    "summary",
    "key_points",
    "follow_ups"
]

def first_value(data, possible_names, default=None):
    '''
	return the 1st available value from the possible field names
	'''
    for name in possible_names:
        if name in data and data[name] is not None:
            return data[name]
    return default

def normalize_segment(segment, index):
    '''
	convert 1 transcript segment into the common internal format'''
    return {
        "segment_id": f"segment_{index:04d}",
        "speaker": str(first_value(segment, ["speaker_name", "speaker", "speaker_id"], "Unknown Speaker")),
        "start": first_value(segment, ["start", "start_time", "timestamp"], None),
        "end": first_value(segment, ["end", "end_time"], first_value(segment, ["start", "start_time", "timestamp"], None)),
        "text": str(first_value(segment, ["text", "content", "transcript"], "")).strip()
    }

def normalize_decision(decision, meeting_id, index):
    '''
	convert 1 decision into the common internal format
    '''
    return {
        "decision_id": f"{meeting_id}_decision_{index:04d}",
        "meeting_id": meeting_id,
        "topic": str(first_value(decision, ["topic", "subject", "category"], "general")),
        "decision": str(first_value(decision, ["decision", "text", "content"], "")),
        "speaker": str(first_value(decision, ["speaker", "speaker_name", "owner"], "Unknown Speaker")),
        "timestamp": first_value(decision, ["timestamp", "start", "time"], None),
        "status": str(first_value(decision, ["status", "state"], "PENDING")).upper(),
        "source": decision
    }

def normalize_meeting(raw):
    '''
    convert (member2) output into one stable format for all (coming) Fns
    '''
    meeting_id = str(first_value(raw, FIELD_ALIASES["meeting_id"], "meeting_unknown"))
    raw_segments = first_value(raw, FIELD_ALIASES["segments"], []) or []
    raw_decisions = first_value(raw, FIELD_ALIASES["decisions"], []) or []

    meeting = {
        "meeting_id": meeting_id,
        "meeting_date": first_value(raw, FIELD_ALIASES["meeting_date"], ""),
        "meeting_title": first_value(raw, FIELD_ALIASES["meeting_title"], meeting_id),
        "summary": first_value(raw, FIELD_ALIASES["summary"], ""),
        "key_points": first_value(raw, FIELD_ALIASES["key_points"], []) or [],
        "segments": [normalize_segment(item, i) for i, item in enumerate(raw_segments)],
        "decisions": [normalize_decision(item, meeting_id, i) for i, item in enumerate(raw_decisions)],
        "action_items": first_value(raw, FIELD_ALIASES["action_items"], []) or [],
        "follow_ups": first_value(raw, FIELD_ALIASES["follow_ups"], []) or []
    }

    if len(meeting["segments"]) == 0:
        raise ValueError("No transcript segments found. Check the JSON field names.")
    return meeting

def chunk_segments(meeting_data, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):

    '''
    split transcript words with keeping the source metadata
    '''
    words_with_source = []
    for segment in meeting_data["segments"]:
        for word in segment["text"].split():
            words_with_source.append((word, segment))

    chunks = []
    start_index = 0
    chunk_number = 0

    while start_index < len(words_with_source):
        end_index = min(start_index + chunk_size, len(words_with_source))
        selected = words_with_source[start_index:end_index]
        selected_segments = [item[1] for item in selected]

        chunks.append({
            "chunk_id": f"{meeting_data['meeting_id']}_chunk_{chunk_number:04d}",
            "meeting_id": meeting_data["meeting_id"],
            "meeting_date": meeting_data["meeting_date"],
            "meeting_title": meeting_data["meeting_title"],
            "speaker": selected_segments[0]["speaker"],
            "start": selected_segments[0]["start"],
            "end": selected_segments[-1]["end"],
            "text": " ".join(item[0] for item in selected)
        })

        chunk_number += 1
        if end_index == len(words_with_source):
            break
        start_index = max(end_index - overlap, start_index + 1)

    return chunks

def semantic_search(query, top_k=TOP_K):

    if not _memory_initialized:
        initialize_memory()

    return search_memory(
        query,
        all_chunk_records,
        all_chunk_vectors,
        top_k
    )

def build_source(result):
    # keep the info needed to show where an answer came from
    return {
        "meeting_id": result["meeting_id"],
        "meeting_title": result["meeting_title"],
        "timestamp": result["start"],
        "speaker": result["speaker"],
        "chunk_id": result["chunk_id"],
        "similarity": round(result["similarity"], 4)
    }


def generate_answer(query, results, decision=None):
    """Generate a grounded answer from retrieved evidence with the HF LLM."""
    evidence = "\n".join(
        f"- {item['meeting_title']} ({item['meeting_id']}): {item['text']}"
        for item in results
    )
    decision_context = "No topic decision was supplied."
    if decision is not None:
        decision_context = (
            f"The latest active decision is authoritative: "
            f"{decision['decision']} (topic: {decision['topic']})."
        )

    prompt = (
        "Answer the question using only the meeting evidence below. "
        "Do not invent facts. If the evidence does not answer the question, "
        "say that there is not enough evidence. "
        f"{decision_context}\n\n"
        f"Question: {query}\n"
        f"Meeting evidence:\n{evidence}\n"
        "Answer:"
    )
    tokenizer, model = get_llm()
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    )
    generated = model.generate(
        **inputs,
        max_new_tokens=96,
        do_sample=False,
    )
    return tokenizer.decode(generated[0], skip_special_tokens=True).strip()


def initialize_memory(database_path: Union[str, Path] = DATABASE_PATH):
    """Load, normalize, embed, and index every meeting in the database."""
    global all_chunk_records, all_chunk_vectors, decision_store, _memory_initialized

    all_chunk_records = []
    all_chunk_vectors = None
    decision_store = []

    for raw_meeting in retrieve_meetings(database_path):
        meeting = normalize_meeting(raw_meeting)
        chunks = chunk_segments(meeting)
        all_chunk_records, all_chunk_vectors = add_chunks_to_memory(
            all_chunk_records,
            all_chunk_vectors,
            chunks,
        )
        add_decisions(meeting["decisions"])

    _memory_initialized = True
    return len(all_chunk_records)

def rag_answer(query, top_k=TOP_K, min_similarity=0.20, decision=None):
    # retrieve only chunks that pass the similarity >
    results = [
        item for item in semantic_search(query, top_k)
        if item["similarity"] >= min_similarity
    ]

    if len(results) == 0:
        return {
            "answer": "I could not find enough relevant evidence in the stored meetings.",
            "sources": [],
            "relevant_chunks": []
        }

    answer = generate_answer(query, results, decision)

    return {
        "answer": answer,
        "sources": [build_source(item) for item in results],
        "relevant_chunks": results
    }


def topic_key(topic):
    return re.sub(r"\s+", " ", str(topic).strip().lower())

def add_decisions(decisions):
    # ddd decisions and supersede older active decisions on the same topic
    for decision in decisions:
        new_decision = dict(decision)
        new_decision["status"] = str(new_decision.get("status", "PENDING")).upper()

        if new_decision["status"] not in DECISION_STATUSES:
            new_decision["status"] = "PENDING"

        if new_decision["status"] == "ACTIVE":
            for old_decision in decision_store:
                same_topic = topic_key(old_decision.get("topic", "")) == topic_key(new_decision.get("topic", ""))
                if same_topic and old_decision.get("status") == "ACTIVE":
                    old_decision["status"] = "SUPERSEDED"

        decision_store.append(new_decision)

def get_decision_history(topic):
    # return all decisions related to 1 topic
    return [
        item for item in decision_store
        if topic_key(item.get("topic", "")) == topic_key(topic)
    ]

def get_latest_active_decision(topic):
    # return the last active decision for a topi.
    history = get_decision_history(topic)
    active_decisions = [item for item in history if item.get("status") == "ACTIVE"]
    return active_decisions[-1] if active_decisions else None

def save_decision_store(path="decision_store.json"):
    # save the list of decisions as readable JSON
    with open(path, "w", encoding="utf-8") as file:
        json.dump(decision_store, file, ensure_ascii=False, indent=2)
    return path

def load_decision_store(path="decision_store.json"):
    global decision_store

    with open(path, "r", encoding="utf-8") as file:
        loaded = json.load(file)

    if not isinstance(loaded, list):
        raise ValueError("The decision store must contain a list of decisions.")

    decision_store = loaded
    return decision_store


def final_response(query, topic=None):
    if not _memory_initialized:
        initialize_memory()

    decision_history = get_decision_history(topic) if topic else []
    latest_decision = get_latest_active_decision(topic) if topic else None
    response = rag_answer(query, decision=latest_decision)
    response["decision_history"] = decision_history
    response["latest_active_decision"] = latest_decision

    if latest_decision is not None:
        response["llm_answer"] = response["answer"]
        response["answer"] = (
            f"The latest active decision for {topic} is: "
            f"{latest_decision['decision']}."
        )

    return response
