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
2. The image is pushed to Artifact Registry with the commit SHA, a sortable
   `main-<run_number>-<short_sha>` tag for Flux image policy, and an immutable
   digest.
3. CI opens a pull request in `videorank-mlops-config` to update the image digest.
4. Merging the config PR promotes the artifact.
5. Flux reconciles the Kubernetes cluster from the config repo.

The config repo also contains a Flux image automation lab. It can scan Artifact
Registry and push marker updates to `flux/image-updates/dev`, but production
promotion still goes through PR review before `main`.

Vertex AI follows a separate managed-GCP Continuous Training flow: pull requests
compile and validate the Kubeflow Pipelines template, then `main`, the weekly
schedule, or a manual `continuous-training` workflow submission creates a Vertex
AI `PipelineJob` through GitHub OIDC and Workload Identity Federation. CT
registers a model candidate; it does not silently promote serving.

## MovieLens + Vertex AI Pipeline

The production-style ML pipeline uses Kubeflow Pipelines v2 on Vertex AI with
MovieLens latest-small as a real user-item interaction dataset. It catalogs the
snapshot in Vertex AI Datasets, publishes feature data for Vertex AI Feature
Store, logs runs to Vertex AI Experiments, trains a CPU-only matrix
factorization ranker, compares it to the popularity baseline, and registers
gated candidates in Vertex AI Model Registry.

Local smoke test:

```bash
python -m pip install -e ".[dev,ml,pipelines]"
make movielens
make compile-pipeline
```

Submit to Vertex AI Pipelines:

```bash
PROJECT_ID=videorank-mlops-werpo78
REGION=europe-west1
PIPELINE_ROOT=gs://${PROJECT_ID}-videorank-artifacts/vertex-pipelines
TRAINING_SA=videorank-training@${PROJECT_ID}.iam.gserviceaccount.com

python pipelines/kfp/submit_vertex.py \
  --project-id "$PROJECT_ID" \
  --region "$REGION" \
  --pipeline-root "$PIPELINE_ROOT" \
  --service-account "$TRAINING_SA" \
  --enable-vertex-datasets true \
  --enable-vertex-experiments true \
  --enable-vertex-model-registry true \
  --enable-vertex-feature-store false
```

From Git, use the `continuous-training` GitHub Actions workflow
(`.github/workflows/vertex-pipeline.yml`). It validates the KFP template on pull
requests and submits CT runs on `main`, weekly schedule, or `workflow_dispatch`.
See `docs/continuous-training.md` for the interview-ready explanation.

Promote a validated model with the manual `promote-model` workflow. It opens a
PR in `videorank-mlops-config` that pins the promoted `VIDEORANK_MODEL_URI`,
model version and lineage fields. The API can load promoted `gs://` model
artifacts at startup without rebuilding the serving image.
