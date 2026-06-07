# Cost And Credit Guardrails

The project assumes a 300 USD Google Cloud credit. The goal is to use real GCP
services while avoiding accidental spend.

## Default Cost Strategy

- Cloud Run is the permanent serving platform because it can scale to zero.
- GKE Autopilot is only for a short Flux/KubeRay lab.
- No GPU or TPU is created.
- BigQuery tables are partitioned and clustered.
- Artifact Registry has cleanup policies.
- Cloud Storage has lifecycle rules.
- Terraform budget alert defaults to 75 EUR because the selected billing account is EUR.

## GKE Lab Rules

Create the GKE cluster only when ready to test Flux/KubeRay.

Always teardown:

```bash
PROJECT_ID=<project> ./scripts/teardown_gke_lab.sh
```

Interview answer: GKE Autopilot reduces node management, but workloads are still
billed. A short-lived lab cluster demonstrates Kubernetes/GitOps without making
Kubernetes the default runtime for a small API.

## BigQuery Cost Rules

- Use partition filters for time-bounded queries.
- Cluster by common filter/join keys.
- Prefer selected columns over `SELECT *`.
- Use dry runs and `maximum_bytes_billed` for exploratory work.
- Remember that `LIMIT` does not guarantee lower scanned bytes.

## Cloud Run Cost Rules

- `min_instance_count = 0` for dev.
- Use small CPU/memory limits.
- Avoid large model downloads at startup.
- Use min instances only if latency SLOs justify the spend.

## Artifact And Storage Rules

- Delete untagged images after 14 days.
- Move older artifacts to Nearline after 30 days.
- Delete lab artifacts after 90 days.
- Keep model artifacts versioned, but cap retention in dev.


## Vertex AI Pipeline Cost Rules

- Use MovieLens latest-small for the lab, not a large benchmark dataset.
- Default GitHub CT to `max_ratings=25000`; raise it manually only when needed.
- Keep components CPU-only and short-lived.
- Keep Vertex pipeline caching enabled during iteration, but change
  `data_snapshot_id` when the training data snapshot changes.
- Store pipeline artifacts in the lifecycle-managed artifacts bucket.
- Do not deploy Vertex Endpoints unless there is a serving experiment to justify it.
- Vertex Datasets, Experiments and Model Registry are metadata/control-plane
  resources for this lab; clean up old runs/models if they become noisy.
- Feature Store online resources are opt-in because online stores can create
  persistent cost; keep `enable_vertex_feature_store=false` unless testing it.
- Use the weekly CT schedule for the lab; disable it if credits become tight.
