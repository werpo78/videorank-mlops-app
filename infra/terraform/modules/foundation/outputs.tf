output "artifact_registry_repository" {
  value = "${google_artifact_registry_repository.docker.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "cloud_run_service_uri" {
  value = google_cloud_run_v2_service.api.uri
}

output "ci_service_account_email" {
  value = google_service_account.ci.email
}

output "runtime_service_account_email" {
  value = google_service_account.cloud_run.email
}

output "training_service_account_email" {
  value = google_service_account.training.email
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "artifacts_bucket" {
  value = google_storage_bucket.artifacts.name
}

