"""
Shared helpers for preparing and persisting the Iris dataset.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.datasets import load_iris


def load_iris_dataframe() -> pd.DataFrame:
    """Return the classic Iris dataset as a pandas DataFrame with a target column."""
    iris = load_iris(as_frame=True)
    df = iris.frame.copy()
    df["target"] = iris.target
    return df


def write_dataframe_to_disk(df: pd.DataFrame, output_path: Path) -> Path:
    """Persist dataframe to Parquet or CSV depending on suffix."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".parquet":
        df.to_parquet(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)
    return output_path


def write_dataframe_to_db(
    df: pd.DataFrame,
    db_path: Path,
    table_name: str = "iris_samples",
    chunk_size: Optional[int] = None,
) -> Path:
    """Write dataframe rows to an SQLite database table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False, chunksize=chunk_size)
    return db_path
