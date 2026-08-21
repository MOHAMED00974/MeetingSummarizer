import os
from pydub import AudioSegment
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from dotenv import load_dotenv


load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

HF_TOKEN = os.environ.get("HF_TOKEN")

_WHISPER_MODEL_SIZE = "small"
_WHISPER_MODEL = None
_DIARIZATION_PIPELINE = None


def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = WhisperModel(
            _WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )
    return _WHISPER_MODEL


def get_diarization_pipeline():
    global _DIARIZATION_PIPELINE
    if _DIARIZATION_PIPELINE is None:
        if not HF_TOKEN:
            raise RuntimeError(
                "HF_TOKEN is not configured for speaker diarization."
            )
        _DIARIZATION_PIPELINE = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN,
        )
    return _DIARIZATION_PIPELINE


def import_audio(path:str)-> bool:
    '''
    if the path for the selected audio exists it will return True, else False
    '''
    return True if os.path.exists(path) else False

def preprocess_audio(
    input_path: str,
    output_path: str = "processed_audio.wav"
) -> str:
    """
    Convert an audio/video file to:
    - WAV
    - 16 kHz sample rate
    - Mono channel

    Returns:
        Path to the processed audio file.
    """

    audio = AudioSegment.from_file(input_path)

    audio = (
        audio
        .set_frame_rate(16000)
        .set_channels(1)
    )

    audio.export(output_path, format="wav")

    return output_path

def asr(audio_path: str):
    """
    Run ASR and return segment-level transcription.

    Output format:
    {
        "text": "...",
        "start": 0.0,
        "end": 2.5
    }
    """

    segments_gen, info = get_whisper_model().transcribe(
        audio_path,
        vad_filter=True,
        word_timestamps=False
    )

    segments = []

    for seg in segments_gen:
        text = seg.text.strip()

        if text:
            segments.append({
                "text": text,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2)
            })

    return segments, info

def run_diarization(audio_path: str):
    """
    Run speaker diarization.

    Returns:
        List of dictionaries containing:
        - speaker_id
        - start
        - end
    """

    output = get_diarization_pipeline()(audio_path)

    # Community-1 returns a DiarizeOutput object.
    # We use exclusive diarization because it is designed
    # to simplify alignment with transcription timestamps.
    diarization = output.exclusive_speaker_diarization

    diar_segments = []

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        diar_segments.append({
            "speaker_id": speaker,
            "start": round(turn.start, 2),
            "end": round(turn.end, 2)
        })

    return diar_segments

def assign_speaker(
    asr_start: float,
    asr_end: float,
    diar_segments: list,
    min_overlap_ratio: float = 0.2
) -> str:
    """
    Assign the speaker with the greatest temporal overlap
    with the ASR segment.

    Returns:
        Speaker ID or UNKNOWN if the overlap is too weak.
    """

    asr_duration = asr_end - asr_start

    if asr_duration <= 0:
        return "UNKNOWN"

    best_speaker = "UNKNOWN"
    best_overlap = 0.0

    for d in diar_segments:

        overlap_start = max(asr_start, d["start"])
        overlap_end = min(asr_end, d["end"])

        overlap = max(
            0.0,
            overlap_end - overlap_start
        )

        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = d["speaker_id"]

    overlap_ratio = best_overlap / asr_duration

    if overlap_ratio < min_overlap_ratio:
        return "UNKNOWN"

    return best_speaker

def build_structured_transcript(
    meeting_id: str,
    asr_segments: list,
    diar_segments: list
) -> dict:
    """
    Merge ASR and diarization results into the
    Member 1 structured transcript contract.
    """

    segments = []

    for seg in asr_segments:

        speaker_id = assign_speaker(
            asr_start=seg["start"],
            asr_end=seg["end"],
            diar_segments=diar_segments
        )

        segments.append({
            "speaker_id": speaker_id,
            "speaker_name": speaker_id,
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"]
        })

    return {
        "meeting_id": meeting_id,
        "segments": segments
    }

def apply_speaker_names(transcript: dict, name_map: dict) -> dict:
    """
    Apply speaker names to a structured transcript
    without modifying the original transcript.

    Parameters:
        transcript:
            Structured transcript produced by Cell 6.

        name_map:
            Mapping from diarization speaker IDs to human-readable names.

            Example:
            {
                "SPEAKER_00": "Ahmed",
                "SPEAKER_01": "Mohamed"
            }

    Returns:
        A new transcript containing speaker_name for each segment.

    If a speaker is not present in name_map, the original
    speaker_id is kept as speaker_name.
    """

    mapped_transcript = {
        **transcript,
        "segments": []
    }

    for seg in transcript["segments"]:

        mapped_segment = {
            **seg,
            "speaker_name": name_map.get(
                seg["speaker_id"],
                seg["speaker_id"]
            )
        }

        mapped_transcript["segments"].append(mapped_segment)

    return mapped_transcript

def full_pipeline(input_audio_path: str, meeting_id: str, speaker_name_map: dict = None) -> dict:
    """
    Full Member 1 pipeline: raw audio/video -> structured transcript JSON.
    This is the single entry point Member 4's FastAPI backend will call
    when a user uploads a meeting recording.
    """
    input_path = os.path.abspath(input_audio_path)
    processed_path = os.path.join(
        os.path.dirname(input_path),
        f"processed_{os.path.splitext(os.path.basename(input_path))[0]}.wav",
    )
    processed = preprocess_audio(input_path, processed_path)
    asr_segs, _ = asr(processed)
    diar_segs = run_diarization(processed)
    transcript = build_structured_transcript(meeting_id, asr_segs, diar_segs)

    if speaker_name_map:
        transcript = apply_speaker_names(transcript, speaker_name_map)

    return transcript