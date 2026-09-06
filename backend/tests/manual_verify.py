import sys
import os
import shutil
import subprocess
from pathlib import Path
import cv2
import numpy as np

# Ensure backend directory is in path to import app services
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.speech_analyzer import transcribe_audio_sync
from app.services.visual_analyzer import (
    analyze_eye_contact_and_head_pose_sync,
    analyze_posture_and_gestures_sync,
)
from app.config import settings


def get_ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return "ffmpeg"


def extract_media_fixtures(video_path: Path, temp_dir: Path):
    temp_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = temp_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    audio_path = temp_dir / "audio.wav"

    # Extract Audio
    ffmpeg_bin = get_ffmpeg_binary()
    ffmpeg_cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(audio_path)
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Extract Frames at 1 fps
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Failed to open video {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, int(round(fps / 1.0))) if fps > 0 else 30
    
    saved_count = 0
    current_frame = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if current_frame % step == 0:
            saved_count += 1
            cv2.imwrite(str(frames_dir / f"frame_{saved_count:04d}.jpg"), frame)
        current_frame += 1
    cap.release()

    return audio_path, frames_dir


def main():
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    clean_video = fixtures_dir / "clean_sample.mp4"
    noisy_video = fixtures_dir / "noisy_sample.mp4"

    if not clean_video.exists() or not noisy_video.exists():
        print(f"Fixtures clean_sample.mp4 or noisy_sample.mp4 are missing in {fixtures_dir}.")
        print("Please add them there for manual verification.")
        sys.exit(0)

    temp_root = fixtures_dir / "temp_processed"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    results = {}

    for name, path in [("Clean Video", clean_video), ("Noisy Video", noisy_video)]:
        print(f"\n--- Processing {name} ---")
        temp_dir = temp_root / name.lower().replace(" ", "_")
        
        try:
            audio_path, frames_dir = extract_media_fixtures(path, temp_dir)
            
            # 1. Speech Transcription Confidence
            print("Running Speech Transcription...")
            transcript_text, words = transcribe_audio_sync(audio_path, settings.WHISPER_MODEL)
            valid_probs = [w.probability for w in words if w.probability is not None]
            avg_speech_conf = sum(valid_probs) / len(valid_probs) if valid_probs else None
            
            # 2. Visual Analysis Confidence
            print("Running Visual Analysis...")
            eye_contact, _ = analyze_eye_contact_and_head_pose_sync(path)
            posture, gesture = analyze_posture_and_gestures_sync(frames_dir)

            results[name] = {
                "transcript": transcript_text,
                "speech_conf": avg_speech_conf,
                "face_conf": eye_contact.average_detection_confidence,
                "face_fallback": eye_contact.fallback_frame_count,
                "face_no_det": eye_contact.no_detection_frame_count,
                "pose_conf": posture.average_detection_confidence,
                "pose_fallback": posture.fallback_frame_count,
                "pose_no_det": posture.no_detection_frame_count,
                "hand_conf": gesture.average_detection_confidence,
                "hand_fallback": gesture.fallback_frame_count,
                "hand_no_det": gesture.no_detection_frame_count,
            }

            print(f"Done processing {name}.")
        except Exception as e:
            print(f"Failed to process {name}: {e}")

    # Print Comparison Table
    print("\n" + "="*80)
    print("MANUAL VERIFICATION RESULTS COMPARISON")
    print("="*80)
    print(f"{'Metric':<35} | {'Clean Video':<18} | {'Noisy Video':<18}")
    print("-"*80)

    metrics = [
        ("Speech Avg Confidence", "speech_conf"),
        ("Face Avg Confidence", "face_conf"),
        ("Face Fallback Frames", "face_fallback"),
        ("Face No-Detection Frames", "face_no_det"),
        ("Pose Avg Confidence", "pose_conf"),
        ("Pose Fallback Frames", "pose_fallback"),
        ("Pose No-Detection Frames", "pose_no_det"),
        ("Hand Avg Confidence", "hand_conf"),
        ("Hand Fallback Frames", "hand_fallback"),
        ("Hand No-Detection Frames", "hand_no_det"),
    ]

    for label, key in metrics:
        clean_val = results.get("Clean Video", {}).get(key)
        noisy_val = results.get("Noisy Video", {}).get(key)
        
        clean_str = f"{clean_val:.4f}" if isinstance(clean_val, float) else str(clean_val)
        noisy_str = f"{noisy_val:.4f}" if isinstance(noisy_val, float) else str(noisy_val)
        
        print(f"{label:<35} | {clean_str:<18} | {noisy_str:<18}")

    print("="*80)

    # Cleanup temp directory
    shutil.rmtree(temp_root)


if __name__ == "__main__":
    main()
