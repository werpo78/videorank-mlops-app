#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${DATASET:=videorank}"
: "${TABLE:=events_raw}"
: "${EVENTS_PATH:=data/events.jsonl}"

bq load \
  --project_id="${PROJECT_ID}" \
  --source_format=NEWLINE_DELIMITED_JSON \
  "${DATASET}.${TABLE}" \
  "${EVENTS_PATH}"

