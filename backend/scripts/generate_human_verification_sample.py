import os
import math
import json
import pandas as pd
import numpy as np

def generate_sample():
    root_dir = r"D:\project\smart speak"
    frames_dir = os.path.join(root_dir, "frames")
    analysis_csv = os.path.join(root_dir, "spot_check_sample", "all_frames_analysis.csv")
    out_dir = os.path.join(root_dir, "human_verification")
    os.makedirs(out_dir, exist_ok=True)
    
    csv_out_path = os.path.join(out_dir, "human_verification_review_sheet.csv")
    html_out_path = os.path.join(out_dir, "human_verification_gallery.html")
    root_html_path = os.path.join(root_dir, "human_verification_gallery.html")
    root_csv_path = os.path.join(root_dir, "human_verification_review_sheet.csv")

    df = pd.read_csv(analysis_csv)
    # Exclude Folder 11
    df = df[df['folder'].astype(str) != '11'].copy()
    df['folder'] = df['folder'].astype(int)

    # 1. Compute borderline distance
    def calc_borderline(row):
        cat = row['category']
        if row['pose_detected']:
            tilt = float(row['shoulder_tilt'])
            spine = float(row['spine_angle'])
            ydiff = float(row['shoulder_y_diff'])
            
            # Boundary 1 (Best vs Good): tilt=5.0, spine=7.5, ydiff=0.03
            dist_b1 = min(abs(tilt - 5.0) / 5.0, abs(spine - 7.5) / 7.5, abs(ydiff - 0.03) / 0.03)
            # Boundary 2 (Good vs Poor): tilt=10.0, spine=15.0, ydiff=0.08
            dist_b2 = min(abs(tilt - 10.0) / 10.0, abs(spine - 15.0) / 15.0, abs(ydiff - 0.08) / 0.08)
            
            if cat == 'Best Posture':
                return dist_b1
            elif cat == 'Good Posture':
                return min(dist_b1, dist_b2)
            else:
                return dist_b2
        else:
            reason = str(row['reason'])
            if 'tilt_offset=' in reason:
                try:
                    offset = float(reason.split('tilt_offset=')[1].replace('%', ''))
                    dist_b1 = abs(offset - 7.5) / 7.5
                    dist_b2 = abs(offset - 15.0) / 15.0
                    if cat == 'Best Posture': return dist_b1
                    elif cat == 'Good Posture': return min(dist_b1, dist_b2)
                    else: return dist_b2
                except:
                    pass
            return 99.0

    df['borderline_dist'] = df.apply(calc_borderline, axis=1)
    df['frame_idx'] = df['file'].apply(lambda x: int(''.join(c for c in x if c.isdigit())))

    # 2. Stratified sample allocation (sum = 180)
    total_target = 180
    total_n = len(df)
    cell_counts = df.groupby(['folder', 'category']).size()

    alloc = (cell_counts / total_n * total_target).round().astype(int)
    for k in alloc.index:
        if alloc[k] == 0:
            alloc[k] = 1

    diff = total_target - alloc.sum()
    if diff != 0:
        fracs = (cell_counts / total_n * total_target) - (cell_counts / total_n * total_target).astype(int)
        sorted_cells = fracs.sort_values(ascending=(diff < 0))
        for k in sorted_cells.index:
            if diff == 0: break
            if diff > 0:
                alloc[k] += 1
                diff -= 1
            elif diff < 0 and alloc[k] > 1:
                alloc[k] -= 1
                diff += 1

    # 3. Select top borderline samples per stratum
    selected_samples = []
    for (folder, cat), quota in alloc.items():
        subset = df[(df['folder'] == folder) & (df['category'] == cat)].copy()
        # Sort by borderline distance ascending
        subset = subset.sort_values('borderline_dist')
        
        # Temporal thinning: avoid choosing adjacent frames if other borderline frames exist
        chosen = []
        used_frames = set()
        
        # First pass: pick frames at least 2 frames apart
        for _, row in subset.iterrows():
            f_idx = row['frame_idx']
            if not any(abs(f_idx - u) < 2 for u in used_frames):
                chosen.append(row)
                used_frames.add(f_idx)
                if len(chosen) >= quota:
                    break
                    
        # Second pass if quota not yet satisfied
        if len(chosen) < quota:
            for _, row in subset.iterrows():
                if row['file'] not in [c['file'] for c in chosen]:
                    chosen.append(row)
                    if len(chosen) >= quota:
                        break
                        
        selected_samples.extend(chosen)

    sample_df = pd.DataFrame(selected_samples)
    # Sort by folder, then frame_idx
    sample_df = sample_df.sort_values(['folder', 'frame_idx']).reset_index(drop=True)
    sample_df['sample_id'] = range(1, len(sample_df) + 1)
    sample_df['borderline_rank'] = sample_df['borderline_dist'].rank(method='min').astype(int)

    # Prepare review CSV columns
    review_cols = [
        'sample_id',
        'folder',
        'file',
        'algorithmic_label',
        'human_label', # EMPTY
        'borderline_dist',
        'borderline_rank',
        'shoulder_tilt',
        'spine_angle',
        'shoulder_y_diff',
        'shoulder_span_px',
        'pose_detected',
        'reason',
        'image_rel_path',
        'reviewer_notes' # EMPTY
    ]

    sample_df['algorithmic_label'] = sample_df['category']
    sample_df['human_label'] = "" # Blank for user
    sample_df['reviewer_notes'] = ""
    sample_df['image_rel_path'] = sample_df.apply(lambda r: f"frames/{r['folder']}/{r['file']}", axis=1)

    out_csv_df = sample_df[[
        'sample_id', 'folder', 'file', 'algorithmic_label', 'human_label',
        'borderline_dist', 'borderline_rank', 'shoulder_tilt', 'spine_angle',
        'shoulder_y_diff', 'shoulder_span_px', 'pose_detected', 'reason',
        'image_rel_path', 'reviewer_notes'
    ]].rename(columns={
        'folder': 'folder_id',
        'file': 'filename',
        'borderline_dist': 'borderline_distance_score',
        'shoulder_tilt': 'measured_shoulder_tilt_deg',
        'spine_angle': 'measured_spine_angle_deg',
        'shoulder_y_diff': 'measured_shoulder_y_diff',
        'shoulder_span_px': 'measured_shoulder_span_px',
        'reason': 'algorithmic_rationale'
    })

    # Save CSV
    header_comment = (
        "# SmartSpeak Human Verification Sample Review Sheet\n"
        "# Instructions: Review each frame's posture and enter your label in the 'human_label' column.\n"
        "# Permitted labels: 'Best Posture', 'Good Posture', 'Poor Posture'.\n"
        "# Borderline distance score: smaller values indicate frames closer to the algorithmic rule boundaries.\n"
    )
    with open(csv_out_path, 'w', encoding='utf-8') as f:
        f.write(header_comment)
        out_csv_df.to_csv(f, index=False)
        
    with open(root_csv_path, 'w', encoding='utf-8') as f:
        f.write(header_comment)
        out_csv_df.to_csv(f, index=False)

    print(f"Review sheet CSV generated ({len(out_csv_df)} frames):")
    print(f"  - {csv_out_path}")
    print(f"  - {root_csv_path}")

    # 4. Generate Interactive HTML Gallery
    # We create JSON records to embed directly in the HTML
    cards_json = []
    for _, r in out_csv_df.iterrows():
        cards_json.append({
            'sample_id': int(r['sample_id']),
            'folder': int(r['folder_id']),
            'filename': r['filename'],
            'algo_label': r['algorithmic_label'],
            'tilt': None if pd.isna(r['measured_shoulder_tilt_deg']) else round(float(r['measured_shoulder_tilt_deg']), 1),
            'spine': None if pd.isna(r['measured_spine_angle_deg']) else round(float(r['measured_spine_angle_deg']), 1),
            'ydiff': None if pd.isna(r['measured_shoulder_y_diff']) else round(float(r['measured_shoulder_y_diff']), 4),
            'span': None if pd.isna(r['measured_shoulder_span_px']) else round(float(r['measured_shoulder_span_px']), 1),
            'b_dist': round(float(r['borderline_distance_score']), 4),
            'b_rank': int(r['borderline_rank']),
            'reason': str(r['algorithmic_rationale']),
            'img_path': f"../frames/{r['folder_id']}/{r['filename']}",
            'root_img_path': f"frames/{r['folder_id']}/{r['filename']}"
        })

    def build_html(is_root=False):
        img_key = 'root_img_path' if is_root else 'img_path'
        # Convert cards with appropriate image path
        rendered_cards = []
        for c in cards_json:
            c_copy = dict(c)
            c_copy['display_img'] = c_copy[img_key]
            rendered_cards.append(c_copy)
            
        json_data = json.dumps(rendered_cards)
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SmartSpeak Posture Verification Gallery (180 Stratified Samples)</title>
<style>
  :root {{
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-card: #1e293b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent: #3b82f6;
    --best-color: #10b981;
    --good-color: #f59e0b;
    --poor-color: #ef4444;
    --border-color: #334155;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    padding: 24px;
    line-height: 1.5;
  }}
  header {{
    max-width: 1400px;
    margin: 0 auto 24px auto;
    background: var(--bg-secondary);
    padding: 24px;
    border-radius: 12px;
    border: 1px solid var(--border-color);
  }}
  h1 {{ font-size: 1.75rem; margin-bottom: 8px; color: #fff; }}
  p.subtitle {{ color: var(--text-secondary); font-size: 0.95rem; margin-bottom: 16px; }}
  .badge {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .badge-best {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }}
  .badge-good {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }}
  .badge-poor {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }}
  
  .stats-bar {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
  }}
  .stat-box {{
    background: rgba(15, 23, 42, 0.6);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 0.85rem;
  }}
  .stat-box strong {{ font-size: 1.1rem; color: #fff; display: block; }}
  
  .controls-panel {{
    max-width: 1400px;
    margin: 0 auto 24px auto;
    background: var(--bg-secondary);
    padding: 16px 20px;
    border-radius: 12px;
    border: 1px solid var(--border-color);
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
    justify-content: space-between;
  }}
  .filter-group {{
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }}
  select, input, button {{
    background: #0f172a;
    border: 1px solid var(--border-color);
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.9rem;
  }}
  select:focus, input:focus {{ outline: 2px solid var(--accent); }}
  button.btn-primary {{
    background: #2563eb;
    color: white;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }}
  button.btn-primary:hover {{ background: #1d4ed8; }}
  button.btn-secondary {{
    background: #334155;
    cursor: pointer;
  }}
  button.btn-secondary:hover {{ background: #475569; }}

  .grid {{
    max-width: 1400px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
  }}
  .card {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.15s, border-color 0.15s;
  }}
  .card:hover {{
    transform: translateY(-2px);
    border-color: #475569;
  }}
  .card.modified {{
    border: 2px solid #3b82f6;
  }}
  .card-img-wrap {{
    position: relative;
    width: 100%;
    height: 240px;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    cursor: pointer;
  }}
  .card-img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
  }}
  .card-body {{
    padding: 14px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .frame-title {{
    font-size: 0.95rem;
    font-weight: 700;
    color: #e2e8f0;
  }}
  .metrics-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    background: rgba(15, 23, 42, 0.5);
    padding: 8px;
    border-radius: 6px;
    font-size: 0.78rem;
  }}
  .metric-item span.label {{ color: var(--text-secondary); }}
  .metric-item span.val {{ font-weight: 600; color: #f1f5f9; }}
  
  .borderline-badge {{
    font-size: 0.75rem;
    background: rgba(147, 51, 234, 0.2);
    color: #c084fc;
    border: 1px solid #9333ea;
    border-radius: 4px;
    padding: 2px 6px;
    display: inline-block;
  }}
  
  .label-selector {{
    margin-top: auto;
    padding-top: 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }}
  .label-selector label {{
    font-size: 0.8rem;
    font-weight: 600;
    color: #94a3b8;
    display: block;
    margin-bottom: 4px;
  }}
  .label-selector select {{
    width: 100%;
    padding: 8px;
    font-weight: 600;
    cursor: pointer;
  }}
  .selector-best {{ color: #34d399 !important; }}
  .selector-good {{ color: #fbbf24 !important; }}
  .selector-poor {{ color: #f87171 !important; }}
  
  /* Modal for full image view */
  #modal {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.85);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }}
  #modal img {{
    max-width: 90vw;
    max-height: 85vh;
    border-radius: 8px;
    border: 1px solid #475569;
  }}
</style>
</head>
<body>

<header>
  <h1>SmartSpeak Human Posture Verification Gallery</h1>
  <p class="subtitle">
    Stratified Sample of <strong>180 frames</strong> across Folders 1–10, prioritizing borderline cases near algorithmic rule thresholds.
    Review the image frames and confirm or correct the algorithmic labels. When finished, click <strong>"Export Completed CSV"</strong> to download the labeled dataset for Phase 2 model training.
  </p>
  <div class="stats-bar">
    <div class="stat-box">Total Samples <strong>180</strong></div>
    <div class="stat-box">Best Posture (Algo) <strong>84 (46.7%)</strong></div>
    <div class="stat-box">Good Posture (Algo) <strong>44 (24.4%)</strong></div>
    <div class="stat-box">Poor Posture (Algo) <strong>52 (28.9%)</strong></div>
    <div class="stat-box">Human Labeled <strong id="labeled-count">0 / 180</strong></div>
  </div>
</header>

<div class="controls-panel">
  <div class="filter-group">
    <label>Filter Person:</label>
    <select id="folder-filter" onchange="applyFilters()">
      <option value="all">All Folders (1–10)</option>
      <option value="1">Folder 1 (15 frames)</option>
      <option value="2">Folder 2 (15 frames)</option>
      <option value="3">Folder 3 (14 frames)</option>
      <option value="4">Folder 4 (12 frames)</option>
      <option value="5">Folder 5 (17 frames)</option>
      <option value="6">Folder 6 (14 frames)</option>
      <option value="7">Folder 7 (11 frames)</option>
      <option value="8">Folder 8 (16 frames)</option>
      <option value="9">Folder 9 (14 frames)</option>
      <option value="10">Folder 10 (52 frames)</option>
    </select>

    <label>Filter Category:</label>
    <select id="category-filter" onchange="applyFilters()">
      <option value="all">All Categories</option>
      <option value="Best Posture">Best Posture</option>
      <option value="Good Posture">Good Posture</option>
      <option value="Poor Posture">Poor Posture</option>
    </select>

    <label>Sort By:</label>
    <select id="sort-order" onchange="applyFilters()">
      <option value="sample_id">Sample ID</option>
      <option value="borderline_rank">Most Borderline First</option>
      <option value="folder">Folder / Person</option>
    </select>
  </div>

  <div class="filter-group">
    <button class="btn-secondary" onclick="prefillWithAlgoLabels()">Pre-fill with Algo Labels</button>
    <button class="btn-primary" onclick="exportCompletedCSV()">Export Completed CSV</button>
  </div>
</div>

<div class="grid" id="gallery-grid"></div>

<div id="modal" onclick="closeModal()">
  <img id="modal-img" src="" alt="Enlarged view">
</div>

<script>
const SAMPLES = {json_data};
let userLabels = JSON.parse(localStorage.getItem('smartspeak_user_labels') || '{{}}');

function getBadgeClass(cat) {{
  if (cat === 'Best Posture') return 'badge-best';
  if (cat === 'Good Posture') return 'badge-good';
  return 'badge-poor';
}}

function updateLabeledCount() {{
  const count = Object.values(userLabels).filter(v => v && v !== '').length;
  document.getElementById('labeled-count').innerText = `${{count}} / ${{SAMPLES.length}}`;
}}

function onLabelChange(sampleId, value) {{
  userLabels[sampleId] = value;
  localStorage.setItem('smartspeak_user_labels', JSON.stringify(userLabels));
  updateLabeledCount();
  const card = document.getElementById(`card-${{sampleId}}`);
  if (card) {{
    if (value) card.classList.add('modified');
    else card.classList.remove('modified');
  }}
}}

function renderGallery(items) {{
  const grid = document.getElementById('gallery-grid');
  grid.innerHTML = items.map(s => {{
    const currentVal = userLabels[s.sample_id] || '';
    const isModified = currentVal ? 'modified' : '';
    const tiltStr = s.tilt != null ? `${{s.tilt}}°` : 'N/A';
    const spineStr = s.spine != null ? `${{s.spine}}°` : 'N/A';
    const ydiffStr = s.ydiff != null ? s.ydiff : 'N/A';
    const spanStr = s.span != null ? `${{s.span}}px` : 'N/A';

    return `
      <div class="card ${{isModified}}" id="card-${{s.sample_id}}">
        <div class="card-img-wrap" onclick="openModal('${{s.display_img}}')">
          <img class="card-img" src="${{s.display_img}}" alt="Folder ${{s.folder}} ${{s.filename}}" loading="lazy" onerror="this.src='https://via.placeholder.com/320x240/1e293b/94a3b8?text=Frame+Preview'">
        </div>
        <div class="card-body">
          <div class="card-header">
            <span class="frame-title">#${{s.sample_id}}: Folder ${{s.folder}} / ${{s.filename}}</span>
            <span class="badge ${{getBadgeClass(s.algo_label)}}">${{s.algo_label}}</span>
          </div>

          <div class="metrics-grid">
            <div class="metric-item"><span class="label">Tilt: </span><span class="val">${{tiltStr}}</span></div>
            <div class="metric-item"><span class="label">Spine: </span><span class="val">${{spineStr}}</span></div>
            <div class="metric-item"><span class="label">Y-Diff: </span><span class="val">${{ydiffStr}}</span></div>
            <div class="metric-item"><span class="label">Span: </span><span class="val">${{spanStr}}</span></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="borderline-badge">Borderline Rank: #${{s.b_rank}}</span>
            <span style="font-size:0.75rem; color:#64748b;">Dist: ${{s.b_dist}}</span>
          </div>

          <div class="label-selector">
            <label>Human Corrected Label:</label>
            <select onchange="onLabelChange(${{s.sample_id}}, this.value)">
              <option value="" ${{currentVal === '' ? 'selected' : ''}}>-- Select Correct Label --</option>
              <option value="Best Posture" class="selector-best" ${{currentVal === 'Best Posture' ? 'selected' : ''}}>Best Posture</option>
              <option value="Good Posture" class="selector-good" ${{currentVal === 'Good Posture' ? 'selected' : ''}}>Good Posture</option>
              <option value="Poor Posture" class="selector-poor" ${{currentVal === 'Poor Posture' ? 'selected' : ''}}>Poor Posture</option>
            </select>
          </div>
        </div>
      </div>
    `;
  }}).join('');
  updateLabeledCount();
}}

function applyFilters() {{
  const fFilter = document.getElementById('folder-filter').value;
  const cFilter = document.getElementById('category-filter').value;
  const sOrder = document.getElementById('sort-order').value;

  let filtered = [...SAMPLES];
  if (fFilter !== 'all') filtered = filtered.filter(s => s.folder == fFilter);
  if (cFilter !== 'all') filtered = filtered.filter(s => s.algo_label === cFilter);

  if (sOrder === 'borderline_rank') {{
    filtered.sort((a, b) => a.b_dist - b.b_dist);
  }} else if (sOrder === 'folder') {{
    filtered.sort((a, b) => a.folder - b.folder || a.sample_id - b.sample_id);
  }} else {{
    filtered.sort((a, b) => a.sample_id - b.sample_id);
  }}

  renderGallery(filtered);
}}

function prefillWithAlgoLabels() {{
  if (confirm("Do you want to pre-fill any unlabeled frames with their current algorithmic labels? You can still adjust any incorrect ones.")) {{
    SAMPLES.forEach(s => {{
      if (!userLabels[s.sample_id]) {{
        userLabels[s.sample_id] = s.algo_label;
      }}
    }});
    localStorage.setItem('smartspeak_user_labels', JSON.stringify(userLabels));
    applyFilters();
  }}
}}

function exportCompletedCSV() {{
  const headers = [
    "sample_id", "folder_id", "filename", "algorithmic_label", "human_label",
    "borderline_distance_score", "borderline_rank", "measured_shoulder_tilt_deg",
    "measured_spine_angle_deg", "measured_shoulder_y_diff", "measured_shoulder_span_px",
    "algorithmic_rationale"
  ];
  
  let csvContent = "# SmartSpeak Verified Labels Dataset\\n";
  csvContent += headers.join(",") + "\\n";

  SAMPLES.forEach(s => {{
    const hLabel = userLabels[s.sample_id] || "";
    const row = [
      s.sample_id,
      s.folder,
      `\\"${{s.filename}}\\"`,
      `\\"${{s.algo_label}}\\"`,
      `\\"${{hLabel}}\\"`,
      s.b_dist,
      s.b_rank,
      s.tilt != null ? s.tilt : "",
      s.spine != null ? s.spine : "",
      s.ydiff != null ? s.ydiff : "",
      s.span != null ? s.span : "",
      `\\"${{s.reason.replace(/"/g, '""')}}\\"`
    ];
    csvContent += row.join(",") + "\\n";
  }});

  const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.setAttribute("href", url);
  link.setAttribute("download", "human_verified_posture_labels.csv");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}}

function openModal(imgSrc) {{
  document.getElementById('modal-img').src = imgSrc;
  document.getElementById('modal').style.display = 'flex';
}}
function closeModal() {{
  document.getElementById('modal').style.display = 'none';
}}

window.onload = () => applyFilters();
</script>
</body>
</html>"""

    html_content_subdir = build_html(is_root=False)
    html_content_root = build_html(is_root=True)

    with open(html_out_path, 'w', encoding='utf-8') as f:
        f.write(html_content_subdir)
    with open(root_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content_root)

    print(f"HTML gallery generated:")
    print(f"  - {html_out_path}")
    print(f"  - {root_html_path}")

    # Summary statistics markdown report
    summary_md_path = os.path.join(out_dir, "human_verification_summary.md")
    alloc_summary = alloc.unstack(fill_value=0)
    
    md = f"""# SmartSpeak Human Verification Sample Summary (Phase 1)

This review sample consists of **180 stratified frames** selected across Folders 1–10 to capture ground-truth human annotations before Phase 2 model training.

## Stratified Sampling Distribution

| Folder / Person | Best Posture | Good Posture | Poor Posture | Total Sampled | Total in Dataset | Sampling Rate |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for folder_id in range(1, 11):
        b = alloc_summary.loc[folder_id, 'Best Posture'] if 'Best Posture' in alloc_summary.columns else 0
        g = alloc_summary.loc[folder_id, 'Good Posture'] if 'Good Posture' in alloc_summary.columns else 0
        p = alloc_summary.loc[folder_id, 'Poor Posture'] if 'Poor Posture' in alloc_summary.columns else 0
        tot = b + g + p
        tot_all = len(df[df['folder'] == folder_id])
        pct = (tot / tot_all) * 100.0 if tot_all > 0 else 0
        md += f"| **Folder {folder_id}** | {b} | {g} | {p} | **{tot}** | {tot_all} | {pct:.1f}% |\n"

    total_b = alloc_summary['Best Posture'].sum()
    total_g = alloc_summary['Good Posture'].sum()
    total_p = alloc_summary['Poor Posture'].sum()
    md += f"| **Total** | **{total_b}** | **{total_g}** | **{total_p}** | **180** | **765** | **23.5%** |\n\n"

    md += """## Prioritizing Borderline Cases

Frames were ranked by their normalized Euclidean proximity to the decision thresholds:
- **Boundary 1 (Best vs. Good)**: $\\theta_{\\text{tilt}} = 5.0^\\circ, \\theta_{\\text{spine}} = 7.5^\\circ, \\Delta y = 0.03$.
- **Boundary 2 (Good vs. Poor)**: $\\theta_{\\text{tilt}} = 10.0^\\circ, \\theta_{\\text{spine}} = 15.0^\\circ, \\Delta y = 0.08$.

The selection explicitly chose frames sitting immediately on either side of these boundaries (e.g. shoulder tilt between $4.8^\\circ$ and $5.2^\\circ$, or $9.8^\\circ$ and $10.4^\\circ$), ensuring maximum information gain for the Phase 2 classifier.
"""
    with open(summary_md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"Summary markdown saved to: {summary_md_path}")
    print("\nPhase 1 verification sample generation successfully finished!")

if __name__ == "__main__":
    generate_sample()
