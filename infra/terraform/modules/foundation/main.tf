locals {
  labels = {
    app         = "videorank"
    environment = "dev"
    owner       = "mlops-interview"
  }
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "services" {
  for_each = var.enabled_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-videorank-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = local.labels

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_bigquery_dataset" "videorank" {
  dataset_id                 = "videorank"
  location                   = var.bigquery_location
  delete_contents_on_destroy = true
  labels                     = local.labels

  depends_on = [google_project_service.services]
}

resource "google_bigquery_table" "events_raw" {
  dataset_id          = google_bigquery_dataset.videorank.dataset_id
  table_id            = "events_raw"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["user_id", "video_id"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED" },
    { name = "user_id", type = "STRING", mode = "REQUIRED" },
    { name = "video_id", type = "STRING", mode = "REQUIRED" },
    { name = "category", type = "STRING", mode = "REQUIRED" },
    { name = "country", type = "STRING", mode = "NULLABLE" },
    { name = "device", type = "STRING", mode = "NULLABLE" },
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "impression", type = "INTEGER", mode = "REQUIRED" },
    { name = "clicked", type = "INTEGER", mode = "REQUIRED" },
    { name = "watch_time_s", type = "INTEGER", mode = "REQUIRED" },
    { name = "completed", type = "INTEGER", mode = "REQUIRED" },
    { name = "label", type = "INTEGER", mode = "REQUIRED" }
  ])
}

resource "google_bigquery_table" "prediction_logs" {
  dataset_id          = google_bigquery_dataset.videorank.dataset_id
  table_id            = "prediction_logs"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["variant", "model_version"]

  schema = jsonencode([
    { name = "request_id", type = "STRING", mode = "REQUIRED" },
    { name = "user_id", type = "STRING", mode = "REQUIRED" },
    { name = "variant", type = "STRING", mode = "REQUIRED" },
    { name = "model_version", type = "STRING", mode = "REQUIRED" },
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "recommendations", type = "JSON", mode = "NULLABLE" }
  ])
}

resource "google_bigquery_table" "model_metrics" {
  dataset_id          = google_bigquery_dataset.videorank.dataset_id
  table_id            = "model_metrics"
  deletion_protection = false

  schema = jsonencode([
    { name = "model_version", type = "STRING", mode = "REQUIRED" },
    { name = "metric_name", type = "STRING", mode = "REQUIRED" },
    { name = "metric_value", type = "FLOAT", mode = "REQUIRED" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "videorank"
  description   = "VideoRank immutable Docker images"
  format        = "DOCKER"
  labels        = local.labels

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "delete-untagged-after-14-days"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "1209600s"
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_service_account" "ci" {
  account_id   = "videorank-ci"
  display_name = "VideoRank CI"
}

resource "google_service_account" "cloud_run" {
  account_id   = "videorank-run"
  display_name = "VideoRank Cloud Run runtime"
}

resource "google_service_account" "training" {
  account_id   = "videorank-training"
  display_name = "VideoRank training pipeline"
}

resource "google_artifact_registry_repository_iam_member" "ci_artifact_writer" {
  location   = google_artifact_registry_repository.docker.location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_cloud_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_service_account_iam_member" "ci_can_deploy_as_runtime" {
  service_account_id = google_service_account.cloud_run.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "runtime_bigquery_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_storage_bucket_iam_member" "runtime_artifact_reader" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_storage_bucket_iam_member" "training_artifact_admin" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.training.email}"
}

resource "google_project_iam_member" "training_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.training.email}"
}

resource "google_project_iam_member" "training_bigquery_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.training.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "OIDC federation for GitHub Actions without JSON keys."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.aud"              = "assertion.aud"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  attribute_condition = "assertion.repository_owner == '${var.github_owner}' && assertion.repository == '${var.github_owner}/${var.app_repo_name}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_can_impersonate_ci" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_owner}/${var.app_repo_name}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "videorank-api"
  location = var.region
  labels   = local.labels

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.initial_image

      ports {
        container_port = 8080
      }

      env {
        name  = "VIDEORANK_ENV"
        value = "dev"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      env {
        name  = "VIDEORANK_BQ_DATASET"
        value = google_bigquery_dataset.videorank.dataset_id
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
      }
    }
  }

  depends_on = [google_project_service.services]

  lifecycle {
    ignore_changes = [
      client,
      client_version,
      scaling,
      template[0].containers[0].image,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.allow_unauthenticated_cloud_run ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_container_cluster" "gitops_lab" {
  count = var.enable_gke_lab ? 1 : 0

  name                = "videorank-gitops-dev"
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false
  resource_labels     = local.labels

  depends_on = [google_project_service.services]
}

resource "google_billing_budget" "project_budget" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "VideoRank MLOps dev budget"

  budget_filter {
    projects = ["projects/${data.google_project.current.number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency_code
      units         = tostring(var.budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }
}
