# Interview Questions And Answers

This file is the script to rehearse before the interview. Keep answers concise:
start with the principle, then point to the concrete implementation in this
project.

## 1. Setup, GCP, GitHub And Direnv

Q: Why two repositories?

A: The app repo produces artifacts: source code, tests, Docker images and ML
artifacts. The config repo declares what runs in Kubernetes. That separation
gives cleaner permissions, explicit promotion, auditable rollbacks and a true
GitOps source of truth.

Q: Is two repos the only Flux best practice?

A: No. Flux documents several valid layouts: monorepo, repository per team,
repository per environment and repository per application. For this project,
two repos are the best production-style compromise because we want to separate
build from runtime promotion.

Q: Why isolate `CLOUDSDK_CONFIG` with direnv?

A: It prevents accidental use of my professional GCP account/project and makes
the local environment reproducible. The project-local `.gcloud` folder is an
operational guardrail.

Q: Why avoid service account JSON keys?

A: JSON keys are long-lived credentials. They are hard to rotate and easy to
leak. Workload Identity Federation uses GitHub OIDC to mint short-lived Google
credentials only for allowed repositories and branches.

Q: What is the difference between CI credentials and runtime credentials?

A: CI credentials build, push and deploy. Runtime credentials let the service
read model artifacts and write logs. They should be different service accounts
so a CI compromise does not automatically expose production data.

## 2. Terraform GCP Foundation

Q: Why Terraform rather than `gcloud` scripts?

A: Terraform gives a declarative, reviewable and reproducible infrastructure
state. `terraform plan` shows drift and proposed changes before applying.

Q: Why is Terraform in the app repo and not the Flux config repo?

A: Flux reconciles Kubernetes objects. Terraform manages cloud primitives like
BigQuery, buckets, IAM and Cloud Run. In a larger organization I might split
cloud infrastructure into a third infra repo, but I would not mix Terraform
state with a Kubernetes GitOps repo unless a platform explicitly supports it.

Q: How do you apply least privilege?

A: Separate service accounts: CI, Cloud Run runtime and training. Each receives
only the roles needed on the smallest practical resource scope.

Q: How do you correct Terraform drift?

A: Detect it with `terraform plan`, then change code and apply. I avoid fixing
drift through the console because that creates hidden state.

Q: If CI deploys the Cloud Run image, how do you avoid Terraform fighting CD?

A: Terraform owns the Cloud Run service shape: IAM, service account, limits,
environment and probes. The deployment pipeline owns image promotion, so the
Terraform resource ignores only the container image field. That keeps service
configuration reviewable without rolling a release back to an initial image.

Q: Why not one service account for everything?

A: It increases blast radius. If the API is compromised, it should not be able
to mutate CI, deploy Cloud Run or administer Artifact Registry.

## 3. Data And Feature Engineering

Q: Why BigQuery as an offline feature store?

A: It is scalable, SQL-native, integrates with GCP pipelines and is suitable
for batch features, logs, backfills and analytics. For a full feature platform,
I would add online features and stricter point-in-time correctness guarantees.

Q: Why partition by date?

A: Most ML/debug queries are time-bounded. Partitioning reduces scanned bytes,
helps TTL/lifecycle policies and makes backfills cheaper.

Q: Why cluster by `user_id` and `video_id`?

A: Recommendation workloads often filter or join on these keys. Clustering
improves locality and can reduce scan work inside partitions.

Q: How do you avoid data leakage?

A: Use temporal splits and compute features only from events that happened
before the prediction timestamp. In this code, online aggregation emits the
feature vector before updating stats with the current event.

Q: Beam/Dataflow vs Airflow/Kestra?

A: Beam defines the data transformation; Dataflow executes it at scale. Airflow
or Kestra orchestrate tasks and dependencies. They can trigger Dataflow but are
not the distributed transform engine themselves.

Q: How do you optimize BigQuery cost?

A: Partitioning, clustering, selected columns, `maximum_bytes_billed`, dry runs,
materialized/pre-aggregated tables, and avoiding the false assumption that
`LIMIT` reduces scanned bytes.

## 4. Training And Evaluation

Q: Why keep a popularity baseline?

A: It gives a minimum quality bar, a sanity check and a safe production fallback.
If a complex model cannot beat it, complexity is not justified.

Q: Why `Recall@K`?

A: It measures whether relevant videos appear in the top K recommendations,
which matches the user experience better than global accuracy.

Q: Why `NDCG@K`?

A: It rewards putting relevant items higher in the ranking. For recommendations,
order is part of the product.

Q: Why not only accuracy?

A: Recommendation labels are often sparse and imbalanced. Accuracy can look high
while the ranking is useless.

Q: How do you version a model?

A: Track code SHA, data snapshot/time window, feature version, model artifact,
metrics and model card. This lets us reproduce and explain any deployed model.

Q: When do you promote a model?

A: After passing offline metrics against baseline, serving constraints
latency/size, tests, and then an online validation step such as canary or A/B.

## 5. Kubeflow / Vertex AI Pipelines

Q: What does Kubeflow Pipelines solve?

A: It makes ML workflows reproducible and observable through components,
artifacts, metadata, caching and retries.

Q: KFP vs Airflow/Dataflow?

A: KFP is ML lifecycle-oriented. Airflow is general orchestration. Dataflow is a
data processing engine. They can work together, but they solve different layers.

Q: Why containerize components?

A: It isolates dependencies, makes tasks portable between Vertex and Kubernetes,
and reduces "works on my machine" failures.

Q: How do caching and retries help?

A: Caching avoids recomputing deterministic steps. Retries handle transient
cloud failures. Both improve productivity and time-to-market.

Q: Vertex AI Pipelines vs self-hosted Kubeflow?

A: Vertex reduces cluster operations and is faster to operate on GCP. Self-hosted
Kubeflow gives more control but requires owning the platform.


Q: What is the concrete Vertex AI/Kubeflow pipeline now?

A: A Kubeflow Pipelines v2 DAG compiled to YAML and submitted to Vertex AI
Pipelines. It prepares MovieLens latest-small, catalogs the snapshot in Vertex
AI Datasets, publishes user features for Vertex AI Feature Store, trains a
matrix factorization ranker, logs metrics to Experiments, applies a quality
gate, uploads the candidate to Model Registry and writes registration metadata.

Q: Why use Vertex AI Pipelines instead of self-hosting Kubeflow?

A: The role needs Kubeflow concepts, but self-hosting Kubeflow would consume
time and GKE budget. Vertex runs KFP pipelines as a managed service, so we can
focus on ML workflow, artifacts, metadata, IAM and promotion decisions.

Q: What does Vertex AI Dataset add over a GCS file?

A: GCS stores bytes; Vertex Dataset is a managed ML metadata resource. It makes
the training snapshot discoverable in Vertex, links it to lineage, and gives ML
teams a common control-plane object to discuss data used by training.

Q: What does Vertex AI Feature Store add over BigQuery?

A: BigQuery is the offline/source table. Vertex AI Feature Store manages feature
views over that source and can serve features online. In this lab we always
publish the BigQuery feature source and make online Feature Store resources
opt-in because they can create persistent cost.

Q: Why use Vertex AI Experiments?

A: Experiments answer run-comparison questions: which Git SHA, data snapshot,
hyperparameters and metrics produced this result. That is different from Model
Registry, which manages model candidates and versions.

Q: Why use Vertex AI Model Registry if Cloud Run serves the API?

A: Model Registry is the model lifecycle record: artifact URI, container URI,
metadata and candidate state. It does not force Vertex Endpoint serving. The
team can still serve via Cloud Run while using Registry for governance.

Q: Why MovieLens for a Dailymotion-like use case?

A: It is a real public user-item interaction dataset with timestamps and item
metadata. Movies are not short-form videos, but the recommendation structure is
the same: users interact with catalog items and we rank candidates.

Q: Why not keep only synthetic data?

A: Synthetic data is useful for deterministic tests and demos, but a real
dataset exposes real sparsity, popularity bias, cold-start cases and temporal
split issues. That makes interview discussion more credible.

Q: Why matrix factorization?

A: It is a standard recommender baseline that learns user and item embeddings.
It is explainable, CPU-friendly, cheap to train and directly tied to ranking,
unlike a generic classifier that ignores collaborative signal.

Q: Why compare to popularity baseline?

A: Popularity is the fallback and a strong simple baseline. A learned ranker
should justify its operational complexity by beating or at least matching that
baseline on ranking metrics before online tests.

Q: Why self-contained KFP components?

A: Vertex executes each component in its own container. Self-contained
components make the compiled YAML runnable without assuming the local repo is
mounted. In production, I would move repeated logic into a versioned training
container or package.

Q: How do you handle KFP artifacts correctly on Vertex?

A: Treat artifact paths as artifact directories. For example, the prepare step
writes `events.jsonl` under the `Dataset` artifact path, and downstream steps
read that file from their materialized input artifact directory. This avoids
confusing artifact URI/path with a raw file path.

Q: Why a dedicated training service account?

A: Vertex pipeline jobs need access to pipeline artifacts and data, not Cloud
Run deployment rights. A `videorank-training` service account limits blast
radius and makes audit logs clearer.

Q: What is `pipeline_root`?

A: It is the GCS location where Vertex stores pipeline artifacts and metadata
payloads. Here it uses the lifecycle-managed artifacts bucket to control cost.

Q: What does the quality gate protect?

A: It blocks registration metadata if offline metrics fail minimum NDCG or lift
thresholds. In production, that gate would also include freshness, bias/safety,
latency and model-size constraints.

Q: What is Continuous Training?

A: Continuous Training is the automated retraining and validation loop for ML
models. It can be triggered by code changes, data changes, a schedule or manual
operation. It produces a model candidate with metrics and lineage; it does not
blindly replace production.

Q: How do you deploy the Vertex AI pipeline from Git?

A: The app repo has a `continuous-training` GitHub Actions workflow. On pull
requests it validates code and compiles the KFP template. On `main`, weekly
schedule or manual dispatch it authenticates with GitHub OIDC through Workload
Identity Federation, uses the CI service account to call Vertex AI, and submits
a `PipelineJob` that runs as the dedicated training service account. No JSON key
is stored.

Q: Why is Flux not deploying this Vertex AI pipeline?

A: Flux reconciles Kubernetes objects. Vertex AI Pipelines is a managed GCP
resource, so in this project CI submits it through the Vertex SDK. If we wanted
full GitOps for GCP resources, we could add Config Connector or a dedicated
platform controller, but that is extra scope for this interview lab.

Q: What permissions are needed for Git-to-Vertex deployment?

A: The GitHub OIDC identity impersonates the CI service account. That CI account
needs `roles/aiplatform.user` to submit pipeline jobs and `iam.serviceAccounts.actAs`
on the training service account. The training account needs only data/artifact
permissions required by the pipeline.

Q: Why pass `data_snapshot_id`, `git_sha` and `run_id` into the pipeline?

A: They make lineage explicit. `data_snapshot_id` says which training data was
used and prevents unsafe cache reuse when data changes; `git_sha` links the run
to code; `run_id` links it to the CI/CT execution.

Q: Why does CT register a candidate instead of deploying the model immediately?

A: Offline validation is necessary but not sufficient. A production promotion
should still have review, serving constraints, canary or A/B controls and a
rollback path. CT creates an auditable candidate; CD handles promotion.

Q: How do you promote a validated model in this project?

A: I run the `promote-model` GitHub Actions workflow with the Vertex/GCS model
artifact URI, model version, Vertex Model Registry resource and lineage fields.
The workflow opens a PR in the config repo that pins `VIDEORANK_MODEL_URI` and
metadata. Merge promotes; revert rolls back.

Q: Why promote by model URI instead of rebuilding the image?

A: The serving code and the model artifact have different lifecycles. Rebuilding
the image for every model couples app release to model release. Pinning an
immutable `gs://` model artifact lets us promote or rollback a model without a
new container build.

Q: How does the API load the promoted model?

A: Runtime config sets `VIDEORANK_MODEL_URI`. If it points to `gs://`, the API
downloads `model.json` to `/tmp/videorank/model-cache` on startup using the
runtime service account. If loading fails, the API falls back to the embedded
baseline catalog rather than taking serving down.

Q: Which Vertex resources are created by default in the CT?

A: Vertex Dataset, Vertex Experiments and Vertex Model Registry are enabled by
default. The pipeline also publishes a BigQuery feature source table. Online
Feature Store resources are off by default and require
`enable_vertex_feature_store=true` because they can create persistent cost.

Q: How do Vertex labels help operations?

A: Labels make runs searchable and auditable by app, environment, trigger, Git
SHA and GitHub run id. They also help cost attribution and incident debugging.

## 6. Serving Cloud Run

Q: Why Cloud Run for permanent serving?

A: It is stateless, simple, scales to zero, supports containers, and is cheap
for low/variable traffic.

Q: Why not GKE for everything?

A: GKE is valuable for GitOps/KubeRay practice, but using it for this small API
would add operational cost without product value.

Q: Why not Vertex Endpoint?

A: Vertex Endpoint is strong for managed model serving. Here the API includes
business logic, fallback, A/B assignment and feedback logging, so Cloud Run
gives more control.

Q: How do you manage cold starts?

A: Small image, lazy/fast model loading, appropriate concurrency, and min
instances only if the SLO requires paying for them.

Q: Why write local fallback logs under `/tmp` on Cloud Run?

A: Cloud Run containers should not rely on writing inside the application
directory, especially when running as non-root. `/tmp` is the writable ephemeral
filesystem for short-lived buffers; durable prediction logs go to BigQuery.

Q: Which metrics matter?

A: Latency p95, error rate, throughput, fallback rate, model version, score
distribution, CTR/watch feedback and feature/model freshness.

Q: Why expose `/health` as well as `/healthz`?

A: Kubernetes commonly uses `/healthz`, and the chart uses it for liveness.
Cloud Run documents some URL paths ending in `z` as reserved on public URLs, so
the public `run.app` endpoint uses `/health` while `/readyz` reports model
readiness.

## 7. GitOps Flux

Q: What exactly does Flux reconcile?

A: Flux controllers reconcile sources like Git/OCI/Helm into Kubernetes
resources. The desired state lives in Git; the controllers converge the cluster
to that state continuously.

Q: GitOps vs CI running `kubectl apply`?

A: CI push-based deployment applies once and then exits. GitOps is pull-based:
an agent inside the cluster continuously reconciles and corrects drift.

Q: What is `GitRepository`?

A: A Flux source object that tells source-controller where to fetch Git content.

Q: What is `Kustomization`?

A: A Flux object that applies a path from a source, with prune, waits, health
checks and dependency ordering.

Q: What is `HelmRelease`?

A: A Flux object managed by helm-controller that installs or upgrades a Helm
chart according to declared values.

Q: Why `dependsOn`, `healthChecks` and `prune`?

A: `dependsOn` controls ordering, `healthChecks` validates rollout health, and
`prune` deletes resources that were removed from Git.

Q: How does Flux handle manual drift?

A: If someone changes the cluster manually, Flux reconciles it back to Git on
the next sync. The durable fix must be committed to Git.

Q: How do you rollback?

A: Revert the config repo commit that changed the image digest or manifest.
Flux applies the previous desired state.


Q: Why use Kustomize base + overlays in the config repo?

A: The base keeps the reusable Kubernetes contract, while overlays isolate
environment-specific choices such as namespace, labels, annotations, generated
values and patches. It avoids copying manifests across environments and makes
GitOps reviews smaller.

Q: Why use `patches:` instead of older patch fields?

A: `patches:` is the current unified Kustomize field. It supports strategic
merge and JSON6902-style targeting, so the overlay can express environment
differences without replacing the base manifest.

Q: Why keep the `configMapGenerator` hash?

A: The hash changes when the values file changes, making configuration updates
visible as a new object name. Disabling it hides config changes behind a stable
name and can make rollout behavior harder to reason about.

Q: Why add a Kustomize `nameReference` for `HelmRelease.valuesFrom`?

A: `HelmRelease` is a Flux CRD, so Kustomize does not automatically know that
`spec.valuesFrom[].name` points to a `ConfigMap`. The custom transformer tells
Kustomize to rewrite that field to the generated hashed name.

Q: Why no `namePrefix` for the dev API release?

A: The environment is already isolated by the `videorank-dev` namespace and
Flux health checks use a stable `HelmRelease` name. Prefixes are useful when
multiple variants share a namespace, but here they add little value and more
operational churn.

## 8. Promotion App Repo To Config Repo

Q: Why promote by pull request?

A: It gives review, auditability, environment ownership and separation between
building an artifact and deciding to run it.

Q: Digest vs tag?

A: A digest is immutable and identifies exact image content. Tags can be moved.

Q: How do you trace code in production?

A: Running image digest maps to app Git SHA, CI run, model version, metrics and
promotion PR.

Q: How do you rollback without rebuild?

A: Revert the config repo digest to the previous image. No new artifact is
needed.

Q: How would you handle cross-repo credentials?

A: The secret belongs in the app repo Actions secrets, because that workflow
opens the promotion PR into the config repo. For the lab, a fine-grained PAT
limited to `videorank-mlops-config` with contents and pull-request write is
acceptable. In production, I prefer a GitHub App or bot identity with scoped,
short-lived installation tokens.

Q: Why not use the default `GITHUB_TOKEN`?

A: The default token is scoped to the repository running the workflow. It is not
the right identity for mutating a separate config repo unless repository access
is deliberately granted through another mechanism.

## 9. Secrets And Security

Q: Where do the different secret classes live?

A: CI/CD secrets live in GitHub Actions secrets; GCP CI identity uses Workload
Identity Federation instead of JSON keys; Kubernetes secrets are SOPS-encrypted
in the config repo; runtime app secrets should come from Secret Manager or a
Kubernetes secret integration. Local operator files such as `.gcloud/`,
`terraform.tfvars` and state are ignored by Git.

Q: Why is Kubernetes Secret base64 not enough?

A: Base64 is encoding, not encryption. A base64 Secret committed to Git is still
effectively plaintext.

Q: SOPS + KMS/Age vs Sealed Secrets?

A: SOPS encrypts files before Git. KMS adds IAM and audit; Age is simple for a
lab. Sealed Secrets depends on a cluster-side controller and private key.

Q: How does Flux decrypt?

A: kustomize-controller is configured with decryption and applies decrypted
objects inside the cluster while Git remains encrypted.

Q: How do you make Flux multi-tenant?

A: Namespaces, RBAC, `serviceAccountName` on Flux Kustomizations/HelmReleases,
and restricting cross-namespace references.

Q: What if a secret leaks?

A: Rotate/revoke it, invalidate affected credentials, audit access, remove it
from Git history if required and document the incident.

## 10. KubeRay

Q: RayCluster vs RayJob vs RayService?

A: RayCluster is the cluster resource, RayJob runs a finite job, RayService
serves Ray Serve apps with high availability and upgrade support.

Q: Why RayJob here?

A: The lab needs a short distributed compute job. RayJob is cheaper and easier
to tear down than a long-running service.

Q: How does autoscaling work?

A: Worker groups define min/max replicas, and Ray/KubeRay autoscaling changes
workers based on workload demand while Kubernetes schedules pods.

Q: How would you use GPUs?

A: Request GPU resources, use node selectors/tolerations or dedicated pools,
set quotas, monitor cost and avoid scheduling GPU workloads accidentally.

Q: How do you monitor Ray?

A: Ray logs, dashboard, Kubernetes CR status and Prometheus metrics.

## 11. Monitoring, Drift And Runbook

Q: Infra vs app vs model monitoring?

A: Infra tracks CPU/memory/pods. App tracks latency/errors/throughput. Model
monitoring tracks quality, drift, fallback and feedback metrics.

Q: Data drift vs concept drift?

A: Data drift means input distribution changed. Concept drift means the
relationship between inputs and target changed.

Q: Why avoid high-cardinality Prometheus labels?

A: Prometheus creates a time series for each label combination. Labels like
`user_id` can explode memory and cost.

Q: What SLOs fit this service?

A: p95 latency, availability, error rate, freshness of model/features and
fallback rate.

Q: How debug a CTR/watch-time drop?

A: Check rollout digest, model version, error logs, drift, A/B assignment,
feature freshness, offline/online metric mismatch and data quality.

## 12. Jx3

Q: What is Jx3?

A: Jenkins X 3 is a Kubernetes-native CI/CD platform using GitOps concepts,
Tekton pipelines and boot/operator workflows.

Q: Difference with Flux?

A: Flux focuses on GitOps CD reconciliation. Jx3 covers more of the CI/CD
platform around pipelines and promotion.

Q: Why not implement Jx3 in this two-day project?

A: Because Flux, KubeRay and GCP give the highest interview value quickly. I can
explain Jx3 tradeoffs without overloading the implementation.
