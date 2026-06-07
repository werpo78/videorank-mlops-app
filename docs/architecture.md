# VideoRank Architecture

## Executive Summary

VideoRank is a compact production-style MLOps system for video recommendation.
It demonstrates the platform concerns in the Dailymotion role: ML engineer
productivity, data access, CI/CD, GitOps, monitoring, production serving,
experimentation, and cost-aware cloud operations.

The project uses two repositories:

- `videorank-mlops-app`: source code, tests, pipelines, Terraform and CI.
- `videorank-mlops-config`: Kubernetes desired state reconciled by Flux.

The important interview point: CI produces artifacts; GitOps promotes and
reconciles runtime state. GitHub Actions does not mutate the cluster directly.

## General Architecture Diagram

```mermaid
flowchart TB
    subgraph Dev["Developer workflow"]
        Engineer["ML / Platform engineer"]
        AppPR["Pull request<br/>app repo"]
        ConfigPR["Pull request<br/>config repo"]
        Engineer --> AppPR
        Engineer --> ConfigPR
    end

    subgraph AppRepo["videorank-mlops-app<br/>Code, CI, Terraform, ML pipelines"]
        Source["Python source<br/>FastAPI, Beam, training"]
        Tests["CI checks<br/>lint, tests, pipeline compile"]
        ImageBuild["Build container<br/>SHA tag + immutable digest"]
        Terraform["Terraform foundation<br/>GCP resources + IAM"]
        CT["Continuous Training<br/>GitHub Actions"]
        PromoteModel["promote-model workflow<br/>opens config PR"]
        Source --> Tests
        Tests --> ImageBuild
        Tests --> CT
        Terraform --> GCPFoundation
        CT --> VertexPipeline
        PromoteModel --> ConfigPR
    end

    subgraph GitHubSecurity["GitHub to GCP security"]
        OIDC["GitHub OIDC token"]
        WIF["Workload Identity Federation"]
        CICDServiceAccount["CI/CD service account<br/>least privilege"]
        OIDC --> WIF --> CICDServiceAccount
    end

    subgraph GCP["GCP project: videorank-mlops-werpo78"]
        GCPFoundation["Foundation resources"]
        ArtifactRegistry["Artifact Registry<br/>container images"]
        GCS["Cloud Storage<br/>models, data snapshots, KFP artifacts"]
        BigQuery["BigQuery<br/>offline features, logs, drift tables"]
        CloudRun["Cloud Run<br/>permanent recommendation API"]
        VertexPipeline["Vertex AI Pipelines<br/>Kubeflow Pipelines v2"]
        VertexDataset["Vertex AI Datasets"]
        FeatureStore["Vertex AI Feature Store<br/>BigQuery source, optional online serving"]
        Experiments["Vertex AI Experiments<br/>metrics and parameters"]
        ModelRegistry["Vertex AI Model Registry<br/>candidate versions"]
        MonitoringData["Monitoring data<br/>latency, errors, fallback, feedback, PSI"]

        GCPFoundation --> ArtifactRegistry
        GCPFoundation --> GCS
        GCPFoundation --> BigQuery
        GCPFoundation --> CloudRun
        VertexPipeline --> VertexDataset
        VertexPipeline --> FeatureStore
        VertexPipeline --> Experiments
        VertexPipeline --> ModelRegistry
        VertexPipeline --> GCS
        VertexPipeline --> BigQuery
        CloudRun --> BigQuery
        BigQuery --> MonitoringData
    end

    subgraph Serving["Serving contract"]
        API["FastAPI endpoints<br/>/recommendations, /feedback, /metrics"]
        ModelURI["VIDEORANK_MODEL_URI<br/>promoted model artifact"]
        Baseline["Popularity baseline<br/>fallback"]
        API --> ModelURI
        API --> Baseline
    end

    subgraph ConfigRepo["videorank-mlops-config<br/>GitOps desired state"]
        ClusterState["clusters/dev<br/>Flux sources + Kustomizations"]
        AppValues["apps/videorank-api<br/>image digest + model URI"]
        InfraControllers["infrastructure/controllers<br/>KubeRay, monitoring, RBAC"]
        Secrets["SOPS encrypted secrets"]
        ConfigPR --> AppValues
        ClusterState --> AppValues
        ClusterState --> InfraControllers
        ClusterState --> Secrets
    end

    subgraph GKE["Ephemeral GKE Autopilot lab"]
        Flux["Flux controllers<br/>pull-based reconciliation"]
        APIOnGKE["VideoRank API<br/>GitOps deployment"]
        KubeRay["KubeRay RayJob<br/>CPU lab workload"]
        Prometheus["Prometheus-compatible metrics"]
        Flux --> APIOnGKE
        Flux --> KubeRay
        APIOnGKE --> Prometheus
    end

    AppPR --> Source
    ImageBuild --> ArtifactRegistry
    CT --> OIDC
    CICDServiceAccount --> VertexPipeline
    CICDServiceAccount --> ArtifactRegistry
    ModelRegistry --> PromoteModel
    PromoteModel --> AppValues
    AppValues --> Flux
    ArtifactRegistry --> CloudRun
    ArtifactRegistry --> APIOnGKE
    GCS --> ModelURI
    ModelURI --> CloudRun
    ModelURI --> APIOnGKE
    API --> CloudRun
    API --> APIOnGKE
    Prometheus --> MonitoringData
```

The diagram is intentionally split by ownership boundary. The app repository
builds and validates artifacts. GCP hosts the data, training and serving
platforms. The config repository declares runtime state for Kubernetes, and Flux
keeps the GKE lab aligned with that state. Model promotion is a reviewable PR
that changes the model URI and lineage fields instead of rebuilding the serving
image.

## Main Design Choices

Cloud Run is the permanent serving platform because it is stateless,
low-ops, scale-to-zero and enough for a portfolio API. GKE is still used in a
short lab because the role explicitly mentions Flux, Kubeflow/KubeRay and
Kubernetes. This is a cost-aware compromise: use Kubernetes where it teaches
the target concepts, not where it adds unnecessary operations.

BigQuery acts as the offline feature store and logging layer. Tables are
partitioned by timestamp and clustered by keys used in recommendation joins.
That supports cost control and lets us explain feature freshness, backfills,
model monitoring and user-level debugging.

The model keeps a popularity baseline and a simple ranker. The baseline is not
a toy; it is the production fallback and the minimum bar a new model must beat.

## Failure Modes To Discuss

- Bad model promotion: revert the config repo digest or switch traffic to the
  baseline variant.
- GCS model unavailable: API falls back to the embedded popularity catalog.
- BigQuery logging delayed: serving continues; logs are retried or buffered.
- Manual cluster drift: Flux reconciles the cluster back to Git.
- CI compromise: CI service account cannot read all runtime data because IAM is
  separated by purpose.
- Cost spike: budget alerts, GKE teardown, resource quotas and no GPU in the lab.



## Vertex AI / Kubeflow Continuous Training

The real-data training path is a Continuous Training loop. GitHub Actions
validates the Kubeflow Pipelines template on pull requests, then submits Vertex
AI `PipelineJob` runs from `main`, weekly schedule or manual dispatch. The
training run is parameterized with `data_snapshot_id`, `git_sha` and `run_id` so
model lineage is explainable.

The pipeline stages are:

1. Download and normalize MovieLens latest-small into VideoRank interaction
   events.
2. Register the snapshot as a Vertex AI managed Dataset.
3. Build user-level features, publish the BigQuery source table, and optionally
   create/update Vertex AI Feature Store online resources.
4. Train a CPU-only matrix factorization ranker with user and item embeddings.
5. Evaluate against popularity baseline with AUC, Brier, Recall@10 and NDCG@10.
6. Log parameters and metrics to Vertex AI Experiments.
7. Apply a quality gate, then upload the candidate to Vertex AI Model Registry.
8. Write final registration metadata linking Git, data, metrics and Vertex
   resources.

This keeps Kubernetes/Kubeflow semantics while avoiding self-hosting Kubeflow on
GKE for the interview lab. Vertex handles orchestration, metadata, artifact
storage, caching and retries; the project still owns data/model code and
promotion policy. CT registers a candidate model and metadata, but serving
promotion remains a separate review step. The `promote-model` workflow turns an
approved candidate into a config repo PR that pins `VIDEORANK_MODEL_URI` and the
related lineage fields.
