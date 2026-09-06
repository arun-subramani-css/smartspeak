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

# Global cached instances to avoid re-loading weights on every call
_whisper_model_cache = {}
_spacy_nlp_cache = None


def get_spacy_nlp():
    """Load and cache spaCy English model for POS-tagging."""
    global _spacy_nlp_cache
    if _spacy_nlp_cache is None:
        try:
            import spacy
            _spacy_nlp_cache = spacy.load("en_core_web_sm")
            logger.info("spaCy 'en_core_web_sm' model loaded into memory.")
        except Exception as e:
            logger.warning(f"Could not load spaCy model en_core_web_sm: {e}")
            _spacy_nlp_cache = False
    return _spacy_nlp_cache if _spacy_nlp_cache is not False else None


def _get_whisper_model(model_name: str):
    """
    ENGINE TRADEOFF NOTE:
    - openai-whisper: Official PyTorch implementation by OpenAI. Highly reliable, standard, cross-platform.
    - faster-whisper: CTranslate2 re-implementation. Up to 4x faster and uses ~50% less memory.
      (Note: If faster-whisper is used, set vad_filter=False or min_silence_duration_ms=1000 to avoid stripping short filler bursts like 'um').
    We use openai-whisper with model size specified by settings.WHISPER_MODEL (default: 'base').
    """
    if model_name not in _whisper_model_cache:
        import whisper
        logger.info(f"Loading Whisper model '{model_name}' into memory...")
        _whisper_model_cache[model_name] = whisper.load_model(model_name)
    return _whisper_model_cache[model_name]


def clean_text(word: str) -> str:
    """Normalize word text by stripping punctuation and converting to lowercase."""
    return re.sub(r"[^\w\s']", "", word.strip()).lower()


def classify_filler_context(word_text: str, pos_tag: str, surrounding_text: str = "") -> bool:
    """
    Determines if a contextual word ("like", "actually", "basically", "you know")
    is acting as a filler word or as a legitimate grammatical part of speech.
    - ALWAYS_FILLER ("um", "uh") skip this check and always return True.
    - "like": Flagged ONLY when NOT a verb (VERB) or preposition (ADP/SCONJ).
    - "actually" / "basically": Flagged ONLY when standalone sentence openers or set off by commas.
    """
    word_clean = clean_text(word_text)
    always_set = {clean_text(w) for w in settings.ALWAYS_FILLER}

    # ALWAYS_FILLER words always flag, no exceptions
    if word_clean in always_set:
        return True

    pos_upper = pos_tag.upper() if pos_tag else ""

    if word_clean == "like":
        # Do NOT flag "like" if it's used as a verb ("I like your project") or preposition ("looks like a cat")
        if pos_upper in ["VERB", "ADP", "SCONJ"]:
            return False
        # Flag if tagged as interjection/discourse marker (INTJ), adverb (ADV), particle (PART), or set off by commas
        if pos_upper in ["INTJ", "ADV", "PART", "X"]:
            return True
        if re.search(r",\s*like\b|\blike\s*,", surrounding_text, re.IGNORECASE):
            return True
        # Fallback: if not explicitly a verb or preposition, treat as filler
        return True

    if word_clean in ["actually", "basically"]:
        # Flag only when standalone sentence opener or set off by commas, not when integrated grammatically ("that's actually correct")
        if pos_upper in ["INTJ", "X"]:
            return True
        if re.search(r"(?:^|[.!?,\n])\s*(?:actually|basically)\b|\b(?:actually|basically)\s*,", surrounding_text, re.IGNORECASE):
            return True
        return False

    if word_clean == "you know":
        if pos_upper in ["INTJ", "X"] or re.search(r",\s*you know\b|\byou know\s*,", surrounding_text, re.IGNORECASE):
            return True
        return True

    return False


def transcribe_audio_sync(audio_path: Path, model_name: str) -> Tuple[str, List[WordTimestamp]]:
    """
    Synchronous Whisper transcription returning full text and word-level timestamps.
    Biases transcription toward filler words verbatim using initial_prompt and condition_on_previous_text=False.
    Robustly handles PyTorch 2.x timing hook exceptions with segment-level fallback.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found at {audio_path}")

    model = _get_whisper_model(model_name)

    try:
        result = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            initial_prompt="Um, uh, so, like, you know, basically...",
            condition_on_previous_text=False
        )
    except Exception as exc:
        logger.warning(f"Whisper word_timestamps=True failed ({exc}); falling back to segment-level transcription.")
        result = model.transcribe(
            str(audio_path),
            word_timestamps=False,
            initial_prompt="Um, uh, so, like, you know, basically...",
            condition_on_previous_text=False
        )

    transcript_text = result.get("text", "").strip()
    words_data: List[WordTimestamp] = []

    segments = result.get("segments", [])
    for segment in segments:
        seg_start = float(segment.get("start", 0.0))
        seg_end = float(segment.get("end", 0.0))
        segment_words = segment.get("words", [])

        if segment_words:
            for w in segment_words:
                w_text = w.get("word", "").strip()
                if not w_text:
                    continue
                words_data.append(
                    WordTimestamp(
                        word=w_text,
                        start=float(w.get("start", seg_start)),
                        end=float(w.get("end", seg_end)),
                        probability=float(w.get("probability")) if w.get("probability") is not None else None
                    )
                )
        else:
            # Estimate word timestamps evenly across segment if word_timestamps array is missing
            tokens = segment.get("text", "").strip().split()
            if tokens:
                duration = max(0.1, seg_end - seg_start)
                step = duration / len(tokens)
                for idx, t in enumerate(tokens):
                    words_data.append(
                        WordTimestamp(
                            word=t,
                            start=round(seg_start + idx * step, 2),
                            end=round(seg_start + (idx + 1) * step, 2),
                            probability=1.0
                        )
                    )

    return transcript_text, words_data


def detect_filler_words(words: List[WordTimestamp], filler_list: List[str] = None) -> Tuple[List[FillerWordItem], int]:
    """
    Detects single-word and multi-word filler phrases from word-level timestamps.
    ALWAYS_FILLER words ('um', 'uh') are always flagged.
    CONTEXTUAL_FILLER words ('like', 'actually', 'basically', 'you know') use spaCy POS-tagging context rules.
    """
    if filler_list is None:
        filler_list = settings.FILLER_WORDS

    detected: List[FillerWordItem] = []
    if not words or not filler_list:
        return [], 0

    always_fillers = {clean_text(f) for f in settings.ALWAYS_FILLER}
    contextual_fillers = {clean_text(f) for f in settings.CONTEXTUAL_FILLER}
    multi_fillers = [[clean_text(t) for t in f.split()] for f in filler_list if " " in f]

    # Build full transcript sentence and run spaCy POS-tagger if available
    full_sentence = " ".join(w.word for w in words)
    nlp = get_spacy_nlp()

    word_pos_map = {}
    if nlp and full_sentence:
        try:
            doc = nlp(full_sentence)
            for token in doc:
                word_pos_map[token.i] = token.pos_
        except Exception as e:
            logger.warning(f"spaCy POS-tagging error: {e}")

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
                pos_tag = word_pos_map.get(i, "")
                surrounding = " ".join(w.word for w in words[max(0, i-2): min(len(words), i+phrase_len+2)])
                if classify_filler_context(phrase_str, pos_tag, surrounding):
                    detected.append(
                        FillerWordItem(
                            word=phrase_str,
                            timestamp=round(words[i].start, 2)
                        )
                    )
                    for idx in range(i, i + phrase_len):
                        used_indices.add(idx)

    # 2. Detect single-word fillers (ALWAYS_FILLER and CONTEXTUAL_FILLER)
    for i, w in enumerate(words):
        if i in used_indices:
            continue
        cleaned = cleaned_words[i]

        # ALWAYS_FILLER: Flag immediately without POS check
        if cleaned in always_fillers:
            detected.append(
                FillerWordItem(
                    word=cleaned,
                    timestamp=round(w.start, 2)
                )
            )
            used_indices.add(i)
        # CONTEXTUAL_FILLER: Apply POS tag and context classification
        elif cleaned in contextual_fillers:
            pos_tag = word_pos_map.get(i, "")
            surrounding = " ".join(word_obj.word for word_obj in words[max(0, i-2): min(len(words), i+3)])
            if classify_filler_context(w.word, pos_tag, surrounding):
                detected.append(
                    FillerWordItem(
                        word=cleaned,
                        timestamp=round(w.start, 2)
                    )
                )
                used_indices.add(i)

    detected.sort(key=lambda item: item.timestamp)
    return detected, len(detected)


def calculate_wpm_data(
    words: List[WordTimestamp],
    window_seconds: float = 15.0,
    step_seconds: float = 5.0,
    long_pause_threshold: float = None
) -> WPMData:
    """
    Calculates overall WPM (excluding long silences) and rolling windowed WPM.
    """
    if long_pause_threshold is None:
        long_pause_threshold = settings.LONG_PAUSE_THRESHOLD_SECONDS

    total_words = len(words)
    if total_words == 0:
        return WPMData(
            overall_wpm=0.0,
            total_words=0,
            total_speaking_duration_seconds=0.0,
            windowed_wpm=[]
        )

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


def detect_long_pauses(words: List[WordTimestamp], threshold: float = None) -> List[PauseItem]:
    """
    Detects gaps between consecutive spoken words exceeding the threshold in seconds (default: 2.0s).
    """
    if threshold is None:
        threshold = settings.LONG_PAUSE_THRESHOLD_SECONDS

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
        matches = list(settings.staging_dir.glob(f"{session_id}.*"))
        if matches:
            staging_file = matches[0]
            ext = staging_file.suffix
            session_doc = {
                "session_id": session_id,
                "original_filename": f"video{ext}",
                "upload_timestamp": datetime.now(timezone.utc),
                "file_size": staging_file.stat().st_size,
                "content_type": f"video/{ext.lstrip('.')}",
                "status": SessionStatus.PROCESSING,
                "file_path": str(staging_file)
            }
            await sessions_col.insert_one(session_doc)
            logger.info(f"Auto-recovered speech session document in DB for {session_id}")
        else:
            logger.error(f"[{session_id}] Session not found for speech analysis.")
            return False

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

        transcript_text, words = await loop.run_in_executor(
            None,
            transcribe_audio_sync,
            audio_path,
            settings.WHISPER_MODEL
        )

        logger.info(f"[{session_id}] Raw Whisper transcript: '{transcript_text}'")
        logger.info(f"[{session_id}] Extracted word tokens ({len(words)}): {[w.word for w in words]}")

        filler_words, filler_count = detect_filler_words(words, settings.FILLER_WORDS)
        wpm_data = calculate_wpm_data(
            words,
            window_seconds=settings.WPM_WINDOW_SECONDS,
            step_seconds=settings.WPM_WINDOW_STEP_SECONDS,
            long_pause_threshold=settings.LONG_PAUSE_THRESHOLD_SECONDS
        )
        long_pauses = detect_long_pauses(words, threshold=settings.LONG_PAUSE_THRESHOLD_SECONDS)
        repetitions = detect_repetitions(words)

        logger.info(f"[{session_id}] Filler detection result: {filler_count} fillers found -> {[f.model_dump() for f in filler_words]}")

        valid_probs = [w.probability for w in words if w.probability is not None]
        avg_confidence = round(sum(valid_probs) / len(valid_probs), 4) if valid_probs else None

        analysis_result = SpeechAnalysisResult(
            transcript_text=transcript_text,
            words=words,
            filler_words=filler_words,
            filler_word_count=filler_count,
            wpm_data=wpm_data,
            long_pauses=long_pauses,
            repetitions=repetitions,
            analyzed_at=datetime.now(timezone.utc),
            average_transcription_confidence=avg_confidence
        )

        speech_dict = analysis_result.model_dump(mode="json")

        # Atomic symmetric update: check if visual_analysis is already present in DB
        res = await sessions_col.update_one(
            {
                "session_id": session_id,
                "visual_analysis": {"$ne": None}
            },
            {
                "$set": {
                    "speech_analysis": speech_dict,
                    "status": SessionStatus.READY_FOR_FUSION,
                    "error_reason": None
                }
            }
        )

        if res.modified_count == 0:
            # Visual analysis is not completed yet, set status to SPEECH_ANALYSIS_COMPLETE
            await sessions_col.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "speech_analysis": speech_dict,
                        "status": SessionStatus.SPEECH_ANALYSIS_COMPLETE,
                        "error_reason": None
                    }
                }
            )

        logger.info(
            f"[{session_id}] Speech analysis complete and stored in MongoDB.\n"
            f"  -> Average Transcription (STT) Confidence: {avg_confidence if avg_confidence is not None else 'N/A'}"
        )
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
