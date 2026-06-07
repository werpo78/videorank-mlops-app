#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=europe-west1}"
: "${CLUSTER_NAME:=videorank-gitops-dev}"
: "${GITHUB_OWNER:?Set GITHUB_OWNER}"
: "${CONFIG_REPO:=videorank-mlops-config}"

gcloud container clusters get-credentials "${CLUSTER_NAME}" --region "${REGION}" --project "${PROJECT_ID}"
flux check --pre
flux bootstrap github \
  --owner="${GITHUB_OWNER}" \
  --repository="${CONFIG_REPO}" \
  --branch=main \
  --path=clusters/dev \
  --personal \
  --private=true

flux get all -A
