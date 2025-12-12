pipeline {
    agent any

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        string(name: 'MLFLOW_TRACKING_URI', defaultValue: '', description: 'Override MLflow tracking URI (optional).')
        string(name: 'MLFLOW_EXPERIMENT_NAME', defaultValue: 'jenkins-mlflow-demo', description: 'Target MLflow experiment.')
        string(name: 'MAX_ITER', defaultValue: '200', description: 'max_iter parameter for LogisticRegression.')
        booleanParam(name: 'USE_MLFLOW_PROJECT', defaultValue: false, description: 'Enable to execute via `mlflow run .` instead of python train.py')
        booleanParam(name: 'RUN_SECURITY_SCANS', defaultValue: true, description: 'Run pip-audit and bandit before training.')
        booleanParam(name: 'RUN_GARAK', defaultValue: false, description: 'Run garak red-team probes (requires model/args).')
        string(name: 'GARAK_COMMAND', defaultValue: '', description: 'Full garak CLI arguments, e.g. "--model openai:gpt-4o-mini --n-probes 10 --report garak_report.json". Leave empty to skip.')
        booleanParam(name: 'RUN_FAIRLEARN', defaultValue: false, description: 'Run Fairlearn bias snapshot after training.')
        booleanParam(name: 'RUN_GISKARD', defaultValue: false, description: 'Run Giskard scan after training.')
        booleanParam(name: 'RUN_CREDO_AI', defaultValue: false, description: 'Capture Credo AI metadata after training.')
        booleanParam(name: 'RUN_CYCLONEDX', defaultValue: false, description: 'Generate CycloneDX SBOM for dependencies.')
    }

    environment {
        VENV_DIR = "${env.WORKSPACE}/.venv"
        PYTHON = "${env.WORKSPACE}/.venv/bin/python"
        PIP = "${env.WORKSPACE}/.venv/bin/pip"
    }

    stages {
        stage('Python Environment') {
            steps {
                sh '''
                    set -e
                    python3 -m venv "${VENV_DIR}"
                    . "${VENV_DIR}/bin/activate"
                    pip install --upgrade pip
                '''
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    "${PIP}" install -r requirements.txt
                '''
            }
        }

        stage('Security Scan') {
            when {
                expression { params.RUN_SECURITY_SCANS }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    "${PIP}" install -r requirements-security.txt
                    # Run pip-audit; allow exit code 1 (vulns found) but fail on other errors.
                    if ! pip-audit -r requirements.txt --format json --output pip-audit.json; then
                        status=$?
                        if [ "$status" -eq 1 ]; then
                            echo "pip-audit found vulnerabilities; marking as warning but continuing build"
                        else
                            echo "pip-audit failed with exit code $status" >&2
                            exit $status
                        fi
                    fi
                    bandit -r . -x .venv -ll -iii -f json -o bandit.json
                '''
            }
        }

        stage('Garak Red Team (optional)') {
            when {
                expression { params.RUN_GARAK }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    if [ -z "${GARAK_COMMAND}" ]; then
                        echo "GARAK_COMMAND is empty; skipping garak run."
                        exit 0
                    fi
                    "${PIP}" install garak
                    garak ${GARAK_COMMAND}
                '''
            }
        }

        stage('Train & Log to MLflow') {
            steps {
                script {
                    String trackingUri = params.MLFLOW_TRACKING_URI?.trim()
                    if (!trackingUri) {
                        trackingUri = env.MLFLOW_TRACKING_URI ?: ''
                    }

                    String experimentName = params.MLFLOW_EXPERIMENT_NAME?.trim()
                    if (!experimentName) {
                        experimentName = env.MLFLOW_EXPERIMENT_NAME ?: 'jenkins-mlflow-demo'
                    }

                    String maxIter = params.MAX_ITER?.trim()
                    if (!maxIter) {
                        maxIter = '200'
                    }

                    withEnv([
                        "TRACKING_URI=${trackingUri}",
                        "EXPERIMENT_NAME=${experimentName}",
                        "MAX_ITER=${maxIter}",
                        "USE_MLFLOW_PROJECT=${params.USE_MLFLOW_PROJECT}",
                        "MLFLOW_ENV_MANAGER=local",
                    ]) {
                        sh '''
                            set -e
                            . "${VENV_DIR}/bin/activate"
                            if [ -n "${TRACKING_URI}" ]; then
                                export MLFLOW_TRACKING_URI="${TRACKING_URI}"
                            fi
                            # Optional: make MLflow token available via Jenkins secret text credential.
                            if [ -n "${MLFLOW_TRACKING_TOKEN}" ]; then
                                export MLFLOW_TRACKING_TOKEN="${MLFLOW_TRACKING_TOKEN}"
                            fi

                            if [ "${USE_MLFLOW_PROJECT}" = "true" ]; then
                                mlflow run . \
                                    -P max_iter="${MAX_ITER}" \
                                    -P experiment_name="${EXPERIMENT_NAME}"
                            else
                                dvc params modify train.max_iter "${MAX_ITER}"
                                dvc params modify train.experiment_name "${EXPERIMENT_NAME}"
                                dvc repro
                            fi
                        '''
                    }
                }
            }
        }

        stage('Fairlearn Bias Check (optional)') {
            when {
                expression { params.RUN_FAIRLEARN }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    "${PIP}" install fairlearn
                    python audit_tools.py --run-fairlearn
                '''
            }
        }

        stage('Giskard QA (optional)') {
            when {
                expression { params.RUN_GISKARD }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    "${PIP}" install giskard
                    python audit_tools.py --run-giskard
                '''
            }
        }

        stage('Credo AI Metadata (optional)') {
            when {
                expression { params.RUN_CREDO_AI }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    if ! "${PIP}" install credoai; then
                        echo "Credo AI package not available on PyPI; skipping Credo metadata."
                        python - <<'PY'
from pathlib import Path
Path("artifacts/credoai_report.json").parent.mkdir(parents=True, exist_ok=True)
Path("artifacts/credoai_report.json").write_text('{"warning": "credoai package not available; skipped."}')
print("Credo AI metadata skipped.")
PY
                    else
                        python audit_tools.py --run-credo
                    fi
                '''
            }
        }

        stage('CycloneDX SBOM (optional)') {
            when {
                expression { params.RUN_CYCLONEDX }
            }
            steps {
                sh '''
                    set -e
                    . "${VENV_DIR}/bin/activate"
                    "${PIP}" install cyclonedx-bom
                    mkdir -p artifacts
                    if command -v cyclonedx-py >/dev/null 2>&1; then
                        cyclonedx-py requirements -j -r requirements.txt -o artifacts/cyclonedx-sbom.json
                    elif command -v cyclonedx-bom >/dev/null 2>&1; then
                        cyclonedx-bom -j -r requirements.txt -o artifacts/cyclonedx-sbom.json
                    else
                        echo "CycloneDX CLI not found after install" >&2
                        exit 1
                    fi
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'mlruns_local/**,pip-audit.json,bandit.json,garak_report.*,artifacts/fairlearn_report.json,artifacts/giskard_report.*,artifacts/credoai_report.json,artifacts/cyclonedx-sbom.json', allowEmptyArchive: true, fingerprint: true
        }
    }
}
