"""
Prepare the Iris dataset for training by materializing it to disk and an SQLite database.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from data_utils import load_iris_dataframe, write_dataframe_to_db, write_dataframe_to_disk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Iris data to disk and an SQLite database.")
    parser.add_argument("--dataset-path", type=str, default="data/iris.parquet", help="Location for the serialized dataset.")
    parser.add_argument("--db-path", type=str, default="data/iris.db", help="SQLite database file path.")
    parser.add_argument("--db-table", type=str, default="iris_samples", help="Target table for storing Iris rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = load_iris_dataframe()
    dataset_path = write_dataframe_to_disk(df, Path(args.dataset_path))
    write_dataframe_to_db(df, Path(args.db_path), args.db_table)

    print(f"Dataset stored at {dataset_path} and loaded into {args.db_table} table in {args.db_path}.")


if __name__ == "__main__":
    main()
