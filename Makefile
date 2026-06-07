.PHONY: test generate train demo-api docker-build

test:
	PYTHONPATH=src python -m unittest discover -s tests

generate:
	PYTHONPATH=src python -m videorank.data.generate --output data/events.jsonl --users 200 --videos 80 --events 5000

train: generate
	PYTHONPATH=src python -m videorank.model.train --events data/events.jsonl --output-dir artifacts/model

demo-api: train
	PYTHONPATH=src VIDEORANK_MODEL_PATH=artifacts/model/model.json python -m videorank.api.app

docker-build:
	docker build -t videorank-api:local .

