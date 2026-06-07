variable "project_id" {
  description = "GCP project id."
  type        = string
}

variable "region" {
  description = "Primary GCP region."
  type        = string
  default     = "europe-west1"
}

variable "bigquery_location" {
  description = "BigQuery dataset location."
  type        = string
  default     = "EU"
}

variable "billing_account_id" {
  description = "Billing account id for budget alerts. Leave empty to skip budget creation."
  type        = string
  default     = ""
}

variable "budget_amount_usd" {
  description = "Budget alert threshold in USD."
  type        = number
  default     = 75
}

variable "github_owner" {
  description = "GitHub user or organization that owns the app repository."
  type        = string
}

variable "app_repo_name" {
  description = "GitHub app repository name."
  type        = string
  default     = "videorank-mlops-app"
}

variable "config_repo_name" {
  description = "GitHub GitOps configuration repository name."
  type        = string
  default     = "videorank-mlops-config"
}

variable "initial_image" {
  description = "Initial Cloud Run image. CI replaces this with the app image."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "enable_gke_lab" {
  description = "Create the short-lived GKE Autopilot GitOps/KubeRay lab cluster."
  type        = bool
  default     = false
}
