# Runbook

## Local Demo

```bash
cd videorank-mlops-app
direnv allow
PYTHONPATH=src python -m videorank.data.generate --output data/events.jsonl --users 200 --videos 80 --events 5000
PYTHONPATH=src python -m videorank.model.train --events data/events.jsonl --output-dir artifacts/model
PYTHONPATH=src VIDEORANK_MODEL_PATH=artifacts/model/model.json python -m videorank.api.app
```

Test a recommendation:

```bash
curl -s localhost:8080/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"user_00001","context":{"preferred_category":"sports","device":"mobile","country":"FR"},"limit":5}' | jq
```

## GCP Setup

Use the personal account with the 300 USD credit. Do not reuse a professional
GCP project.

```bash
cd videorank-mlops-app
direnv allow
gcloud auth login werpo78@gmail.com
gcloud billing accounts list
PROJECT_ID=videorank-mlops-dev-$(date +%s)
REGION=europe-west1
BILLING_ACCOUNT_ID=<billing-account> ./scripts/setup_gcp_project.sh
```

Current lab values:

- project: `videorank-mlops-werpo78`
- region: `europe-west1`
- artifact registry: `europe-west1-docker.pkg.dev/videorank-mlops-werpo78/videorank`
- Cloud Run URL: `https://videorank-api-xzs2u6x3kq-ew.a.run.app`
- WIF provider: `projects/57648357123/locations/global/workloadIdentityPools/github-actions/providers/github`
- CI service account: `videorank-ci@videorank-mlops-werpo78.iam.gserviceaccount.com`
- runtime service account: `videorank-run@videorank-mlops-werpo78.iam.gserviceaccount.com`

Cloud Run public URL note: Google documents some paths ending in `z` as
reserved. The API still exposes `/healthz` for Kubernetes probes, but use
`/health` on the public `run.app` URL and `/readyz` for model readiness.

Terraform:

```bash
cd infra/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

## GitHub OIDC Secrets

After Terraform, set app repo secrets:

- `GCP_PROJECT_ID`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_CI_SERVICE_ACCOUNT`
- `GCP_RUNTIME_SERVICE_ACCOUNT`
- `CONFIG_REPO_TOKEN` for opening promotion PRs into the config repo

Production note: use a GitHub App instead of a PAT for cross-repo promotion.

## Flux Lab

Install Flux CLI if needed:

```bash
brew install fluxcd/tap/flux
```

Create GKE lab cluster by enabling `enable_gke_lab = true` for Terraform, then:

```bash
PROJECT_ID=<project> GITHUB_OWNER=<owner> ./scripts/bootstrap_flux_lab.sh
flux get all -A
kubectl get helmreleases -A
kubectl get rayjobs -A
```

Teardown immediately after the lab:

```bash
PROJECT_ID=<project> ./scripts/teardown_gke_lab.sh
```

## Incident Patterns

Bad model:

1. Check current digest in `videorank-mlops-config/apps/videorank-api/dev/values.yaml`.
2. Revert the promotion commit.
3. Let Flux reconcile.
4. Compare prediction logs and model metrics.

API errors:

1. Check Cloud Run revision and logs.
2. Check `/readyz` and `/metrics`.
3. Confirm model artifact path and runtime service account access.
4. If dependency failure, switch to fallback or previous digest.

GitOps reconciliation failure:

1. `flux get kustomizations -A`
2. `flux get helmreleases -A`
3. `kubectl describe kustomization <name> -n flux-system`
4. Fix Git, not the cluster, unless the fix is temporary diagnostic work.
