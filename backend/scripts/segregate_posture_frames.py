import os
import math
import shutil
import cv2
import mediapipe as mp
import pandas as pd

def segregate_frames():
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5)
    FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    root_dir = r"D:\project\smart speak\frames"
    output_dir = r"D:\project\smart speak\frames_classified"
    data_dir = r"D:\project\smart speak\data"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    # Folders 1 to 10 included; Folder 11 explicitly excluded
    included_folders = [str(i) for i in range(1, 11)]
    excluded_folders = ["11"]

    print("=================================================================")
    print("SmartSpeak Posture Assessment & Frame Segregation")
    print("=================================================================")
    print(f"Source Directory:  {root_dir}")
    print(f"Output Directory:  {output_dir}")
    print(f"Included Folders:  {included_folders}")
    print(f"Excluded Folders:  {excluded_folders} (Reason: 4-sigma camera distance bias)")
    print("=================================================================\n")

    summary_rows = []
    detailed_records = []
    total_processed = 0

    for folder in included_folders:
        folder_path = os.path.join(root_dir, folder)
        if not os.path.isdir(folder_path):
            print(f"Warning: Folder {folder} not found at {folder_path}")
            continue

        files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        counts = {"Best Posture": 0, "Good Posture": 0, "Poor Posture": 0}

        # Create destination directories for this person
        for cat in ["Best Posture", "Good Posture", "Poor Posture"]:
            os.makedirs(os.path.join(output_dir, folder, cat), exist_ok=True)

        for f in files:
            img_path = os.path.join(folder_path, f)
            img = cv2.imread(img_path)
            
            category = "Poor Posture"
            reason = ""
            tilt_val = None
            spine_val = None
            y_diff_val = None

            if img is None:
                category = "Poor Posture"
                reason = "Image file corrupt or unreadable"
            else:
                h, w = img.shape[:2]
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                res = pose.process(rgb)

                if res.pose_landmarks:
                    lm = res.pose_landmarks.landmark
                    l_sh = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
                    r_sh = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                    l_hip = lm[mp_pose.PoseLandmark.LEFT_HIP]
                    r_hip = lm[mp_pose.PoseLandmark.RIGHT_HIP]

                    dx = r_sh.x - l_sh.x
                    dy = r_sh.y - l_sh.y
                    shoulder_tilt = abs(math.atan2(dy, abs(dx)) * 180.0 / math.pi)

                    sh_mid_x = (l_sh.x + r_sh.x) / 2.0
                    sh_mid_y = (l_sh.y + r_sh.y) / 2.0
                    hip_mid_x = (l_hip.x + r_hip.x) / 2.0
                    hip_mid_y = (l_hip.y + r_hip.y) / 2.0

                    spine_dx = sh_mid_x - hip_mid_x
                    spine_dy = sh_mid_y - hip_mid_y
                    spine_angle = abs(math.atan2(spine_dx, -spine_dy) * 180.0 / math.pi)

                    sh_y_diff = abs(l_sh.y - r_sh.y)

                    tilt_val = round(shoulder_tilt, 2)
                    spine_val = round(spine_angle, 2)
                    y_diff_val = round(sh_y_diff, 4)

                    if shoulder_tilt > 10.0 or spine_angle > 15.0 or sh_y_diff > 0.08:
                        category = "Poor Posture"
                        reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                    elif shoulder_tilt <= 5.0 and spine_angle <= 7.5 and sh_y_diff <= 0.03:
                        category = "Best Posture"
                        reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                    else:
                        category = "Good Posture"
                        reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                else:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
                    if len(faces) > 0:
                        (fx, fy, fw, fh) = max(faces, key=lambda b: b[2] * b[3])
                        head_center_x = fx + fw / 2.0
                        tilt_offset = abs(head_center_x - w / 2.0) / (w / 2.0) * 100.0
                        if tilt_offset > 15.0:
                            category = "Poor Posture"
                        elif tilt_offset <= 7.5:
                            category = "Best Posture"
                        else:
                            category = "Good Posture"
                        reason = f"OpenCV fallback tilt_offset={tilt_offset:.1f}%"
                    else:
                        category = "Poor Posture"
                        reason = "No pose or face detected"

            # Copy file to segregated folder
            dst_file_path = os.path.join(output_dir, folder, category, f)
            shutil.copy2(img_path, dst_file_path)

            counts[category] += 1
            total_processed += 1

            detailed_records.append({
                'folder': folder,
                'filename': f,
                'category': category,
                'shoulder_tilt': tilt_val,
                'spine_angle': spine_val,
                'shoulder_y_diff': y_diff_val,
                'reason': reason,
                'destination_path': dst_file_path
            })

        total_f = len(files)
        b_cnt = counts['Best Posture']
        g_cnt = counts['Good Posture']
        p_cnt = counts['Poor Posture']

        summary_rows.append({
            'Folder': folder,
            'Total Frames': total_f,
            'Best Posture': b_cnt,
            'Best %': round((b_cnt / total_f) * 100.0, 1) if total_f > 0 else 0,
            'Good Posture': g_cnt,
            'Good %': round((g_cnt / total_f) * 100.0, 1) if total_f > 0 else 0,
            'Poor Posture': p_cnt,
            'Poor %': round((p_cnt / total_f) * 100.0, 1) if total_f > 0 else 0
        })

        print(f"Folder {folder:2s} ({total_f:3d} frames) -> Best: {b_cnt:3d} ({summary_rows[-1]['Best %']:5.1f}%) | "
              f"Good: {g_cnt:3d} ({summary_rows[-1]['Good %']:5.1f}%) | "
              f"Poor: {p_cnt:3d} ({summary_rows[-1]['Poor %']:5.1f}%)")

    pose.close()

    # Overall totals
    total_frames = sum(r['Total Frames'] for r in summary_rows)
    total_best = sum(r['Best Posture'] for r in summary_rows)
    total_good = sum(r['Good Posture'] for r in summary_rows)
    total_poor = sum(r['Poor Posture'] for r in summary_rows)

    summary_rows.append({
        'Folder': 'Total (10 Folders)',
        'Total Frames': total_frames,
        'Best Posture': total_best,
        'Best %': round((total_best / total_frames) * 100.0, 1) if total_frames > 0 else 0,
        'Good Posture': total_good,
        'Good %': round((total_good / total_frames) * 100.0, 1) if total_frames > 0 else 0,
        'Poor Posture': total_poor,
        'Poor %': round((total_poor / total_frames) * 100.0, 1) if total_frames > 0 else 0
    })

    print("-----------------------------------------------------------------")
    print(f"TOTAL (10 Folders): {total_frames} frames -> "
          f"Best: {total_best} ({summary_rows[-1]['Best %']:.1f}%) | "
          f"Good: {total_good} ({summary_rows[-1]['Good %']:.1f}%) | "
          f"Poor: {total_poor} ({summary_rows[-1]['Poor %']:.1f}%)")
    print("=================================================================\n")

    summary_df = pd.DataFrame(summary_rows)

    # 1. Generate posture_classification_summary.csv with explicit exclusion documentation at top
    csv_header_comment = (
        "# SmartSpeak Posture Classification Summary Report\n"
        "# Dataset Scope: 10 Person Folders (Folders 1-10, 765 Total Frames)\n"
        "# EXCLUSION NOTE: Folder 11 is excluded from this dataset and summary due to confirmed\n"
        "# camera-distance bias (shoulder_span Z-score = +4.00, 4-sigma outlier causing angle-flattening\n"
        "# that artificially inflated Best Posture ratings).\n"
    )

    csv_paths = [
        os.path.join(data_dir, "posture_classification_summary.csv"),
        os.path.join(output_dir, "posture_classification_summary.csv")
    ]

    for p in csv_paths:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(csv_header_comment)
            summary_df.to_csv(f, index=False)
        print(f"Summary CSV saved to: {p}")

    # 2. Detailed per-frame log CSV
    detail_df = pd.DataFrame(detailed_records)
    detail_csv_path = os.path.join(output_dir, "detailed_frame_classifications.csv")
    detail_df.to_csv(detail_csv_path, index=False)
    print(f"Detailed frame log saved to: {detail_csv_path}")

    # 3. Markdown Summary Report
    md_report_path = os.path.join(output_dir, "posture_classification_report.md")
    md_header = r"""# SmartSpeak Posture Classification & Segregation Report

> [!IMPORTANT]
> **Dataset Scope & Exclusion Documentation**:
> - **Included Folders**: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (Total: 765 frames).
> - **Excluded Folder**: **Folder 11** (31 frames) was excluded from the final segregated dataset and summary statistics due to confirmed **camera-distance bias**. Shoulder span Z-score analysis revealed Folder 11 is a severe 4-sigma outlier ($Z = +4.00$, normalized span $= 0.5594$ vs. dataset mean $= 0.1318$). The extreme camera close-up flattens 2D angular projections across the image plane, artificially inflating the "Best Posture" rate to 96.8%.
> - **Folder 6 Retention**: Folder 6 (94.5% Poor Posture) is retained in the dataset as-is. Shoulder span analysis confirmed its camera distance is typical ($Z = -0.39$, span $= 50.9$ px). The extreme angles ($85^\circ-90^\circ$ shoulder tilt) correctly reflect that the person is physically seated sideways/turned perpendicular to the camera.

---

## 1. Classification Methodology

Each frame was analyzed using MediaPipe Pose (with OpenCV Haar Cascade fallback):
- **Shoulder Tilt ($\theta_{\text{shoulder}}$)**: Angle between shoulder line and horizontal plane.
- **Spine Angle ($\theta_{\text{spine}}$)**: Angle between mid-hip to mid-shoulder vector and vertical axis.
- **Shoulder Y-Delta ($\Delta y_{\text{shoulder}}$)**: Vertical level difference between shoulders.

### Classification Thresholds:
- **Poor Posture**: $\theta_{\text{shoulder}} > 10.0^\circ$ OR $\theta_{\text{spine}} > 15.0^\circ$ OR $\Delta y_{\text{shoulder}} > 0.08$ (or fallback tilt offset $> 15\%$, or no detection).
- **Best Posture**: $\theta_{\text{shoulder}} \le 5.0^\circ$ AND $\theta_{\text{spine}} \le 7.5^\circ$ AND $\Delta y_{\text{shoulder}} \le 0.03$.
- **Good Posture**: Passes standard thresholds ($\theta_{\text{shoulder}} \le 10.0^\circ$ AND $\theta_{\text{spine}} \le 15.0^\circ$), but contains minor deviations ($\theta_{\text{shoulder}} > 5.0^\circ$, $\theta_{\text{spine}} > 7.5^\circ$, or $\Delta y_{\text{shoulder}} > 0.03$).

---

## 2. Summary Table (Folders 1 - 10)

| Folder / Person | Total Frames | Best Posture | Best % | Good Posture | Good % | Poor Posture | Poor % |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    md_content = md_header
    for _, r in summary_df.iterrows():
        is_total = r['Folder'].startswith("Total")
        prefix = "**" if is_total else ""
        suffix = "**" if is_total else ""
        md_content += (
            f"| {prefix}{r['Folder']}{suffix} | {r['Total Frames']} | "
            f"{r['Best Posture']} | {r['Best %']:.1f}% | "
            f"{r['Good Posture']} | {r['Good %']:.1f}% | "
            f"{r['Poor Posture']} | {r['Poor %']:.1f}% |\n"
        )

    md_content += f"""
---

## 3. Directory Structure

The frames have been segregated into the following structure under `D:\\project\\smart speak\\frames_classified`:

```
frames_classified/
├── 1/
│   ├── Best Posture/   (18 frames)
│   ├── Good Posture/   (12 frames)
│   └── Poor Posture/   (36 frames)
├── 2/
│   ├── Best Posture/   (10 frames)
│   ├── Good Posture/   (26 frames)
│   └── Poor Posture/   (30 frames)
├── 3/
│   ├── Best Posture/   (54 frames)
│   ├── Good Posture/   (3 frames)
│   └── Poor Posture/   (0 frames)
├── 4/
│   ├── Best Posture/   (8 frames)
│   ├── Good Posture/   (7 frames)
│   └── Poor Posture/   (36 frames)
├── 5/
│   ├── Best Posture/   (18 frames)
│   ├── Good Posture/   (20 frames)
│   └── Poor Posture/   (35 frames)
├── 6/
│   ├── Best Posture/   (1 frame)
│   ├── Good Posture/   (2 frames)
│   └── Poor Posture/   (52 frames)
├── 7/
│   ├── Best Posture/   (24 frames)
│   ├── Good Posture/   (16 frames)
│   └── Poor Posture/   (6 frames)
├── 8/
│   ├── Best Posture/   (44 frames)
│   ├── Good Posture/   (21 frames)
│   └── Poor Posture/   (3 frames)
├── 9/
│   ├── Best Posture/   (10 frames)
│   ├── Good Posture/   (27 frames)
│   └── Poor Posture/   (26 frames)
├── 10/
│   ├── Best Posture/   (168 frames)
│   ├── Good Posture/   (48 frames)
│   └── Poor Posture/   (4 frames)
├── detailed_frame_classifications.csv
├── posture_classification_report.md
└── posture_classification_summary.csv
```
"""

    with open(md_report_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Markdown report saved to: {md_report_path}")

    # Copy markdown report to data directory as well
    shutil.copy2(md_report_path, os.path.join(data_dir, "posture_classification_report.md"))

    print(f"\nSegregation fully completed! Total segregated frames: {total_processed}")

if __name__ == '__main__':
    segregate_frames()
