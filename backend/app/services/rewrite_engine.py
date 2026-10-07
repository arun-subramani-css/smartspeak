"""
AI Rewrite Engine — objective #3: "generate AI-based fluent rewrites of
affected speech segments".

Takes the timestamped mistakes produced by the fusion engine and, for each
QUALIFYING mistake (category "speech" or "compound" carrying a filler_word or
repetition event), rewrites only the flagged transcript clause — never the
whole transcript, never an unflagged span.

Two-stage rewrite per segment:
  1. Deterministic cleanup — strip standalone filler words ("um", "uh") and
     collapse immediately repeated words/phrases.
  2. Grammar/fluency correction via a locally-run T5 seq2seq checkpoint
     (settings.REWRITE_MODEL_NAME, default "vennify/t5-base-grammar-correction").
     No external API, no cost, no data leaves the machine.

Storage shape: a list of RewriteItem(original_segment, rewritten_segment,
mistake_type, timestamp) that is added alongside the transcript inside
fusion_report.rewrites. The transcript itself is never modified.

Graceful degradation (spec'd in STEP 6 of the objective):
  - transformers not installed, checkpoint unavailable/failed to load,
    or rewrites disabled -> empty list (never an exception);
  - per-segment inference failure -> that segment is skipped, the rest
    are still returned.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models.session import RewriteItem

logger = logging.getLogger("smartspeak.rewrite_engine")

# Module-level singleton. None = not loaded yet; False = load failed
# (sentinel so a broken checkpoint is not re-downloaded on every segment).
_rewrite_model_cache = None

# Segment-extraction heuristics. Whisper word timestamps have no reliable
# punctuation at word level, so clause boundaries are approximated by long
# inter-word gaps plus sentence punctuation when present.
_WINDOW_SECONDS = 6.0        # candidate words must start within +/-6s of the mistake
_WORD_GAP_SECONDS = 1.2      # a gap this long marks a clause boundary
_SENTENCE_END = re.compile(r"[.?!]['\"]?$")
_WORD_STRIP = re.compile(r"[^\w']")

# Qualifying event labels carried in MistakeItem.events, e.g.
# "filler_word: um", "repetition: i am", or compounds with an "(x2)" suffix.
_QUALIFIER = re.compile(r"^(filler_word|repetition):")
_COUNT_SUFFIX = re.compile(r"\s*\(x\d+\)$")


def _get_rewrite_model():
    """Load (once) and return the local T5 grammar-correction (tokenizer, model).

    Returns None whenever the model is unusable: settings disabled,
    transformers missing, download/load failed. A failure caches a False
    sentinel so we never retry per segment. Mirrors _get_posture_model().
    """
    global _rewrite_model_cache
    if not settings.REWRITES_ENABLED:
        return None
    if _rewrite_model_cache is None:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            name = settings.REWRITE_MODEL_NAME
            logger.info(
                f"Loading Rewrite Model '{name}' (one-time download, then cached)..."
            )
            tokenizer = AutoTokenizer.from_pretrained(name)
            model = AutoModelForSeq2SeqLM.from_pretrained(name)
            model.eval()
            _rewrite_model_cache = (tokenizer, model)
            logger.info(f"Rewrite Model '{name}' loaded and ready.")
        except Exception as exc:
            logger.warning(f"Rewrite Model unavailable ({exc}); rewrites disabled.")
            _rewrite_model_cache = False
    return _rewrite_model_cache or None


def _qualifying_event(mistake) -> Optional[str]:
    """Return "filler_word" | "repetition" when the mistake qualifies for a
    rewrite, else None.

    Qualifies: category "speech" or "compound" AND its event labels include a
    filler_word or repetition event. long_pause and visual-only events never
    qualify (there is no spoken text to rewrite).
    """
    if getattr(mistake, "category", None) not in ("speech", "compound"):
        return None
    for raw in (getattr(mistake, "events", None) or []):
        label = _COUNT_SUFFIX.sub("", str(raw)).strip()
        match = _QUALIFIER.match(label)
        if match:
            return match.group(1)
    return None


def extract_segment(words: List[Dict[str, Any]], timestamp: float,
                    window_seconds: float = _WINDOW_SECONDS) -> str:
    """Extract the transcript clause around `timestamp` from word-level data.

    `words` are stored WordTimestamp dicts ({word, start, end}). The anchor is
    the word starting closest to the mistake timestamp; the clause then expands
    outward until a sentence-ending word, a >1.2s inter-word gap, or the
    extraction window edge is hit. Returns "" when nothing sensible exists.
    """
    if not words:
        return ""
    lo, hi = timestamp - window_seconds, timestamp + window_seconds
    candidates = [
        (i, w) for i, w in enumerate(words)
        if lo <= float(w.get("start", 0.0)) <= hi
    ]
    if not candidates:
        return ""

    # Anchor: in-window word closest to the mistake timestamp.
    anchor_pos = min(range(len(candidates)),
                     key=lambda k: abs(float(candidates[k][1].get("start", 0.0)) - timestamp))
    anchor_idx = candidates[anchor_pos][0]

    # Expand left: stop at a previous word that ends a sentence, or a long gap.
    left = anchor_idx
    while left > 0:
        prev = words[left - 1]
        if _SENTENCE_END.search(str(prev.get("word", ""))):
            break
        if float(words[left].get("start", 0.0)) - float(prev.get("end", 0.0)) > _WORD_GAP_SECONDS:
            break
        if float(prev.get("start", 0.0)) < lo:
            break
        left -= 1

    # Expand right: include a word that ends a sentence, stop at a long gap.
    right = anchor_idx
    while right < len(words) - 1:
        if _SENTENCE_END.search(str(words[right].get("word", ""))):
            break
        nxt = words[right + 1]
        if float(nxt.get("start", 0.0)) - float(words[right].get("end", 0.0)) > _WORD_GAP_SECONDS:
            break
        if float(nxt.get("start", 0.0)) > hi:
            break
        right += 1

    return " ".join(str(w.get("word", "")).strip() for w in words[left:right + 1]).strip()


def _norm(text: str) -> str:
    """Case/whitespace-normalized comparison key so a change that is only
    capitalization or spacing is not mistaken for a real improvement."""
    return " ".join(text.lower().split())


def _deterministic_clean(segment: str) -> str:
    """Stage 1: rule-based cleanup that needs no model.

    Drops standalone ALWAYS_FILLER tokens ("um", "uh"), collapses adjacent
    duplicate words ("i i am" -> "i am") and immediately repeated phrases
    ("i am i am" -> "i am"), then tidies spacing/capitalization.
    """
    fillers = {str(f).lower() for f in settings.ALWAYS_FILLER}
    tokens = segment.split()

    kept = [t for t in tokens if _WORD_STRIP.sub("", t).lower() not in fillers]

    collapsed: List[str] = []
    for t in kept:
        if collapsed and _WORD_STRIP.sub("", t).lower() == _WORD_STRIP.sub("", collapsed[-1]).lower():
            continue
        collapsed.append(t)

    text = " ".join(collapsed)

    # Collapse immediately repeated n-grams ("i am i am" -> "i am"), to fixpoint.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\b((?:\w+[ ']+)+\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+([,.!?])", r"\1", text).strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


def _correct_with_model(text: str, tokenizer, model) -> Optional[str]:
    """Stage 2: T5 grammar/fluency correction. Returns None on any failure so
    the caller keeps the deterministic result."""
    try:
        import torch

        inputs = tokenizer(
            f"{settings.REWRITE_MODEL_INPUT_PREFIX}{text}",
            return_tensors="pt",
            truncation=True,
            max_length=128,
        )
        with torch.no_grad():
            output_ids = model.generate(
                **inputs, max_length=128, num_beams=4, early_stopping=True
            )
        corrected = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
        return corrected or None
    except Exception as exc:
        logger.warning(f"Rewrite model inference failed: {exc}")
        return None


def generate_rewrites(
    speech_analysis: Optional[Dict[str, Any]],
    mistakes: List[Any],
) -> List[RewriteItem]:
    """Produce one RewriteItem per qualifying mistake (deduped per clause).

    Contract (STEP 3/6 of the objective):
      - only mistakes with category "speech"/"compound" carrying a filler_word
        or repetition event are rewritten;
      - the input speech_analysis (the transcript) is read-only;
      - empty list — never an exception — when the rewrite model is
        unavailable, disabled, or no qualifying segments exist.
    """
    if not speech_analysis or not mistakes:
        return []
    words = speech_analysis.get("words") or []
    if not words:
        return []

    model_pair = _get_rewrite_model()
    if model_pair is None:
        # Model unavailable/disabled: graceful empty output, no crash.
        return []
    tokenizer, model = model_pair

    rewrites: List[RewriteItem] = []
    seen_segments = set()
    for mistake in mistakes:
        mistake_type = _qualifying_event(mistake)
        if mistake_type is None:
            continue

        original = extract_segment(words, float(mistake.timestamp))
        if not original or original.lower() in seen_segments:
            continue
        seen_segments.add(original.lower())

        rewritten = _deterministic_clean(original)
        if tokenizer is not None:
            corrected = _correct_with_model(rewritten, tokenizer, model)
            # Keep the model output only when it differs from the original text
            # (a model that echoes input back must not undo stage-1 cleanup).
            if corrected and _norm(corrected) != _norm(original):
                rewritten = corrected

        # Emit nothing when the rewrite is empty (e.g. the whole clause was
        # fillers) or not a genuine improvement over the original.
        if not rewritten.strip() or _norm(rewritten) == _norm(original):
            continue

        rewrites.append(RewriteItem(
            original_segment=original,
            rewritten_segment=rewritten,
            mistake_type=mistake_type,
            timestamp=round(float(mistake.timestamp), 2),
        ))
    return rewrites
