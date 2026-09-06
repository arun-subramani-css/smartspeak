import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db.database import Database
from app.models.session import (
    FusionReportResult,
    MistakeItem,
    SessionStatus,
)

logger = logging.getLogger("smartspeak.fusion_engine")


def correlate_events(
    speech_analysis: Optional[Dict[str, Any]],
    visual_analysis: Optional[Dict[str, Any]],
    window_seconds: float = 1.0
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    STEP 1 — TIMESTAMP CORRELATION:
    Merges timestamped events from speech and visual analysis into a single chronological timeline.
    Checks for cross-modal overlaps within a window of ±window_seconds (default 1.0s).
    
    Returns:
        (compound_events, unassigned_speech_events, unassigned_visual_events)
    """
    speech_events: List[Dict[str, Any]] = []
    visual_events: List[Dict[str, Any]] = []

    # 1. Extract speech events
    if speech_analysis:
        for fw in speech_analysis.get("filler_words", []):
            ts = float(fw.get("timestamp", 0.0))
            speech_events.append({
                "type": "filler_word",
                "start": ts,
                "end": ts,
                "timestamp": ts,
                "label": f"filler_word: {fw.get('word', 'filler')}",
                "detail": fw
            })

        for p in speech_analysis.get("long_pauses", []):
            s = float(p.get("start_time", 0.0))
            e = float(p.get("end_time", s))
            dur = float(p.get("duration", e - s))
            speech_events.append({
                "type": "long_pause",
                "start": s,
                "end": e,
                "timestamp": s,
                "label": f"pause: {dur:.1f}s",
                "detail": p
            })

        for r in speech_analysis.get("repetitions", []):
            ts = float(r.get("timestamp", 0.0))
            speech_events.append({
                "type": "repetition",
                "start": ts,
                "end": ts,
                "timestamp": ts,
                "label": f"repetition: {r.get('phrase', '')}",
                "detail": r
            })

    # 2. Extract visual events
    if visual_analysis:
        eye_data = visual_analysis.get("eye_contact", {})
        for r in eye_data.get("looking_away_ranges", []):
            s = float(r.get("start_time", 0.0))
            e = float(r.get("end_time", s))
            cat = r.get("category", "looking_away")
            visual_events.append({
                "type": "eye_contact",
                "category": cat,
                "start": s,
                "end": e,
                "timestamp": s,
                "label": cat,
                "detail": r
            })

        posture_data = visual_analysis.get("posture", {})
        for r in posture_data.get("poor_posture_ranges", []):
            s = float(r.get("start_time", 0.0))
            e = float(r.get("end_time", s))
            visual_events.append({
                "type": "poor_posture",
                "start": s,
                "end": e,
                "timestamp": s,
                "label": "poor_posture",
                "detail": r
            })

        head_data = visual_analysis.get("head_movement", {})
        for ts in head_data.get("excessive_movement_timestamps", []):
            t = float(ts)
            visual_events.append({
                "type": "head_movement",
                "start": t,
                "end": t,
                "timestamp": t,
                "label": "excessive_head_movement",
                "detail": {"timestamp": t}
            })

    # Sort events chronologically
    speech_events.sort(key=lambda x: x["start"])
    visual_events.sort(key=lambda x: x["start"])

    # 3. Detect cross-modal overlaps within ±window_seconds
    matched_speech_indices = set()
    matched_visual_indices = set()
    compound_events: List[Dict[str, Any]] = []

    for s_idx, s_ev in enumerate(speech_events):
        s_start, s_end = s_ev["start"], s_ev["end"]
        overlapping_visuals = []

        for v_idx, v_ev in enumerate(visual_events):
            v_start, v_end = v_ev["start"], v_ev["end"]
            
            # Check temporal interval proximity within ±window_seconds
            # Distance between [s_start, s_end] and [v_start, v_end] <= window_seconds
            distance = max(0.0, max(s_start, v_start) - min(s_end, v_end))
            if distance <= window_seconds:
                overlapping_visuals.append((v_idx, v_ev))

        if overlapping_visuals:
            matched_speech_indices.add(s_idx)
            raw_labels = [s_ev["label"]]
            v_event_details = []
            
            for v_idx, v_ev in overlapping_visuals:
                matched_visual_indices.add(v_idx)
                raw_labels.append(v_ev["label"])
                v_event_details.append(v_ev)

            # Deduplicate labels within compound entry while preserving chronological order
            label_counts: Dict[str, int] = {}
            for lbl in raw_labels:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

            deduped_labels = []
            for lbl, count in label_counts.items():
                if count > 1:
                    deduped_labels.append(f"{lbl} (x{count})")
                else:
                    deduped_labels.append(lbl)

            compound_timestamp = round(min(s_ev["timestamp"], *(v["timestamp"] for _, v in overlapping_visuals)), 2)
            
            compound_events.append({
                "timestamp": compound_timestamp,
                "type": "compound",
                "events": deduped_labels,
                "speech_event": s_ev,
                "visual_events": v_event_details
            })

    unassigned_speech = [ev for idx, ev in enumerate(speech_events) if idx not in matched_speech_indices]
    unassigned_visual = [ev for idx, ev in enumerate(visual_events) if idx not in matched_visual_indices]

    compound_events.sort(key=lambda x: x["timestamp"])
    return compound_events, unassigned_speech, unassigned_visual


def detect_mistakes(
    speech_analysis: Optional[Dict[str, Any]],
    visual_analysis: Optional[Dict[str, Any]]
) -> List[MistakeItem]:
    """
    STEP 2 — RULE-BASED MISTAKE DETECTION:
    Produces a final list of timestamped mistakes with category and calibrated severity:
      - minor: small filler, pause 2-4s, brief gaze break 2-4s, brief slouch 2-4s
      - medium: pause 4-6s, gaze break 4-6s, slouch 4-6s, compound overlap, 3+ repetitions
      - high: pause >6s, extended disengagement >6s, prolonged slouch >6s, severe compound overlap
    """
    compound_events, unassigned_speech, unassigned_visual = correlate_events(speech_analysis, visual_analysis)
    mistakes: List[MistakeItem] = []

    # 1. Process Compound Mistakes (Cross-modal correlation)
    for c in compound_events:
        ts = c["timestamp"]
        evs = c["events"]
        
        # Determine compound severity: co-occurrence of verbal and non-verbal tells reinforces hesitation
        has_high = False
        has_medium = False
        
        for v in c["visual_events"]:
            dur = float(v.get("detail", {}).get("duration", 0.0))
            if dur >= 6.0:
                has_high = True
            elif dur >= 4.0:
                has_medium = True

        s_detail = c["speech_event"].get("detail", {})
        if c["speech_event"]["type"] == "long_pause":
            dur = float(s_detail.get("duration", 0.0))
            if dur >= 6.0:
                has_high = True
            elif dur >= 4.0:
                has_medium = True

        if has_high:
            severity = "high"
        elif has_medium or len(evs) >= 2:
            severity = "medium"
        else:
            severity = "minor"

        desc = f"Compound behavioral cue: correlated {', '.join(evs)}"
        mistakes.append(MistakeItem(
            timestamp=ts,
            category="compound",
            description=desc,
            severity=severity,
            events=evs
        ))

    # 2. Process Standalone Speech Mistakes
    for ev in unassigned_speech:
        t = ev["type"]
        ts = ev["timestamp"]
        detail = ev["detail"]

        if t == "filler_word":
            word = detail.get("word", "filler")
            mistakes.append(MistakeItem(
                timestamp=ts,
                category="speech",
                description=f"Used filler word '{word}'",
                severity="minor",
                events=[ev["label"]]
            ))
        elif t == "long_pause":
            dur = float(detail.get("duration", 0.0))
            if dur >= 6.0:
                sev = "high"
                desc = f"Extended awkward silence ({dur:.1f}s)"
            elif dur >= 4.0:
                sev = "medium"
                desc = f"Noticeable hesitation pause ({dur:.1f}s)"
            else:
                sev = "minor"
                desc = f"Brief pause ({dur:.1f}s)"

            mistakes.append(MistakeItem(
                timestamp=ts,
                category="speech",
                description=desc,
                severity=sev,
                events=[ev["label"]]
            ))
        elif t == "repetition":
            phrase = detail.get("phrase", "")
            cnt = detail.get("count", 2)
            sev = "medium" if cnt > 2 else "minor"
            mistakes.append(MistakeItem(
                timestamp=ts,
                category="speech",
                description=f"Repeated phrase '{phrase}' ({cnt}x)",
                severity=sev,
                events=[ev["label"]]
            ))

    # 3. Process Standalone Visual Mistakes
    for ev in unassigned_visual:
        t = ev["type"]
        ts = ev["timestamp"]
        detail = ev["detail"]

        if t == "eye_contact":
            dur = float(detail.get("duration", 0.0))
            cat = detail.get("category", "looking_away")
            if dur >= 6.0:
                sev = "high"
                desc = f"Sustained eye contact loss ({cat.replace('_', ' ')} for {dur:.1f}s)"
            elif dur >= 4.0:
                sev = "medium"
                desc = f"Looking away from audience ({cat.replace('_', ' ')} for {dur:.1f}s)"
            else:
                sev = "minor"
                desc = f"Brief gaze shift ({cat.replace('_', ' ')} for {dur:.1f}s)"

            mistakes.append(MistakeItem(
                timestamp=ts,
                category="visual",
                description=desc,
                severity=sev,
                events=[ev["label"]]
            ))
        elif t == "poor_posture":
            dur = float(detail.get("duration", 0.0))
            if dur >= 6.0:
                sev = "high"
                desc = f"Sustained slouching or torso lean ({dur:.1f}s)"
            elif dur >= 4.0:
                sev = "medium"
                desc = f"Noticeable poor posture ({dur:.1f}s)"
            else:
                sev = "minor"
                desc = f"Brief posture deviation ({dur:.1f}s)"

            mistakes.append(MistakeItem(
                timestamp=ts,
                category="visual",
                description=desc,
                severity=sev,
                events=[ev["label"]]
            ))
        elif t == "head_movement":
            mistakes.append(MistakeItem(
                timestamp=ts,
                category="visual",
                description="Excessive or abrupt head movement detected",
                severity="minor",
                events=[ev["label"]]
            ))

    # Sort all mistakes chronologically
    mistakes.sort(key=lambda m: m.timestamp)
    return mistakes


def compute_composite_scores(
    speech_analysis: Optional[Dict[str, Any]],
    visual_analysis: Optional[Dict[str, Any]],
    confidence_analysis: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    STEP 3 — COMPOSITE SCORING & SMART SPEAK INDEX:
    
    Defensible mathematical scoring formula:
      - Verbal Score (40% weight):
          * 40% Filler Ratio Score: max(0, 100 - (filler_ratio * 300))
          * 30% WPM Pacing Score: max(0, 100 - 1.5 * |WPM - target|) [target: 130-160 WPM]
          * 30% Pause/Repetition Score: max(0, 100 - pause_deductions)
      - Non-Verbal Score (40% weight):
          * 35% Eye Contact Percentage (0-100)
          * 30% Posture Score (0-100)
          * 20% Gesture Classification (Average=100, Too Few=60, Too Many=65)
          * 15% Head Movement Score (0-100)
      - ML Confidence Score (20% weight):
          * Direct score from trained confidence model (0-100)
    
    DYNAMIC PROPORTIONAL RE-WEIGHTING:
    If any component is None or missing, its weight is proportionally redistributed
    across the remaining available components:
      Index = sum(Weight_i * Score_i) / sum(Weight_i for valid components)
    
    GRADE BOUNDARIES:
      Executive: >= 85.0
      Polished:  70.0 - 84.9
      Competent: 50.0 - 69.9
      Needs Practice: < 50.0
    """
    verbal_score: Optional[float] = None
    non_verbal_score: Optional[float] = None
    ml_confidence_score: Optional[float] = None

    # --- 1. Verbal Delivery Sub-Score ---
    if speech_analysis is not None:
        wpm_data = speech_analysis.get("wpm_data", {})
        total_words = int(wpm_data.get("total_words", 0))
        speaking_duration = float(wpm_data.get("total_speaking_duration_seconds", 0.0))
        filler_count = int(speech_analysis.get("filler_word_count", 0))
        
        # A. Filler Ratio Score (40% of Verbal)
        # Recalibrated formula: max(0, 100 - (filler_ratio * 300))
        # 2% -> 94.0, 5% -> 85.0, 7.7% -> 76.9, 10% -> 70.0, 20% -> 40.0
        if total_words > 0:
            filler_ratio = filler_count / total_words
            s_filler = max(0.0, 100.0 - (filler_ratio * 300.0))
        else:
            s_filler = 100.0 if filler_count == 0 else 0.0

        # B. WPM Pacing Score (30% of Verbal)
        # Target conversational public speaking rate: 130 - 160 WPM
        wpm = float(wpm_data.get("overall_wpm", 0.0))
        if total_words == 0:
            s_wpm = 50.0 if speaking_duration > 0.0 else 100.0
        else:
            if 130.0 <= wpm <= 160.0:
                s_wpm = 100.0
            elif wpm < 130.0:
                s_wpm = max(0.0, 100.0 - 1.5 * (130.0 - wpm))
            else:
                s_wpm = max(0.0, 100.0 - 1.5 * (wpm - 160.0))

        # C. Pause & Fluency Score (30% of Verbal)
        # Deduct 5 per minor pause (2-4s), 10 per medium pause (4-6s), 15 per long pause (>6s), 5 per repetition
        s_pause = 100.0
        for p in speech_analysis.get("long_pauses", []):
            dur = float(p.get("duration", 0.0))
            if dur >= 6.0:
                s_pause -= 15.0
            elif dur >= 4.0:
                s_pause -= 10.0
            elif dur >= 2.0:
                s_pause -= 5.0

        for r in speech_analysis.get("repetitions", []):
            s_pause -= 5.0 * int(r.get("count", 1))

        s_pause = max(0.0, s_pause)

        verbal_score = round(0.40 * s_filler + 0.30 * s_wpm + 0.30 * s_pause, 1)

    # --- 2. Non-Verbal Delivery Sub-Score ---
    if visual_analysis is not None:
        eye_data = visual_analysis.get("eye_contact", {})
        posture_data = visual_analysis.get("posture", {})
        gesture_data = visual_analysis.get("gesture", {})
        head_data = visual_analysis.get("head_movement", {})

        s_eye = float(eye_data.get("eye_contact_percentage", 100.0))
        s_eye = min(100.0, max(0.0, s_eye))

        s_head = float(head_data.get("head_movement_score", 100.0))
        s_head = min(100.0, max(0.0, s_head))

        # Gestures
        g_class = gesture_data.get("gesture_usage_classification", "average")
        if g_class == "average":
            s_gesture = 100.0
        elif g_class == "too_few":
            s_gesture = 60.0
        elif g_class == "too_many":
            s_gesture = 65.0
        else:
            s_gesture = 80.0

        # Posture
        total_posture_frames = int(posture_data.get("total_frames_analyzed", 0))
        raw_posture_score = posture_data.get("posture_score")
        
        if total_posture_frames > 0 and raw_posture_score is not None:
            s_posture = min(100.0, max(0.0, float(raw_posture_score)))
            # Standard weights: Eye (35%), Posture (30%), Gesture (20%), Head (15%)
            non_verbal_score = round(
                0.35 * s_eye + 0.30 * s_posture + 0.20 * s_gesture + 0.15 * s_head, 1
            )
        else:
            # Posture not detected / no frames: redistribute posture weight (30%) proportionally
            # Total remaining = 0.35 + 0.20 + 0.15 = 0.70
            non_verbal_score = round(
                (0.35 * s_eye + 0.20 * s_gesture + 0.15 * s_head) / 0.70, 1
            )

    # --- 3. ML Confidence Sub-Score ---
    if confidence_analysis is not None:
        raw_conf = confidence_analysis.get("confidence_score")
        if raw_conf is not None:
            ml_confidence_score = round(min(100.0, max(0.0, float(raw_conf))), 1)

    # --- 4. Composite SmartSpeak Index & Proportional Re-Weighting ---
    weights = []
    scores = []

    if verbal_score is not None:
        weights.append(0.40)
        scores.append(verbal_score)

    if non_verbal_score is not None:
        weights.append(0.40)
        scores.append(non_verbal_score)

    if ml_confidence_score is not None:
        weights.append(0.20)
        scores.append(ml_confidence_score)

    total_weight = sum(weights)
    if total_weight > 0:
        composite_index = round(sum(w * s for w, s in zip(weights, scores)) / total_weight, 1)
    else:
        composite_index = 0.0

    # Grade Label Mapping
    if composite_index >= 85.0:
        grade = "Executive"
    elif composite_index >= 70.0:
        grade = "Polished"
    elif composite_index >= 50.0:
        grade = "Competent"
    else:
        grade = "Needs Practice"

    return {
        "smartspeak_index": composite_index,
        "grade": grade,
        "verbal_score": verbal_score if verbal_score is not None else 0.0,
        "non_verbal_score": non_verbal_score if non_verbal_score is not None else 0.0,
        "ml_confidence_score": ml_confidence_score if ml_confidence_score is not None else 0.0
    }


def generate_fusion_report_sync(
    speech_analysis: Optional[Dict[str, Any]],
    visual_analysis: Optional[Dict[str, Any]],
    confidence_analysis: Optional[Dict[str, Any]]
) -> FusionReportResult:
    """Synchronously creates the complete FusionReportResult."""
    mistakes = detect_mistakes(speech_analysis, visual_analysis)
    scores = compute_composite_scores(speech_analysis, visual_analysis, confidence_analysis)

    return FusionReportResult(
        mistakes=mistakes,
        smartspeak_index=scores["smartspeak_index"],
        grade=scores["grade"],
        verbal_score=scores["verbal_score"],
        non_verbal_score=scores["non_verbal_score"],
        ml_confidence_score=scores["ml_confidence_score"],
        analyzed_at=datetime.now(timezone.utc)
    )


async def process_fusion_session(session_id: str) -> bool:
    """
    Background orchestrator that loads the session document from MongoDB,
    generates the Feature Fusion and Mistake Detection report,
    and updates session status to FUSION_COMPLETE.
    """
    logger.info(f"[{session_id}] Starting Feature Fusion & Mistake Detection engine...")
    sessions_col = Database.get_collection("sessions")
    session_doc = await sessions_col.find_one({"session_id": session_id})
    if not session_doc:
        logger.error(f"[{session_id}] Session not found for fusion analysis.")
        return False

    speech_analysis = session_doc.get("speech_analysis")
    visual_analysis = session_doc.get("visual_analysis")
    confidence_analysis = session_doc.get("confidence_analysis")

    try:
        fusion_result = generate_fusion_report_sync(
            speech_analysis, visual_analysis, confidence_analysis
        )
        fusion_dict = fusion_result.model_dump(mode="json")

        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "fusion_report": fusion_dict,
                    "status": SessionStatus.FUSION_COMPLETE,
                    "error_reason": None
                }
            }
        )

        logger.info(
            f"[{session_id}] Feature Fusion complete and stored in MongoDB.\n"
            f"  -> SmartSpeak Index: {fusion_result.smartspeak_index}/100 ({fusion_result.grade})\n"
            f"  -> Verbal Score: {fusion_result.verbal_score}/100\n"
            f"  -> Non-Verbal Score: {fusion_result.non_verbal_score}/100\n"
            f"  -> ML Confidence Score: {fusion_result.ml_confidence_score}/100\n"
            f"  -> Total Mistakes Detected: {len(fusion_result.mistakes)}"
        )
        return True

    except Exception as exc:
        logger.exception(f"[{session_id}] Feature Fusion failed: {exc}")
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.FAILED,
                    "error_reason": f"Feature Fusion failed: {str(exc)}"
                }
            }
        )
        return False
