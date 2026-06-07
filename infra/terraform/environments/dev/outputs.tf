output "artifact_registry_repository" {
  value = module.foundation.artifact_registry_repository
}

output "cloud_run_service_uri" {
  value = module.foundation.cloud_run_service_uri
}

output "ci_service_account_email" {
  value = module.foundation.ci_service_account_email
}

output "workload_identity_provider" {
  value = module.foundation.workload_identity_provider
}

