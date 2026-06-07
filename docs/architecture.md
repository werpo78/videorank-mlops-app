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

## 1. System Boundaries

```mermaid
flowchart TB
    subgraph App["videorank-mlops-app"]
        Code["Python code<br/>FastAPI, training, KFP"]
        CI["GitHub Actions<br/>CI, image build, CT submit"]
        TF["Terraform<br/>GCP foundation"]
    end

    subgraph GCP["GCP project"]
        AR["Artifact Registry<br/>container images"]
        Vertex["Vertex AI<br/>Pipelines, Datasets, Experiments, Model Registry"]
        Storage["GCS + BigQuery<br/>artifacts, features, logs"]
        Run["Cloud Run<br/>permanent API"]
    end

    subgraph Config["videorank-mlops-config"]
        Desired["Kubernetes desired state<br/>HelmRelease, values, Flux CRDs"]
        PromoPR["Promotion PRs<br/>image digest or model URI"]
    end

    subgraph GKE["Ephemeral GKE lab"]
        Flux["Flux controllers"]
        ApiPod["VideoRank API on Kubernetes"]
        Ray["KubeRay RayJob"]
    end

    Code -->|"1. PR tested by CI"| CI
    CI -->|"2. push image by SHA + sortable tag"| AR
    CI -->|"3. submit managed CT run"| Vertex
    TF -->|"4a. create registry"| AR
    TF -->|"4b. create storage and datasets"| Storage
    TF -->|"4c. create Cloud Run service"| Run
    Vertex -->|"5. write model artifacts + metrics"| Storage
    CI -->|"6. open runtime promotion PR"| PromoPR
    PromoPR -->|"7. merge updates desired state"| Desired
    Desired -->|"8. Flux pulls from Git"| Flux
    Flux -->|"9. applies HelmRelease/jobs"| ApiPod
    Flux -->|"10. applies RayJob"| Ray
    AR -->|"image digest"| Run
    AR -->|"image digest"| ApiPod
    Storage -->|"model URI + logs"| Run
    Storage -->|"model URI + logs"| ApiPod
```

Read it left to right by responsibility: the app repo produces artifacts, GCP
stores and runs managed services, the config repo declares Kubernetes runtime
state, and Flux applies that state inside the GKE lab.

## 2. Flux Bootstrap

```mermaid
sequenceDiagram
    autonumber
    participant Operator as Operator
    participant GKE as GKE cluster
    participant CLI as flux CLI
    participant GitHub as GitHub config repo
    participant Flux as Flux controllers

    Operator->>GKE: Select cluster context with gcloud
    Operator->>CLI: Run flux check --pre
    CLI-->>Operator: Confirm cluster prerequisites
    Operator->>CLI: Run flux bootstrap github
    CLI->>GitHub: Commit gotk components under clusters/dev
    CLI->>GKE: Install Flux controllers
    CLI->>GitHub: Create read-write deploy key
    Flux->>GitHub: Pull clusters/dev desired state
    Flux->>GKE: Reconcile namespaces, apps, controllers, jobs
```

Bootstrap is idempotent. `--components-extra` installs image automation
controllers, and `--read-write-key=true` is required because the image automation
lab pushes a staging branch back to Git.

## 3. Flux Reconciliation Loop

```mermaid
flowchart TD
    A["1. GitRepository<br/>source-controller fetches config repo"] --> B["2. Artifact stored<br/>source revision is recorded"]
    B --> C["3. Kustomization<br/>kustomize-controller builds target path"]
    C --> D["4. Apply manifests<br/>prune removed resources"]
    D --> E["5. Health checks<br/>wait for HelmRelease or CR status"]
    E --> F{"6. Live state matches Git?"}
    F -->|"yes: wait interval or webhook"| A
    F -->|"no: reconcile drift"| C
```

This is the core GitOps answer: Git is the desired state, Kubernetes is the live
state, and Flux repeatedly converges live state back to Git.

## 4. HelmRelease Mechanism

```mermaid
flowchart TD
    A["1. apps/videorank-api/overlays/dev/values.yaml<br/>environment values"] --> B["2. configMapGenerator<br/>creates hashed values ConfigMap"]
    B --> C["3. kustomizeconfig.yaml<br/>rewrites HelmRelease valuesFrom name"]
    C --> D["4. HelmRelease<br/>chart path + generated values ConfigMap"]
    D --> E["5. helm-controller<br/>renders chart and applies release"]
    E --> F["6. Kubernetes resources<br/>Deployment, Service, ServiceAccount"]
    E --> G["7. remediation policy<br/>retry install, rollback failed upgrade"]
```

The values `ConfigMap` keeps its hash. That makes values changes visible as new
desired state while the custom Kustomize name reference keeps
`HelmRelease.spec.valuesFrom[].name` correct.

## 5. Application Image Promotion

```mermaid
sequenceDiagram
    autonumber
    participant CI as app repo CI
    participant Registry as Artifact Registry
    participant Config as config repo PR
    participant Human as Reviewer
    participant Flux as Flux
    participant Cluster as GKE lab

    CI->>Registry: Build and push image with full Git SHA tag
    CI->>Registry: Also push sortable tag main-run-shortsha
    CI->>Registry: Resolve immutable image digest
    CI->>Config: Open PR updating repository, tag and digest
    Human->>Config: Review and merge PR
    Flux->>Config: Pull new config repo revision
    Flux->>Cluster: Upgrade HelmRelease using image digest
```

The key interview phrase: tags help selection and traceability; the digest is
the immutable deployment identity.

## 6. Flux Image Automation Lab

```mermaid
sequenceDiagram
    autonumber
    participant CI as app CI
    participant Registry as Artifact Registry
    participant Repo as ImageRepository
    participant Policy as ImagePolicy
    participant Auto as ImageUpdateAutomation
    participant Branch as flux/image-updates/dev
    participant Main as config repo main

    CI->>Registry: Push main-run-shortsha tag
    Repo->>Registry: Scan tags with provider=gcp
    Repo-->>Policy: Expose scanned tag metadata
    Policy->>Policy: Filter main-* tags and choose highest run number
    Policy-->>Auto: Latest image name, tag and digest
    Auto->>Branch: Commit values.yaml marker updates
    Branch->>Main: Human opens and merges PR
    Main-->>Auto: Next reconcile sees no pending change
```

This is intentionally not direct-to-main automation. Flux prepares an update
branch, but promotion remains a reviewed Git change.

## 7. Continuous Training And Model Promotion

```mermaid
sequenceDiagram
    autonumber
    participant Git as app repo
    participant Vertex as Vertex AI Pipelines
    participant Data as BigQuery and GCS
    participant Registry as Vertex Model Registry
    participant Human as ML/platform reviewer
    participant Promote as promote-model workflow
    participant Config as config repo PR
    participant API as Cloud Run or GKE API

    Git->>Vertex: Submit KFP v2 PipelineJob
    Vertex->>Data: Read dataset and write pipeline artifacts
    Vertex->>Vertex: Train and evaluate candidate model
    Vertex->>Registry: Register candidate with metrics and lineage
    Human->>Registry: Review quality gate and metadata
    Human->>Promote: Provide model URI, version and lineage
    Promote->>Config: Open PR updating VIDEORANK_MODEL_URI fields
    Config->>API: Merge changes runtime model config
    API->>Data: Load promoted gs:// model artifact at startup
```

Continuous Training creates a candidate. Promotion is a separate decision with
review, lineage and rollback. The serving image does not need to be rebuilt for
every model candidate.

## 8. Rollback

```mermaid
sequenceDiagram
    autonumber
    participant OnCall as Operator
    participant Config as config repo
    participant Flux as Flux
    participant Runtime as Cloud Run or GKE API
    participant Obs as Metrics and logs

    OnCall->>Obs: Detect bad image or model rollout
    OnCall->>Config: Revert the promotion commit
    Flux->>Config: Pull reverted desired state
    Flux->>Runtime: Restore previous digest or model URI
    OnCall->>Obs: Verify /readyz, errors, fallback rate and business metrics
```

Rollback does not require rebuilding. Git history records both the bad
promotion and the rollback decision.

## Main Design Choices

Cloud Run is the permanent serving platform because it is stateless, low-ops,
scale-to-zero and enough for a portfolio API. GKE is still used in a short lab
because the role explicitly mentions Flux, Kubeflow/KubeRay and Kubernetes.
This is a cost-aware compromise: use Kubernetes where it teaches the target
concepts, not where it adds unnecessary operations.

BigQuery acts as the offline feature store and logging layer. Tables are
partitioned by timestamp and clustered by keys used in recommendation joins.
That supports cost control and lets us explain feature freshness, backfills,
model monitoring and user-level debugging.

The model keeps a popularity baseline. The baseline is not a toy; it is the
production fallback and the minimum bar a new model must beat.

## Failure Modes To Discuss

- Bad model promotion: revert the config repo model promotion PR.
- Bad image promotion: revert the config repo digest promotion PR.
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
