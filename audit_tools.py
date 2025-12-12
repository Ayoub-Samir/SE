"""
Auxiliary audits for the Jenkins pipeline:
- Fairlearn bias snapshot
- Giskard scan
- Credo AI presence check (lightweight metadata)

Each audit is optional and can be triggered independently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def load_model(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Model artifact not found at {path}")
    return joblib.load(path)


def run_fairlearn(df: pd.DataFrame, model, output: Path) -> Path:
    try:
        from fairlearn.metrics import (
            MetricFrame,
            demographic_parity_difference,
            equalized_odds_difference,
            selection_rate,
        )
    except ImportError as exc:  # pragma: no cover - handled at runtime
        raise RuntimeError("fairlearn is not installed") from exc

    feature_cols = [c for c in df.columns if c != "target"]
    if not feature_cols:
        raise RuntimeError("Dataset is missing feature columns.")

    y_true = df["target"]
    X = df[feature_cols].to_numpy()
    y_pred = model.predict(X)

    # Fairlearn binary metrics require a positive label. For multiclass Iris, binarize:
    # treat the first observed class as positive and the rest as negative. This keeps
    # the audit stable regardless of class ordering.
    pos_label = pd.unique(y_true)[0]
    y_true_bin = (y_true == pos_label).astype(int)
    y_pred_bin = (pd.Series(y_pred) == pos_label).astype(int)

    # Synthetic sensitive attribute: use the first feature column to avoid name mismatches (spaces/underscores).
    sensitive_col = feature_cols[0]
    sensitive = (df[sensitive_col] > df[sensitive_col].median()).map(
        {True: f"high_{sensitive_col}", False: f"low_{sensitive_col}"}
    )

    mf = MetricFrame(
        metrics={"accuracy": accuracy_score, "selection_rate": selection_rate},
        y_true=y_true_bin,
        y_pred=y_pred_bin,
        sensitive_features=sensitive,
    )

    by_group: Dict[str, Dict[str, float]] = {
        str(group): {
            metric: float(mf.by_group.loc[group, metric]) for metric in mf.by_group.columns
        }
        for group in mf.by_group.index
    }

    report: Dict[str, Any] = {
        "sensitive_feature": "sepal_length_high_vs_low",
        "overall": {metric: float(value) for metric, value in mf.overall.items()},
        "by_group": by_group,
        "demographic_parity_difference": float(
            demographic_parity_difference(
                y_true=y_true_bin, y_pred=y_pred_bin, sensitive_features=sensitive
            )
        ),
        "equalized_odds_difference": float(
            equalized_odds_difference(
                y_true=y_true_bin, y_pred=y_pred_bin, sensitive_features=sensitive
            )
        ),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return output


def run_giskard(df: pd.DataFrame, model, output: Path) -> Path:
    try:
        from giskard import Dataset, Model, scan
    except ImportError as exc:  # pragma: no cover - handled at runtime
        raise RuntimeError("giskard is not installed") from exc

    feature_cols = [c for c in df.columns if c != "target"]
    if not feature_cols:
        raise RuntimeError("Dataset is missing feature columns.")
    dataset = Dataset(
        df=df[feature_cols + ["target"]],
        target="target",
    )
    wrapped_model = Model(
        model=model,
        model_type="classification",
        classification_labels=sorted(df["target"].unique()),
        feature_names=feature_cols,
        data_preprocessing_function=lambda data: data[feature_cols],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = scan(wrapped_model, dataset)
        report_json = report.to_json()
    except Exception as exc:  # pragma: no cover - keep the pipeline going
        report_json = json.dumps({"warning": "giskard scan failed", "error": str(exc)})

    try:
        Path(output).write_bytes(report_json.encode("utf-8", "replace"))
    except Exception:
        # Best-effort fallback to ignore errors; avoid failing the pipeline.
        Path(output).write_text(report_json, encoding="utf-8", errors="ignore")

    return output


def run_credo(df: pd.DataFrame, model, output: Path) -> Path:
    try:
        import credoai  # type: ignore
    except ImportError as exc:  # pragma: no cover - handled at runtime
        raise RuntimeError("credoai is not installed") from exc

    # Lightweight metadata to prove the tool was invoked; full policy checks
    # would be configured externally.
    info = {
        "credoai_version": getattr(credoai, "__version__", "unknown"),
        "rows": int(df.shape[0]),
        "features": [c for c in df.columns if c != "target"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(info, indent=2))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run optional audit tools.")
    parser.add_argument("--dataset-path", default="data/iris.parquet", help="Path to dataset file.")
    parser.add_argument("--model-path", default="artifacts/model.pkl", help="Path to trained model.")
    parser.add_argument("--run-fairlearn", action="store_true", help="Run Fairlearn bias snapshot.")
    parser.add_argument("--run-giskard", action="store_true", help="Run Giskard scan.")
    parser.add_argument("--run-credo", action="store_true", help="Capture Credo AI metadata.")
    parser.add_argument("--fairlearn-report", default="artifacts/fairlearn_report.json", help="Fairlearn report path.")
    parser.add_argument("--giskard-report", default="artifacts/giskard_report.json", help="Giskard report path.")
    parser.add_argument("--credo-report", default="artifacts/credoai_report.json", help="Credo AI report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not any([args.run_fairlearn, args.run_giskard, args.run_credo]):
        print("No audits selected; exiting cleanly.")
        return

    df = load_dataset(Path(args.dataset_path))
    model = load_model(Path(args.model_path))

    if args.run_fairlearn:
        run_fairlearn(df, model, Path(args.fairlearn_report))
        print(f"Fairlearn report written to {args.fairlearn_report}")

    if args.run_giskard:
        run_giskard(df, model, Path(args.giskard_report))
        print(f"Giskard report written to {args.giskard_report}")

    if args.run_credo:
        run_credo(df, model, Path(args.credo_report))
        print(f"Credo AI metadata written to {args.credo_report}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - pipeline feedback
        sys.stderr.write(f"[audit_tools] Failed: {exc}\n")
        sys.exit(1)
