"""Delivery Dynamics — higher-order delivery metrics computed from the
speech-analysis time series.

Where the rest of the pipeline scores *what* the speaker did (fillers, pace,
posture), this module scores *how the delivery moves over time*:

1. **Energy curve & peak placement.** Windowed WPM is normalized into a
   speaking-energy envelope. The envelope's peak position is judged against
   the audience-attention heuristic that a talk should crest near the end
   (recency emphasis) rather than front-loading energy and fading.

2. **Rhythm entropy.** Each 15s WPM window is quantized into a band relative
   to the speaker's own median pace (slow < 0.75x, steady, fast > 1.25x) and
   the sequence of band transitions is scored with Shannon entropy, normalized
   by log2(3). Low entropy = metronomic delivery that audiences habituate to;
   moderate-high = varied, engaging rhythm. Median-relative bands (rather
   than raw pause detection) keep the metric robust to Whisper's outlier
   windows on sparse-word stretches. Degenerate cases are scored 0.

3. **Momentum recovery.** For each long pause, recovery is measured from the
   pause's own pre-pause WPM baseline (not the global mean), giving
   context-true pickup scores after each silence.

All functions are pure: they read the stored speech_analysis dict and return
plain types, so they are trivially unit-testable and safe to recompute for
historical sessions.
"""
from typing import Any, Dict, List, Optional

# --- Heuristic constants (tuned once, documented here) -----------------------

# Ideal position of the energy peak as a fraction of the talk (0.0-1.0).
PEAK_PLACEMENT_IDEAL = 0.7
# Full credit when the peak is within this fraction of the ideal position.
PEAK_PLACEMENT_TOLERANCE = 0.25
# Windows count as rhythm events only relative to the speaker's own pace:
# slow < SLOW_BAND_FRACTION x median, fast > FAST_BAND_FRACTION x median.
SLOW_BAND_FRACTION = 0.75
FAST_BAND_FRACTION = 1.25
# After a pause, recovery WPM within this fraction of the pre-pause baseline
# counts as fully recovered.
RECOVERY_TOLERANCE = 0.85
# Entropy in this band is considered a healthy delivery rhythm.
ENTROPY_IDEAL_MIN = 0.55
ENTROPY_IDEAL_MAX = 0.85


def _window_series(speech: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The 15s WPM windows, ascending, with finite numeric wpm."""
    windows = (speech.get("wpm_data") or {}).get("windowed_wpm") or []
    series = [
        w for w in windows
        if isinstance(w, dict)
        and isinstance(w.get("wpm"), (int, float))
        and isinstance(w.get("window_start"), (int, float))
    ]
    return sorted(series, key=lambda w: w["window_start"])


def analyze_energy_curve(speech: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalizes windowed WPM into a 0-1 energy envelope and judges peak placement."""
    series = _window_series(speech)
    if len(series) < 3:
        return None  # too short to have a meaningful curve

    wps = [float(w["wpm"]) for w in series]
    lo, hi = min(wps), max(wps)
    if hi - lo < 15:  # essentially flat pace — no curve to speak of
        return {
            "peak_fraction": None,
            "peak_placement_score": 50.0,  # neutral: flat delivery, nothing rewarded
            "opening_energy": round(wps[0] / hi, 2),
            "closing_energy": round(wps[-1] / hi, 2),
            "curve": [round(w / hi, 2) for w in wps],
            "verdict": "flat — a steady machine-gun pace reads as low engagement",
        }

    peak_idx = max(range(len(wps)), key=lambda i: wps[i])
    n = len(wps)
    peak_fraction = peak_idx / (n - 1)

    # Score: 100 when the peak sits in the ideal band, decaying linearly with
    # distance from it. A peak at position 0 (front-loaded) scores worst.
    distance = abs(peak_fraction - PEAK_PLACEMENT_IDEAL)
    score = max(0.0, 100.0 * (1.0 - distance / (PEAK_PLACEMENT_TOLERANCE * 2)))

    if peak_fraction <= 0.2:
        verdict = "front-loaded — you started at your peak and faded from there"
    elif peak_fraction >= 0.85:
        verdict = "all energy dumped at the very end — spread the build earlier"
    elif peak_fraction < PEAK_PLACEMENT_IDEAL - PEAK_PLACEMENT_TOLERANCE:
        verdict = "energy crested too early — hold the build through the close"
    else:
        verdict = "well placed — the talk crests where attention peaks"

    return {
        "peak_fraction": round(peak_fraction, 3),
        "peak_placement_score": round(score, 1),
        "opening_energy": round(wps[0] / hi, 2),
        "closing_energy": round(wps[-1] / hi, 2),
        "curve": [round(w / hi, 2) for w in wps],
        "verdict": verdict,
    }


def analyze_rhythm_entropy(speech: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Shannon entropy of the pace-band transitions across WPM windows."""
    series = _window_series(speech)
    if len(series) < 4:
        return None

    wps = [float(w["wpm"]) for w in series]
    ordered = sorted(wps)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    if median <= 0:
        return None

    # Quantize each window into a pace band relative to the speaker's median.
    slow_cut, fast_cut = SLOW_BAND_FRACTION * median, FAST_BAND_FRACTION * median

    def band(w: float) -> str:
        if w < slow_cut:
            return "slow"
        if w > fast_cut:
            return "fast"
        return "steady"

    # Collapse runs so a long stretch in one band counts once per switch.
    events: List[str] = []
    last = None
    for w in wps:
        b = band(w)
        if b != last:
            events.append(b)
            last = b

    n = len(events)
    if n < 3:
        return {
            "entropy_bits": 0.0,
            "normalized_entropy": 0.0,
            "rhythm_score": 0.0,
            "alternation_rate": round(n / len(series), 3),
            "verdict": "monotone delivery — near-constant pace, no rhythmic variety",
        }

    import math

    counts: Dict[str, int] = {}
    for b in events:
        counts[b] = counts.get(b, 0) + 1
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    max_entropy = math.log2(3)  # three pace bands
    normalized = entropy / max_entropy if max_entropy > 0 else 0.0

    # Map to 0-100: 0.55-0.85 normalized entropy is the healthy band, outside
    # it decays linearly to the edges.
    if ENTROPY_IDEAL_MIN <= normalized <= ENTROPY_IDEAL_MAX:
        score = 70.0 + 30.0 * (normalized - ENTROPY_IDEAL_MIN) / (ENTROPY_IDEAL_MAX - ENTROPY_IDEAL_MIN)
    elif normalized < ENTROPY_IDEAL_MIN:
        score = 35.0 + 35.0 * (normalized / ENTROPY_IDEAL_MIN)
    else:
        score = 100.0 - 30.0 * ((normalized - ENTROPY_IDEAL_MAX) / (1.0 - ENTROPY_IDEAL_MAX))

    if normalized < 0.35:
        verdict = "metronomic — constant rhythm invites the audience to tune out"
    elif normalized > 0.92:
        verdict = "choppy — pacing swings hard between fast and slow"
    else:
        verdict = "good rhythmic variety — pace changes keep listeners engaged"

    return {
        "entropy_bits": round(entropy, 3),
        "normalized_entropy": round(normalized, 3),
        "rhythm_score": round(score, 1),
        "alternation_rate": round(n / len(series), 3),
        "verdict": verdict,
    }


def analyze_momentum_recovery(speech: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """How quickly the speaker regains pace after each long pause.

    Recovery is measured against the pre-pause window's own WPM (local
    baseline) so a naturally slow section isn't punished twice.
    """
    series = _window_series(speech)
    pauses = speech.get("long_pauses") or []
    if not pauses or not series:
        return None

    recoveries: List[Dict[str, Any]] = []
    for pause in pauses:
        start = pause.get("start_time")
        if not isinstance(start, (int, float)):
            continue

        # Local pre-pause baseline: mean WPM of windows overlapping the 15s
        # before the pause, falling back to the nearest earlier window.
        pre_windows = [
            w for w in series
            if w["window_start"] < start and w["window_start"] + 15.0 > start - 15.0
        ]
        if pre_windows:
            baseline = sum(float(w["wpm"]) for w in pre_windows) / len(pre_windows)
        else:
            earlier = [w for w in series if w["window_start"] < start]
            if not earlier:
                continue  # pause happens before any speech window — nothing to recover from
            baseline = float(earlier[-1]["wpm"])

        # First window that starts after the pause ends (or nearest after start).
        end = pause.get("end_time", start)
        after = [w for w in series if w["window_start"] >= end] or \
                [w for w in series if w["window_start"] >= start]
        if not after:
            continue  # pause at the very end — no post-pause window exists

        post_wpm = float(after[0]["wpm"])
        ratio = post_wpm / baseline if baseline > 0 else 0.0
        if ratio >= 1.0:
            score = 100.0
        elif ratio >= RECOVERY_TOLERANCE:
            score = 100.0 * (ratio - RECOVERY_TOLERANCE) / (1.0 - RECOVERY_TOLERANCE) if ratio > RECOVERY_TOLERANCE else 90.0
        else:
            score = max(0.0, 100.0 * ratio / RECOVERY_TOLERANCE)

        recoveries.append({
            "pause_start": round(float(start), 2),
            "baseline_wpm": round(baseline, 1),
            "post_wpm": round(post_wpm, 1),
            "ratio": round(ratio, 2),
            "score": round(score, 1),
        })

    if not recoveries:
        return None

    avg_score = sum(r["score"] for r in recoveries) / len(recoveries)
    worst = min(recoveries, key=lambda r: r["score"])
    if avg_score >= 85:
        verdict = "strong — you come out of pauses at full speed"
    elif avg_score >= 60:
        verdict = "okay — momentum dips slightly after silences"
    else:
        verdict = "weak — long silences knock your pace down; rehearse resuming mid-thought"

    return {
        "recoveries": recoveries,
        "average_score": round(avg_score, 1),
        "weakest": worst,
        "verdict": verdict,
    }


def compute_delivery_dynamics(speech_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Entry point used by the fusion engine. Empty dict when speech data is absent."""
    if not speech_analysis:
        return {}
    energy = analyze_energy_curve(speech_analysis)
    rhythm = analyze_rhythm_entropy(speech_analysis)
    recovery = analyze_momentum_recovery(speech_analysis)
    if energy is None and rhythm is None and recovery is None:
        return {}

    parts: List[Dict[str, Any]] = []
    if energy:
        parts.append({
            "name": "Energy curve",
            "score": energy["peak_placement_score"],
            "verdict": energy["verdict"],
        })
    if rhythm:
        parts.append({
            "name": "Rhythm variety",
            "score": rhythm["rhythm_score"],
            "verdict": rhythm["verdict"],
        })
    if recovery:
        parts.append({
            "name": "Momentum recovery",
            "score": recovery["average_score"],
            "verdict": recovery["verdict"],
        })

    overall = round(sum(p["score"] for p in parts) / len(parts), 1) if parts else 0.0
    return {
        "overall": overall,
        "parts": parts,
        "energy_curve": energy,
        "rhythm_entropy": rhythm,
        "momentum_recovery": recovery,
    }
