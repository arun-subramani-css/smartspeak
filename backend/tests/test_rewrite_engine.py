"""Tests for the AI Rewrite Engine (objective #3).

All model interaction is stubbed — no network, no checkpoint download. The
suite verifies the generation contract from the build spec:

  1. rewrites are produced ONLY for qualifying mistake types
     (speech/compound carrying a filler_word or repetition event);
  2. the original transcript (speech_analysis) is never modified;
  3. missing/failed rewrite generation degrades gracefully to an empty
     list — never an exception.
"""
import copy

import pytest

from app.services.rewrite_engine import (
    _get_rewrite_model,
    _qualifying_event,
    extract_segment,
    generate_rewrites,
)
from app.models.session import FusionReportResult, MistakeItem, RewriteItem


# ---- Fixtures ---------------------------------------------------------------

WORDS = [
    {"word": "um", "start": 5.0, "end": 5.3},
    {"word": "so", "start": 5.4, "end": 5.8},
    {"word": "i", "start": 5.9, "end": 6.0},
    {"word": "am", "start": 6.1, "end": 6.3},
    {"word": "going", "start": 6.4, "end": 6.9},
    {"word": "there.", "start": 7.0, "end": 7.4},
    {"word": "and", "start": 12.0, "end": 12.1},   # separate clause (>1.2s gap)
    {"word": "uh", "start": 12.2, "end": 12.4},
    {"word": "stuff.", "start": 12.5, "end": 13.0},
]

SPEECH = {"words": WORDS}


def mistake(ts, category, events):
    return MistakeItem(
        timestamp=ts, category=category, description="x", severity="minor", events=events
    )


@pytest.fixture
def fake_model(monkeypatch):
    """Stub the T5 pair: the tokenizer echoes a 'grammar:' prefix stripped,
    the model output is controlled per-test via the returned dict."""
    state = {"output": "So I am going there."}

    class FakeTokenizer:
        def __call__(self, text, **kwargs):
            assert text.startswith("grammar: "), "checkpoint task prefix must be applied"
            return {"input_ids": [1]}

        def decode(self, ids, **kwargs):
            return state["output"]

    class FakeModel:
        def eval(self):
            return self

        def generate(self, **kwargs):
            return [[2]]

    monkeypatch.setattr(
        "app.services.rewrite_engine._rewrite_model_cache",
        (FakeTokenizer(), FakeModel()),
    )
    return state


# ---- Qualification rules ----------------------------------------------------

def test_qualifying_event_rules():
    assert _qualifying_event(mistake(5.0, "speech", ["filler_word: um"])) == "filler_word"
    assert _qualifying_event(mistake(5.0, "speech", ["repetition: i am (x2)"])) == "repetition"
    assert _qualifying_event(
        mistake(5.0, "compound", ["filler_word: um", "looking_down"])
    ) == "filler_word"
    assert _qualifying_event(mistake(5.0, "speech", ["long_pause: 2.0s"])) is None
    assert _qualifying_event(mistake(5.0, "visual", ["looking_down"])) is None
    assert _qualifying_event(
        mistake(5.0, "compound", ["long_pause: 2.0s", "looking_down"])
    ) is None
    assert _qualifying_event(mistake(5.0, "speech", None)) is None


# ---- Rewrites are only generated for qualifying mistakes --------------------

def test_generates_rewrites_for_qualifying_mistakes(fake_model):
    mistakes = [
        mistake(6.2, "speech", ["filler_word: um"]),
        mistake(12.3, "compound", ["repetition: uh", "looking_down"]),
    ]
    rewrites = generate_rewrites(SPEECH, mistakes)
    assert len(rewrites) == 2
    for r, m in zip(rewrites, mistakes):
        assert isinstance(r, RewriteItem)
        assert r.original_segment and r.rewritten_segment
        assert r.mistake_type in ("filler_word", "repetition")
        assert r.timestamp == pytest.approx(m.timestamp, abs=0.01)


def test_skips_non_qualifying_mistakes(fake_model):
    mistakes = [
        mistake(6.2, "speech", ["long_pause: 2.5s"]),
        mistake(6.2, "visual", ["looking_down"]),
        mistake(6.2, "compound", ["long_pause: 2.5s", "poor_posture"]),
    ]
    assert generate_rewrites(SPEECH, mistakes) == []


def test_only_flagged_spans_are_rewritten(fake_model):
    """A qualifying mistake must yield exactly one rewrite for exactly the
    clause around its timestamp — nothing else in the transcript is touched."""
    mistakes = [mistake(6.2, "speech", ["filler_word: um"])]
    rewrites = generate_rewrites(SPEECH, mistakes)
    assert len(rewrites) == 1
    assert rewrites[0].original_segment == "um so i am going there."
    # The later, separate clause is not part of the flagged span.
    assert "stuff" not in rewrites[0].original_segment
    # Stage 1 dropped the filler; stage 2 (stub) applied its correction.
    assert rewrites[0].rewritten_segment == "So I am going there."


def test_duplicate_clause_segments_are_deduped(fake_model):
    mistakes = [
        mistake(6.2, "speech", ["filler_word: um"]),
        mistake(6.3, "speech", ["filler_word: um"]),
    ]
    rewrites = generate_rewrites(SPEECH, mistakes)
    assert len(rewrites) == 1


def test_noop_suggestion_is_not_emitted(monkeypatch):
    """If the stubbed model just echoes the original text and stage 1 finds
    nothing to clean, no pointless suggestion is stored."""
    monkeypatch.setattr(
        "app.services.rewrite_engine._rewrite_model_cache",
        (None, None),  # tokenizer None -> model stage skipped
    )
    # Speech with no fillers/duplicates: cleaned text == original.
    words = [{"word": "all", "start": 5.0, "end": 5.3},
             {"word": "good.", "start": 5.4, "end": 5.8}]
    mistakes = [mistake(5.2, "speech", ["filler_word: um"])]
    # NOTE: the filler_word event qualifies, but there is no "um" in the words;
    # stage 1 cannot improve it and the (None) tokenizer skips the model stage.
    assert generate_rewrites({"words": words}, mistakes) == []


# ---- Transcript immutability ------------------------------------------------

def test_speech_analysis_is_never_modified(fake_model):
    original = copy.deepcopy(SPEECH)
    mistakes = [
        mistake(6.2, "speech", ["filler_word: um"]),
        mistake(6.2, "compound", ["repetition: i am", "looking_down"]),
    ]
    generate_rewrites(SPEECH, mistakes)
    assert SPEECH == original


# ---- Graceful degradation ---------------------------------------------------

def test_no_words_returns_empty(fake_model):
    assert generate_rewrites({"words": []}, [mistake(6.2, "speech", ["filler_word: um"])]) == []


def test_missing_speech_analysis_returns_empty(fake_model):
    assert generate_rewrites(None, [mistake(6.2, "speech", ["filler_word: um"])]) == []


def test_model_unavailable_returns_empty_not_crash(monkeypatch):
    """Loader returning None (disabled/failed load) -> empty list, no raise."""
    monkeypatch.setattr("app.services.rewrite_engine._get_rewrite_model", lambda: None)
    assert generate_rewrites(SPEECH, [mistake(6.2, "speech", ["filler_word: um"])]) == []


def test_model_cache_sentinel_false_returns_empty(monkeypatch):
    """The False sentinel cached after a failed load coerces to None so
    callers degrade to an empty list instead of crashing."""
    import app.services.rewrite_engine as re_mod
    monkeypatch.setattr(re_mod, "_rewrite_model_cache", False)
    assert re_mod._get_rewrite_model() is None
    assert generate_rewrites(SPEECH, [mistake(6.2, "speech", ["filler_word: um"])]) == []


def test_disabled_config_returns_empty(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "REWRITES_ENABLED", False)
    assert generate_rewrites(SPEECH, [mistake(6.2, "speech", ["filler_word: um"])]) == []


def test_per_segment_inference_failure_skips_only_that_segment(monkeypatch):
    """One broken segment must not abort the batch: the failed one falls back
    to the deterministic pass (or is dropped when that yields nothing), while
    the other segments still get their rewrites."""
    class ExplodingTokenizer:
        def __call__(self, *a, **k):
            raise RuntimeError("cuda exploded")

        def decode(self, *a, **k):  # pragma: no cover - never reached
            return ""

    monkeypatch.setattr(
        "app.services.rewrite_engine._rewrite_model_cache",
        (ExplodingTokenizer(), object()),
    )

    words = [
        {"word": "um", "start": 5.0, "end": 5.3},
        {"word": "so", "start": 5.4, "end": 5.8},
        {"word": "we", "start": 5.9, "end": 6.2},
        {"word": "did", "start": 6.3, "end": 6.6},
        {"word": "it.", "start": 6.7, "end": 7.0},
        {"word": "uh", "start": 12.0, "end": 12.3},  # clause that is ONLY a filler
    ]
    mistakes = [
        mistake(5.0, "speech", ["filler_word: um"]),
        mistake(12.0, "speech", ["filler_word: uh"]),
    ]
    rewrites = generate_rewrites({"words": words}, mistakes)
    # Segment 1 survives via the deterministic fallback; segment 2's cleanup
    # is empty (nothing left after stripping "uh") so it is dropped. Nothing
    # raised anywhere.
    assert len(rewrites) == 1
    assert rewrites[0].rewritten_segment == "So we did it."


# ---- Segment extraction -----------------------------------------------------

def test_extract_segment_respects_clause_gap():
    words = [
        {"word": "first.", "start": 1.0, "end": 1.4},
        {"word": "um", "start": 5.0, "end": 5.3},
        {"word": "second", "start": 5.4, "end": 5.9},
    ]
    assert extract_segment(words, 5.2) == "um second"


def test_extract_segment_empty_inputs():
    assert extract_segment([], 5.0) == ""
    assert extract_segment(WORDS, 60.0) == ""


# ---- Model round-trip through the report model ------------------------------

def test_fusion_report_result_accepts_rewrites():
    """The endpoint model must round-trip the new field (legacy reports with
    no rewrites key keep working thanks to the default [])."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    legacy = FusionReportResult(
        smartspeak_index=70.0, grade="Competent", verbal_score=60.0,
        non_verbal_score=65.0, ml_confidence_score=70.0, analyzed_at=now,
    )
    assert legacy.rewrites == []

    report = FusionReportResult(
        smartspeak_index=70.0, grade="Competent", verbal_score=60.0,
        non_verbal_score=65.0, ml_confidence_score=70.0, analyzed_at=now,
        rewrites=[RewriteItem(
            original_segment="um so i am going there.",
            rewritten_segment="So I am going there.",
            mistake_type="filler_word",
            timestamp=6.2,
        )],
    )
    dumped = report.model_dump(mode="json")
    assert dumped["rewrites"][0]["rewritten_segment"] == "So I am going there."
    assert FusionReportResult(**dumped).rewrites[0].mistake_type == "filler_word"


def test_generate_fusion_report_sync_survives_rewrite_engine_crash(monkeypatch):
    """The fusion wire-in is failure-safe: a rewrite-engine explosion must not
    fail the report — rewrites degrade to []."""
    from app.services import fusion_engine

    def boom(*a, **k):
        raise RuntimeError("rewrite engine down")

    monkeypatch.setattr(fusion_engine, "generate_rewrites", boom)
    speech = {
        "words": WORDS,
        "filler_words": [{"word": "um", "timestamp": 6.2}],
        "filler_word_count": 1,
        "long_pauses": [],
        "repetitions": [],
        "wpm_data": {"total_words": 10, "overall_wpm": 150.0,
                     "total_speaking_duration_seconds": 4.0},
    }
    visual = {
        "eye_contact": {"eye_contact_percentage": 80.0, "looking_away_ranges": []},
        "posture": {"total_frames_analyzed": 20, "posture_score": 95.0},
        "gesture": {"gesture_usage_classification": "average"},
        "head_movement": {"head_movement_score": 90.0},
    }
    result = fusion_engine.generate_fusion_report_sync(speech, visual, None)
    assert result.rewrites == []
    assert result.smartspeak_index > 0
