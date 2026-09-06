import os
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
import shap

def format_confusion_matrix_markdown(cm, class_names):
    markdown = f"| Actual \\ Predicted | " + " | ".join(class_names) + " |\n"
    markdown += "| --- | " + " | ".join(["---"] * len(class_names)) + " |\n"
    for i, row_label in enumerate(class_names):
        row_str = f"| **{row_label}** | " + " | ".join(str(val) for val in cm[i]) + " |\n"
        markdown += row_str
    return markdown

def main():
    # 1. FILE FORMAT CHECK
    excel_path = r"d:\project\smart speak\confidence_features.csv.xlsx"
    csv_dir = r"d:\project\smart speak\data"
    csv_path = os.path.join(csv_dir, "confidence_features.csv")
    models_dir = r"d:\project\smart speak\models"

    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)

    print("=================================================================")
    print("STEP 1: File Format Check")
    print("=================================================================")
    
    # Read the first 4 bytes to verify if it's a true Excel file
    with open(excel_path, 'rb') as f:
        sig = f.read(4)
    print(f"File path: {excel_path}")
    print(f"File signature (hex): {sig.hex()}")
    
    is_xlsx = sig == b'PK\x03\x04'
    if is_xlsx:
        print("Result: True Excel ZIP/XML binary format detected. Parsing via pandas.read_excel().")
        df = pd.read_excel(excel_path)
    else:
        print("Result: Plain text format detected. Parsing via pandas.read_csv().")
        df = pd.read_csv(excel_path)

    # Save to data/confidence_features.csv
    df.to_csv(csv_path, index=False)
    print(f"Dataset successfully saved to {csv_path}")
    print(f"Dataset shape: {df.shape} (Rows: {df.shape[0]}, Columns: {df.shape[1]})")
    print("\n--- First 3 Rows ---")
    print(df.head(3))
    print("\n--- Dataset Column Data Types (dtypes) ---")
    print(df.dtypes)
    print("=================================================================\n")

    # 2. HANDLE CORRELATED ROWS (BLOCK ID DEFINITION)
    print("=================================================================")
    print("STEP 2: Contiguous Block Identification")
    print("=================================================================")
    # block_id increments whenever confidence_label changes from the previous row
    df['block_id'] = (df['confidence_label'] != df['confidence_label'].shift()).cumsum()
    
    num_rows = len(df)
    class_dist = df['confidence_label'].value_counts()
    num_blocks = df['block_id'].nunique()
    block_lengths = df['block_id'].value_counts()
    avg_block_len = block_lengths.mean()
    min_block_len = block_lengths.min()
    max_block_len = block_lengths.max()

    print(f"Total Rows: {num_rows}")
    print(f"Number of Blocks Identified: {num_blocks}")
    print(f"Average Block Length: {avg_block_len:.2f} rows")
    print(f"Min Block Length: {min_block_len} rows")
    print(f"Max Block Length: {max_block_len} rows")
    print("\nClass distribution:")
    print(class_dist)
    print("=================================================================\n")

    # 3. PREPROCESSING & ENCODING
    # Separate numeric vs categorical columns
    num_cols = [
        'eye_shoulder_y_ratio', 'shoulder_y_diff', 'wrist_distance_x', 'wrist_shoulder_ratio', 
        'nose_eye_center_offset_x', 'shoulder_span', 'hip_shoulder_y_diff', 'body_lean_x', 
        'shoulder_center_x', 'hip_center_x', 'spine_angle', 'eye_distance', 'head_tilt_angle', 
        'eye_distance_ratio', 'shoulder_slope'
    ]
    cat_cols = ['head_direction', 'arm_position', 'posture']
    target_col = 'confidence_label'

    # Target Mapping
    target_map = {'Low': 0, 'Neutral': 1, 'Confident': 2}
    class_names = ['Low', 'Neutral', 'Confident']
    df['target'] = df[target_col].map(target_map)

    X = df[num_cols + cat_cols]
    y = df['target']
    groups = df['block_id']

    # Preprocessing Pipeline for features
    # OneHotEncoder for the categorical columns, remainder passthrough
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_cols)
        ],
        remainder='passthrough'
    )

    # 4. TRAIN-TEST SPLITS
    # Group-aware split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))
    X_train_g, X_test_g = X.iloc[train_idx], X.iloc[test_idx]
    y_train_g, y_test_g = y.iloc[train_idx], y.iloc[test_idx]

    # Naive split (random rows)
    X_train_n, X_test_n, y_train_n, y_test_n = train_test_split(X, y, test_size=0.2, random_state=42)

    print("=================================================================")
    print("STEP 3: Splitting Statistics")
    print("=================================================================")
    print("GROUP-AWARE Split:")
    print(f"  Train set: {X_train_g.shape[0]} rows, {y_train_g.nunique()} classes, {groups.iloc[train_idx].nunique()} blocks")
    print(f"  Test set:  {X_test_g.shape[0]} rows, {y_test_g.nunique()} classes, {groups.iloc[test_idx].nunique()} blocks")
    print("NAIVE Split:")
    print(f"  Train set: {X_train_n.shape[0]} rows")
    print(f"  Test set:  {X_test_n.shape[0]} rows")
    print("=================================================================\n")

    # Instantiate pipelines
    # We wrap the preprocessor and the classifier inside a Pipeline so that when we save/load,
    # the preprocessing steps (including OneHotEncoder state) are preserved and done automatically on raw data.
    from sklearn.pipeline import Pipeline
    
    rf_g_pipeline = Pipeline([
        ('preprocessor', clone(preprocessor)),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    
    xgb_g_pipeline = Pipeline([
        ('preprocessor', clone(preprocessor)),
        ('classifier', XGBClassifier(n_estimators=100, random_state=42, eval_metric='mlogloss'))
    ])

    rf_n_pipeline = Pipeline([
        ('preprocessor', clone(preprocessor)),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
    ])

    xgb_n_pipeline = Pipeline([
        ('preprocessor', clone(preprocessor)),
        ('classifier', XGBClassifier(n_estimators=100, random_state=42, eval_metric='mlogloss'))
    ])

    print("=================================================================")
    print("STEP 4: Training and Evaluation")
    print("=================================================================")
    results = {}

    # Define helper to evaluate a model pipeline
    def evaluate_model(pipeline, X_train, y_train, X_test, y_test, split_name, model_name):
        print(f"Training {model_name} on {split_name} split...")
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        
        acc = accuracy_score(y_test, y_pred)
        prec, rec, f1, _ = precision_recall_fscore_support(y_test, y_pred, average='macro')
        cm = confusion_matrix(y_test, y_pred)
        
        return {
            'accuracy': acc,
            'precision': prec,
            'recall': rec,
            'f1': f1,
            'confusion_matrix': cm,
            'pipeline': pipeline
        }

    # Evaluate all 4 scenarios
    results[('Group-Aware', 'Random Forest')] = evaluate_model(
        rf_g_pipeline, X_train_g, y_train_g, X_test_g, y_test_g, 'Group-Aware', 'Random Forest'
    )
    results[('Group-Aware', 'XGBoost')] = evaluate_model(
        xgb_g_pipeline, X_train_g, y_train_g, X_test_g, y_test_g, 'Group-Aware', 'XGBoost'
    )
    results[('Naive', 'Random Forest')] = evaluate_model(
        rf_n_pipeline, X_train_n, y_train_n, X_test_n, y_test_n, 'Naive', 'Random Forest'
    )
    results[('Naive', 'XGBoost')] = evaluate_model(
        xgb_n_pipeline, X_train_n, y_train_n, X_test_n, y_test_n, 'Naive', 'XGBoost'
    )
    print("=================================================================\n")

    # Print comparative results table to console
    print("=================================================================")
    print("COMPARATIVE RESULTS SUMMARY (CONSOLE OUTPUT)")
    print("=================================================================")
    header = f"{'Split Strategy':<15} | {'Model':<15} | {'Accuracy':<10} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10}"
    separator = "-" * len(header)
    print(header)
    print(separator)
    for (split_name, model_name), metrics in results.items():
        print(f"{split_name:<15} | {model_name:<15} | {metrics['accuracy']:<10.4f} | {metrics['precision']:<10.4f} | {metrics['recall']:<10.4f} | {metrics['f1']:<10.4f}")
    print("=================================================================\n")

    # Print confusion matrices to console
    print("=================================================================")
    print("CONFUSION MATRICES (CONSOLE OUTPUT)")
    print("=================================================================")
    for (split_name, model_name), metrics in results.items():
        print(f"\n--- {model_name} ({split_name}) ---")
        print(f"Classes: {class_names}")
        print(metrics['confusion_matrix'])
    print("=================================================================\n")

    # 5. DETERMINE BEST MODEL (Based on Group-Aware F1-Score)
    rf_g_f1 = results[('Group-Aware', 'Random Forest')]['f1']
    xgb_g_f1 = results[('Group-Aware', 'XGBoost')]['f1']

    if rf_g_f1 >= xgb_g_f1:
        best_key = ('Group-Aware', 'Random Forest')
        best_name = 'Random Forest'
    else:
        best_key = ('Group-Aware', 'XGBoost')
        best_name = 'XGBoost'

    best_pipeline = results[best_key]['pipeline']
    best_metrics = results[best_key]

    print("=================================================================")
    print(f"STEP 5: Save Best Model ({best_name})")
    print("=================================================================")
    model_save_path = os.path.join(models_dir, "confidence_model.pkl")
    joblib.dump(best_pipeline, model_save_path)
    print(f"Best performing group-aware model ({best_name}) saved to {model_save_path}")
    print("=================================================================\n")

    # 6. SHAP EXPLAINABILITY
    print("=================================================================")
    print("STEP 6: Generate SHAP Summary Plot")
    print("=================================================================")
    # Preprocess test set using the fitted ColumnTransformer from the best pipeline
    fitted_preprocessor = best_pipeline.named_steps['preprocessor']
    classifier = best_pipeline.named_steps['classifier']
    
    # Process test features
    X_test_preprocessed = fitted_preprocessor.transform(X_test_g)
    
    # Extract feature names from OneHotEncoder + remainder
    raw_features = fitted_preprocessor.get_feature_names_out()
    # Clean the feature names to make them look nice and human-readable
    clean_features = [f.replace('cat__', '').replace('remainder__', '') for f in raw_features]
    
    X_test_preprocessed_df = pd.DataFrame(X_test_preprocessed, columns=clean_features)

    print("Preprocessed feature names:")
    print(clean_features)

    # Initialize SHAP explainer
    # TreeExplainer works directly on the scikit-learn classifier of tree-based models
    explainer = shap.TreeExplainer(classifier)
    shap_values = explainer.shap_values(X_test_preprocessed_df)

    # Generate and save SHAP plot
    shap_plot_path = os.path.join(models_dir, "shap_summary.png")
    
    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_values, X_test_preprocessed_df, class_names=class_names, show=False)
    plt.title(f"SHAP Feature Importance Summary for {best_name} (Group-Aware)", fontsize=14, pad=15)
    plt.tight_layout()
    plt.savefig(shap_plot_path, dpi=300)
    plt.close()
    print(f"SHAP summary plot saved to {shap_plot_path}")
    print("=================================================================\n")

    # 7. Programmatic Feature Importance Extraction for Report
    # Calculate average absolute SHAP values across all classes to rank features
    if isinstance(shap_values, list):
        # shap_values is a list of arrays (one per class), shape of each is (n_samples, n_features)
        mean_abs_shap = np.mean([np.mean(np.abs(cls_shap), axis=0) for cls_shap in shap_values], axis=0)
    elif isinstance(shap_values, np.ndarray):
        if shap_values.ndim == 3:
            # Let's inspect the shapes to determine which axis represents features
            shape = shap_values.shape
            num_features = len(clean_features)
            if shape[2] == num_features:
                # Shape is (n_classes, n_samples, n_features)
                mean_abs_shap = np.mean(np.mean(np.abs(shap_values), axis=1), axis=0)
            elif shape[1] == num_features:
                # Shape is (n_samples, n_features, n_classes)
                mean_abs_shap = np.mean(np.mean(np.abs(shap_values), axis=0), axis=1)
            else:
                # Fallback to mean over samples and classes
                mean_abs_shap = np.mean(np.abs(shap_values), axis=(0, 2))
        elif shap_values.ndim == 2:
            # shape (n_samples, n_features)
            mean_abs_shap = np.mean(np.abs(shap_values), axis=0)
        else:
            mean_abs_shap = classifier.feature_importances_ if hasattr(classifier, 'feature_importances_') else np.zeros(len(clean_features))
    else:
        # Check if it is a SHAP Explanation object
        if hasattr(shap_values, 'values') and isinstance(shap_values.values, np.ndarray):
            vals = shap_values.values
            if vals.ndim == 3:
                mean_abs_shap = np.mean(np.mean(np.abs(vals), axis=0), axis=1)
            elif vals.ndim == 2:
                mean_abs_shap = np.mean(np.abs(vals), axis=0)
            else:
                mean_abs_shap = np.zeros(len(clean_features))
        else:
            mean_abs_shap = classifier.feature_importances_ if hasattr(classifier, 'feature_importances_') else np.zeros(len(clean_features))

    importance_df = pd.DataFrame({
        'Feature': clean_features,
        'Importance': mean_abs_shap
    }).sort_values(by='Importance', ascending=False)
    
    top_5_features = importance_df.head(5)
    print("Top 5 Features based on SHAP Importance:")
    print(top_5_features)

    # 8. WRITE CONFIDENCE MODEL REPORT
    report_path = os.path.join(models_dir, "confidence_model_report.md")
    print(f"\nWriting Report to {report_path}...")

    # Dictionary of human-readable feature descriptions
    feature_interpretations = {
        'wrist_shoulder_ratio': 'Ratio of wrist distance to shoulder span. Open arm positioning suggests expansive, confident body language.',
        'arm_position_Closed Arms': 'Indicates closed/crossed arms, which strongly suggests a defensive, closed posture and lower confidence.',
        'arm_position_Open Arms': 'Indicates open arms, which is highly associated with an open, welcoming, and confident posture.',
        'arm_position_Partially Open': 'Indicates partially open arm gestures, indicating moderate or relaxed confidence.',
        'posture_Upright': 'Indicates upright posture, which demonstrates an active, attentive, and confident physical state.',
        'posture_Slouched': 'Indicates slouched posture, showing upper body collapse, representing low confidence or energy.',
        'posture_Stiff': 'Indicates high physical stiffness/tension, which is often associated with anxiety or forced posture.',
        'head_direction_Looking Straight': 'Indicates looking directly at the camera, representing stable, confident eye contact.',
        'head_direction_Center': 'Head oriented directly center, reflecting good eye contact and presentation engagement.',
        'head_direction_Looking Left': 'Indicates head turned left, which is correlated with looking away/avoiding eye contact.',
        'head_direction_Looking Right': 'Indicates head turned right, which is correlated with looking away/avoiding eye contact.',
        'spine_angle': 'Measures deviation of spine alignment. Straighter spine angles indicate confident, upright postures.',
        'body_lean_x': 'Tracks horizontal body swaying. Stable values represent centered confidence; high sway represents nervousness.',
        'shoulder_slope': 'Slope of the shoulders. Level shoulders correspond to a relaxed, natural, and confident stance.',
        'eye_distance_ratio': 'Tracks forward/backward head translation. High movements correspond to leaning, which signals posture shifts.',
        'wrist_distance_x': 'Horizontal distance between wrists. Larger spacing corresponds to active, expressive hand gestures.',
        'eye_shoulder_y_ratio': 'Ratio of eye level to shoulder level. Tracks neck extension; higher values reflect open, upright head positioning.',
        'head_tilt_angle': 'Measures head tilt sideways. Large tilt angles indicate physical tension or self-doubt.',
        'shoulder_span': 'Pixel span of shoulders, providing the baseline for physical sizing and normalization.',
        'shoulder_y_diff': 'Vertical difference between left and right shoulder levels. Level shoulders indicate good posture and confidence, whereas large differences represent tilt or asymmetric slouching.',
        'nose_eye_center_offset_x': 'Horizontal displacement of the nose relative to the eye center. Larger values indicate head turning/looking away, while centered values represent looking straight at the audience.'
    }

    # Format Top 5 Feature Interpretations
    top_5_text = ""
    for idx, row in top_5_features.iterrows():
        feat = row['Feature']
        val = row['Importance']
        interpretation = feature_interpretations.get(feat, "Postural or head position measurement relevant to physical body language.")
        top_5_text += f"- **{feat}** (Importance: {val:.4f}) — {interpretation}\n"

    # Compile the Markdown Report content
    report_content = f"""# SmartSpeak Confidence Classifier Training & Evaluation Report

This report documents the offline training, validation, and explainability results for the SmartSpeak Confidence Model, which evaluates speaker confidence from pose-derived features.

## 1. Dataset Summary

The dataset consists of sequential video frames processing body-postural landmarks, which creates a highly correlated sequence of contiguous frames.

- **Total Rows (Samples)**: {num_rows:,}
- **Features**: 18 input features (15 numeric, 3 categorical)
- **Target Variable**: `confidence_label` (3 classes: Confident, Neutral, Low)
- **Class Distribution**:
  - **Confident**: {class_dist.get('Confident', 0)} ({class_dist.get('Confident', 0)/num_rows*100:.1f}%)
  - **Neutral**: {class_dist.get('Neutral', 0)} ({class_dist.get('Neutral', 0)/num_rows*100:.1f}%)
  - **Low**: {class_dist.get('Low', 0)} ({class_dist.get('Low', 0)/num_rows*100:.1f}%)

### Contiguous Block Structure
Since the dataset is captured frame-by-frame, sequential samples are highly correlated. To prevent data leakage during train/test splitting, we grouped rows into blocks of contiguous labels:
- **Number of blocks detected**: {num_blocks}
- **Average block length**: {avg_block_len:.2f} rows (range: {min_block_len} - {max_block_len} rows)

---

## 2. Evaluation Results: Naive vs. Group-Aware Splits

We trained a **Random Forest Classifier** and an **XGBoost Classifier** under two different data splitting strategies:
1. **Naive Split (Random-Row)**: An 80/20 train/test split on individual rows. Because consecutive frames are highly correlated, this strategy leaks information from train to test, artificially inflating metrics.
2. **Group-Aware Split (Block-Grouping)**: An 80/20 split based on `block_id` using `GroupShuffleSplit`. This guarantees that all frames from the same block land entirely in either train or test, reflecting real-world generalization performance on unseen videos.

### Performance Comparison Table

| Split Strategy | Model Name | Accuracy | Precision (Macro) | Recall (Macro) | F1-Score (Macro) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Naive (Random-Row)** | Random Forest | {results[('Naive', 'Random Forest')]['accuracy']:.4f} | {results[('Naive', 'Random Forest')]['precision']:.4f} | {results[('Naive', 'Random Forest')]['recall']:.4f} | {results[('Naive', 'Random Forest')]['f1']:.4f} |
| **Naive (Random-Row)** | XGBoost | {results[('Naive', 'XGBoost')]['accuracy']:.4f} | {results[('Naive', 'XGBoost')]['precision']:.4f} | {results[('Naive', 'XGBoost')]['recall']:.4f} | {results[('Naive', 'XGBoost')]['f1']:.4f} |
| **Group-Aware (Block-Grouping)** | Random Forest | {results[('Group-Aware', 'Random Forest')]['accuracy']:.4f} | {results[('Group-Aware', 'Random Forest')]['precision']:.4f} | {results[('Group-Aware', 'Random Forest')]['recall']:.4f} | {results[('Group-Aware', 'Random Forest')]['f1']:.4f} |
| **Group-Aware (Block-Grouping)** | XGBoost | {results[('Group-Aware', 'XGBoost')]['accuracy']:.4f} | {results[('Group-Aware', 'XGBoost')]['precision']:.4f} | {results[('Group-Aware', 'XGBoost')]['recall']:.4f} | {results[('Group-Aware', 'XGBoost')]['f1']:.4f} |

> [!WARNING]
> **Why the Naive split results are misleading:**
> The naive split yields near-perfect accuracy (~98%+) because contiguous video frames share almost identical coordinates. When split randomly, a frame $t$ might end up in the training set and frame $t+1$ (which is virtually identical) in the test set. This leaks the training data directly into the evaluation. 
> The **Group-Aware split** represents the true generalization capacity when evaluating confidence on new, unseen speech sessions.

---

## 3. Final Chosen Model: {best_name} (Group-Aware)

Based on the Group-Aware evaluation, the **{best_name}** model was selected as it yielded the highest macro F1-score of **{best_metrics['f1']:.4f}**.

### Group-Aware Performance Metrics
- **Accuracy**: {best_metrics['accuracy']:.4f}
- **Macro Precision**: {best_metrics['precision']:.4f}
- **Macro Recall**: {best_metrics['recall']:.4f}
- **Macro F1-Score**: {best_metrics['f1']:.4f}

### Confusion Matrices

#### Chosen Model: {best_name} (Group-Aware Split)
{format_confusion_matrix_markdown(results[('Group-Aware', best_name)]['confusion_matrix'], class_names)}

#### Reference: Random Forest (Group-Aware Split)
{format_confusion_matrix_markdown(results[('Group-Aware', 'Random Forest')]['confusion_matrix'], class_names)}

#### Reference: XGBoost (Group-Aware Split)
{format_confusion_matrix_markdown(results[('Group-Aware', 'XGBoost')]['confusion_matrix'], class_names)}

#### Reference: Random Forest (Naive Random Split)
{format_confusion_matrix_markdown(results[('Naive', 'Random Forest')]['confusion_matrix'], class_names)}

#### Reference: XGBoost (Naive Random Split)
{format_confusion_matrix_markdown(results[('Naive', 'XGBoost')]['confusion_matrix'], class_names)}

---

## 4. SHAP Feature Interpretations

The SHAP summary plot is saved at `/models/shap_summary.png`. It explains how the features drive the predictions for each confidence category (Low, Neutral, Confident).

Here are the top 5 features based on their average absolute SHAP impact:

{top_5_text}

---

## 5. Model Loading and Usage

The model is saved as a complete scikit-learn Pipeline (preprocessing + classifier) at `/models/confidence_model.pkl`. It can be loaded and run on raw features as follows:

```python
import joblib
import pandas as pd

# Load pipeline
pipeline = joblib.load('models/confidence_model.pkl')

# Expects raw dataframe with columns:
# ['eye_shoulder_y_ratio', 'shoulder_y_diff', 'wrist_distance_x', 'wrist_shoulder_ratio', 
#  'nose_eye_center_offset_x', 'shoulder_span', 'hip_shoulder_y_diff', 'body_lean_x', 
#  'shoulder_center_x', 'hip_center_x', 'spine_angle', 'eye_distance', 'head_tilt_angle', 
#  'eye_distance_ratio', 'shoulder_slope', 'head_direction', 'arm_position', 'posture']

# Predict confidence class (0 = Low, 1 = Neutral, 2 = Confident)
predictions = pipeline.predict(df_features)
```

---
*Report generated on 2026-08-01*
"""

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"Report successfully saved to {report_path}")
    print("=================================================================\n")

if __name__ == '__main__':
    main()
