variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "bigquery_location" {
  type    = string
  default = "EU"
}

variable "billing_account_id" {
  type    = string
  default = ""
}

variable "budget_amount_usd" {
  type    = number
  default = 75
}

variable "budget_currency_code" {
  type    = string
  default = "EUR"
}

variable "github_owner" {
  type = string
}

variable "app_repo_name" {
  type = string
}

variable "config_repo_name" {
  type = string
}

variable "initial_image" {
  type = string
}

variable "enable_gke_lab" {
  type    = bool
  default = false
}

variable "allow_unauthenticated_cloud_run" {
  type    = bool
  default = true
}

variable "enabled_apis" {
  type = set(string)
  default = [
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "dataflow.googleapis.com",
  ]
}
