#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-src}"
python -m videorank.data.generate --output data/events.jsonl --users 200 --videos 80 --events 5000
python -m videorank.model.train --events data/events.jsonl --output-dir artifacts/model
VIDEORANK_MODEL_PATH=artifacts/model/model.json python -m videorank.api.app

