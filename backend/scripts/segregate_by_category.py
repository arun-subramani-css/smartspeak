import os
import shutil
import pandas as pd

def organize_by_category():
    src_csv = r"D:\project\smart speak\frames_classified\detailed_frame_classifications.csv"
    dest_root = r"D:\project\smart speak\frames_by_category"
    
    df = pd.read_csv(src_csv)
    print(f"Loaded {len(df)} records from {src_csv}")
    
    categories = ["Best Posture", "Good Posture", "Poor Posture"]
    for cat in categories:
        os.makedirs(os.path.join(dest_root, cat), exist_ok=True)
        
    records = []
    
    for idx, row in df.iterrows():
        folder = int(row['folder'])
        filename = row['filename']
        category = row['category']
        src_path = row['destination_path'] # From frames_classified
        
        # Fallback to original frames if needed
        if not os.path.exists(src_path):
            src_path = os.path.join(r"D:\project\smart speak\frames", str(folder), filename)
            
        # Target filename preserving person/folder association
        new_filename = f"person_{folder:02d}_{filename}"
        dest_path = os.path.join(dest_root, category, new_filename)
        
        shutil.copy2(src_path, dest_path)
        
        records.append({
            'category': category,
            'person_id': folder,
            'original_filename': filename,
            'categorized_filename': new_filename,
            'full_path': dest_path,
            'shoulder_tilt': row.get('shoulder_tilt'),
            'spine_angle': row.get('spine_angle'),
            'shoulder_y_diff': row.get('shoulder_y_diff'),
            'reason': row.get('reason')
        })
        
    out_df = pd.DataFrame(records)
    out_csv = os.path.join(dest_root, "category_manifest.csv")
    out_df.to_csv(out_csv, index=False)
    
    print("\n=======================================================")
    print("SEGREGATION BY CATEGORY COMPLETED")
    print("=======================================================")
    print(f"Destination: {dest_root}")
    for cat in categories:
        cat_count = len(os.listdir(os.path.join(dest_root, cat)))
        print(f"  - {cat:15s}: {cat_count:3d} frames")
    print(f"Manifest saved to: {out_csv}")
    print("=======================================================\n")

if __name__ == "__main__":
    organize_by_category()
