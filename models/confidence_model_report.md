# SmartSpeak Confidence Classifier Training & Evaluation Report

This report documents the offline training, validation, and explainability results for the SmartSpeak Confidence Model, which evaluates speaker confidence from pose-derived features.

## 1. Dataset Summary

The dataset consists of sequential video frames processing body-postural landmarks, which creates a highly correlated sequence of contiguous frames.

- **Total Rows (Samples)**: 5,949
- **Features**: 18 input features (15 numeric, 3 categorical)
- **Target Variable**: `confidence_label` (3 classes: Confident, Neutral, Low)
- **Class Distribution**:
  - **Confident**: 3132 (52.6%)
  - **Neutral**: 1662 (27.9%)
  - **Low**: 1155 (19.4%)

### Contiguous Block Structure
Since the dataset is captured frame-by-frame, sequential samples are highly correlated. To prevent data leakage during train/test splitting, we grouped rows into blocks of contiguous labels:
- **Number of blocks detected**: 601
- **Average block length**: 9.90 rows (range: 1 - 225 rows)

---

## 2. Evaluation Results: Naive vs. Group-Aware Splits

We trained a **Random Forest Classifier** and an **XGBoost Classifier** under two different data splitting strategies:
1. **Naive Split (Random-Row)**: An 80/20 train/test split on individual rows. Because consecutive frames are highly correlated, this strategy leaks information from train to test, artificially inflating metrics.
2. **Group-Aware Split (Block-Grouping)**: An 80/20 split based on `block_id` using `GroupShuffleSplit`. This guarantees that all frames from the same block land entirely in either train or test, reflecting real-world generalization performance on unseen videos.

### Performance Comparison Table

| Split Strategy | Model Name | Accuracy | Precision (Macro) | Recall (Macro) | F1-Score (Macro) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Naive (Random-Row)** | Random Forest | 0.9782 | 0.9823 | 0.9748 | 0.9783 |
| **Naive (Random-Row)** | XGBoost | 0.9807 | 0.9800 | 0.9804 | 0.9802 |
| **Group-Aware (Block-Grouping)** | Random Forest | 0.9583 | 0.9572 | 0.9463 | 0.9515 |
| **Group-Aware (Block-Grouping)** | XGBoost | 0.9614 | 0.9589 | 0.9508 | 0.9547 |

> [!WARNING]
> **Why the Naive split results are misleading:**
> The naive split yields near-perfect accuracy (~98%+) because contiguous video frames share almost identical coordinates. When split randomly, a frame $t$ might end up in the training set and frame $t+1$ (which is virtually identical) in the test set. This leaks the training data directly into the evaluation. 
> The **Group-Aware split** represents the true generalization capacity when evaluating confidence on new, unseen speech sessions.

---

## 3. Final Chosen Model: XGBoost (Group-Aware)

Based on the Group-Aware evaluation, the **XGBoost** model was selected as it yielded the highest macro F1-score of **0.9547**.

### Group-Aware Performance Metrics
- **Accuracy**: 0.9614
- **Macro Precision**: 0.9589
- **Macro Recall**: 0.9508
- **Macro F1-Score**: 0.9547

### Confusion Matrices

#### Chosen Model: XGBoost (Group-Aware Split)
| Actual \ Predicted | Low | Neutral | Confident |
| --- | --- | --- | --- |
| **Low** | 342 | 5 | 0 |
| **Neutral** | 2 | 240 | 28 |
| **Confident** | 0 | 15 | 664 |


#### Reference: Random Forest (Group-Aware Split)
| Actual \ Predicted | Low | Neutral | Confident |
| --- | --- | --- | --- |
| **Low** | 343 | 4 | 0 |
| **Neutral** | 1 | 236 | 33 |
| **Confident** | 0 | 16 | 663 |


#### Reference: XGBoost (Group-Aware Split)
| Actual \ Predicted | Low | Neutral | Confident |
| --- | --- | --- | --- |
| **Low** | 342 | 5 | 0 |
| **Neutral** | 2 | 240 | 28 |
| **Confident** | 0 | 15 | 664 |


#### Reference: Random Forest (Naive Random Split)
| Actual \ Predicted | Low | Neutral | Confident |
| --- | --- | --- | --- |
| **Low** | 243 | 2 | 1 |
| **Neutral** | 1 | 315 | 18 |
| **Confident** | 0 | 4 | 606 |


#### Reference: XGBoost (Naive Random Split)
| Actual \ Predicted | Low | Neutral | Confident |
| --- | --- | --- | --- |
| **Low** | 244 | 2 | 0 |
| **Neutral** | 3 | 322 | 9 |
| **Confident** | 0 | 9 | 601 |


---

## 4. SHAP Feature Interpretations

The SHAP summary plot is saved at `/models/shap_summary.png`. It explains how the features drive the predictions for each confidence category (Low, Neutral, Confident).

Here are the top 5 features based on their average absolute SHAP impact:

- **wrist_shoulder_ratio** (Importance: 2.2948) — Ratio of wrist distance to shoulder span. Open arm positioning suggests expansive, confident body language.
- **eye_shoulder_y_ratio** (Importance: 1.3066) — Ratio of eye level to shoulder level. Tracks neck extension; higher values reflect open, upright head positioning.
- **shoulder_y_diff** (Importance: 0.9924) — Vertical difference between left and right shoulder levels. Level shoulders indicate good posture and confidence, whereas large differences represent tilt or asymmetric slouching.
- **shoulder_span** (Importance: 0.6579) — Pixel span of shoulders, providing the baseline for physical sizing and normalization.
- **nose_eye_center_offset_x** (Importance: 0.3697) — Horizontal displacement of the nose relative to the eye center. Larger values indicate head turning/looking away, while centered values represent looking straight at the audience.


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
