# VideoRank MLOps App Repo

This repository contains the application and ML side of the VideoRank project:

- synthetic video watch-event generation
- offline feature engineering
- baseline and ranking model training
- FastAPI recommendation service
- Beam/Dataflow and KFP/Vertex pipeline definitions
- GCP foundation Terraform for non-Kubernetes resources
- CI that builds immutable images and promotes by pull request to the config repo

The paired GitOps repository is `videorank-mlops-config`. The app repo produces artifacts;
the config repo declares what runs on Kubernetes and is reconciled by Flux.

## Local Quickstart

```bash
direnv allow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ml]"
python -m videorank.data.generate --output data/events.jsonl --users 200 --videos 80 --events 5000
python -m videorank.model.train --events data/events.jsonl --output-dir artifacts/model
uvicorn videorank.api.app:create_app --factory --reload
```

If dependencies are not installed yet, the stdlib-only core can still be checked with:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Production Flow

1. Pull request in this app repo runs tests, lint, and image build.
2. The image is pushed to Artifact Registry with the commit SHA and digest.
3. CI opens a pull request in `videorank-mlops-config` to update the image digest.
4. Merging the config PR promotes the artifact.
5. Flux reconciles the Kubernetes cluster from the config repo.

