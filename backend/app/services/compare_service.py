"""
Session comparison service.

Builds normalized metric snapshots for two completed sessions and derives
per-metric deltas with direction verdicts. Higher-is-better vs lower-is-better
semantics are declared per metric so "improved" always means what a speaker
would intuitively consider better.
"""
from typing import Any, Dict, List, Optional

from app.models.session import (
    FocusGoalProgress,
    SessionMetricDelta,
    SessionMetricSnapshot,
)
from app.services.improvement_plan import METRIC_LABELS


def _f(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric.replace("_", " ").capitalize())


def build_metric_snapshot(session_doc: Dict[str, Any]) -> SessionMetricSnapshot:
    """Extracts the normalized metric set from a session document."""
    fusion = session_doc.get("fusion_report") or {}
    speech = session_doc.get("speech_analysis") or {}
    visual = session_doc.get("visual_analysis") or {}
    wpm_data = speech.get("wpm_data") or {}
    eye = visual.get("eye_contact") or {}
    posture = visual.get("posture") or {}
    gesture = visual.get("gesture") or {}
    head = visual.get("head_movement") or {}

    total_words = int(_f(wpm_data.get("total_words")) or 0)
    filler_count = int(_f(speech.get("filler_word_count")) or 0)

    # A stored overall_wpm of 0 is either stale pre-fix data or a take with no
    # detectable speech — treat as missing so it never poisons comparisons.
    wpm_value = _f(wpm_data.get("overall_wpm"))
    if wpm_value is not None and wpm_value <= 0:
        wpm_value = None

    pauses = speech.get("long_pauses") or []
    longest_pause = max((_f(p.get("duration")) or 0.0) for p in pauses) if pauses else None

    return SessionMetricSnapshot(
        session_id=str(session_doc.get("session_id", "")),
        original_filename=str(session_doc.get("original_filename", "")),
        upload_timestamp=session_doc.get("upload_timestamp"),
        smartspeak_index=_f(fusion.get("smartspeak_index")),
        grade=fusion.get("grade"),
        eye_contact=_f(eye.get("eye_contact_percentage")),
        posture=_f(posture.get("posture_score")) if int(posture.get("total_frames_analyzed") or 0) > 0 else None,
        gesture_active=_f(gesture.get("active_hand_percentage")),
        head_movement=_f(head.get("head_movement_score")),
        wpm=wpm_value,
        filler_count=filler_count,
        filler_ratio=round(filler_count * 100.0 / total_words, 1) if total_words > 0 else None,
        repetition_count=len(speech.get("repetitions") or []),
        long_pause_count=len(pauses),
        longest_pause=longest_pause,
        duration_seconds=_f(wpm_data.get("total_speaking_duration_seconds")),
        focus_goal=fusion.get("focus_goal"),
    )


# metric key -> (unit, higher_is_better, is_band_metric)
_METRIC_DEFS = {
    "smartspeak_index": ("", True, False),
    "eye_contact": ("%", True, False),
    "posture": ("%", True, False),
    "head_movement": ("%", True, False),
    "wpm": (" WPM", False, True),  # band: closer to 130-160 is better
    "filler_ratio": ("%", False, False),
    "repetition_count": ("", False, False),
    "long_pause_count": ("", False, False),
    "longest_pause": ("s", False, False),
}


def build_metric_delta(
    metric: str,
    older: Optional[float],
    newer: Optional[float],
) -> Optional[SessionMetricDelta]:
    """Delta + direction verdict for one metric; None when either side lacks data."""
    if older is None or newer is None:
        return None

    unit, higher_better, is_band = _METRIC_DEFS[metric]
    delta = round(newer - older, 1)
    label = _metric_label(metric)
    label = {"smartspeak_index": "SmartSpeak score"}.get(metric, label)

    if is_band:
        # WPM: distance from the ideal 130-160 band decides the direction.
        def band_distance(v: float) -> float:
            if v < 130.0:
                return 130.0 - v
            if v > 160.0:
                return v - 160.0
            return 0.0

        dist_older, dist_newer = band_distance(older), band_distance(newer)
        if dist_newer < dist_older - 0.05:
            direction = "improved"
        elif dist_newer > dist_older + 0.05:
            direction = "regressed"
        else:
            direction = "same"
        if direction == "improved" and dist_newer == 0:
            verdict = "now in the ideal 130–160 range"
        elif direction == "improved":
            verdict = f"closer to the ideal 130–160 band (off by {dist_newer:.0f})"
        elif direction == "regressed":
            verdict = f"drifted further from the ideal band (off by {dist_newer:.0f})"
        else:
            verdict = "unchanged pace"
        return SessionMetricDelta(
            metric=metric, label=label, unit=unit,
            older=older, newer=newer, delta=delta,
            direction=direction, verdict=verdict,
        )

    if abs(delta) < 0.05:
        direction = "same"
        verdict = "unchanged"
    elif (delta > 0) == higher_better:
        direction = "improved"
        verdict = f"{'+' if delta > 0 else ''}{delta:g}{unit} vs before"
    else:
        direction = "regressed"
        verdict = f"{'+' if delta > 0 else ''}{delta:g}{unit} vs before"

    return SessionMetricDelta(
        metric=metric, label=label, unit=unit,
        older=older, newer=newer, delta=delta,
        direction=direction, verdict=verdict,
    )


def build_focus_goal_progress(
    older_snap: SessionMetricSnapshot,
    newer_snap: SessionMetricSnapshot,
) -> Optional[FocusGoalProgress]:
    """
    Progress on the older session's focus goal between the two sessions,
    using the newest of (improvement_plan.current_value, raw metric) so both
    legacy and fresh reports have a value.
    """
    goal = older_snap.focus_goal
    if not goal:
        return None

    # Goal metric -> snapshot field + whether lower is better
    GOAL_FIELDS = {
        "wpm": ("wpm", True),
        "fillers": ("filler_count", True),
        "pauses": ("long_pause_count", True),
        "repetitions": ("repetition_count", True),
        "eye_contact": ("eye_contact", False),
        "posture": ("posture", False),
        "gestures": ("gesture_active", False),
        "head_movement": ("head_movement", False),
    }
    if goal not in GOAL_FIELDS:
        return None
    field, lower_better = GOAL_FIELDS[goal]

    def value_of(snapshot: SessionMetricSnapshot) -> Optional[float]:
        return getattr(snapshot, field, None)

    older_value = value_of(older_snap)
    newer_value = value_of(newer_snap)
    if older_value is None or newer_value is None:
        return None

    improved = (newer_value < older_value) if lower_better else (newer_value > older_value)
    if abs(newer_value - older_value) < 0.05:
        summary = f"{_metric_label(goal)} held steady at {newer_value:g}"
        improved = False
    elif improved:
        summary = f"{_metric_label(goal)} improved from {older_value:g} to {newer_value:g}"
    else:
        summary = f"{_metric_label(goal)} went from {older_value:g} to {newer_value:g} — still a focus area"

    return FocusGoalProgress(
        goal_metric=goal,
        goal_label=_metric_label(goal),
        older_value=older_value,
        newer_value=newer_value,
        improved=improved,
        summary=summary,
    )
