#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID, e.g. videorank-mlops-dev-123}"
: "${BILLING_ACCOUNT_ID:?Set BILLING_ACCOUNT_ID from gcloud billing accounts list}"
: "${REGION:=europe-west1}"

gcloud projects create "${PROJECT_ID}" --name="VideoRank MLOps"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"
gcloud config set project "${PROJECT_ID}"
gcloud config set run/region "${REGION}"

gcloud services enable \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com \
  container.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  serviceusage.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  dataflow.googleapis.com

echo "GCP project ${PROJECT_ID} is ready. Continue with Terraform in infra/terraform/environments/dev."
