module "foundation" {
  source = "../../modules/foundation"

  project_id         = var.project_id
  region             = var.region
  bigquery_location  = var.bigquery_location
  billing_account_id = var.billing_account_id
  budget_amount_usd  = var.budget_amount_usd
  github_owner       = var.github_owner
  app_repo_name      = var.app_repo_name
  config_repo_name   = var.config_repo_name
  initial_image      = var.initial_image
  enable_gke_lab     = var.enable_gke_lab
}
