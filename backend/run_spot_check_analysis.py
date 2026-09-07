import os
import math
import random
import shutil
import cv2
import mediapipe as mp
import numpy as np
import pandas as pd

def analyze_and_sample():
    random.seed(42)
    np.random.seed(42)
    
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5)
    FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    root_dir = r"D:\project\smart speak\frames"
    review_dir = r"D:\project\smart speak\spot_check_sample"
    os.makedirs(review_dir, exist_ok=True)
    
    subdirs = sorted([d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))], key=lambda x: int(x) if x.isdigit() else x)
    
    records = []
    
    print(f"Analyzing all 11 folders in {root_dir}...")
    
    for folder in subdirs:
        folder_path = os.path.join(root_dir, folder)
        files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        
        for f in files:
            img_path = os.path.join(folder_path, f)
            img = cv2.imread(img_path)
            if img is None:
                records.append({
                    'folder': folder,
                    'file': f,
                    'full_path': img_path,
                    'category': 'Poor Posture',
                    'pose_detected': False,
                    'shoulder_tilt': None,
                    'spine_angle': None,
                    'shoulder_y_diff': None,
                    'shoulder_span_norm': None,
                    'shoulder_span_px': None,
                    'image_w': None,
                    'image_h': None,
                    'reason': 'Corrupt or unreadable image'
                })
                continue
                
            h, w = img.shape[:2]
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)
            
            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark
                l_sh = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
                r_sh = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
                l_hip = lm[mp_pose.PoseLandmark.LEFT_HIP]
                r_hip = lm[mp_pose.PoseLandmark.RIGHT_HIP]
                
                # Shoulder span: Euclidean distance between shoulder landmarks
                sh_span_norm = math.sqrt((l_sh.x - r_sh.x) ** 2 + (l_sh.y - r_sh.y) ** 2)
                sh_span_px = math.sqrt(((l_sh.x - r_sh.x) * w) ** 2 + ((l_sh.y - r_sh.y) * h) ** 2)
                
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
                
                if shoulder_tilt > 10.0 or spine_angle > 15.0 or sh_y_diff > 0.08:
                    category = "Poor Posture"
                    reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                elif shoulder_tilt <= 5.0 and spine_angle <= 7.5 and sh_y_diff <= 0.03:
                    category = "Best Posture"
                    reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                else:
                    category = "Good Posture"
                    reason = f"Tilt={shoulder_tilt:.1f}°, Spine={spine_angle:.1f}°, YDiff={sh_y_diff:.3f}"
                    
                records.append({
                    'folder': folder,
                    'file': f,
                    'full_path': img_path,
                    'category': category,
                    'pose_detected': True,
                    'shoulder_tilt': round(shoulder_tilt, 2),
                    'spine_angle': round(spine_angle, 2),
                    'shoulder_y_diff': round(sh_y_diff, 4),
                    'shoulder_span_norm': round(sh_span_norm, 4),
                    'shoulder_span_px': round(sh_span_px, 1),
                    'image_w': w,
                    'image_h': h,
                    'reason': reason
                })
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
                    
                records.append({
                    'folder': folder,
                    'file': f,
                    'full_path': img_path,
                    'category': category,
                    'pose_detected': False,
                    'shoulder_tilt': None,
                    'spine_angle': None,
                    'shoulder_y_diff': None,
                    'shoulder_span_norm': None,
                    'shoulder_span_px': None,
                    'image_w': w,
                    'image_h': h,
                    'reason': reason
                })
                
    pose.close()
    df = pd.DataFrame(records)
    print(f"Total analyzed frames: {len(df)}")
    
    # Save full dataset metrics
    df.to_csv(os.path.join(review_dir, "all_frames_analysis.csv"), index=False)
    
    # -------------------------------------------------------------------------
    # 1. HUMAN SPOT-CHECK SAMPLE
    # Select 5 frames each for Best, Good, Poor across different folders
    # -------------------------------------------------------------------------
    spot_samples = []
    for cat in ["Best Posture", "Good Posture", "Poor Posture"]:
        cat_df = df[df['category'] == cat]
        folders_with_cat = cat_df['folder'].unique().tolist()
        random.shuffle(folders_with_cat)
        
        selected_for_cat = []
        # Attempt to take from 5 distinct folders first
        for fol in folders_with_cat:
            sub = cat_df[cat_df['folder'] == fol]
            if not sub.empty:
                chosen = sub.sample(1, random_state=42).iloc[0]
                selected_for_cat.append(chosen)
            if len(selected_for_cat) >= 5:
                break
                
        # If fewer than 5 folders, fill remaining randomly
        if len(selected_for_cat) < 5:
            remaining = cat_df[~cat_df.index.isin([x.name for x in selected_for_cat])]
            if not remaining.empty:
                extra = remaining.sample(min(5 - len(selected_for_cat), len(remaining)), random_state=42)
                for _, r in extra.iterrows():
                    selected_for_cat.append(r)
                    
        for r in selected_for_cat:
            r_dict = r.to_dict()
            r_dict['sample_type'] = 'spot_check'
            spot_samples.append(r_dict)
            
    # -------------------------------------------------------------------------
    # 2. OUTLIER SAMPLES (Folders 6, 3, 11)
    # Pull 5 sample frames each
    # -------------------------------------------------------------------------
    outlier_samples = []
    for target_folder in ['6', '3', '11']:
        fol_df = df[df['folder'] == target_folder]
        # Pick 5 spread out / representative samples
        sample_count = min(5, len(fol_df))
        chosen_indices = np.linspace(0, len(fol_df) - 1, sample_count, dtype=int)
        for idx in chosen_indices:
            r_dict = fol_df.iloc[idx].to_dict()
            r_dict['sample_type'] = f'outlier_check_folder_{target_folder}'
            outlier_samples.append(r_dict)
            
    # -------------------------------------------------------------------------
    # COPY SAMPLES TO spot_check_sample/ WITH DESCRIPTIVE FILENAMES
    # -------------------------------------------------------------------------
    manifest_entries = []
    
    # Copy spot check samples
    for item in spot_samples:
        src = item['full_path']
        ext = os.path.splitext(item['file'])[1]
        cat_clean = item['category'].replace(" ", "")
        base_name = os.path.splitext(item['file'])[0]
        dst_name = f"spotcheck_{cat_clean}_folder{int(item['folder']):02d}_{base_name}{ext}"
        dst_path = os.path.join(review_dir, dst_name)
        shutil.copy2(src, dst_path)
        item['review_filename'] = dst_name
        manifest_entries.append(item)
        
    # Copy outlier check samples
    for item in outlier_samples:
        src = item['full_path']
        ext = os.path.splitext(item['file'])[1]
        cat_clean = item['category'].replace(" ", "")
        base_name = os.path.splitext(item['file'])[0]
        dst_name = f"outlier_folder{int(item['folder']):02d}_{cat_clean}_{base_name}{ext}"
        dst_path = os.path.join(review_dir, dst_name)
        shutil.copy2(src, dst_path)
        item['review_filename'] = dst_name
        manifest_entries.append(item)
        
    manifest_df = pd.DataFrame(manifest_entries)
    manifest_df.to_csv(os.path.join(review_dir, "manifest.csv"), index=False)
    print(f"Copied {len(manifest_entries)} sample frames to {review_dir}")
    print(f"Manifest saved to {os.path.join(review_dir, 'manifest.csv')}")

    # -------------------------------------------------------------------------
    # 3. SHOULDER SPAN OUTLIER STATISTICS
    # -------------------------------------------------------------------------
    # Only frames where pose landmarks were detected can have a valid shoulder span
    df_pose = df[df['pose_detected'] == True].copy()
    
    overall_span_norm_mean = df_pose['shoulder_span_norm'].mean()
    overall_span_norm_std = df_pose['shoulder_span_norm'].std()
    overall_span_px_mean = df_pose['shoulder_span_px'].mean()
    overall_span_px_std = df_pose['shoulder_span_px'].std()
    
    print("\n=======================================================")
    print("SHOULDER SPAN (DISTANCE FROM CAMERA) ANALYSIS")
    print("=======================================================")
    print(f"Overall Dataset (Pose detected frames: {len(df_pose)} / {len(df)}):")
    print(f"  Normalized Shoulder Span: Mean = {overall_span_norm_mean:.4f}, Std = {overall_span_norm_std:.4f}")
    print(f"  Pixel Shoulder Span:      Mean = {overall_span_px_mean:.1f} px, Std = {overall_span_px_std:.1f} px")
    print("-------------------------------------------------------")
    
    outlier_stats = []
    for f_id in subdirs:
        sub = df_pose[df_pose['folder'] == f_id]
        total_in_f = len(df[df['folder'] == f_id])
        det_in_f = len(sub)
        if det_in_f > 0:
            m_norm = sub['shoulder_span_norm'].mean()
            s_norm = sub['shoulder_span_norm'].std()
            m_px = sub['shoulder_span_px'].mean()
            s_px = sub['shoulder_span_px'].std()
            z_norm = (m_norm - overall_span_norm_mean) / overall_span_norm_std if overall_span_norm_std > 0 else 0
            z_px = (m_px - overall_span_px_mean) / overall_span_px_std if overall_span_px_std > 0 else 0
            
            # Dominant category
            top_cat = df[df['folder'] == f_id]['category'].value_counts().index[0]
            top_cat_pct = df[df['folder'] == f_id]['category'].value_counts().iloc[0] / total_in_f * 100
            
            # Image shape
            w = df[df['folder'] == f_id]['image_w'].iloc[0]
            h = df[df['folder'] == f_id]['image_h'].iloc[0]
            
            outlier_stats.append({
                'folder': f_id,
                'resolution': f"{w}x{h}",
                'total_frames': total_in_f,
                'detected_frames': det_in_f,
                'top_category': f"{top_cat} ({top_cat_pct:.1f}%)",
                'mean_span_norm': round(m_norm, 4),
                'z_score_norm': round(z_norm, 2),
                'mean_span_px': round(m_px, 1),
                'z_score_px': round(z_px, 2)
            })
            
            print(f"Folder {f_id:2s} ({w}x{h}, {det_in_f}/{total_in_f} detected, Top: {top_cat} {top_cat_pct:.1f}%):")
            print(f"  Norm Span: {m_norm:.4f} (Z={z_norm:+.2f}) | Pixel Span: {m_px:.1f} px (Z={z_px:+.2f})")
        else:
            print(f"Folder {f_id:2s}: 0 frames detected by MediaPipe Pose")
            
    stats_df = pd.DataFrame(outlier_stats)
    stats_df.to_csv(os.path.join(review_dir, "shoulder_span_summary.csv"), index=False)
    print("=======================================================\n")

if __name__ == "__main__":
    analyze_and_sample()
