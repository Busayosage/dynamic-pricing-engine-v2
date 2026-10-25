# Data lineage

1. Raw files (earliest known copy: Desktop\sample\, dated 2 Oct 2025; origin of download not established)
   -> copied to data/raw/ (from Desktop\perishable_project, hashes verified 21 Oct 2026)
2. perishable_project/src/merge_data.py joined them -> merged_dataset.csv (28 Oct 2025)
   -> reference copy: data/reference/merged_dataset.csv (sha256 24a9b9d3...6a67)
3. dynamic-pricing-engine (Mar 2026) imported that CSV unchanged into SQLite.
4. perishable_project/src/baseline_model.py produced validation_predictions.csv
   -> data/reference/validation_predictions.csv (reference benchmark only)

Reference benchmark (holdout 2024-11-04 to 2024-12-23, 1-week-ahead):
RF MAE 487.2 / RMSE 714.0 / R2 0.635; naive MAE 597.1 / RMSE 878.5 / R2 0.448.

## Additional reference file (added 21 Oct 2026)
5. Original exploratory notebook, copied unchanged for reference only (not executed):
   legacy/perishable_project/notebooks/predicting_demand_for_perishable_goodipynb.ipynb
   Source: Desktop\perishable_project\ (last modified 22 Oct 2025). SHA-256 recorded in docs/CHECKSUMS.sha256.
   Contains EDA and business summaries only; no model training.
