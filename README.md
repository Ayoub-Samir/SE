# Jenkins + MLflow + DVC + SQLite

This repo demonstrates how to automate an MLflow experiment with Jenkins, persist the data set in a relational store, and version both data and trained models with DVC so that everything can be pushed to GitHub.

## What You Get
- `prepare_data.py`: materialises the Iris data set to `data/iris.parquet` and populates the same rows into `data/iris.db` (SQLite).
- `train.py`: trains Logistic Regression on the prepared data, logs runs/artifacts to MLflow, and serialises the trained model to `artifacts/model.pkl`.
- `data_utils.py`: shared helpers for reading/writing the Iris data.
- `dvc.yaml` / `dvc.lock` / `params.yaml`: describe the DVC pipeline (`prepare_data` ➜ `train_model`) and the hyper‑parameters Jenkins modifies.
- `Jenkinsfile` + `Jenkinsfile.windows`: CI pipelines. By default they activate a Python venv, install deps, tweak `params.yaml`, then run `dvc repro`. Setting the `USE_MLFLOW_PROJECT` parameter switches to `mlflow run .` instead.
- `MLproject` + `python_env.yaml`: optional Mlflow Projects interface for ad-hoc runs.

## Data to Database Flow
1. `prepare_data.py` (and the DVC `prepare_data` stage) exports the Iris frame to `data/iris.parquet`.
2. The same script writes the rows into the `iris_samples` table inside `data/iris.db` (SQLite). You can inspect it with any SQLite client:  
   `sqlite3 data/iris.db "SELECT * FROM iris_samples LIMIT 5;"`
3. `train.py` reuses the serialized data; if the file is missing it regenerates it and refreshes the DB, so standalone runs also stay consistent.

## Jenkins Usage
1. Create a Jenkins pipeline job that points at this repo.
2. Parameters exposed by both Jenkinsfiles:
   - `MLFLOW_TRACKING_URI`: MLflow server URL; leave blank to rely on agent env vars.
   - `MLFLOW_EXPERIMENT_NAME`: overrides the experiment stored in `params.yaml`.
   - `MAX_ITER`: forwarded to `params.yaml` before `dvc repro`.
   - `USE_MLFLOW_PROJECT`: when `true`, skip DVC and call `mlflow run .` (requires the MLflow tracking URI to be reachable from the agent).
3. The Linux Jenkinsfile uses `sh` while `Jenkinsfile.windows` uses PowerShell—pick the one matching your agent.
4. After each build Jenkins archives `mlruns_local/**`, so you can download the per-run classification reports even without MLflow UI access.

## DVC Workflow
Data (`data/iris.parquet`, `data/iris.db`) and the serialized model (`artifacts/model.pkl`) are tracked as `outs` with `cache: false`, so the actual files remain in Git history while DVC keeps the lineage in `dvc.lock`. Typical commands:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
dvc repro          # run both stages locally
dvc exp show       # compare different params
# optional: configure a remote if you later want off-repo blob storage
# dvc remote add -d s3 s3://my-bucket/path
```

## GitHub Publishing (`https://github.com/Ayoub-Samir/SE`)
```bash
git add .
git commit -m "Add Jenkins + MLflow + DVC pipeline"
git branch -M main
git remote add origin https://github.com/Ayoub-Samir/SE.git
git push -u origin main
```
Because the tracked data/model files are small, they can live directly in the repo; DVC metadata (`dvc.yaml`, `dvc.lock`, `.dvc/`) captures the reproducibility story.

## Local Smoke Test
```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
export MLFLOW_TRACKING_URI=http://localhost:5000   # optional
dvc repro                      # or: python prepare_data.py && python train.py
mlflow ui --backend-store-uri ./mlruns --port 5000
```
Open `http://127.0.0.1:5000` to inspect the two latest runs that the CLI produced.

## Extending Further
1. Point `params.yaml` to a different database table or dataset location and re-run `dvc repro`.
2. Configure `dvc remote add` to an object store (S3, Azure, GDrive) when the data/models grow larger.
3. Add a Jenkins post step that links directly to your hosted MLflow UI with the run ID printed in the logs.
