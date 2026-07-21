import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import List, Tuple

from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import (
    FillerWordItem,
    PauseItem,
    RepetitionItem,
    SessionStatus,
    SpeechAnalysisResult,
    WindowedWPM,
    WordTimestamp,
    WPMData,
)

logger = logging.getLogger(__name__)

# Global cached Whisper model instance to avoid re-loading weights on every call
_whisper_model_cache = {}


def _get_whisper_model(model_name: str):
    """
    ENGINE TRADEOFF NOTE:
    - openai-whisper: Official PyTorch implementation by OpenAI. Highly reliable, standard, cross-platform.
    - faster-whisper: CTranslate2 re-implementation. Up to 4x faster and uses ~50% less memory.
    We use openai-whisper with model size specified by settings.WHISPER_MODEL (default: 'base').
    """
    if model_name not in _whisper_model_cache:
        import whisper
        logger.info(f"Loading Whisper model '{model_name}' into memory...")
        _whisper_model_cache[model_name] = whisper.load_model(model_name)
    return _whisper_model_cache[model_name]


def clean_text(word: str) -> str:
    """Normalize word text by stripping punctuation and converting to lowercase."""
    return re.sub(r"[^\w\s']", "", word.strip().lower())


def transcribe_audio_sync(audio_path: Path, model_name: str) -> Tuple[str, List[WordTimestamp]]:
    """
    Synchronous Whisper transcription returning full text and word-level timestamps.
    Handles silent or music-only audio files gracefully.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found at {audio_path}")

    model = _get_whisper_model(model_name)
    result = model.transcribe(str(audio_path), word_timestamps=True)

    transcript_text = result.get("text", "").strip()
    words_data: List[WordTimestamp] = []

    segments = result.get("segments", [])
    for segment in segments:
        segment_words = segment.get("words", [])
        for w in segment_words:
            w_text = w.get("word", "").strip()
            if not w_text:
                continue
            words_data.append(
                WordTimestamp(
                    word=w_text,
                    start=float(w.get("start", 0.0)),
                    end=float(w.get("end", 0.0)),
                    probability=float(w.get("probability")) if w.get("probability") is not None else None
                )
            )

    return transcript_text, words_data


def detect_filler_words(words: List[WordTimestamp], filler_list: List[str]) -> Tuple[List[FillerWordItem], int]:
    """
    Detects single-word and multi-word filler phrases from word-level timestamps.
    """
    detected: List[FillerWordItem] = []
    if not words or not filler_list:
        return [], 0

    single_fillers = {f.lower() for f in filler_list if " " not in f}
    multi_fillers = [f.lower().split() for f in filler_list if " " in f]

    cleaned_words = [clean_text(w.word) for w in words]
    used_indices = set()

    # 1. Detect multi-word filler phrases (e.g. "you know")
    for phrase_tokens in multi_fillers:
        phrase_len = len(phrase_tokens)
        phrase_str = " ".join(phrase_tokens)
        for i in range(len(cleaned_words) - phrase_len + 1):
            if any(idx in used_indices for idx in range(i, i + phrase_len)):
                continue
            if cleaned_words[i: i + phrase_len] == phrase_tokens:
                detected.append(
                    FillerWordItem(
                        word=phrase_str,
                        timestamp=round(words[i].start, 2)
                    )
                )
                for idx in range(i, i + phrase_len):
                    used_indices.add(idx)

    # 2. Detect single-word fillers (e.g. "um", "uh", "like")
    for i, w in enumerate(words):
        if i in used_indices:
            continue
        cleaned = cleaned_words[i]
        if cleaned in single_fillers:
            detected.append(
                FillerWordItem(
                    word=cleaned,
                    timestamp=round(w.start, 2)
                )
            )

    # Sort filler occurrences chronologically by timestamp
    detected.sort(key=lambda item: item.timestamp)
    return detected, len(detected)


def calculate_wpm_data(
    words: List[WordTimestamp],
    window_seconds: float = 15.0,
    step_seconds: float = 5.0,
    long_pause_threshold: float = 3.0
) -> WPMData:
    """
    Calculates overall WPM (excluding long silences) and rolling windowed WPM.
    """
    total_words = len(words)
    if total_words == 0:
        return WPMData(
            overall_wpm=0.0,
            total_words=0,
            total_speaking_duration_seconds=0.0,
            windowed_wpm=[]
        )

    # Calculate total speaking duration (subtracting long pauses > long_pause_threshold)
    first_start = words[0].start
    last_end = words[-1].end
    raw_duration = max(0.1, last_end - first_start)

    long_pauses_total = 0.0
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap >= long_pause_threshold:
            long_pauses_total += gap

    actual_speaking_duration = max(0.1, raw_duration - long_pauses_total)
    overall_wpm = round((total_words / (actual_speaking_duration / 60.0)), 1)

    # Rolling windowed WPM
    windowed_wpm_list: List[WindowedWPM] = []
    max_time = last_end

    t = 0.0
    while t < max_time:
        win_end = t + window_seconds
        w_count = sum(1 for w in words if t <= w.start < win_end)
        wpm_val = round((w_count / (window_seconds / 60.0)), 1)
        windowed_wpm_list.append(
            WindowedWPM(
                window_start=round(t, 1),
                window_end=round(win_end, 1),
                wpm=wpm_val
            )
        )
        t += step_seconds

    return WPMData(
        overall_wpm=overall_wpm,
        total_words=total_words,
        total_speaking_duration_seconds=round(actual_speaking_duration, 2),
        windowed_wpm=windowed_wpm_list
    )


def detect_long_pauses(words: List[WordTimestamp], threshold: float = 3.0) -> List[PauseItem]:
    """
    Detects gaps between consecutive spoken words exceeding the threshold in seconds.
    """
    pauses: List[PauseItem] = []
    if len(words) < 2:
        return pauses

    for i in range(len(words) - 1):
        start_time = words[i].end
        end_time = words[i + 1].start
        gap = end_time - start_time
        if gap >= threshold:
            pauses.append(
                PauseItem(
                    start_time=round(start_time, 2),
                    end_time=round(end_time, 2),
                    duration=round(gap, 2)
                )
            )

    return pauses


def detect_repetitions(words: List[WordTimestamp]) -> List[RepetitionItem]:
    """
    Detects immediate single word repetitions and 2-4 word repeated phrase sequences.
    """
    repetitions: List[RepetitionItem] = []
    if len(words) < 2:
        return repetitions

    cleaned_words = [clean_text(w.word) for w in words]
    n = len(cleaned_words)
    seen_ranges = set()

    # 1. Immediate single-word repetitions (e.g. "the the")
    i = 0
    while i < n - 1:
        if cleaned_words[i] and cleaned_words[i] == cleaned_words[i + 1]:
            count = 2
            j = i + 1
            while j < n - 1 and cleaned_words[j] == cleaned_words[j + 1]:
                count += 1
                j += 1
            repetitions.append(
                RepetitionItem(
                    phrase=cleaned_words[i],
                    timestamp=round(words[i].start, 2),
                    count=count
                )
            )
            for idx in range(i, j + 1):
                seen_ranges.add(idx)
            i = j + 1
        else:
            i += 1

    # 2. Repeated phrase sequences (2 to 4 words) within a short window (10s)
    for phrase_length in range(2, 5):
        for idx in range(n - (phrase_length * 2) + 1):
            if any(k in seen_ranges for k in range(idx, idx + phrase_length)):
                continue

            phrase_tokens = cleaned_words[idx: idx + phrase_length]
            if not all(phrase_tokens):
                continue
            phrase_str = " ".join(phrase_tokens)

            # Look ahead within 10 seconds for repetition
            window_limit = words[idx].start + 10.0
            next_idx = idx + phrase_length
            while next_idx <= n - phrase_length and words[next_idx].start <= window_limit:
                if cleaned_words[next_idx: next_idx + phrase_length] == phrase_tokens:
                    repetitions.append(
                        RepetitionItem(
                            phrase=phrase_str,
                            timestamp=round(words[idx].start, 2),
                            count=2
                        )
                    )
                    break
                next_idx += 1

    repetitions.sort(key=lambda r: r.timestamp)
    return repetitions


async def process_speech_analysis_session(session_id: str) -> bool:
    """
    Background worker function for speech analysis.
    Offloads synchronous Whisper transcription to thread pool executor to avoid blocking asyncio event loop.
    Updates MongoDB session document with speech_analysis sub-document.
    """
    sessions_col = MongoDB.get_collection("sessions")

    session_doc = await sessions_col.find_one({"session_id": session_id})
    if not session_doc:
        logger.error(f"[{session_id}] Session not found for speech analysis.")
        return False

    # Mark status as processing during speech analysis
    await sessions_col.update_one(
        {"session_id": session_id},
        {"$set": {"status": SessionStatus.PROCESSING}}
    )

    try:
        audio_rel_path = session_doc.get("audio_path")
        if not audio_rel_path:
            audio_path = settings.processed_dir / session_id / "audio.wav"
        else:
            audio_path = settings.base_storage_path / audio_rel_path

        if not audio_path.exists():
            raise FileNotFoundError(f"Processed audio file missing at {audio_path}")

        logger.info(f"[{session_id}] Running Whisper STT offloaded to thread pool executor...")
        loop = asyncio.get_running_loop()

        # Offload synchronous Whisper transcription to thread pool executor
        transcript_text, words = await loop.run_in_executor(
            None,
            transcribe_audio_sync,
            audio_path,
            settings.WHISPER_MODEL
        )

        logger.info(f"[{session_id}] Whisper transcription completed ({len(words)} words transcribed).")

        # Run analysis algorithms
        filler_words, filler_count = detect_filler_words(words, settings.FILLER_WORDS)
        wpm_data = calculate_wpm_data(
            words,
            window_seconds=settings.WPM_WINDOW_SECONDS,
            step_seconds=settings.WPM_WINDOW_STEP_SECONDS,
            long_pause_threshold=settings.LONG_PAUSE_THRESHOLD_SECONDS
        )
        long_pauses = detect_long_pauses(words, threshold=settings.LONG_PAUSE_THRESHOLD_SECONDS)
        repetitions = detect_repetitions(words)

        analysis_result = SpeechAnalysisResult(
            transcript_text=transcript_text,
            words=words,
            filler_words=filler_words,
            filler_word_count=filler_count,
            wpm_data=wpm_data,
            long_pauses=long_pauses,
            repetitions=repetitions,
            analyzed_at=datetime.now(timezone.utc)
        )

        # Overwrite speech_analysis sub-document and update status
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "speech_analysis": analysis_result.model_dump(),
                    "status": SessionStatus.SPEECH_ANALYSIS_COMPLETE,
                    "error_reason": None
                }
            }
        )

        logger.info(f"[{session_id}] Speech analysis complete and stored in MongoDB.")
        return True

    except Exception as exc:
        err_reason = str(exc)
        logger.exception(f"[{session_id}] Speech analysis failed: {err_reason}")
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.FAILED,
                    "error_reason": f"Speech Analysis Error: {err_reason}"
                }
            }
        )
        return False
