#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=europe-west1}"
: "${CLUSTER_NAME:=videorank-gitops-dev}"

gcloud container clusters delete "${CLUSTER_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --quiet
