# SE

## Jenkins + MLflow + DVC + SQLite

This project shows how to automate an MLflow experiment with Jenkins, persist the Iris data set in SQLite, and version both data and trained models with DVC so everything can be pushed to GitHub.

### What You Get
- `prepare_data.py`: materialises the Iris data to `data/iris.parquet` and loads the same rows into `data/iris.db` (SQLite).
- `train.py`: trains Logistic Regression, logs runs/artifacts to MLflow, and serialises the model to `artifacts/model.pkl`.
- `data_utils.py`: helper functions for reading/writing the Iris data.
- `dvc.yaml` / `dvc.lock` / `params.yaml`: define the DVC pipeline (`prepare_data` -> `train_model`) and the hyperparameters Jenkins modifies.
- `Jenkinsfile` + `Jenkinsfile.windows`: CI pipelines. By default they install dependencies, tweak `params.yaml`, then run `dvc repro`. Set the `USE_MLFLOW_PROJECT` parameter to switch to `mlflow run .`.
- `MLproject` + `python_env.yaml`: optional MLflow Projects entry point for ad-hoc runs.

### Data to Database Flow
1. `prepare_data.py` exports the Iris frame to `data/iris.parquet`.
2. The same script writes the rows into the `iris_samples` table inside `data/iris.db`. Example query: `sqlite3 data/iris.db "SELECT * FROM iris_samples LIMIT 5;"`.
3. `train.py` reuses the serialized data; if it is missing, the script regenerates the file and refreshes the DB.

### Jenkins Usage
1. Create a pipeline job pointing to this repo.
2. Parameters available in both Jenkinsfiles:
   - `MLFLOW_TRACKING_URI`: MLflow server URL (falls back to agent env vars if empty).
   - `MLFLOW_EXPERIMENT_NAME`: overrides the experiment in `params.yaml`.
   - `MAX_ITER`: forwarded into `params.yaml` before `dvc repro`.
   - `USE_MLFLOW_PROJECT`: when `true`, skip DVC and call `mlflow run .`.
   - `RUN_SECURITY_SCANS`: when `true`, installs `requirements-security.txt` and runs `pip-audit` (dependency CVEs) and `bandit` (Python static analysis) before training.
3. Linux agents use `Jenkinsfile` (shell), Windows agents use `Jenkinsfile.windows` (PowerShell).
4. Jenkins archives `mlruns_local/**` so classification reports are downloadable even without MLflow UI access.

### DVC Workflow
Data (`data/iris.parquet`, `data/iris.db`) and the model (`artifacts/model.pkl`) are tracked as DVC outputs with `cache: false`, so the actual files stay in Git while DVC captures lineage in `dvc.lock`.

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
dvc repro
dvc exp show
# optional: configure remote storage
# dvc remote add -d s3 s3://my-bucket/path
```

### Publishing to GitHub (`https://github.com/Ayoub-Samir/SE`)
```bash
git add .
git commit -m "Add Jenkins + MLflow + DVC pipeline"
git branch -M main
git remote add origin https://github.com/Ayoub-Samir/SE.git
git push -u origin main
```

### Local Smoke Test
```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
export MLFLOW_TRACKING_URI=http://localhost:5000   # optional
dvc repro                      # or: python prepare_data.py && python train.py
mlflow ui --backend-store-uri ./mlruns --port 5000
```
Open `http://127.0.0.1:5000` to inspect the latest runs.

### Extending Further
1. Point `params.yaml` to a different data source or table and re-run `dvc repro`.
2. Configure `dvc remote add` to S3/Azure/GDrive when data/models grow larger.
3. Add a Jenkins post step that prints a link to your hosted MLflow UI using the run ID from the logs.
4. For stronger MLSecOps/OWASP coverage, add secrets scanning (e.g., gitleaks/detect-secrets) and artifact signing; hashes are already logged to MLflow via `security_manifest.json` for integrity checks.
