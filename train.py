"""
Train a Logistic Regression model on the Iris dataset and log to MLflow.
Also persists the dataset to disk/SQLite for reproducibility & DVC tracking.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

import hashlib
import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from data_utils import load_iris_dataframe, write_dataframe_to_db, write_dataframe_to_disk

DEFAULT_EXPERIMENT = "jenkins-mlflow-demo"
DEFAULT_DATASET_PATH = "data/iris.parquet"
DEFAULT_MODEL_PATH = "artifacts/model.pkl"
DEFAULT_DB_PATH = "data/iris.db"
DEFAULT_DB_TABLE = "iris_samples"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Logistic Regression on Iris and log to MLflow.")
    parser.add_argument("--params-file", type=str, default=None, help="Optional YAML file containing defaults (params.yaml).")
    parser.add_argument("--test-size", type=float, default=None, help="Test split size (0, 1).")
    parser.add_argument("--random-state", type=int, default=None, help="Seed for train/test split.")
    parser.add_argument("--max-iter", type=int, default=None, help="Maximum iterations for LogisticRegression.")
    parser.add_argument("--tracking-uri", type=str, default=os.environ.get("MLFLOW_TRACKING_URI"),
                        help="MLflow tracking URI. Falls back to env var if unset.")
    parser.add_argument("--experiment-name", type=str, default=os.environ.get("MLFLOW_EXPERIMENT_NAME"),
                        help="MLflow experiment name. Falls back to params/env/default.")
    parser.add_argument("--data-path", type=str, default=None, help="Serialized dataset path (Parquet/CSV).")
    parser.add_argument("--model-path", type=str, default=None, help="Where to store the trained model binary.")
    parser.add_argument("--db-path", type=str, default=os.environ.get("IRIS_DB_PATH"),
                        help="SQLite database file path for persisting the dataset.")
    parser.add_argument("--db-table", type=str, default=os.environ.get("IRIS_DB_TABLE", DEFAULT_DB_TABLE),
                        help="Table name for dataset rows.")
    parser.add_argument("--skip-db", action="store_true", help="Skip writing the dataset to the database.")
    parser.add_argument("--force-prepare", action="store_true", help="Rebuild dataset file even if it exists.")
    return parser.parse_args()


def read_params(path: str | None) -> Dict[str, Any]:
    if path:
        params_path = Path(path)
    else:
        params_path = Path("params.yaml")
        if not params_path.exists():
            return {}
    if not params_path.exists():
        return {}
    return yaml.safe_load(params_path.read_text()) or {}


def resolve_config(args: argparse.Namespace) -> argparse.Namespace:
    params = read_params(args.params_file)
    train_cfg = params.get("train", {})

    args.test_size = args.test_size if args.test_size is not None else train_cfg.get("test_size", 0.2)
    args.random_state = args.random_state if args.random_state is not None else train_cfg.get("random_state", 42)
    args.max_iter = args.max_iter if args.max_iter is not None else train_cfg.get("max_iter", 200)
    args.experiment_name = args.experiment_name or train_cfg.get("experiment_name") or DEFAULT_EXPERIMENT
    args.data_path = args.data_path or train_cfg.get("dataset_path", DEFAULT_DATASET_PATH)
    args.model_path = args.model_path or train_cfg.get("model_path", DEFAULT_MODEL_PATH)
    args.db_path = args.db_path or train_cfg.get("db_path", DEFAULT_DB_PATH)

    return args


def ensure_dataset(data_path: Path, force_prepare: bool) -> pd.DataFrame:
    if data_path.exists() and not force_prepare:
        if data_path.suffix.lower() == ".parquet":
            return pd.read_parquet(data_path)
        return pd.read_csv(data_path)

    df = load_iris_dataframe()
    write_dataframe_to_disk(df, data_path)
    return df


def file_sha256(path: Path) -> str:
    """Compute a SHA256 hash for integrity tracking."""
    BUF_SIZE = 1024 * 1024
    sha = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha.update(data)
    return sha.hexdigest()


def split_features_targets(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    features = df.drop(columns=["target"])
    target = df["target"]
    return features, target


def persist_model(model, model_path: Path) -> Path:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    return model_path


def ensure_output_dir(run_id: str) -> Path:
    output_dir = Path("mlruns_local") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main() -> None:
    args = resolve_config(parse_args())

    data_path = Path(args.data_path)
    dataset_df = ensure_dataset(data_path, args.force_prepare)

    if not args.skip_db and args.db_path:
        write_dataframe_to_db(dataset_df, Path(args.db_path), args.db_table)

    x_df, y_series = split_features_targets(dataset_df)

    x_train, x_test, y_train, y_test = train_test_split(
        x_df.values,
        y_series.values,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=y_series.values,
    )

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)

    mlflow.set_experiment(args.experiment_name or DEFAULT_EXPERIMENT)

    with mlflow.start_run() as run:
        run_id = run.info.run_id
        mlflow.log_params({
            "test_size": args.test_size,
            "random_state": args.random_state,
            "max_iter": args.max_iter,
            "dataset_path": str(data_path),
        })

        model = LogisticRegression(max_iter=args.max_iter, multi_class="auto")
        model.fit(x_train, y_train)

        y_pred = model.predict(x_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)

        mlflow.log_metric("accuracy", accuracy)

        for label, values in report.items():
            if not isinstance(values, dict):
                continue
            for metric_name, metric_value in values.items():
                mlflow.log_metric(f"{label}_{metric_name}", metric_value)

        mlflow.sklearn.log_model(model, artifact_path="model")

        model_path = persist_model(model, Path(args.model_path))
        mlflow.log_artifact(str(model_path), artifact_path="serialized_model")

        data_hash = file_sha256(data_path)
        model_hash = file_sha256(model_path)
        integrity_manifest = {
            "data_path": str(data_path),
            "data_sha256": data_hash,
            "model_path": str(model_path),
            "model_sha256": model_hash,
        }
        mlflow.set_tag("data_sha256", data_hash)
        mlflow.set_tag("model_sha256", model_hash)
        mlflow.log_dict(integrity_manifest, artifact_file="security_manifest.json")

        output_dir = ensure_output_dir(run_id)
        report_path = output_dir / "classification_report.json"
        report_path.write_text(json.dumps(report, indent=2))
        mlflow.log_artifact(str(report_path), artifact_path="reports")

        print(f"Run {run_id} finished; accuracy={accuracy:.4f}")


if __name__ == "__main__":
    main()
