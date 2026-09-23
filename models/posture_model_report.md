# SmartSpeak Posture Classifier Training & Evaluation Report (Phase 2)

This report documents the training, cross-validation, and explainability results for the SmartSpeak Machine Learning Posture Classifier, trained on human-verified ground-truth labels to replace brittle, fixed geometric thresholds.

---

## 1. Dataset Summary

The dataset contains verified postural assessment frames captured across multiple individual speakers (Folders 1–10). Camera-distance outlier Folder 11 was excluded during Phase 1 based on 4-sigma Z-score calibration.

- **Total Evaluated Sample Frames**: 180 frames (160 complete landmark-tracked frames)
- **Subjects (Folders)**: 10 distinct individuals (`folder_id` 1 to 10)
- **Features (4 input features)**:
  1. `shoulder_tilt`: Angle of the shoulder line relative to horizontal axis ($^\circ$).
  2. `spine_angle`: Vertical alignment of the mid-shoulder to mid-hip spinal vector ($^\circ$).
  3. `shoulder_y_diff`: Normalized vertical height disparity between left and right shoulders.
  4. `shoulder_span`: Pixel distance between shoulders (provides camera distance and body depth context).
- **Target Variable**: `human_label` (3 classes: Poor Posture, Good Posture, Best Posture)
- **Class Distribution**:
  - **Best Posture**: 78 (48.8%)
  - **Poor Posture**: 45 (28.1%)
  - **Good Posture**: 37 (23.1%)

---

## 2. Evaluation Results: Naive vs. Group-Aware Splits

To prevent information leakage from highly correlated consecutive frames of the same speaker, models were evaluated under two splitting strategies:
1. **Naive Split (Random-Row)**: Standard 80/20 train/test split. Consecutive frames of the same person are shared across train and test sets, artificially inflating metrics.
2. **Group-Aware Split (Subject-Grouping)**: An 80/20 `GroupShuffleSplit` strictly grouped on `folder_id`. All frames of a given person appear exclusively in either the train or test set, simulating real-world inference on unseen users.

### Performance Comparison Table

| Split Strategy | Model Name | Accuracy | Precision (Macro) | Recall (Macro) | F1-Score (Macro) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Naive (Random-Row)** | Random Forest | 0.9375 | 0.9328 | 0.9153 | 0.9227 |
| **Naive (Random-Row)** | XGBoost | 0.9375 | 0.9328 | 0.9153 | 0.9227 |
| **Group-Aware (Subject-Grouped)** | **Random Forest (Chosen)** | **0.9565** | **0.9667** | **0.9667** | **0.9649** |
| **Group-Aware (Subject-Grouped)** | XGBoost | 0.8696 | 0.9167 | 0.9000 | 0.8936 |

> [!NOTE]
> **5-Fold Group Cross-Validation Across All Subjects:**
> - **Random Forest**: **91.11% ± 6.63%** Accuracy | **0.8941** Macro F1
> - **XGBoost**: **90.28% ± 4.93%** Accuracy | **0.8774** Macro F1

---

## 3. Final Chosen Model: Random Forest (Group-Aware)

The **Random Forest Classifier** achieved the highest Group-Aware generalization score:
- **Group-Aware Accuracy on Unseen Speakers**: **95.65%** (22 out of 23 frames correct)
- **Macro F1-Score**: **0.9649**
- **Macro Precision**: **0.9667**
- **Macro Recall**: **0.9667**

### Confusion Matrices (Group-Aware Test Set: Subjects [2, 9])

#### Chosen Model: Random Forest
| Actual \ Predicted | Poor Posture | Good Posture | Best Posture |
| :--- | :---: | :---: | :---: |
| **Poor Posture** | **9** | 1 | 0 |
| **Good Posture** | 0 | **9** | 0 |
| **Best Posture** | 0 | 0 | **4** |

#### Reference Model: XGBoost
| Actual \ Predicted | Poor Posture | Good Posture | Best Posture |
| :--- | :---: | :---: | :---: |
| **Poor Posture** | **7** | 3 | 0 |
| **Good Posture** | 0 | **9** | 0 |
| **Best Posture** | 0 | 0 | **4** |

---

## 4. Feature Importance & Explainability (SHAP)

The SHAP summary plot is generated at `models/posture_shap_summary.png`. It explains the contribution of each geometrical landmark feature in driving classification decisions.

### Feature Importance Ranking (Mean Decrease in Impurity)

| Rank | Feature Name | MDI Importance | Clinical / Physical Significance |
| :---: | :--- | :---: | :--- |
| **1** | `shoulder_tilt` | **0.5760** | Primary indicator of asymmetric shoulder drop and sideways leaning. |
| **2** | `spine_angle` | **0.2217** | Measures upright vertical posture vs. forward/backward spinal hunching. |
| **3** | `shoulder_y_diff` | **0.1463** | Direct pixel height disparity between left and right clavicles. |
| **4** | `shoulder_span` | **0.0559** | Calibrates camera distance and subject proximity to avoid distance bias. |

---

## 5. Model Loading & Deployment Interface

The production-ready model is exported as a scikit-learn `Pipeline` (including median imputation and Random Forest classifier) at `models/posture_model.pkl`:

```python
import joblib
import pandas as pd

# 1. Load pipeline
posture_model = joblib.load('models/posture_model.pkl')

# 2. Input format (expects DataFrame with 4 features)
df_sample = pd.DataFrame([{
    'shoulder_tilt': 4.2,      # degrees
    'spine_angle': 2.5,        # degrees
    'shoulder_y_diff': 0.005,   # normalized difference
    'shoulder_span': 54.2      # pixels
}])

# 3. Predict class (0 = Poor Posture, 1 = Good Posture, 2 = Best Posture)
prediction_idx = posture_model.predict(df_sample)[0]
class_names = ['Poor Posture', 'Good Posture', 'Best Posture']
print("Predicted Posture:", class_names[prediction_idx])
```

---
*Report generated automatically for Phase 2 Verification on 2026-09-11.*
