"""
Prioritized improvement plan generation.

Pure computation: ranks the session's weakest metrics by their distance from
the scoring targets and pairs each with a concrete drill derived from the
session's own numbers (no canned strings). The single worst metric becomes the
session's focus goal so subsequent sessions can show progress against it.
"""
from typing import Any, Dict, List, Optional

from app.models.session import ImprovementAction

# Public-speaking targets used by the composite scorer (kept in sync with
# compute_composite_scores) plus per-metric baselines for coaching copy.
TARGETS = {
    "wpm": {"min": 130.0, "max": 160.0},
    "eye_contact": {"min": 60.0, "max": 100.0},   # 60%+ face-visible gaze at/around audience
    "posture": {"min": 90.0, "max": 100.0},
    "head_movement": {"min": 80.0, "max": 100.0},
}


def _fmt(value: float) -> str:
    value = round(float(value), 1)
    return f"{value:g}"


def _build_filler_action(speech: Dict[str, Any], total_words: int) -> Optional[ImprovementAction]:
    filler_count = int(speech.get("filler_word_count") or 0)
    fillers = speech.get("filler_words") or []
    if not fillers:
        return None

    ratio = (filler_count / total_words) if total_words > 0 else 0.0
    # Mirror the verbal score: 100 - ratio*300 hits 0 at ~33% ratio
    severity = min(100.0, max(0.0, ratio * 300.0))

    # Most frequent filler word from the actual list
    counts: Dict[str, int] = {}
    for fw in fillers:
        w = str(fw.get("word", "")).lower().strip()
        if w:
            counts[w] = counts.get(w, 0) + 1
    top_word = max(counts, key=counts.get) if counts else "um"
    top_count = counts.get(top_word, 0)

    drill = (
        f"You used {filler_count} fillers in {total_words} words"
        + (f" — '{top_word}' alone {top_count} times" if top_count > 1 else "")
        + ". For your next take, pause silently instead of filling: "
        "a 1-second silent pause reads as confident, a filler reads as unsure."
    )
    return ImprovementAction(
        metric="fillers",
        title="Cut filler words with silent pauses",
        drill=drill,
        severity=round(severity, 1),
        current_value=float(filler_count),
        target_value=0.0,
    )


def _build_pause_action(speech: Dict[str, Any]) -> Optional[ImprovementAction]:
    pauses = speech.get("long_pauses") or []
    if not pauses:
        return None

    worst = max(float(p.get("duration", 0.0) or 0.0) for p in pauses)
    severity = min(100.0, worst * 12.0)  # 8s silence -> ~96 impact

    drill = (
        f"Your longest silence stretched to {worst:.1f}s ({len(pauses)} long pause"
        f"{'s' if len(pauses) != 1 else ''} total). Practice bridging: when you need to "
        "think, summarize your last point in one phrase — e.g. 'so the key idea is…' — "
        "instead of going quiet."
    )
    return ImprovementAction(
        metric="pauses",
        title="Bridge long silences",
        drill=drill,
        severity=round(severity, 1),
        current_value=float(worst),
        target_value=3.0,
    )


def _build_wpm_action(speech: Dict[str, Any]) -> Optional[ImprovementAction]:
    wpm_data = speech.get("wpm_data") or {}
    wpm = float(wpm_data.get("overall_wpm", 0.0) or 0.0)
    total_words = int(wpm_data.get("total_words", 0) or 0)
    if total_words == 0 or wpm <= 0:
        return None

    if wpm < TARGETS["wpm"]["min"]:
        gap = TARGETS["wpm"]["min"] - wpm
        severity = min(100.0, gap * 1.5)  # mirror pacing score penalty
        drill = (
            f"You spoke at {wpm:.0f} WPM — below the {130:.0f}-{160:.0f} range that keeps "
            "audiences engaged. Rehearse with a timer at a slightly faster clip, and "
            "trim sentences you don't need."
        )
        return ImprovementAction(
            metric="wpm",
            title="Pick up your pace",
            drill=drill,
            severity=round(severity, 1),
            current_value=float(wpm),
            target_value=TARGETS["wpm"]["min"],
        )

    if wpm > TARGETS["wpm"]["max"]:
        gap = wpm - TARGETS["wpm"]["max"]
        severity = min(100.0, gap * 1.5)
        drill = (
            f"You hit {wpm:.0f} WPM — above the {130:.0f}-{160:.0f} range. Your fastest stretch "
            "is where listeners get lost. Practice full stops: end each sentence, breathe, "
            "then continue."
        )
        return ImprovementAction(
            metric="wpm",
            title="Slow down for clarity",
            drill=drill,
            severity=round(severity, 1),
            current_value=float(wpm),
            target_value=TARGETS["wpm"]["max"],
        )

    return None


def _build_repetition_action(speech: Dict[str, Any]) -> Optional[ImprovementAction]:
    reps = speech.get("repetitions") or []
    if not reps:
        return None
    top = max(int(r.get("count", 2) or 2) for r in reps)
    phrase = max(reps, key=lambda r: int(r.get("count", 2) or 2)).get("phrase", "")
    severity = min(100.0, float(len(reps) * 8 + (top - 2) * 5))

    drill = (
        f"'{phrase}' came out {top} times — repeated phrases give a draft feel. "
        "Record yourself listing your main points once; if a phrase repeats, "
        "swap it for a synonym or cut it."
    )
    return ImprovementAction(
        metric="repetitions",
        title="Vary repeated phrases",
        drill=drill,
        severity=round(severity, 1),
        current_value=float(len(reps)),
        target_value=0.0,
    )


def _build_eye_action(visual: Dict[str, Any]) -> Optional[ImprovementAction]:
    eye = (visual.get("eye_contact") or {})
    pct = eye.get("eye_contact_percentage")
    if pct is None:
        return None
    pct = float(pct)
    if pct >= TARGETS["eye_contact"]["min"]:
        return None

    ranges = eye.get("looking_away_ranges") or []
    away_events = len(ranges)
    longest = max((float(r.get("duration", 0.0) or 0.0) for r in ranges), default=0.0)
    severity = min(100.0, TARGETS["eye_contact"]["min"] - pct)

    down = sum(1 for r in ranges if str(r.get("category", "")).startswith("looking_down"))
    drill = (
        f"You held eye contact only {pct:.0f}% of the time"
        + (f" across {away_events} look-away moment{'s' if away_events != 1 else ''}"
           + (f" — the longest stretched {longest:.1f}s" if longest >= 2.0 else "")
           + (f", mostly looking down" if down > away_events / 2 else ""))
        + ". Anchor your gaze to the lens for a full sentence, then sweep back every ~10 seconds."
    )
    return ImprovementAction(
        metric="eye_contact",
        title="Anchor your gaze to the lens",
        drill=drill,
        severity=round(severity, 1),
        current_value=pct,
        target_value=TARGETS["eye_contact"]["min"],
    )


def _build_posture_action(visual: Dict[str, Any]) -> Optional[ImprovementAction]:
    posture = (visual.get("posture") or {})
    score = posture.get("posture_score")
    total_frames = int(posture.get("total_frames_analyzed", 0) or 0)
    if score is None or total_frames == 0:
        return None
    score = float(score)
    if score >= TARGETS["posture"]["min"]:
        return None

    bad_frames = int(round((100.0 - score) / 100.0 * total_frames))
    severity = min(100.0, TARGETS["posture"]["min"] - score)
    drill = (
        f"{bad_frames} of {total_frames} analyzed frames showed slouched shoulders or a "
        "leaning spine. Reset between sections: imagine a string lifting the crown of "
        "your head, shoulders back and level."
    )
    return ImprovementAction(
        metric="posture",
        title="Reset your posture between sections",
        drill=drill,
        severity=round(severity, 1),
        current_value=score,
        target_value=TARGETS["posture"]["min"],
    )


def _build_gesture_action(visual: Dict[str, Any]) -> Optional[ImprovementAction]:
    gesture = (visual.get("gesture") or {})
    classification = gesture.get("gesture_usage_classification")
    if classification not in ("too_few", "too_many"):
        return None
    pct = float(gesture.get("active_hand_percentage", 0.0) or 0.0)

    if classification == "too_few":
        severity = 40.0  # fixed scoring penalty for too_few
        drill = (
            f"Your hands were active only {pct:.0f}% of the take. Locked hands read as "
            "tension. Plan two gestures: one to open (count on your fingers), one to "
            "emphasize your closing line."
        )
        return ImprovementAction(
            metric="gestures",
            title="Add purposeful hand gestures",
            drill=drill,
            severity=severity,
            current_value=pct,
            target_value=25.0,
        )

    severity = 35.0  # fixed scoring penalty for too_many
    drill = (
        f"Your hands were moving {pct:.0f}% of the take, which can distract from your words. "
        "Practice resting your hands loosely between points, then bring them up only to "
        "underscore a key line."
    )
    return ImprovementAction(
        metric="gestures",
        title="Dial gestures to emphasis moments",
        drill=drill,
        severity=severity,
        current_value=pct,
        target_value=45.0,
    )


def _build_head_action(visual: Dict[str, Any]) -> Optional[ImprovementAction]:
    head = (visual.get("head_movement") or {})
    score = head.get("head_movement_score")
    if score is None:
        return None
    score = float(score)
    if score >= TARGETS["head_movement"]["min"]:
        return None

    triggers = int(head.get("excessive_movement_count", 0) or 0)
    severity = min(100.0, TARGETS["head_movement"]["min"] - score)
    drill = (
        f"{triggers} rapid head movements broke your frame stillness. Keep gesture "
        "emphasis in your hands: turn your head deliberately when addressing a new "
        "point, not mid-sentence."
    )
    return ImprovementAction(
        metric="head_movement",
        title="Steady your head between points",
        drill=drill,
        severity=round(severity, 1),
        current_value=score,
        target_value=TARGETS["head_movement"]["min"],
    )


# Display labels shared with the frontend and history summaries.
METRIC_LABELS = {
    "wpm": "Speaking pace",
    "fillers": "Filler words",
    "pauses": "Long pauses",
    "repetitions": "Repeated phrases",
    "eye_contact": "Eye contact",
    "posture": "Posture",
    "gestures": "Hand gestures",
    "head_movement": "Head movement",
}


def compute_improvement_plan(
    speech_analysis: Optional[Dict[str, Any]],
    visual_analysis: Optional[Dict[str, Any]],
    max_actions: int = 3,
) -> List[ImprovementAction]:
    """
    Ranks concrete improvement actions by their impact on the composite score
    and returns the top `max_actions`. Every drill cites this session's real
    numbers; metrics that already meet their target produce no action.
    """
    actions: List[ImprovementAction] = []

    if speech_analysis:
        total_words = int((speech_analysis.get("wpm_data") or {}).get("total_words", 0) or 0)
        for builder in (_build_filler_action, _build_pause_action, _build_wpm_action, _build_repetition_action):
            action = builder(speech_analysis, total_words) if builder is _build_filler_action else builder(speech_analysis)
            if action:
                actions.append(action)

    if visual_analysis:
        for builder in (_build_eye_action, _build_posture_action, _build_gesture_action, _build_head_action):
            action = builder(visual_analysis)
            if action:
                actions.append(action)

    actions.sort(key=lambda a: a.severity, reverse=True)
    return actions[:max_actions]


def pick_focus_goal(actions: List[ImprovementAction]) -> Optional[str]:
    """The single worst metric (highest-impact action) becomes the focus goal."""
    return actions[0].metric if actions else None
