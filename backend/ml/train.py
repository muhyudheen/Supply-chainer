"""Train the p50/p85/p95 leg-delay models and write the artifact and metrics.

    uv run python -m backend.ml.train

Three HistGradientBoostingRegressor(loss="quantile") models, one per quantile (MR5). Categories are one-hot
encoded: shap.TreeExplainer gives wrong values on the trees' native categorical splits (the SHAP values don't
add up to the prediction), and one-hot columns also avoid ordering categories as numbers (MR3). Evaluation
holds out whole routes (MR4) and reports coverage and pinball loss per mode (MR2).
"""
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_pinball_loss
from sklearn.model_selection import GroupShuffleSplit

from backend.ml.dataset import MODES, build_dataset
from backend.ml.features import CATEGORICAL, FEATURES

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
ARTIFACT = os.path.join(ARTIFACTS, "delay_models.joblib")
METRICS = os.path.join(ARTIFACTS, "metrics.json")
QUANTILES = [0.5, 0.85, 0.95]
NAMES = ["p50", "p85", "p95"]


def route_key(df):
    """The origin-destination hub pair of each row, the same both ways and for every mode."""
    return pd.Series([" | ".join(sorted((u.split(":")[0], v.split(":")[0]))) for u, v in zip(df["u"], df["v"])],
                     index=df.index)


def group_split(df, seed=42, test_size=0.2):
    """Positions of train and test rows; a route is entirely in one or the other (MR4)."""
    return next(GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
                .split(df, groups=route_key(df)))


def encode(bundle, rows):
    """Feature rows (leg_features dicts or a DataFrame) to the model's numeric columns.
    A category not seen in training raises (TI10): the trees would otherwise read it as all zeros."""
    X = pd.DataFrame(rows)[FEATURES]
    for col in CATEGORICAL:
        unknown = set(X[col]) - set(bundle["categories"][col])
        if unknown:
            raise ValueError(f"{col} {sorted(unknown)} was not in the training data")
    numeric = X.drop(columns=CATEGORICAL).astype(float).to_numpy()
    one_hot = [(X[col].to_numpy()[:, None] == np.array(bundle["categories"][col])[None, :]).astype(float)
               for col in CATEGORICAL]
    return np.hstack([numeric, *one_hot])


def encoded_columns(bundle):
    """Names of the encoded columns, e.g. "region=RED"; SHAP values are summed back per feature by prefix."""
    return [f for f in FEATURES if f not in CATEGORICAL] + \
           [f"{col}={c}" for col in CATEGORICAL for c in bundle["categories"][col]]


def fit(train_df, seed=42):
    bundle = {"features": list(FEATURES), "quantiles": list(QUANTILES),
              "categories": {col: sorted(train_df[col].unique()) for col in CATEGORICAL}}
    X, y = encode(bundle, train_df), train_df["delay_h"].to_numpy()
    bundle["models"] = [HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=500, early_stopping=True,
                                                      random_state=seed).fit(X, y) for q in QUANTILES]
    return bundle


def predict_quantiles(bundle, rows, raw=False):
    """Hours of delay at p50, p85, p95, one row per leg. Three separate models can cross slightly, so each row
    is sorted (a crossing means the upper model was too low there); raw=True skips that, for the report."""
    X = encode(bundle, rows)
    pred = np.column_stack([np.maximum(m.predict(X), 0.0) for m in bundle["models"]])
    return pred if raw else np.sort(pred, axis=1)


def _scores(y, pred, baseline):
    return {
        "rows": int(len(y)),
        "coverage": {n: round(float(np.mean(y <= pred[:, i])), 3) for i, n in enumerate(NAMES)},
        "pinball": {n: round(float(mean_pinball_loss(y, pred[:, i], alpha=q)), 3)
                    for i, (n, q) in enumerate(zip(NAMES, QUANTILES))},
        "baseline_pinball": {n: round(float(mean_pinball_loss(y, baseline[:, i], alpha=q)), 3)
                             for i, (n, q) in enumerate(zip(NAMES, QUANTILES))},
        "median_width_p50_to_p95_h": round(float(np.median(pred[:, 2] - pred[:, 0])), 1),
    }


def evaluate(bundle, train_df, test_df):
    """Coverage and pinball loss on held-out routes, per mode and overall. The baseline is the training
    rows' own quantile for the leg's mode: a model that can't beat it has learned nothing from the features."""
    y = test_df["delay_h"].to_numpy()
    raw = predict_quantiles(bundle, test_df, raw=True)
    pred = np.sort(raw, axis=1)
    per_mode_q = {m: np.quantile(train_df.loc[train_df["mode"] == m, "delay_h"], QUANTILES) for m in MODES}
    baseline = np.array([per_mode_q[m] for m in test_df["mode"]])
    mode = test_df["mode"].to_numpy()
    out = {"overall": _scores(y, pred, baseline),
           "per_mode": {m: _scores(y[mode == m], pred[mode == m], baseline[mode == m]) for m in MODES}}
    out["overall"]["crossing_rows_before_sort"] = round(float(np.mean((np.diff(raw, axis=1) < 0).any(axis=1))), 4)
    return out


def load(path=ARTIFACT):
    return joblib.load(path)


def load_metrics(path=METRICS):
    with open(path) as f:
        return json.load(f)


def main(n_rows=50_000, seed=42):
    df = build_dataset(n_rows=n_rows, seed=seed)
    tr, te = group_split(df, seed=seed)
    train_df, test_df = df.iloc[tr], df.iloc[te]
    bundle = fit(train_df, seed=seed)
    metrics = evaluate(bundle, train_df, test_df)
    # MR6: the artifact says what made it
    bundle.update({"seed": seed, "n_rows": n_rows, "train_rows": len(train_df), "test_rows": len(test_df),
                   "sklearn_version": sklearn.__version__, "data": "backend/ml/dataset.py (simulated)",
                   "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    metrics["split"] = "GroupShuffleSplit by origin-destination hub pair, 20% of routes held out"
    metrics["data"] = f"{n_rows} simulated rows from backend/ml/dataset.py, seed {seed}"
    os.makedirs(ARTIFACTS, exist_ok=True)
    joblib.dump(bundle, ARTIFACT, compress=3)
    with open(METRICS, "w") as f:
        json.dump(metrics, f, indent=2)
    return metrics


if __name__ == "__main__":
    m = main()
    print(f"{'mode':6} {'rows':>6}  coverage p50/p85/p95   pinball p50/p85/p95 (baseline)")
    for name, s in [*m["per_mode"].items(), ("all", m["overall"])]:
        cov = "/".join(f"{s['coverage'][n]:.1%}" for n in NAMES)
        pin = "/".join(f"{s['pinball'][n]:.2f} ({s['baseline_pinball'][n]:.2f})" for n in NAMES)
        print(f"{name:6} {s['rows']:>6}  {cov:20}  {pin}")
    print(f"Rows with crossing quantiles before sorting: {m['overall']['crossing_rows_before_sort']:.2%}")
    print(f"Wrote {ARTIFACT} and {METRICS}")
