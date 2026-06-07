# Two-Minute Demo Script

1. Show the two repos.
   - App repo: code, CI, Terraform.
   - Config repo: Kubernetes desired state.

2. Explain the delivery chain.
   - App PR builds and tests.
   - Image is pushed by SHA/digest.
   - Promotion PR updates config repo.
   - Flux reconciles the cluster.

3. Run local model training.
   - Generate synthetic events.
   - Train ranker with temporal split.
   - Show model card and metrics.

4. Call the API.
   - `/recommendations` returns top-K videos.
   - Variant is stable by user hash.
   - `/metrics` exposes Prometheus metrics.

5. Show GitOps.
   - `HelmRelease` references immutable image values.
   - `Kustomization` uses `dependsOn`, `wait`, `prune`, `healthChecks`.
   - KubeRay is installed as an operator via Flux.

6. Close with production tradeoffs.
   - Cloud Run for low-cost serving.
   - GKE lab for GitOps/KubeRay learning.
   - BigQuery for features/logs.
   - Workload Identity Federation, no JSON keys.
   - Rollback by Git revert.

